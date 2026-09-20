# core/integracoes/status_padrao.py — amarração global status DN ↔ integrações
from __future__ import annotations

import json
import logging
import re
from typing import Any

_log = logging.getLogger(__name__)

APLICACOES = ("bling", "mercado_livre", "tiktok", "amazon")
CONTEXTOS = ("vendedor", "fornecedor", "ambos")
DIRECOES = ("inbound", "outbound", "ambos")

FLAG_MIGRADO = "status_padrao_v2"
CHAVES_SITUACAO_LEGADO = (
    "bling_situacao_importar",
    "bling_situacao_criar",
    "bling_situacao_pago",
    "bling_situacao_expedido",
    "bling_situacao_entregue",
    "bling_situacao_cancelado",
)

_FALLBACK_EVENTO_NOMES: dict[str, tuple[str, ...]] = {
    "importar": ("atendido",),
    "criar": ("em aberto", "atendido"),
    "pago": ("verificado", "pago", "aprovado"),
    "expedido": ("em transporte", "enviado", "despachado", "expedido", "postado"),
    "entregue": ("entregue",),
    "cancelado": ("cancelado", "cancelada"),
}

_COLS = """
    id, aplicacao, contexto, status_dn, status_dn_label, evento,
    status_externo, aliases, direcao, descricao, ativo, ordem
"""


def _norm(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "").strip().lower())


def _row_to_dict(row: tuple) -> dict[str, Any]:
    aliases = row[7]
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except json.JSONDecodeError:
            aliases = []
    if not isinstance(aliases, list):
        aliases = []
    return {
        "id": row[0],
        "aplicacao": row[1],
        "contexto": row[2],
        "status_dn": row[3],
        "status_dn_label": row[4],
        "evento": row[5],
        "status_externo": row[6],
        "aliases": [str(a) for a in aliases],
        "direcao": row[8],
        "descricao": row[9] or "",
        "ativo": bool(row[10]),
        "ordem": int(row[11] or 0),
    }


def garantir_tabela(cur) -> None:
    """Garante que a tabela existe. Não tenta DDL se já existir (evita 'must be owner')."""
    cur.execute("SELECT to_regclass('public.tbl_integracao_status_padrao')")
    if cur.fetchone()[0]:
        return
    cur.execute(
        """
        CREATE TABLE tbl_integracao_status_padrao (
          id              SERIAL PRIMARY KEY,
          aplicacao       VARCHAR(40)  NOT NULL,
          contexto        VARCHAR(20)  NOT NULL DEFAULT 'ambos',
          status_dn       VARCHAR(40)  NOT NULL,
          status_dn_label VARCHAR(80)  NOT NULL,
          evento          VARCHAR(40)  NOT NULL,
          status_externo  VARCHAR(120) NOT NULL,
          aliases         JSONB        NOT NULL DEFAULT '[]'::jsonb,
          direcao         VARCHAR(20)  NOT NULL DEFAULT 'ambos',
          descricao       TEXT,
          ativo           BOOLEAN      NOT NULL DEFAULT TRUE,
          ordem           INTEGER      NOT NULL DEFAULT 0,
          criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
          atualizado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
          CHECK (contexto IN ('vendedor', 'fornecedor', 'ambos')),
          CHECK (direcao IN ('inbound', 'outbound', 'ambos'))
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_isp_app_ctx_evento
          ON tbl_integracao_status_padrao (aplicacao, contexto, evento)
        """
    )


