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
    # API manda em reais (79 = R$ 79,00). Inteiro grande (>100000) pode já ser centavos.
    if isinstance(valor, int) and valor >= 10000 and valor % 100 == 0 and "." not in str(valor):
        # heurística fraca: preferir sempre reais (documentação Efí)
        pass
    return int(round(v * 100))


def _reais_str_para_centavos(raw) -> int:
    if raw is None or raw == "":
        return 0
    try:
        return int(round(float(str(raw).replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


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


def _fmt_data_br_dt(v) -> str:
    dt = _parse_dt(v)
    if not dt:
        return "—"
    return dt.strftime("%d/%m/%Y")


def _txid_do_pix(det: dict) -> str:
    tx = str(det.get("txid") or "").strip()
    if tx:
        return tx
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
        ref = data_tx or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        inicio = ref - timedelta(days=45)
        fim = ref + timedelta(days=7)
        cur.execute(
            """
            SELECT id, id_tenant, status, efi_txid
            FROM tbl_fatura
            WHERE valor_centavos = %s
              AND status IN ('pago', 'pendente', 'vencido', 'bloqueado')
              AND COALESCE(pago_em, criado_em, vencimento_em) >= %s
              AND COALESCE(pago_em, criado_em, vencimento_em) <= %s
            ORDER BY id DESC
            LIMIT 5
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
        novo = "pago" if st_local in ("bloqueado", "pendente", "vencido", "pago") else st_local or "pago"
    else:
        # Status desconhecido mas veio na listagem → trata como bloqueado se ainda não pago/cancelado
        novo = "bloqueado" if st_local not in ("cancelado",) else st_local

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


def _normalizar_infracao(item: dict) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    med_id = str(item.get("idInfracao") or item.get("id") or "").strip()
    e2e = str(item.get("endToEndId") or item.get("endToEndID") or "").strip()
    med_status = str(item.get("status") or "").strip().upper()
    protocolo = str(item.get("protocolo") or item.get("protocol") or "").strip()
    razao = str(
        item.get("razao")
        or item.get("tipoSituacao")
        or item.get("tipoFraude")
        or "MED Pix"
    ).strip()
    valor_c = _valor_med_centavos(item.get("valor"))
    data_tx = _parse_dt(item.get("dataTransacao") or item.get("dataCriacao"))
    return {
        "med_id": med_id,
        "protocolo": protocolo,
        "e2e": e2e,
        "med_status": med_status or "ABERTA",
        "razao": razao,
        "valor_centavos": int(valor_c or 0),
        "data_tx": data_tx,
        "raw": item,
    }


def sincronizar_bloqueios_med(cur, *, dias: int = 180) -> dict[str, Any]:
    """
    Consulta MED + saldo bloqueado na Efí.
    Atualiza faturas quando dá match; sempre devolve a lista de MEDs abertos
    (mesmo sem vínculo) para a aba Bloqueados.
    """
    from api.efi.efi import (
        consultar_pix_recebido,
        consultar_saldo_efi,
        efi_disponivel,
        listar_infracoes_med,
    )

    garantir_colunas_med_fatura(cur)
    out: dict[str, Any] = {
        "ok": False,
        "message": "",
        "atualizados": 0,
        "abertos": 0,
        "sem_fatura": 0,
        "total_med": 0,
        "saldo_centavos": 0,
        "bloqueio_med_centavos": 0,
        "bloqueio_judicial_centavos": 0,
        "bloqueio_total_centavos": 0,
        "infracoes_abertas": [],
    }
    if not efi_disponivel():
        out["message"] = "Efí indisponível."
        return out

    # Saldo / bloqueios (mesmo se MED list falhar)
    try:
        saldo = consultar_saldo_efi(com_bloqueios=True)
        out["saldo_centavos"] = _reais_str_para_centavos(saldo.get("saldo"))
        bloq = saldo.get("bloqueios") if isinstance(saldo.get("bloqueios"), dict) else {}
        out["bloqueio_med_centavos"] = _reais_str_para_centavos(bloq.get("med"))
        out["bloqueio_judicial_centavos"] = _reais_str_para_centavos(bloq.get("judicial"))
        out["bloqueio_total_centavos"] = _reais_str_para_centavos(
            bloq.get("total")
        ) or (out["bloqueio_med_centavos"] + out["bloqueio_judicial_centavos"])
    except Exception as e:
        log.warning("Saldo Efí com bloqueios: %s", e)
        out["message"] = f"Saldo: {e}"

    agora = datetime.now(timezone.utc)
    inicio = (agora - timedelta(days=max(30, int(dias)))).strftime("%Y-%m-%dT00:00:00Z")
    fim = (agora + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59Z")

    try:
        raw = listar_infracoes_med(inicio=inicio, fim=fim)
    except Exception as e:
        log.exception("Falha ao listar MED Efí")
        msg = str(e)
        if "escopo" in msg.lower() or "scope" in msg.lower() or "autoriz" in msg.lower() or "403" in msg:
            msg = (
                f"{msg} — Ative o escopo gn.infractions.read (e gn.balance.read) "
                "na aplicação da Efí."
            )
        out["message"] = (out.get("message") + " | " if out.get("message") else "") + msg
        out["ok"] = out["bloqueio_total_centavos"] > 0  # ainda útil mostrar saldo
        return out

    infracoes = raw.get("infracoes") if isinstance(raw, dict) else None
    if not isinstance(infracoes, list):
        infracoes = []
    out["total_med"] = len(infracoes)

    atualizados = 0
    sem_fatura = 0
    abertos_itens: list[dict] = []

    for item in infracoes:
        norm = _normalizar_infracao(item)
        if not norm:
            continue
        med_status = norm["med_status"]
        aberto = med_status not in (_MED_LIBERADOS | _MED_ESTORNO)

        txid = ""
        if norm["e2e"]:
            try:
                pix = consultar_pix_recebido(norm["e2e"])
                txid = _txid_do_pix(pix)
            except Exception:
                log.debug("Pix %s sem detalhe (MED %s)", norm["e2e"], norm["med_id"], exc_info=True)

        fat = _buscar_fatura_para_med(
            cur,
            e2e=norm["e2e"],
            txid=txid,
            valor_centavos=norm["valor_centavos"] or None,
            data_tx=norm["data_tx"],
        )

        vinculo = None
        if fat:
            id_fatura, id_tenant, st_atual, _tx = int(fat[0]), int(fat[1]), fat[2], fat[3]
            _aplicar_med_na_fatura(
                cur,
                id_fatura=id_fatura,
                status_atual=str(st_atual or ""),
                med_status=med_status or "ABERTA",
                med_id=norm["med_id"],
                e2e=norm["e2e"],
                txid=txid,
                razao=norm["razao"],
            )
            atualizados += 1
            vinculo = {"id_fatura": id_fatura, "id_tenant": id_tenant}
        elif aberto:
            sem_fatura += 1

        if aberto:
            abertos_itens.append(
                {
                    "med_id": norm["med_id"],
                    "protocolo": norm["protocolo"],
                    "efi_e2e": norm["e2e"],
                    "efi_txid": txid,
                    "med_status": med_status or "ABERTA",
                    "med_status_label": rotulo_med_status(med_status or "ABERTA"),
                    "med_razao": norm["razao"] or "MED Pix",
                    "valor_centavos": norm["valor_centavos"],
                    "data_tx_br": _fmt_data_br_dt(norm["data_tx"]),
                    "id_fatura": vinculo["id_fatura"] if vinculo else None,
                    "id_tenant": vinculo["id_tenant"] if vinculo else None,
                    "vinculado": bool(vinculo),
                }
            )

    # Conta tem saldo MED mas a listagem veio vazia → mostra resumo do saldo
    if out["bloqueio_med_centavos"] > 0 and not abertos_itens:
        abertos_itens.append(
            {
                "med_id": "",
                "protocolo": "",
                "efi_e2e": "",
                "efi_txid": "",
                "med_status": "ABERTA",
                "med_status_label": "Bloqueio (saldo)",
                "med_razao": "Saldo MED bloqueado na Efí — detalhe da infração não veio na API (confira escopo gn.infractions.read).",
                "valor_centavos": out["bloqueio_med_centavos"],
                "data_tx_br": "—",
                "id_fatura": None,
                "id_tenant": None,
                "vinculado": False,
            }
        )

    out["atualizados"] = atualizados
    out["sem_fatura"] = sem_fatura
    out["abertos"] = len(abertos_itens)
    out["infracoes_abertas"] = abertos_itens
    out["ok"] = True
    if not out.get("message") or out["message"] == "":
        out["message"] = "ok"
    return out


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
