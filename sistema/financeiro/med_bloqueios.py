# sistema/financeiro/med_bloqueios.py — sync MED (pago bloqueado) da Efí
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

# Em disputa / aguardando análise → mostra em Bloqueados
_MED_ABERTOS = frozenset({"ABERTA", "EM_DEFESA"})
# Liberado a favor do recebedor → volta a pago
_MED_LIBERADOS = frozenset({"REJEITADA", "CANCELADA_EFI"})
# Aceito a favor do pagador → estorno
_MED_ESTORNO = frozenset({"ACEITA"})

_MED_STATUS_LABEL = {
    "ABERTA": "Aberta",
    "EM_DEFESA": "Em defesa",
    "ACEITA": "Aceita (estorno)",
    "REJEITADA": "Rejeitada (liberado)",
    "CANCELADA_EFI": "Cancelada Efí",
}


def garantir_colunas_med_fatura(cur) -> None:
    cur.execute(
        """
        ALTER TABLE tbl_fatura
            ADD COLUMN IF NOT EXISTS efi_e2e_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS efi_med_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS efi_med_status VARCHAR(24),
            ADD COLUMN IF NOT EXISTS efi_med_razao TEXT,
            ADD COLUMN IF NOT EXISTS efi_med_atualizado_em TIMESTAMP
        """
    )


def _valor_med_centavos(valor) -> int | None:
    if valor is None or valor == "":
        return None
    try:
        if isinstance(valor, str):
            v = float(valor.replace(",", ".").strip())
        else:
            v = float(valor)
    except (TypeError, ValueError):
        return None
    # API costuma mandar em reais (100 = R$ 100,00)
    return int(round(v * 100))


