# api/pix_manual/pix_manual.py — configuração, payload BR Code e pedidos PIX manual
from __future__ import annotations

# ── cliente ───────────────────────────────────────────

from global_utils import agora_utc

TIPOS_CHAVE = ("cpf", "cnpj", "email", "telefone", "aleatoria")

_TABELA_OK: bool | None = None


def _tem_tabela(cur) -> bool:
    global _TABELA_OK
    if _TABELA_OK is True:
        return True
    cur.execute("SELECT to_regclass(%s)", ("tbl_integracao_pix_manual",))
    row = cur.fetchone()
    ok = bool(row and row[0])
    if ok:
        _TABELA_OK = True
    return ok


def carregar_config_pix_manual(cur, id_tenant: int) -> dict:
    if not _tem_tabela(cur):
        return {"ativo": False, "configurado": False}
    cur.execute(
        """
        SELECT ativo, tipo_chave, chave_pix, nome_beneficiario, cidade_beneficiario, atualizado_em
        FROM tbl_integracao_pix_manual WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "ativo": False,
            "configurado": False,
            "tipo_chave": "aleatoria",
            "chave_pix": "",
            "nome_beneficiario": "",
            "cidade_beneficiario": "",
        }
    return {
        "ativo": bool(row[0]),
        "configurado": bool((row[2] or "").strip()),
        "tipo_chave": row[1] or "aleatoria",
        "chave_pix": row[2] or "",
        "nome_beneficiario": row[3] or "",
        "cidade_beneficiario": row[4] or "",
        "atualizado_em": row[5].isoformat() if row[5] else None,
    }


def pix_manual_ativo(cur, id_tenant: int) -> bool:
    cfg = carregar_config_pix_manual(cur, id_tenant)
    return bool(cfg.get("ativo") and cfg.get("configurado"))


def salvar_config_pix_manual(
    cur,
    id_tenant: int,
    *,
    ativo: bool,
    tipo_chave: str,
    chave_pix: str,
    nome_beneficiario: str,
    cidade_beneficiario: str,
) -> None:
    if not _tem_tabela(cur):
        raise ValueError("Execute a migração SQL 064_pix_manual.sql.")
    tipo = (tipo_chave or "aleatoria").strip().lower()
    if tipo not in TIPOS_CHAVE:
        raise ValueError("Tipo de chave PIX inválido.")
    chave = (chave_pix or "").strip()
    nome = (nome_beneficiario or "").strip()[:25]
    cidade = (cidade_beneficiario or "").strip()[:15]
    if ativo and not chave:
        raise ValueError("Informe a chave PIX.")
    if ativo and not nome:
        raise ValueError("Informe o nome do beneficiário (como no banco).")
    if ativo and not cidade:
        raise ValueError("Informe a cidade do beneficiário.")

    cur.execute(
        """
        INSERT INTO tbl_integracao_pix_manual (
            id_tenant, ativo, tipo_chave, chave_pix, nome_beneficiario, cidade_beneficiario, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            ativo = EXCLUDED.ativo,
            tipo_chave = EXCLUDED.tipo_chave,
            chave_pix = EXCLUDED.chave_pix,
            nome_beneficiario = EXCLUDED.nome_beneficiario,
            cidade_beneficiario = EXCLUDED.cidade_beneficiario,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, ativo, tipo, chave, nome, cidade, agora_utc()),
    )


