# api/bling/config.py — configuração padrão, conta empresa e eco de estoque
from __future__ import annotations

# ── config_padrao ─────────────────────────────────────

from global_utils import agora_utc

DEFAULTS_CONEXAO = {
    "fornecedor": {
        "fonte_principal": "bling",
        "modo_imagem": "link",
        "produtos_modo": "importar",
        "estoque_modo": "atualizar",
        "pedidos_modo": "exportar",
    },
    "vendedor": {
        "fonte_principal": "bling",
        "modo_imagem": "link",
        "produtos_modo": "exportar",
        "estoque_modo": "exportar",
        "pedidos_modo": "atualizar",
    },
}


def aplicar_defaults_conexao(cur, id_tenant: int, contexto: str) -> None:
    """Aplica configuração padronizada do módulo ativo (fornecedor ou vendedor)."""
    ctx = contexto if contexto in DEFAULTS_CONEXAO else "fornecedor"
    cfg = DEFAULTS_CONEXAO[ctx]
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_config (
            id_tenant, contexto, fonte_principal, modo_imagem,
            produtos_modo, estoque_modo, pedidos_modo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, contexto) DO UPDATE SET
            fonte_principal = EXCLUDED.fonte_principal,
            modo_imagem = EXCLUDED.modo_imagem,
            produtos_modo = EXCLUDED.produtos_modo,
            estoque_modo = EXCLUDED.estoque_modo,
            pedidos_modo = EXCLUDED.pedidos_modo,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            ctx,
            cfg["fonte_principal"],
            cfg["modo_imagem"],
            cfg["produtos_modo"],
            cfg["estoque_modo"],
            cfg["pedidos_modo"],
            agora,
        ),
    )


def garantir_config_contexto(cur, id_tenant: int, contexto: str) -> None:
    """Cria linha de config do módulo ativo se ainda não existir (sem sobrescrever)."""
    ctx = contexto if contexto in DEFAULTS_CONEXAO else "fornecedor"
    cur.execute(
        "SELECT 1 FROM tbl_integracao_bling_config WHERE id_tenant = %s AND contexto = %s",
        (id_tenant, ctx),
    )
    if cur.fetchone():
        return
    cfg = DEFAULTS_CONEXAO[ctx]
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_config (
            id_tenant, contexto, fonte_principal, modo_imagem,
            produtos_modo, estoque_modo, pedidos_modo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_tenant,
            ctx,
            cfg["fonte_principal"],
            cfg["modo_imagem"],
            cfg["produtos_modo"],
            cfg["estoque_modo"],
            cfg["pedidos_modo"],
            agora,
        ),
    )


# ── eco_estoque ───────────────────────────────────────

from datetime import timedelta

from global_utils import agora_utc

ECO_TTL_SEGUNDOS = 180


def registrar_eco_pendente(
    cur,
    id_tenant: int,
    *,
    id_bling_produto: str,
    id_bling_deposito: str,
    quantidade_esperada: int | None,
    origem: str,
    ttl_segundos: int = ECO_TTL_SEGUNDOS,
) -> None:
    agora = agora_utc()
    expira = agora + timedelta(seconds=max(30, ttl_segundos))
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_eco_estoque (
            id_tenant, id_bling_produto, id_bling_deposito,
            quantidade_esperada, origem, criado_em, expira_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_tenant,
            str(id_bling_produto),
            str(id_bling_deposito),
            quantidade_esperada,
            origem,
            agora,
            expira,
        ),
    )


def limpar_ecos_expirados(cur) -> None:
    cur.execute(
        """
        DELETE FROM tbl_integracao_bling_eco_estoque
        WHERE expira_em < %s AND consumido_em IS NULL
        """,
        (agora_utc(),),
    )