def _parse_dt(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _txid_do_pix(det: dict) -> str:
    tx = str(det.get("txid") or "").strip()
    if tx:
        return tx
    # alguns payloads aninham cob
    cob = det.get("cob") if isinstance(det.get("cob"), dict) else {}
    return str(cob.get("txid") or "").strip()


def _buscar_fatura_para_med(
    cur,
    *,
    e2e: str,
    txid: str,
    valor_centavos: int | None,
    data_tx: datetime | None,
) -> tuple | None:
    if e2e:
        cur.execute(
            """
            SELECT id, id_tenant, status, efi_txid
            FROM tbl_fatura
            WHERE efi_e2e_id = %s
            ORDER BY id DESC LIMIT 1
            """,
            (e2e,),
        )
        row = cur.fetchone()
        if row:
            return row
    if txid:
        cur.execute(
            """
            SELECT id, id_tenant, status, efi_txid
            FROM tbl_fatura
            WHERE efi_txid = %s OR efi_charge_id = %s
            ORDER BY id DESC LIMIT 1
            """,
            (txid, txid),
        )
        row = cur.fetchone()
        if row:
            return row
    if valor_centavos and valor_centavos > 0:
        # fallback: valor + janela de 10 dias em torno da transação
        ref = data_tx or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        inicio = ref - timedelta(days=10)
        fim = ref + timedelta(days=3)
        cur.execute(
            """
            SELECT id, id_tenant, status, efi_txid
            FROM tbl_fatura
            WHERE valor_centavos = %s
              AND COALESCE(forma_pagamento, '') ILIKE 'pix%%'
              AND status IN ('pago', 'pendente', 'vencido', 'bloqueado')
              AND COALESCE(pago_em, criado_em, vencimento_em) >= %s
              AND COALESCE(pago_em, criado_em, vencimento_em) <= %s
            ORDER BY id DESC
            LIMIT 3
            """,
            (valor_centavos, inicio, fim),
        )
        rows = cur.fetchall() or []
        if len(rows) == 1:
            return rows[0]
    return None


def _aplicar_med_na_fatura(
    cur,
    *,
    id_fatura: int,
    status_atual: str,
    med_status: str,
    med_id: str,
    e2e: str,
    txid: str,
    razao: str,
) -> str:
    st_med = med_status.upper()
    st_local = (status_atual or "").strip().lower()

    if st_med in _MED_ABERTOS:
        novo = "bloqueado"
    elif st_med in _MED_ESTORNO:
        novo = "cancelado"
    elif st_med in _MED_LIBERADOS:
        # só restaura pago se estava bloqueado / pendente por causa do MED
        novo = "pago" if st_local in ("bloqueado", "pendente", "vencido", "pago") else st_local or "pago"
    else:
        novo = st_local or "bloqueado"

    cur.execute(
        """
        UPDATE tbl_fatura
        SET status = %s,
            efi_e2e_id = COALESCE(NULLIF(%s, ''), efi_e2e_id),
            efi_txid = COALESCE(NULLIF(%s, ''), efi_txid),
            efi_med_id = %s,
            efi_med_status = %s,
            efi_med_razao = %s,
            efi_med_atualizado_em = NOW(),
            pago_em = CASE
                WHEN %s IN ('bloqueado', 'pago') THEN COALESCE(pago_em, NOW())
                ELSE pago_em
            END,
            atualizado_em = NOW()
        WHERE id = %s
        """,
        (novo, e2e, txid, med_id or None, st_med, (razao or "")[:500] or None, novo, id_fatura),
    )
    return novo


def sincronizar_bloqueios_med(cur, *, dias: int = 180) -> dict[str, Any]:
    """Consulta MED na Efí e marca faturas como bloqueado / liberado / estornado."""
    from api.efi.efi import consultar_pix_recebido, efi_disponivel, listar_infracoes_med

    garantir_colunas_med_fatura(cur)
    if not efi_disponivel():
        return {"ok": False, "message": "Efí indisponível.", "atualizados": 0, "abertos": 0}

    agora = datetime.now(timezone.utc)
    inicio = (agora - timedelta(days=max(30, int(dias)))).strftime("%Y-%m-%dT00:00:00Z")
    fim = agora.strftime("%Y-%m-%dT23:59:59Z")

    try:
        raw = listar_infracoes_med(inicio=inicio, fim=fim)
    except Exception as e:
        log.exception("Falha ao listar MED Efí")
        return {"ok": False, "message": str(e), "atualizados": 0, "abertos": 0}

    infracoes = raw.get("infracoes") if isinstance(raw, dict) else None
    if not isinstance(infracoes, list):
        infracoes = []

    atualizados = 0
    sem_fatura = 0
    abertos = 0

    for item in infracoes:
        if not isinstance(item, dict):
            continue
        med_id = str(item.get("idInfracao") or item.get("id") or "").strip()
        e2e = str(item.get("endToEndId") or item.get("endToEndID") or "").strip()
        med_status = str(item.get("status") or "").strip().upper()
        razao = str(item.get("razao") or item.get("tipoSituacao") or "").strip()
        valor_c = _valor_med_centavos(item.get("valor"))
        data_tx = _parse_dt(item.get("dataTransacao"))

        if med_status in _MED_ABERTOS:
            abertos += 1

        txid = ""
        if e2e:
            try:
                pix = consultar_pix_recebido(e2e)
                txid = _txid_do_pix(pix)
            except Exception:
                log.debug("Pix %s sem detalhe (MED %s)", e2e, med_id, exc_info=True)

        fat = _buscar_fatura_para_med(
            cur,
            e2e=e2e,
            txid=txid,
            valor_centavos=valor_c,
            data_tx=data_tx,
        )
        if not fat:
            sem_fatura += 1
            continue

        id_fatura, _tid, st_atual, _tx = int(fat[0]), int(fat[1]), fat[2], fat[3]
        _aplicar_med_na_fatura(
            cur,
            id_fatura=id_fatura,
            status_atual=str(st_atual or ""),
            med_status=med_status,
            med_id=med_id,
            e2e=e2e,
            txid=txid,
            razao=razao,
        )
        atualizados += 1

    return {
        "ok": True,
        "atualizados": atualizados,
        "abertos": abertos,
        "sem_fatura": sem_fatura,
        "total_med": len(infracoes),
    }


def listar_faturas_bloqueadas(cur) -> list[dict]:
    """Retorna linhas brutas; o painel formata rótulos."""
    garantir_colunas_med_fatura(cur)
    cur.execute(
        """
        SELECT
          f.id, f.id_tenant, t.nome, f.referencia, f.plano_slug, f.valor_centavos,
          f.status, f.forma_pagamento, f.vencimento_em, f.pago_em, f.criado_em,
          f.efi_txid, f.efi_e2e_id, f.efi_med_id, f.efi_med_status, f.efi_med_razao,
          f.efi_med_atualizado_em, t.tipo_negocio,
          COALESCE(NULLIF(f.periodicidade, ''), 'mensal')
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status = 'bloqueado'
           OR (
             NULLIF(TRIM(COALESCE(f.efi_med_status, '')), '') IS NOT NULL
             AND UPPER(TRIM(f.efi_med_status)) IN ('ABERTA', 'EM_DEFESA')
           )
        ORDER BY COALESCE(f.efi_med_atualizado_em, f.pago_em, f.criado_em) DESC NULLS LAST, f.id DESC
        LIMIT 200
        """
    )
    return list(cur.fetchall() or [])


def rotulo_med_status(status: str | None) -> str:
    st = str(status or "").strip().upper()
    return _MED_STATUS_LABEL.get(st, st or "—")
