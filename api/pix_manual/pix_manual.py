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

from core.pedidos.servico import (
    STATUS_AGUARDANDO,
    STATUS_AGUARDANDO_CONFIRMACAO,
    STATUS_IMPORTADO,
    STATUS_PAGO,
    _sql_set_status_vendedor,
    _status_vendedor_pagavel,
    marcar_pedido_pago,
    obter_pedido,
    origem_e_canal_externo,
    pedido_tem_comprovante_pix,
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


def _gerar_payload_e_gravar_pix(cur, ped: dict, *, id_pedido: int) -> dict:
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
        "status_pagamento": "pendente",
        "status_vendedor": status_vendedor_pedido(ped),
    }


def iniciar_pix_manual(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
) -> dict:
    """
    Gera QR/copia e cola. Não marca como pago.
    Fluxo: gerar PIX → anexar comprovante → fornecedor aprova.
    Com comprovante anexado, não gera de novo (remova o comprovante antes).
    """
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    st = status_vendedor_pedido(ped)
    if st in ("entregue", "cancelado"):
        raise ValueError("Não é possível gerar PIX neste status do pedido.")
    if pedido_tem_comprovante_pix(cur, id_pedido):
        raise ValueError(
            "Já existe comprovante anexado. Remova o comprovante para gerar o PIX novamente."
        )

    # Qualquer status sem comprovante (pago/expedição legado etc.): reabre e gera
    if st not in (STATUS_IMPORTADO, STATUS_AGUARDANDO):
        return reabrir_pagamento_pix_manual(
            cur, id_vendedor, id_pedido, id_usuario=id_usuario
        )

    return _gerar_payload_e_gravar_pix(cur, ped, id_pedido=id_pedido)


def voltar_cobranca_apos_remover_comprovante(
    cur,
    id_pedido: int,
    *,
    id_vendedor: int | None = None,
    id_usuario: int | None = None,
) -> dict:
    """Após excluir o comprovante: volta a permitir Gerar PIX (ainda não pago)."""
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    st = status_vendedor_pedido(ped)
    if st in ("em_expedicao", "entregue", "cancelado"):
        raise ValueError("Não é possível alterar cobrança neste status.")
    if st == STATUS_PAGO and (
        ped.get("pago_em") or (ped.get("status_pagamento") or "").lower() == "pago"
    ):
        raise ValueError("Pagamento já aprovado pelo fornecedor. Não é possível remover o comprovante.")

    alvo = (
        STATUS_IMPORTADO
        if origem_e_canal_externo(ped.get("origem"))
        else STATUS_AGUARDANDO
    )
    set_sv, dup = _sql_set_status_vendedor(cur)
    params: list = [alvo]
    if dup:
        params.append(alvo)
    params.extend([agora_utc(), id_pedido])
    cur.execute(
        f"""
        UPDATE tbl_pedido SET
            {set_sv},
            status_pagamento = 'pendente',
            pago_em = NULL,
            meio_pagamento = COALESCE(NULLIF(meio_pagamento, ''), 'pix_manual'),
            atualizado_em = %s
        WHERE id = %s
        """,
        params,
    )
    registrar_historico(
        cur,
        id_pedido,
        "comprovante_removido",
        "Comprovante PIX removido. Gere o PIX novamente se precisar.",
        id_usuario,
    )
    ped2 = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    return ped2 or ped


def marcar_comprovante_enviado(cur, id_pedido: int, *, id_vendedor: int | None = None) -> None:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Pedido não usa PIX manual.")
    st = status_vendedor_pedido(ped)
    if st not in (STATUS_AGUARDANDO, STATUS_IMPORTADO, STATUS_AGUARDANDO_CONFIRMACAO):
        raise ValueError("Pedido não está aguardando pagamento.")

    set_sv, dup = _sql_set_status_vendedor(cur)
    params = [STATUS_AGUARDANDO_CONFIRMACAO]
    if dup:
        params.append(STATUS_AGUARDANDO_CONFIRMACAO)
    params.extend([agora_utc(), id_pedido])
    cur.execute(
        f"""
        UPDATE tbl_pedido SET
            {set_sv},
            status_pagamento = 'comprovante_enviado',
            atualizado_em = %s
        WHERE id = %s
        """,
        params,
    )
    registrar_historico(cur, id_pedido, "comprovante", "Vendedor anexou comprovante PIX.", None)
    try:
        from core.pedidos.notificacoes import notificar_evento_pedido

        notificar_evento_pedido(cur, id_pedido, "comprovante_enviado")
    except Exception:
        pass