def seed_bling_se_vazio(cur) -> None:
    garantir_tabela(cur)
    cur.execute("SELECT COUNT(*) FROM tbl_integracao_status_padrao WHERE aplicacao = 'bling'")
    if int(cur.fetchone()[0] or 0) > 0:
        return
    rows = [
        (
            "bling",
            "vendedor",
            "aguardando_pagamento",
            "Aguardando pagamento",
            "importar",
            "Atendido",
            "[]",
            "inbound",
            "Pedido Atendido no Bling entra no DropNexo (cliente já pagou o vendedor).",
            10,
        ),
        (
            "bling",
            "vendedor",
            "pago",
            "Pago",
            "pago",
            "Verificado",
            '["Pago"]',
            "outbound",
            "Vendedor pagou o fornecedor e anexou comprovante (espelha no Bling se houver situação).",
            20,
        ),
        (
            "bling",
            "vendedor",
            "em_expedicao",
            "Expedido",
            "expedido",
            "Em transporte",
            '["Enviado","Despachado","Expedido","Postado"]',
            "outbound",
            "Pedido em expedição / etiqueta impressa.",
            30,
        ),
        (
            "bling",
            "vendedor",
            "entregue",
            "Entregue",
            "entregue",
            "Entregue",
            "[]",
            "ambos",
            "Entregue ao destinatário final.",
            40,
        ),
        (
            "bling",
            "vendedor",
            "cancelado",
            "Cancelado",
            "cancelado",
            "Cancelado",
            "[]",
            "ambos",
            "Cancelamento no Bling cancela no DropNexo e estorna estoque.",
            50,
        ),
        (
            "bling",
            "fornecedor",
            "aguardando_pagamento",
            "Aguardando pagamento",
            "criar",
            "Em aberto",
            '["Atendido"]',
            "outbound",
            "Pedido canal chegou — cria o pedido de venda no seu Bling.",
            10,
        ),
        (
            "bling",
            "fornecedor",
            "pago",
            "Pago",
            "pago",
            "Verificado",
            '["Atendido","Pago"]',
            "outbound",
            "Vendedor quitou com você (comprovante anexado).",
            20,
        ),
        (
            "bling",
            "fornecedor",
            "em_expedicao",
            "Expedido",
            "expedido",
            "Em transporte",
            '["Enviado","Despachado","Expedido","Postado"]',
            "outbound",
            "Você imprimiu a etiqueta no DropNexo.",
            30,
        ),
        (
            "bling",
            "fornecedor",
            "entregue",
            "Entregue",
            "entregue",
            "Entregue",
            '["Atendido"]',
            "outbound",
            "Entregue ao destinatário final.",
            40,
        ),
        (
            "bling",
            "fornecedor",
            "cancelado",
            "Cancelado",
            "cancelado",
            "Cancelado",
            "[]",
            "outbound",
            "Pedido cancelado — espelha no Bling e estorna estoque no DropNexo.",
            50,
        ),
    ]
    for r in rows:
        cur.execute(
            """
            INSERT INTO tbl_integracao_status_padrao (
              aplicacao, contexto, status_dn, status_dn_label, evento,
              status_externo, aliases, direcao, descricao, ordem
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
            ON CONFLICT (aplicacao, contexto, evento) DO NOTHING
            """,
            r,
        )


def seed_ml_se_vazio(cur) -> None:
    garantir_tabela(cur)
    cur.execute(
        "SELECT COUNT(*) FROM tbl_integracao_status_padrao WHERE aplicacao = 'mercado_livre'"
    )
    if int(cur.fetchone()[0] or 0) > 0:
        return
    rows = [
        (
            "mercado_livre",
            "vendedor",
            "aguardando_pagamento",
            "Aguardando pagamento",
            "importar",
            "paid",
            '["confirmed"]',
            "inbound",
            "Pedido pago no Mercado Livre entra no DropNexo (comprador já pagou o marketplace).",
            10,
        ),
        (
            "mercado_livre",
            "vendedor",
            "em_expedicao",
            "Expedido",
            "expedido",
            "shipped",
            '["ready_to_ship","handling"]',
            "ambos",
            "Envio em andamento no ML / etiqueta — espelha no DropNexo e vice-versa quando possível.",
            30,
        ),
        (
            "mercado_livre",
            "vendedor",
            "entregue",
            "Entregue",
            "entregue",
            "delivered",
            "[]",
            "ambos",
            "Entregue ao destinatário final.",
            40,
        ),
        (
            "mercado_livre",
            "vendedor",
            "cancelado",
            "Cancelado",
            "cancelado",
            "cancelled",
            '["canceled"]',
            "ambos",
            "Cancelamento no ML cancela no DropNexo (e estorna estoque se aplicável).",
            50,
        ),
    ]
    for r in rows:
        cur.execute(
            """
            INSERT INTO tbl_integracao_status_padrao (
              aplicacao, contexto, status_dn, status_dn_label, evento,
              status_externo, aliases, direcao, descricao, ordem
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
            ON CONFLICT (aplicacao, contexto, evento) DO NOTHING
            """,
            r,
        )


def seed_padrao_se_vazio(cur) -> None:
    seed_bling_se_vazio(cur)
    seed_ml_se_vazio(cur)