def desativar_pix_manual(cur, id_tenant: int) -> None:
    if not _tem_tabela(cur):
        return
    cur.execute(
        """
        UPDATE tbl_integracao_pix_manual SET ativo = FALSE, atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), id_tenant),
    )


# ── payload ───────────────────────────────────────────

import re


def _crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for ch in data:
        crc ^= ord(ch) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def normalizar_txid(referencia: str, *, max_len: int = 25) -> str:
    """TXID alfanumérico (BACEN) — ex.: 002-00005 → 00200005."""
    limpo = re.sub(r"[^A-Za-z0-9]", "", referencia or "")
    return (limpo or "PEDIDO")[:max_len]


def gerar_payload_pix(
    *,
    chave: str,
    nome_beneficiario: str,
    cidade: str,
    valor: float,
    txid: str,
) -> str:
    chave = (chave or "").strip()
    if not chave:
        raise ValueError("Chave PIX não configurada.")

    nome = (nome_beneficiario or "FORNECEDOR").strip()[:25].upper()
    cidade_fmt = (cidade or "BRASIL").strip()[:15].upper()
    txid_fmt = normalizar_txid(txid)

    merchant_account = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    payload = ""
    payload += _tlv("00", "01")
    payload += _tlv("26", merchant_account)
    payload += _tlv("52", "0000")
    payload += _tlv("53", "986")
    if valor and float(valor) > 0:
        payload += _tlv("54", f"{float(valor):.2f}")
    payload += _tlv("58", "BR")
    payload += _tlv("59", nome)
    payload += _tlv("60", cidade_fmt)
    if txid_fmt:
        payload += _tlv("62", _tlv("05", txid_fmt))

    sem_crc = payload + "6304"
    return sem_crc + _crc16_ccitt(sem_crc)


# ── pedido ────────────────────────────────────────────

from global_utils import agora_utc
from core.pedidos.servico import (
    STATUS_AGUARDANDO,
    STATUS_IMPORTADO,
    STATUS_PAGO,
    _status_vendedor_pagavel,
    marcar_pedido_pago,
    obter_pedido,
    registrar_historico,
    status_vendedor_pedido,
)


def meio_pix_manual_fornecedor(cur, id_fornecedor: int) -> dict:
    ativo = pix_manual_ativo(cur, id_fornecedor)
    return {
        "integracao": "pix-manual",
        "integracao_nome": "PIX Manual",
        "conectado": ativo,
        "pix_manual": ativo,
        "pix": False,
        "cartao": False,
    }


def iniciar_pix_manual(cur, id_vendedor: int, id_pedido: int) -> dict:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _status_vendedor_pagavel(status_vendedor_pedido(ped)):
        raise ValueError("Somente pedidos importados ou aguardando pagamento podem usar PIX manual.")

    id_forn = int(ped["id_tenant_fornecedor"])
    if not pix_manual_ativo(cur, id_forn):
        raise ValueError("Fornecedor não configurou PIX manual.")

    cfg = carregar_config_pix_manual(cur, id_forn)
    txid = normalizar_txid(ped.get("numero") or f"PED{id_pedido}")
    payload = gerar_payload_pix(
        chave=cfg["chave_pix"],
        nome_beneficiario=cfg["nome_beneficiario"],
        cidade=cfg["cidade_beneficiario"],
        valor=float(ped["valor_total"]),
        txid=txid,
    )

    cur.execute(
        """
        UPDATE tbl_pedido SET
            meio_pagamento = 'pix_manual',
            pix_manual_payload = %s,
            pix_manual_txid = %s,
            atualizado_em = %s
        WHERE id = %s
        """,
        (payload, txid, agora_utc(), id_pedido),
    )
    registrar_historico(
        cur,
        id_pedido,
        "pix_manual",
        f"PIX manual gerado. Referência: {txid}.",
        None,
    )
    return {
        "payload": payload,
        "txid": txid,
        "valor_total": ped["valor_total"],
        "numero_pedido": ped.get("numero"),
        "nome_beneficiario": cfg.get("nome_beneficiario"),
        "status_pagamento": ped.get("status_pagamento") or "pendente",
    }


def marcar_comprovante_enviado(cur, id_pedido: int, *, id_vendedor: int | None = None) -> None:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Pedido não usa PIX manual.")
    if not _status_vendedor_pagavel(status_vendedor_pedido(ped)):
        raise ValueError("Pedido não está aguardando pagamento.")
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status_pagamento = 'comprovante_enviado',
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_pedido),
    )
    registrar_historico(cur, id_pedido, "comprovante", "Vendedor anexou comprovante PIX.", None)


def confirmar_pix_manual(
    cur,
    id_pedido: int,
    *,
    id_fornecedor: int,
    id_usuario: int | None = None,
) -> None:
    ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Este pedido não foi pago via PIX manual.")
    if not _status_vendedor_pagavel(status_vendedor_pedido(ped)):
        raise ValueError("Pedido não está aguardando confirmação de pagamento.")
    if ped.get("status_pagamento") not in ("comprovante_enviado", "pendente"):
        raise ValueError("Situação de pagamento inválida para confirmação.")

    marcar_pedido_pago(cur, id_pedido, id_usuario=id_usuario)
    registrar_historico(
        cur,
        id_pedido,
        "pago_manual",
        "Fornecedor confirmou recebimento do PIX manual.",
        id_usuario,
    )


def rejeitar_comprovante_pix(
    cur,
    id_pedido: int,
    *,
    id_fornecedor: int,
    id_usuario: int | None = None,
    motivo: str | None = None,
) -> None:
    ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Este pedido não usa PIX manual.")
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status_pagamento = 'pendente',
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_pedido),
    )
    registrar_historico(
        cur,
        id_pedido,
        "comprovante_rejeitado",
        motivo or "Fornecedor rejeitou o comprovante. Envie novamente.",
        id_usuario,
    )