def confirmar_pix_manual(
    cur,
    id_pedido: int,
    *,
    id_fornecedor: int,
    id_usuario: int | None = None,
) -> None:
    """Só marca pago depois do vendedor anexar o comprovante (aprovação do fornecedor)."""
    ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Este pedido não foi pago via PIX manual.")
    st = status_vendedor_pedido(ped)
    if st != STATUS_AGUARDANDO_CONFIRMACAO:
        raise ValueError("Aguarde o vendedor anexar o comprovante PIX antes de aprovar.")
    if (ped.get("status_pagamento") or "").strip().lower() != "comprovante_enviado":
        raise ValueError("Só é possível aprovar após o envio do comprovante.")

    marcar_pedido_pago(
        cur,
        id_pedido,
        id_usuario=id_usuario,
        detalhe="Fornecedor aprovou o comprovante PIX manual.",
    )
    registrar_historico(
        cur,
        id_pedido,
        "pago_manual",
        "Fornecedor confirmou recebimento do PIX manual.",
        id_usuario,
    )


def reabrir_pagamento_pix_manual(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
) -> dict:
    """
    Volta o pedido para cobrança PIX (QR/copia e cola), sem marcar pago.
    Fluxo: gerar PIX → anexar comprovante → fornecedor aprova.
    """
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    st = status_vendedor_pedido(ped)
    if st in ("entregue", "cancelado"):
        raise ValueError("Não é possível reabrir cobrança neste status.")
    if pedido_tem_comprovante_pix(cur, id_pedido):
        raise ValueError("Remova o comprovante antes de gerar o PIX novamente.")

    alvo = (
        STATUS_IMPORTADO
        if origem_e_canal_externo(ped.get("origem"))
        else STATUS_AGUARDANDO
    )
    set_sv, dup = _sql_set_status_vendedor(cur)
    params: list = [alvo]
    if dup:
        params.append(alvo)
    params.extend([agora_utc(), id_pedido])
    cur.execute(
        f"""
        UPDATE tbl_pedido SET
            {set_sv},
            status_pagamento = 'pendente',
            pago_em = NULL,
            meio_pagamento = COALESCE(NULLIF(meio_pagamento, ''), 'pix_manual'),
            atualizado_em = %s
        WHERE id = %s
        """,
        params,
    )
    registrar_historico(
        cur,
        id_pedido,
        "pix_reaberto",
        "Cobrança PIX reaberta. Gere o QR/copia e cola, anexe o comprovante e aguarde o fornecedor aprovar.",
        id_usuario,
    )
    ped2 = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped2:
        raise ValueError("Pedido não encontrado após reabrir cobrança.")
    out = _gerar_payload_e_gravar_pix(cur, ped2, id_pedido=id_pedido)
    out["status_vendedor"] = status_vendedor_pedido(ped2)
    out["reaberto"] = True
    return out


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
    motivo_txt = (motivo or "").strip()
    if len(motivo_txt) < 5:
        raise ValueError("Informe o motivo da rejeição (mínimo 5 caracteres).")

    st = status_vendedor_pedido(ped)
    if st not in (STATUS_AGUARDANDO_CONFIRMACAO, STATUS_AGUARDANDO) and ped.get(
        "status_pagamento"
    ) != "comprovante_enviado":
        raise ValueError("Não há comprovante pendente de validação.")

    set_sv, dup = _sql_set_status_vendedor(cur)
    params = [STATUS_AGUARDANDO]
    if dup:
        params.append(STATUS_AGUARDANDO)
    params.extend([agora_utc(), id_pedido])
    cur.execute(
        f"""
        UPDATE tbl_pedido SET
            {set_sv},
            status_pagamento = 'pendente',
            atualizado_em = %s
        WHERE id = %s
        """,
        params,
    )
    registrar_historico(
        cur,
        id_pedido,
        "comprovante_rejeitado",
        f"Fornecedor rejeitou o comprovante: {motivo_txt}",
        id_usuario,
    )
    try:
        from core.pedidos.notificacoes import notificar_evento_pedido

        notificar_evento_pedido(cur, id_pedido, "comprovante_rejeitado", criado_por=id_usuario)
    except Exception:
        pass