def listar_status_padrao(
    cur,
    *,
    aplicacao: str | None = None,
    contexto: str | None = None,
    apenas_ativos: bool = True,
) -> list[dict[str, Any]]:
    seed_padrao_se_vazio(cur)
    clauses = ["1=1"]
    params: list[Any] = []
    if aplicacao:
        clauses.append("aplicacao = %s")
        params.append(aplicacao.strip().lower())
    if contexto and contexto != "ambos":
        clauses.append("contexto IN (%s, 'ambos')")
        params.append(contexto.strip().lower())
    if apenas_ativos:
        clauses.append("ativo = TRUE")
    cur.execute(
        f"""
        SELECT {_COLS}
        FROM tbl_integracao_status_padrao
        WHERE {' AND '.join(clauses)}
        ORDER BY aplicacao, contexto, ordem, id
        """,
        params,
    )
    return [_row_to_dict(r) for r in cur.fetchall()]


def obter_status_padrao(cur, id_row: int) -> dict[str, Any] | None:
    seed_padrao_se_vazio(cur)
    cur.execute(
        f"SELECT {_COLS} FROM tbl_integracao_status_padrao WHERE id = %s",
        (int(id_row),),
    )
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def nomes_externos_para_evento(
    cur,
    aplicacao: str,
    contexto: str,
    evento: str,
) -> list[str]:
    """Lista de nomes (principal + aliases) para resolver ID na conta externa."""
    seed_padrao_se_vazio(cur)
    ev = (evento or "").strip().lower()
    app = (aplicacao or "").strip().lower()
    ctx = (contexto or "").strip().lower()
    cur.execute(
        """
        SELECT status_externo, aliases
        FROM tbl_integracao_status_padrao
        WHERE aplicacao = %s AND evento = %s AND ativo = TRUE
          AND contexto IN (%s, 'ambos')
        ORDER BY CASE WHEN contexto = %s THEN 0 ELSE 1 END, ordem
        LIMIT 1
        """,
        (app, ev, ctx, ctx),
    )
    row = cur.fetchone()
    if not row:
        return list(_FALLBACK_EVENTO_NOMES.get(ev, ()))
    nomes: list[str] = []
    principal = (row[0] or "").strip()
    if principal:
        nomes.append(principal)
    aliases = row[1]
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except json.JSONDecodeError:
            aliases = []
    if isinstance(aliases, list):
        for a in aliases:
            s = str(a or "").strip()
            if s and s not in nomes:
                nomes.append(s)
    return nomes or list(_FALLBACK_EVENTO_NOMES.get(ev, ()))


def mapear_externo_para_dn(
    cur,
    aplicacao: str,
    nome_externo: str | None,
    *,
    contexto: str | None = None,
) -> str | None:
    """Resolve status_dn a partir do nome externo usando a tabela (best-effort)."""
    n = _norm(nome_externo or "")
    if not n:
        return None
    rows = listar_status_padrao(cur, aplicacao=aplicacao, contexto=contexto, apenas_ativos=True)
    for row in rows:
        candidatos = [_norm(row["status_externo"])] + [_norm(a) for a in row.get("aliases") or []]
        for c in candidatos:
            if not c:
                continue
            if n == c or c in n or n in c:
                return row["status_dn"]
    return None