def eco_deve_ignorar_webhook(
    cur,
    id_tenant: int,
    *,
    id_bling_produto: str,
    id_bling_deposito: str,
    quantidade: int | None,
) -> bool:
    """True se o webhook é eco de operação originada pelo DropNexo."""
    limpar_ecos_expirados(cur)
    cur.execute(
        """
        SELECT id, quantidade_esperada FROM tbl_integracao_bling_eco_estoque
        WHERE id_tenant = %s
          AND id_bling_produto = %s
          AND id_bling_deposito = %s
          AND consumido_em IS NULL
          AND expira_em >= %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (id_tenant, str(id_bling_produto), str(id_bling_deposito), agora_utc()),
    )
    row = cur.fetchone()
    if not row:
        return False
    eco_id, qtd_esperada = row[0], row[1]
    if qtd_esperada is not None and quantidade is not None and int(qtd_esperada) != int(quantidade):
        return False
    cur.execute(
        "UPDATE tbl_integracao_bling_eco_estoque SET consumido_em = %s WHERE id = %s",
        (agora_utc(), eco_id),
    )
    return True


# ── conta_empresa ─────────────────────────────────────

import json
import logging
from typing import Any

from api.bling.cliente import api_request
from global_utils import agora_utc

_log = logging.getLogger(__name__)


def normalizar_cnpj(valor: str | None) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def obter_dados_empresa_bling(id_tenant: int) -> dict[str, Any]:
    resp = api_request(id_tenant, "GET", "/empresas/me/dados-basicos")
    data = resp.get("data") or {}
    if not isinstance(data, dict):
        return {}
    return data


def salvar_conta_bling(cur, id_tenant: int, dados: dict[str, Any]) -> dict[str, Any]:
    company_id = str(dados.get("id") or "").strip()
    if not company_id:
        raise ValueError("Bling não retornou id da empresa.")

    cnpj = normalizar_cnpj(dados.get("cnpj"))
    info = {
        "company_id": company_id,
        "cnpj": cnpj,
        "nome": (dados.get("nome") or "").strip(),
        "email": (dados.get("email") or "").strip(),
        "obtido_em": agora_utc().isoformat(),
    }

    cur.execute("SELECT documento FROM tbl_tenant WHERE id = %s", (id_tenant,))
    row = cur.fetchone()
    doc_tenant = normalizar_cnpj(row[0] if row else "")
    if doc_tenant and cnpj and doc_tenant != cnpj:
        _log.warning(
            "CNPJ Bling (%s) difere do tenant %s (%s)",
            cnpj,
            id_tenant,
            doc_tenant,
        )
        info["cnpj_divergente"] = True

    cur.execute(
        """
        UPDATE tbl_integracao_bling
        SET bling_conta_info = %s::jsonb,
            bling_company_id = %s,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (json.dumps(info, ensure_ascii=False), company_id, agora_utc(), id_tenant),
    )
    return info


def conta_bling_preenchida(cur, id_tenant: int) -> bool:
    cur.execute(
        """
        SELECT bling_company_id, bling_conta_info
        FROM tbl_integracao_bling
        WHERE id_tenant = %s AND status = 'conectado'
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return False
    if row[0]:
        return True
    info = row[1] if isinstance(row[1], dict) else {}
    if isinstance(row[1], str):
        try:
            info = json.loads(row[1]) or {}
        except json.JSONDecodeError:
            info = {}
    return bool((info or {}).get("company_id"))


def garantir_conta_bling(cur, id_tenant: int, *, forcar: bool = False) -> dict[str, Any] | None:
    """Busca dados-basicos no Bling se ainda não houver company_id (backfill lazy)."""
    if not forcar and conta_bling_preenchida(cur, id_tenant):
        cur.execute(
            "SELECT bling_conta_info FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        info = row[0] if row else {}
        if isinstance(info, str):
            try:
                info = json.loads(info) or {}
            except json.JSONDecodeError:
                info = {}
        return info if isinstance(info, dict) else {}

    dados = obter_dados_empresa_bling(id_tenant)
    if not dados:
        return None
    return salvar_conta_bling(cur, id_tenant, dados)


def resolver_tenant_por_company(cur, company_id: str) -> int | None:
    cid = str(company_id or "").strip()
    if not cid:
        return None
    cur.execute(
        """
        SELECT id_tenant FROM tbl_integracao_bling
        WHERE status = 'conectado'
          AND (
            bling_company_id = %s
            OR bling_conta_info->>'company_id' = %s
          )
        LIMIT 1
        """,
        (cid, cid),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def backfill_contas_conectadas(cur, *, id_tenant: int | None = None) -> list[dict]:
    """Preenche bling_conta_info para tenants conectados sem company_id."""
    if id_tenant:
        cur.execute(
            """
            SELECT id_tenant FROM tbl_integracao_bling
            WHERE id_tenant = %s AND status = 'conectado'
            """,
            (id_tenant,),
        )
    else:
        cur.execute(
            """
            SELECT id_tenant FROM tbl_integracao_bling
            WHERE status = 'conectado'
              AND (
                bling_company_id IS NULL OR bling_company_id = ''
                OR bling_conta_info = '{}'::jsonb
                OR bling_conta_info->>'company_id' IS NULL
              )
            ORDER BY id_tenant
            """
        )
    resultados: list[dict] = []
    for (tid,) in cur.fetchall():
        try:
            info = garantir_conta_bling(cur, int(tid), forcar=True)
            resultados.append({"id_tenant": int(tid), "ok": True, "info": info})
        except Exception as e:
            resultados.append({"id_tenant": int(tid), "ok": False, "erro": str(e)})
    return resultados