def salvar_status_padrao(cur, dados: dict[str, Any]) -> int:
    seed_padrao_se_vazio(cur)
    aplicacao = (dados.get("aplicacao") or "").strip().lower()
    contexto = (dados.get("contexto") or "ambos").strip().lower()
    status_dn = (dados.get("status_dn") or "").strip().lower()
    status_dn_label = (dados.get("status_dn_label") or status_dn).strip()
    evento = (dados.get("evento") or "").strip().lower()
    status_externo = (dados.get("status_externo") or "").strip()
    direcao = (dados.get("direcao") or "ambos").strip().lower()
    descricao = (dados.get("descricao") or "").strip() or None
    ativo = bool(dados.get("ativo", True))
    try:
        ordem = int(dados.get("ordem") or 0)
    except (TypeError, ValueError):
        ordem = 0

    if not aplicacao:
        raise ValueError("Informe a aplicação.")
    if contexto not in CONTEXTOS:
        raise ValueError("Contexto inválido.")
    if direcao not in DIRECOES:
        raise ValueError("Direção inválida.")
    if not status_dn or not evento or not status_externo:
        raise ValueError("status_dn, evento e status_externo são obrigatórios.")

    aliases_raw = dados.get("aliases") or []
    if isinstance(aliases_raw, str):
        aliases_raw = [p.strip() for p in aliases_raw.split(",") if p.strip()]
    if not isinstance(aliases_raw, list):
        aliases_raw = []
    aliases = [str(a).strip() for a in aliases_raw if str(a).strip()]
    aliases_json = json.dumps(aliases, ensure_ascii=False)

    sid = dados.get("id")
    if sid:
        cur.execute(
            """
            UPDATE tbl_integracao_status_padrao SET
              aplicacao=%s, contexto=%s, status_dn=%s, status_dn_label=%s,
              evento=%s, status_externo=%s, aliases=%s::jsonb, direcao=%s,
              descricao=%s, ativo=%s, ordem=%s, atualizado_em=NOW()
            WHERE id=%s
            RETURNING id
            """,
            (
                aplicacao,
                contexto,
                status_dn,
                status_dn_label,
                evento,
                status_externo,
                aliases_json,
                direcao,
                descricao,
                ativo,
                ordem,
                int(sid),
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO tbl_integracao_status_padrao (
              aplicacao, contexto, status_dn, status_dn_label, evento,
              status_externo, aliases, direcao, descricao, ativo, ordem
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                aplicacao,
                contexto,
                status_dn,
                status_dn_label,
                evento,
                status_externo,
                aliases_json,
                direcao,
                descricao,
                ativo,
                ordem,
            ),
        )
    row = cur.fetchone()
    return int(row[0])


def excluir_status_padrao(cur, id_row: int) -> None:
    seed_padrao_se_vazio(cur)
    cur.execute("DELETE FROM tbl_integracao_status_padrao WHERE id = %s", (int(id_row),))


def tenant_precisa_migrar_bling(opcoes: dict | None) -> bool:
    op = opcoes if isinstance(opcoes, dict) else {}
    if op.get(FLAG_MIGRADO) is True or str(op.get(FLAG_MIGRADO) or "").lower() in ("1", "true"):
        return False
    return True


def migrar_tenant_bling_status_padrao(cur, id_tenant: int, contexto: str) -> dict[str, Any]:
    """Remove IDs legados por tenant e marca status_padrao_v2."""
    ctx = (contexto or "").strip().lower()
    if ctx not in ("vendedor", "fornecedor"):
        raise ValueError("Contexto inválido.")

    cur.execute(
        """
        SELECT opcoes FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s
        """,
        (int(id_tenant), ctx),
    )
    row = cur.fetchone()
    opcoes: dict[str, Any] = {}
    if row and row[0]:
        raw = row[0]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict):
            opcoes = dict(raw)

    removidas = [k for k in CHAVES_SITUACAO_LEGADO if k in opcoes and opcoes[k] not in (None, "")]

    flag_json = json.dumps({FLAG_MIGRADO: True}, ensure_ascii=False)
    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET opcoes = COALESCE(opcoes, '{}'::jsonb)
              - 'bling_situacao_importar'
              - 'bling_situacao_criar'
              - 'bling_situacao_pago'
              - 'bling_situacao_expedido'
              - 'bling_situacao_entregue'
              - 'bling_situacao_cancelado'
              || %s::jsonb,
            atualizado_em = NOW()
        WHERE id_tenant = %s AND contexto = %s
        """,
        (flag_json, int(id_tenant), ctx),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO tbl_integracao_bling_config (
              id_tenant, contexto, fonte_principal, modo_imagem,
              produtos_modo, estoque_modo, pedidos_modo, opcoes, atualizado_em
            ) VALUES (
              %s, %s, 'bling', 'download',
              CASE WHEN %s = 'vendedor' THEN 'exportar' ELSE 'importar' END,
              CASE WHEN %s = 'vendedor' THEN 'exportar' ELSE 'importar' END,
              CASE WHEN %s = 'vendedor' THEN 'atualizar' ELSE 'exportar' END,
              %s::jsonb, NOW()
            )
            ON CONFLICT (id_tenant, contexto) DO UPDATE SET
              opcoes = COALESCE(tbl_integracao_bling_config.opcoes, '{}'::jsonb)
                - 'bling_situacao_importar'
                - 'bling_situacao_criar'
                - 'bling_situacao_pago'
                - 'bling_situacao_expedido'
                - 'bling_situacao_entregue'
                - 'bling_situacao_cancelado'
                || EXCLUDED.opcoes,
              atualizado_em = NOW()
            """,
            (int(id_tenant), ctx, ctx, ctx, ctx, flag_json),
        )

    _log.info(
        "Bling status migrado para padrão: tenant=%s ctx=%s removidas=%s",
        id_tenant,
        ctx,
        removidas,
    )
    return {
        "migrado": True,
        "contexto": ctx,
        "chaves_removidas": removidas,
        "linhas_padrao": listar_status_padrao(cur, aplicacao="bling", contexto=ctx),
    }
