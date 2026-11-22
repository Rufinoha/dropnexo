# api/assistente/servico.py — auth, consultas e escritas (fase/contato)
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from sistema.planos.fornecedor_acompanhamento import (
    FASE_ROTULO,
    definir_fase,
    listar_contatos,
    registrar_contato,
    triagem_rotulo,
)
from sistema.planos.fornecedor_fundador import prazo_ativacao_fundador

RATE_LIMIT_POR_MIN = 60
_rate: dict[str, list[float]] = {}


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _hint(token: str) -> str:
    """Dica do token: primeiros 4 … últimos 4 caracteres."""
    t = token or ""
    if len(t) < 12:
        return "••••"
    return f"{t[:4]}…{t[-4:]}"


def _tem_coluna_tenant(cur, coluna: str) -> bool:
    from sistema.planos.fornecedor_acompanhamento import _tem_coluna_tenant as _f

    return _f(cur, coluna)


def _tentar(cur, fn, padrao, *, aviso: str | None = None, avisos: list[str] | None = None):
    """Executa fn() dentro de SAVEPOINT; em erro registra log/aviso e devolve `padrao`."""
    try:
        cur.execute("SAVEPOINT assist_sp")
    except Exception:
        if avisos is not None and aviso:
            avisos.append(aviso)
        return padrao
    try:
        out = fn()
        cur.execute("RELEASE SAVEPOINT assist_sp")
        return out
    except Exception:
        _log.exception("assistente bloco falhou: %s", aviso or "desconhecido")
        try:
            cur.execute("ROLLBACK TO SAVEPOINT assist_sp")
        except Exception:
            pass
        if avisos is not None and aviso:
            avisos.append(aviso)
        return padrao


def _parse_desde(valor: str) -> str:
    try:
        return datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00")).isoformat()
    except ValueError:
        raise ValueError("Parâmetro 'desde' inválido (use ISO 8601).") from None


def _reais(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def erro_generico(msg: str = "Não foi possível concluir a solicitação.") -> dict:
    return {"success": False, "message": msg}


_log = logging.getLogger(__name__)


def autenticar(conn, authorization: str | None) -> tuple[dict | None, str | None]:
    """Retorna (token_row, erro). token_row tem id, hint."""
    raw = (authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        return None, "Token ausente ou inválido."
    token = raw[7:].strip()
    if not token.startswith("dn_assist_") or len(token) < 20:
        return None, "Token ausente ou inválido."
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, token_hint, ativo, revogado_em
          FROM tbl_assistente_token
         WHERE token_hash = %s
         LIMIT 1
        """,
        (_hash_token(token),),
    )
    row = cur.fetchone()
    if not row or not row[2] or row[3]:
        return None, "Token ausente ou inválido."
    hint = row[1] or _hint(token)
    if not _rate_ok(hint):
        return None, "Limite de requisições excedido. Tente em instantes."
    return {"id": int(row[0]), "hint": hint}, None


def _rate_ok(hint: str) -> bool:
    agora = time.time()
    janela = int(agora // 60)
    chave = f"{hint}:{janela}"
    # limpa chaves antigas ocasionalmente
    if len(_rate) > 500:
        _rate.clear()
    bucket = _rate.setdefault(chave, [])
    bucket[:] = [t for t in bucket if agora - t < 60]
    if len(bucket) >= RATE_LIMIT_POR_MIN:
        return False
    bucket.append(agora)
    return True


def auditar(
    conn,
    *,
    rota: str,
    metodo: str,
    ip: str | None,
    token_hint: str | None,
    http_status: int,
    id_tenant_alvo: int | None = None,
) -> None:
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tbl_assistente_auditoria
              (rota, metodo, ip, token_hint, http_status, id_tenant_alvo)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (rota[:300], (metodo or "GET")[:12], (ip or "")[:80], (token_hint or "")[:40], http_status, id_tenant_alvo),
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def status_token(conn) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, token_hint, nome, ativo, criado_em, revogado_em
          FROM tbl_assistente_token
         ORDER BY criado_em DESC
         LIMIT 5
        """
    )
    itens = []
    for r in cur.fetchall():
        itens.append(
            {
                "id": int(r[0]),
                "token_hint": r[1],
                "nome": r[2],
                "ativo": bool(r[3]),
                "criado_em": r[4].isoformat() if r[4] else None,
                "revogado_em": r[5].isoformat() if r[5] else None,
            }
        )
    ativo = next((i for i in itens if i["ativo"]), None)
    return {"ativo": ativo, "itens": itens}


def gerar_token(conn, *, id_usuario: int | None, nome: str = "Assistente") -> tuple[dict, str]:
    token = "dn_assist_" + secrets.token_urlsafe(32)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_assistente_token
           SET ativo = FALSE, revogado_em = NOW(), revogado_por = %s
         WHERE ativo = TRUE
        """,
        (id_usuario,),
    )
    cur.execute(
        """
        INSERT INTO tbl_assistente_token (token_hash, token_hint, nome, criado_por)
        VALUES (%s, %s, %s, %s)
        RETURNING id, token_hint, nome, criado_em
        """,
        (_hash_token(token), _hint(token), (nome or "Assistente")[:80], id_usuario),
    )
    r = cur.fetchone()
    cfg = {
        "id": int(r[0]),
        "token_hint": r[1],
        "nome": r[2],
        "ativo": True,
        "criado_em": r[3].isoformat() if r[3] else None,
    }
    return cfg, token


def revogar_token(conn, *, id_usuario: int | None) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_assistente_token
           SET ativo = FALSE, revogado_em = NOW(), revogado_por = %s
         WHERE ativo = TRUE
        """,
        (id_usuario,),
    )
    return status_token(conn)


def _eh_fornecedor(cur, id_tenant: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_tenant
         WHERE id = %s AND tipo_negocio IN ('fornecedor', 'hibrido')
        """,
        (int(id_tenant),),
    )
    return bool(cur.fetchone())


def eh_indicado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT 1 FROM tbl_comissao_indicacao WHERE id_tenant_indicado = %s LIMIT 1",
        (int(id_tenant),),
    )
    return bool(cur.fetchone())


def _ultimo_acesso_dono(cur, id_tenant: int):
    cur.execute(
        """
        SELECT ut.ultimo_acesso_em
          FROM tbl_usuario_tenant ut
          JOIN tbl_perfil pf ON pf.id = ut.id_perfil
         WHERE ut.id_tenant = %s AND LOWER(COALESCE(pf.codigo, '')) = 'dono'
         ORDER BY ut.ativo DESC NULLS LAST, ut.ultimo_acesso_em DESC NULLS LAST
         LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return row[0].isoformat() if row and row[0] else None


def _contato_dono(cur, id_tenant: int) -> dict[str, str]:
    from sistema.planos.fornecedor_fundador import contato_whatsapp_dono

    cur.execute(
        """
        SELECT u.email
          FROM tbl_usuario_tenant ut
          JOIN tbl_usuario u ON u.id = ut.id_usuario
          JOIN tbl_perfil pf ON pf.id = ut.id_perfil
         WHERE ut.id_tenant = %s AND LOWER(COALESCE(pf.codigo, '')) = 'dono'
         ORDER BY ut.ativo DESC NULLS LAST, ut.id
         LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return {
        "email": (row[0] or "").strip() if row else "",
        "whatsapp": contato_whatsapp_dono(cur, id_tenant),
    }


def _resumo_numeros(cur, id_tenant: int) -> dict[str, Any]:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT
          (SELECT COUNT(*)::int FROM tbl_produto p WHERE p.id_tenant = %s AND COALESCE(p.publicado, FALSE) = TRUE),
          (SELECT COUNT(*)::int FROM tbl_produto p WHERE p.id_tenant = %s),
          (SELECT COUNT(*)::int FROM tbl_pedido ped
            WHERE ped.id_tenant_fornecedor = %s
              AND ped.criado_em >= NOW() - INTERVAL '30 days'
              AND COALESCE(ped.{st}, '') NOT IN ('rascunho', 'cancelado')),
          (SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor v
            WHERE v.id_tenant_fornecedor = %s AND v.status = 'ativo'),
          (SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor v
            WHERE v.id_tenant_fornecedor = %s AND v.status = 'aguardando')
        """.format(st=col_st),
        (tid, tid, tid, tid, tid),
    )
    r = cur.fetchone() or (0, 0, 0, 0, 0)
    atrasados = _contar_atrasados(cur, tid)
    return {
        "produtos_publicados": int(r[0] or 0),
        "produtos_total": int(r[1] or 0),
        "pedidos_30d": int(r[2] or 0),
        "pedidos_atrasados": atrasados,
        "vendedores_conectados": int(r[3] or 0),
        "vendedores_aguardando": int(r[4] or 0),
    }


def _contar_atrasados(cur, id_tenant: int) -> int:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    cur.execute(
        f"""
        SELECT COUNT(*)::int
          FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND {_sql_atrasado(col_st)}
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _sql_fase_cols(tem_fase: bool, tem_tri: bool) -> str:
    fase = "t.fornecedor_fase, t.fornecedor_fase_em" if tem_fase else "NULL::text, NULL::timestamptz"
    tri = "t.fornecedor_triagem" if tem_tri else "NULL::jsonb"
    return f"{fase}, {tri}"


def listar_fornecedores(
    cur,
    *,
    page: int = 1,
    per_page: int = 50,
    fundador: int | None = None,
    fase: str | None = None,
    indicado: int | None = None,
    desde: str | None = None,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 100))
    where = ["t.tipo_negocio IN ('fornecedor', 'hibrido')"]
    params: list[Any] = []
    if fundador == 1:
        where.append("COALESCE(t.eh_fornecedor_fundador, FALSE) = TRUE")
    elif fundador == 0:
        where.append("COALESCE(t.eh_fornecedor_fundador, FALSE) = FALSE")
    tem_fase = _tem_coluna_tenant(cur, "fornecedor_fase")
    tem_tri = _tem_coluna_tenant(cur, "fornecedor_triagem")
    if fase:
        if fase not in FASE_ROTULO:
            raise ValueError("Fase inválida.")
        if tem_fase:
            where.append("t.fornecedor_fase = %s")
            params.append(fase)
        else:
            where.append("FALSE")
    if indicado == 1:
        where.append("EXISTS (SELECT 1 FROM tbl_comissao_indicacao i WHERE i.id_tenant_indicado = t.id)")
    elif indicado == 0:
        where.append("NOT EXISTS (SELECT 1 FROM tbl_comissao_indicacao i WHERE i.id_tenant_indicado = t.id)")
    if desde:
        where.append("t.criado_em >= %s::timestamptz")
        params.append(_parse_desde(desde))
    wh = " AND ".join(where)
    cur.execute(f"SELECT COUNT(*)::int FROM tbl_tenant t WHERE {wh}", params)
    total = int((cur.fetchone() or (0,))[0] or 0)
    offset = (page - 1) * per_page
    fase_sql = _sql_fase_cols(tem_fase, tem_tri)
    cur.execute(
        f"""
        SELECT t.id, t.nome, t.documento, t.cidade, t.uf, t.criado_em, t.plano,
               COALESCE(t.eh_fornecedor_fundador, FALSE),
               COALESCE(t.fornecedor_fundador_ativo, FALSE),
               t.fornecedor_fundador_em, t.sistema_erp,
               {fase_sql}
          FROM tbl_tenant t
         WHERE {wh}
         ORDER BY t.criado_em DESC NULLS LAST, t.id DESC
         LIMIT %s OFFSET %s
        """,
        (*params, per_page, offset),
    )
    rows = cur.fetchall()
    itens = []
    for r in rows:
        tid = int(r[0])
        resumo = _resumo_numeros(cur, tid)
        prazo = prazo_ativacao_fundador(r[9], resumo["produtos_publicados"])
        uc = listar_contatos(cur, tid, limite=1)
        contato = None
        if uc:
            contato = {
                "data": uc[0].get("criado_em"),
                "canal": uc[0].get("canal"),
                "resumo": uc[0].get("resumo"),
            }
        dono = _contato_dono(cur, tid)
        tri = r[13] if isinstance(r[13], dict) else None
        itens.append(
            {
                "id": tid,
                "nome": r[1] or "",
                "documento": r[2] or "",
                "cidade": r[3] or "",
                "uf": r[4] or "",
                "criado_em": r[5].isoformat() if r[5] else None,
                "ultimo_acesso_em": _ultimo_acesso_dono(cur, tid),
                "plano": r[6] or "",
                "eh_fundador": bool(r[7]),
                "fundador_ativo": bool(r[8]),
                "fundador_em": r[9].isoformat() if r[9] else None,
                "prazo_ativacao": prazo.get("prazo_em"),
                "prazo_ativacao_cor": prazo.get("prazo_cor"),
                "sistema_erp": r[10] or "",
                "indicado": eh_indicado(cur, tid),
                "fase": r[11],
                "fase_em": r[12].isoformat() if r[12] else None,
                "fase_rotulo": FASE_ROTULO.get(r[11] or "", ""),
                "ultimo_contato": contato,
                "whatsapp": dono["whatsapp"],
                "email": dono["email"],
                "triagem": tri,
                "triagem_rotulo": triagem_rotulo(tri),
                "resumo": resumo,
            }
        )
    return {
        "itens": itens,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page) if total else 1,
    }


# Flags de incompletude calculadas no SQL (1 consulta, sem N+1).
_SQL_FLAGS_PRODUTO = """
    (COALESCE(p.preco, 0) <= 0 AND COALESCE(p.valor_drop, 0) <= 0) AS f_preco,
    (p.id_categoria IS NULL) AS f_categoria,
    (LENGTH(TRIM(COALESCE(p.descricao, ''))) < 10) AS f_descricao,
    (
      (COALESCE(p.peso_bruto_kg, 0) <= 0 AND COALESCE(p.peso_liquido_kg, 0) <= 0
        AND COALESCE(p.peso_gramas, 0) <= 0)
      OR COALESCE(p.altura_cm, 0) <= 0 OR COALESCE(p.largura_cm, 0) <= 0
      OR COALESCE(p.profundidade_cm, 0) <= 0
    ) AS f_peso_dim,
    (
      COALESCE(NULLIF(TRIM(p.imagem_url), ''), '') = ''
      AND NOT EXISTS (SELECT 1 FROM tbl_produto_imagem im WHERE im.id_produto = p.id)
    ) AS f_foto,
    (
      COALESCE((SELECT SUM(GREATEST(COALESCE(ve.quantidade, 0) - COALESCE(ve.reservado, 0), 0))
                  FROM tbl_produto_variante v
                  JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
                 WHERE v.id_produto = p.id), 0)
      + COALESCE((SELECT SUM(GREATEST(COALESCE(pe.quantidade, 0) - COALESCE(pe.reservado, 0), 0))
                    FROM tbl_produto_estoque pe WHERE pe.id_produto = p.id), 0)
    ) <= 0 AS f_estoque,
    (NOT EXISTS (SELECT 1 FROM tbl_produto_variante v WHERE v.id_produto = p.id)) AS f_variacao
"""

_MOTIVOS = (
    ("sem preço", 7),
    ("sem categoria", 8),
    ("sem descrição", 9),
    ("sem peso/dimensões", 10),
    ("sem foto", 11),
    ("sem estoque", 12),
    ("sem variação cadastrada", 13),
)
# Colunas: 0 id, 1 sku, 2 nome, 3 preco, 4 publicado, 5 atualizado_em, 6 estoque, 7.. flags


def _motivos_de_linha(r) -> list[str]:
    return [txt for txt, idx in _MOTIVOS if r[idx]]


_SQL_PRODUTO_SEL = (
    "SELECT p.id, p.sku, p.nome, p.preco, COALESCE(p.publicado, FALSE), p.atualizado_em,\n"
    "       (COALESCE((SELECT SUM(GREATEST(COALESCE(ve.quantidade, 0) - COALESCE(ve.reservado, 0), 0))\n"
    "                    FROM tbl_produto_variante v\n"
    "                    JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id\n"
    "                   WHERE v.id_produto = p.id), 0)\n"
    "        + COALESCE((SELECT SUM(GREATEST(COALESCE(pe.quantidade, 0) - COALESCE(pe.reservado, 0), 0))\n"
    "                      FROM tbl_produto_estoque pe WHERE pe.id_produto = p.id), 0)\n"
    "       )::numeric AS estoque,\n"
    + _SQL_FLAGS_PRODUTO
    + "\n  FROM tbl_produto p\n"
)

_ANY_FLAG = "(f_preco OR f_categoria OR f_descricao OR f_peso_dim OR f_foto OR f_estoque OR f_variacao)"


def _item_produto(r) -> dict[str, Any]:
    return {
        "id": int(r[0]),
        "sku": r[1] or "",
        "nome": r[2] or "",
        "preco": float(r[3] or 0),
        "estoque": float(r[6] or 0),
        "publicado": bool(r[4]),
        "motivos": _motivos_de_linha(r),
        "atualizado_em": r[5].isoformat() if r[5] else None,
    }


def _fixar_produtos_incompletos(cur, id_tenant: int) -> dict[str, Any]:
    tid = int(id_tenant)
    cur.execute(
        "SELECT * FROM (" + _SQL_PRODUTO_SEL + " WHERE p.id_tenant = %s) x ORDER BY x.id DESC",
        (tid,),
    )
    contagem: dict[str, int] = {}
    incompletos: list[dict[str, Any]] = []
    total = pub = inc_total = 0
    for r in cur.fetchall():
        total += 1
        if r[4]:
            pub += 1
        motivos = _motivos_de_linha(r)
        if not motivos:
            continue
        inc_total += 1
        for m in motivos:
            contagem[m] = contagem.get(m, 0) + 1
        if len(incompletos) < 50:
            incompletos.append({"id": int(r[0]), "sku": r[1] or "", "nome": r[2] or "", "motivos": motivos})
    return {
        "total": total,
        "publicados": pub,
        "inativos": total - pub,
        "incompletos": incompletos,
        "incompletos_total": inc_total,
        "contagem_motivos": contagem,
    }


def detalhe_fornecedor(cur, id_tenant: int) -> dict[str, Any] | None:
    if not _eh_fornecedor(cur, id_tenant):
        return None
    tid = int(id_tenant)
    fase_sql = _sql_fase_cols(
        _tem_coluna_tenant(cur, "fornecedor_fase"), _tem_coluna_tenant(cur, "fornecedor_triagem")
    )
    cur.execute(
        f"""
        SELECT t.id, t.nome, t.documento, t.cidade, t.uf, t.criado_em, t.plano,
               COALESCE(t.eh_fornecedor_fundador, FALSE),
               COALESCE(t.fornecedor_fundador_ativo, FALSE),
               t.fornecedor_fundador_em, t.sistema_erp,
               {fase_sql},
               t.ativo
          FROM tbl_tenant t WHERE t.id = %s
        """,
        (tid,),
    )
    r = cur.fetchone()
    if not r:
        return None
    resumo = _resumo_numeros(cur, tid)
    prazo = prazo_ativacao_fundador(r[9], resumo["produtos_publicados"])
    dono = _contato_dono(cur, tid)
    tri = r[13] if isinstance(r[13], dict) else None
    cur.execute(
        """
        SELECT u.nome, pf.codigo, pf.nome, ut.ultimo_acesso_em, COALESCE(u.ativo, TRUE), COALESCE(ut.ativo, TRUE)
          FROM tbl_usuario_tenant ut
          JOIN tbl_usuario u ON u.id = ut.id_usuario
          JOIN tbl_perfil pf ON pf.id = ut.id_perfil
         WHERE ut.id_tenant = %s
         ORDER BY ut.id
        """,
        (tid,),
    )
    usuarios = []
    for u in cur.fetchall():
        usuarios.append(
            {
                "nome": u[0] or "",
                "perfil": u[1] or "",
                "perfil_nome": u[2] or "",
                "ultimo_acesso_em": u[3].isoformat() if u[3] else None,
                "ativo": bool(u[4] and u[5]),
            }
        )
    avisos: list[str] = []
    produtos = _tentar(
        cur,
        lambda: _fixar_produtos_incompletos(cur, tid),
        {
            "total": 0,
            "publicados": 0,
            "inativos": 0,
            "incompletos": [],
            "incompletos_total": 0,
            "contagem_motivos": {},
        },
        aviso="produtos indisponível",
        avisos=avisos,
    )
    pedidos = _tentar(
        cur,
        lambda: _bloco_pedidos(cur, tid),
        {
            "por_status_30d": {},
            "por_status_90d": {},
            "atrasados": [],
            "cancelados_30d": 0,
            "devolvidos_30d": 0,
        },
        aviso="pedidos indisponível",
        avisos=avisos,
    )
    desempenho = _tentar(
        cur,
        lambda: _bloco_desempenho(cur, tid),
        {
            "30d": {"pedidos": 0, "faturamento": 0.0, "ticket_medio": 0.0},
            "90d": {"pedidos": 0, "faturamento": 0.0, "ticket_medio": 0.0},
            "taxa_cancelamento_30d": None,
            "tempo_medio_pago_expedido_horas": None,
            "ultimo_pedido_em": None,
            "top_produtos_30d": [],
        },
        aviso="desempenho indisponível",
        avisos=avisos,
    )
    if isinstance(desempenho, dict) and desempenho.get("avisos"):
        avisos.extend(desempenho.pop("avisos") or [])
    rede = _tentar(
        cur,
        lambda: _bloco_rede(cur, tid),
        {
            "vendedores_conectados": 0,
            "vendedores_aguardando": 0,
            "aguardando_mais_antigo_dias": None,
            "vendedores_com_pedido_30d": 0,
        },
        aviso="rede indisponível",
        avisos=avisos,
    )
    integracoes = _tentar(
        cur,
        lambda: _bloco_integracoes(cur, tid, avisos=avisos),
        [],
        aviso="integracoes indisponível",
        avisos=avisos,
    )
    contatos = listar_contatos(cur, tid, limite=200)
    return {
        "avisos": avisos,
        "cadastro": {
            "id": tid,
            "nome": r[1] or "",
            "documento": r[2] or "",
            "cidade": r[3] or "",
            "uf": r[4] or "",
            "criado_em": r[5].isoformat() if r[5] else None,
            "ultimo_acesso_em": _ultimo_acesso_dono(cur, tid),
            "plano": r[6] or "",
            "ativo": bool(r[14]),
            "eh_fundador": bool(r[7]),
            "fundador_ativo": bool(r[8]),
            "fundador_em": r[9].isoformat() if r[9] else None,
            "prazo_ativacao": prazo,
            "sistema_erp": r[10] or "",
            "indicado": eh_indicado(cur, tid),
            "fase": r[11],
            "fase_em": r[12].isoformat() if r[12] else None,
            "whatsapp": dono["whatsapp"],
            "email": dono["email"],
            "triagem": tri,
            "triagem_rotulo": triagem_rotulo(tri),
            "usuarios": usuarios,
        },
        "produtos": produtos,
        "pedidos": pedidos,
        "desempenho": desempenho,
        "rede": rede,
        "integracoes": integracoes,
        "acompanhamento": {
            "fase": r[11],
            "fase_rotulo": FASE_ROTULO.get(r[11] or "", ""),
            "prazo": prazo,
            "contatos": contatos,
        },
        "resumo": resumo,
    }


_ATRASO_HORAS = 48


def _sql_atrasado(col_st: str) -> str:
    """Atrasado = pago ou em_expedicao há mais de 48h (início: pago_em, senão criado_em).
    Não inclui aguardando_confirmacao (PIX ainda não confirmado)."""
    return (
        f"(COALESCE(ped.{col_st}, '') IN ('pago', 'em_expedicao') "
        f" AND COALESCE(ped.pago_em, ped.criado_em) < NOW() - INTERVAL '{_ATRASO_HORAS} hours')"
    )


def _horas_atraso(ref) -> int:
    if not ref:
        return 0
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    horas = int((datetime.now(timezone.utc) - ref).total_seconds() // 3600)
    return max(0, horas - _ATRASO_HORAS)


def _item_pedido(r) -> dict[str, Any]:
    """Sem dados do comprador final nem do vendedor (só cidade/UF de entrega)."""
    return {
        "id": int(r[0]),
        "numero": r[1] or "",
        "criado_em": r[2].isoformat() if r[2] else None,
        "status": r[3] or "",
        "status_pagamento": r[4] or "",
        "valor_total": _reais(r[5]),
        "pago_em": r[6].isoformat() if r[6] else None,
        "expedido_em": r[7].isoformat() if r[7] else None,
        "entregue_em": r[8].isoformat() if r[8] else None,
        "cidade": (r[9] or "").strip(),
        "uf": (r[10] or "").strip(),
        "atrasado": bool(r[11]),
        "horas_em_atraso": _horas_atraso(r[12]) if r[11] else 0,
    }


_SQL_PEDIDO_SEL = """
    SELECT ped.id, ped.numero, ped.criado_em, COALESCE(ped.{col_st}, ''), ped.status_pagamento,
           ped.valor_total, ped.pago_em, ped.expedido_em, ped.entregue_em,
           COALESCE(ped.entrega_cidade, ''), COALESCE(ped.entrega_uf, ''),
           {atrasado} AS atrasado,
           COALESCE(ped.pago_em, ped.criado_em) AS ref_em
      FROM tbl_pedido ped
"""


def _bloco_pedidos(cur, id_tenant: int) -> dict[str, Any]:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    tid = int(id_tenant)

    def _por_status(dias: int) -> dict[str, int]:
        cur.execute(
            f"""
            SELECT COALESCE(NULLIF(ped.{col_st}, ''), 'sem_status'), COUNT(*)::int
              FROM tbl_pedido ped
             WHERE ped.id_tenant_fornecedor = %s
               AND ped.criado_em >= NOW() - (%s || ' days')::interval
             GROUP BY 1
            """,
            (tid, str(dias)),
        )
        return {str(a): int(b or 0) for a, b in cur.fetchall()}

    cur.execute(
        _SQL_PEDIDO_SEL.format(col_st=col_st, atrasado=_sql_atrasado(col_st))
        + """
     WHERE ped.id_tenant_fornecedor = %s
       AND """
        + _sql_atrasado(col_st)
        + """
     ORDER BY ped.criado_em ASC
     LIMIT 50
        """,
        (tid,),
    )
    atrasados = [_item_pedido(r) for r in cur.fetchall()]
    cur.execute(
        f"""
        SELECT COUNT(*)::int FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND ped.criado_em >= NOW() - INTERVAL '30 days'
           AND COALESCE(ped.{col_st}, '') = 'cancelado'
        """,
        (tid,),
    )
    canc = int((cur.fetchone() or (0,))[0] or 0)
    return {
        "por_status_30d": _por_status(30),
        "por_status_90d": _por_status(90),
        "atrasados": atrasados,
        "cancelados_30d": canc,
        "devolvidos_30d": 0,
    }


def _bloco_desempenho(cur, id_tenant: int) -> dict[str, Any]:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    tid = int(id_tenant)

    def _agg(dias: int) -> dict[str, Any]:
        cur.execute(
            f"""
            SELECT COUNT(*)::int, COALESCE(SUM(COALESCE(ped.valor_total, 0)), 0)
              FROM tbl_pedido ped
             WHERE ped.id_tenant_fornecedor = %s
               AND ped.criado_em >= NOW() - (%s || ' days')::interval
               AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
            """,
            (tid, str(dias)),
        )
        n, fat = cur.fetchone() or (0, 0)
        n = int(n or 0)
        fat_r = _reais(fat)
        return {
            "pedidos": n,
            "faturamento": fat_r,
            "ticket_medio": round(fat_r / n, 2) if n else 0.0,
        }

    a30 = _agg(30)
    a90 = _agg(90)
    cur.execute(
        f"""
        SELECT COUNT(*) FILTER (WHERE COALESCE(ped.{col_st}, '') = 'cancelado')::int,
               COUNT(*) FILTER (WHERE COALESCE(ped.{col_st}, '') <> 'rascunho')::int
          FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND ped.criado_em >= NOW() - INTERVAL '30 days'
        """,
        (tid,),
    )
    c, t = cur.fetchone() or (0, 0)
    taxa = round(100.0 * (c or 0) / t, 1) if t else None
    cur.execute(
        """
        SELECT AVG(EXTRACT(EPOCH FROM (ped.expedido_em - ped.pago_em)) / 3600.0)
          FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND ped.pago_em IS NOT NULL AND ped.expedido_em IS NOT NULL
           AND ped.expedido_em >= ped.pago_em
           AND ped.criado_em >= NOW() - INTERVAL '90 days'
        """,
        (tid,),
    )
    tm = (cur.fetchone() or (None,))[0]
    avisos_local: list[str] = []
    if tm is None:
        avisos_local.append("tempo_medio_pago_expedido indisponível (sem pares pago_em/expedido_em)")
    cur.execute(
        f"""
        SELECT MAX(ped.criado_em) FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
        """,
        (tid,),
    )
    ult = cur.fetchone()
    top = _tentar(
        cur,
        lambda: _top_produtos_30d(cur, tid, col_st),
        [],
        aviso="top_produtos_30d indisponível",
        avisos=avisos_local,
    )
    out = {
        "30d": a30,
        "90d": a90,
        "taxa_cancelamento_30d": taxa,
        "tempo_medio_pago_expedido_horas": round(float(tm), 1) if tm is not None else None,
        "ultimo_pedido_em": ult[0].isoformat() if ult and ult[0] else None,
        "top_produtos_30d": top,
    }
    if avisos_local:
        out["avisos"] = avisos_local
    return out


def _top_produtos_30d(cur, tid: int, col_st: str) -> list[dict[str, Any]]:
    cur.execute(
        f"""
        SELECT COALESCE(it.id_produto, 0), COALESCE(it.nome_produto, ''), SUM(it.quantidade)::int
          FROM tbl_pedido_item it
          JOIN tbl_pedido ped ON ped.id = it.id_pedido
         WHERE ped.id_tenant_fornecedor = %s
           AND ped.criado_em >= NOW() - INTERVAL '30 days'
           AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
         GROUP BY 1, 2
         ORDER BY 3 DESC
         LIMIT 5
        """,
        (tid,),
    )
    return [
        {"id": int(a) or None, "nome": b, "quantidade": int(c or 0)}
        for a, b, c in cur.fetchall()
    ]


def _bloco_rede(cur, id_tenant: int) -> dict[str, Any]:
    """Somente contagens — nunca identifica vendedores."""
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'ativo')::int,
          COUNT(*) FILTER (WHERE status = 'aguardando')::int,
          MIN(solicitado_em) FILTER (WHERE status = 'aguardando')
          FROM tbl_vinculo_vendedor_fornecedor
         WHERE id_tenant_fornecedor = %s
        """,
        (tid,),
    )
    row = cur.fetchone() or (0, 0, None)
    dias_espera = None
    if row[2]:
        cri = row[2]
        if cri.tzinfo is None:
            cri = cri.replace(tzinfo=timezone.utc)
        dias_espera = max(0, int((datetime.now(timezone.utc) - cri).total_seconds() // 86400))
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    cur.execute(
        f"""
        SELECT COUNT(DISTINCT ped.id_tenant_vendedor)::int
          FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND ped.id_tenant_vendedor IS NOT NULL
           AND ped.criado_em >= NOW() - INTERVAL '30 days'
           AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
        """,
        (tid,),
    )
    com_ped = int((cur.fetchone() or (0,))[0] or 0)
    return {
        "vendedores_conectados": int(row[0] or 0),
        "vendedores_aguardando": int(row[1] or 0),
        "aguardando_mais_antigo_dias": dias_espera,
        "vendedores_com_pedido_30d": com_ped,
    }


def _bloco_integracoes(
    cur, id_tenant: int, *, avisos: list[str] | None = None
) -> list[dict[str, Any]]:
    """Bling e Tiny/Olist com colunas reais (status/conectado + sync do config)."""
    out: list[dict[str, Any]] = []
    tid = int(id_tenant)
    fila = _tentar(
        cur,
        lambda: _fila_imagens_pendentes(cur, tid),
        0,
        aviso="fila de imagens indisponível",
        avisos=avisos,
    )

    def _bling():
        cur.execute(
            """
            SELECT b.status, b.conectado_em, b.ultimo_erro,
                   GREATEST(c.ultima_sync_produtos, c.ultima_sync_estoque, c.ultima_sync_pedidos)
              FROM tbl_integracao_bling b
              LEFT JOIN tbl_integracao_bling_config c
                ON c.id_tenant = b.id_tenant
             WHERE b.id_tenant = %s
             ORDER BY c.contexto NULLS LAST
             LIMIT 1
            """,
            (tid,),
        )
        return cur.fetchone()

    row_b = _tentar(cur, _bling, None, aviso="integracao Bling indisponível", avisos=avisos)
    if row_b:
        sync = row_b[3] or row_b[1]
        out.append(
            {
                "nome": "Bling",
                "ligado": (row_b[0] or "").lower() == "conectado",
                "status": row_b[0] or "",
                "ultima_sincronizacao": sync.isoformat() if sync else None,
                "ultimo_erro": (row_b[2] or "")[:200],
                "fila_imagens_pendentes": fila,
            }
        )

    def _olist():
        cur.execute(
            """
            SELECT o.status, o.conectado_em, o.ultimo_erro,
                   GREATEST(c.ultima_sync_produtos, c.ultima_sync_estoque, c.ultima_sync_pedidos)
              FROM tbl_integracao_olist o
              LEFT JOIN tbl_integracao_olist_config c
                ON c.id_tenant = o.id_tenant AND c.contexto = 'fornecedor'
             WHERE o.id_tenant = %s
             LIMIT 1
            """,
            (tid,),
        )
        return cur.fetchone()

    row_o = _tentar(cur, _olist, None, aviso="integracao Tiny/Olist indisponível", avisos=avisos)
    if row_o:
        sync = row_o[3] or row_o[1]
        out.append(
            {
                "nome": "Tiny/Olist",
                "ligado": (row_o[0] or "").lower() == "conectado",
                "status": row_o[0] or "",
                "ultima_sincronizacao": sync.isoformat() if sync else None,
                "ultimo_erro": (row_o[2] or "")[:200],
                "fila_imagens_pendentes": 0,
            }
        )
    return out


def _fila_imagens_pendentes(cur, tid: int) -> int:
    cur.execute(
        "SELECT COUNT(*)::int FROM tbl_produto_imagem_download_fila "
        "WHERE id_tenant = %s AND status IN ('pendente', 'processando')",
        (tid,),
    )
    return int((cur.fetchone() or (0,))[0] or 0)


def listar_produtos_pagina(
    cur, id_tenant: int, *, status: str | None = None, page: int = 1, per_page: int = 50
) -> dict[str, Any]:
    if not _eh_fornecedor(cur, id_tenant):
        raise LookupError("Fornecedor não encontrado.")
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 100))
    st = (status or "").strip().lower()
    if st not in ("", "publicado", "inativo", "incompleto"):
        raise ValueError("Status inválido.")
    filtro = ""
    if st == "publicado":
        filtro = "WHERE x.publicado = TRUE"
    elif st == "inativo":
        filtro = "WHERE x.publicado = FALSE"
    elif st == "incompleto":
        filtro = "WHERE " + _ANY_FLAG.replace("f_", "x.f_")
    base = "(" + _SQL_PRODUTO_SEL + " WHERE p.id_tenant = %s) x"
    cur.execute(f"SELECT COUNT(*)::int FROM {base} {filtro}", (int(id_tenant),))
    total = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute(
        f"SELECT x.* FROM {base} {filtro} ORDER BY x.id DESC LIMIT %s OFFSET %s",
        (int(id_tenant), per_page, (page - 1) * per_page),
    )
    itens = [_item_produto(r) for r in cur.fetchall()]
    return {"itens": itens, "page": page, "per_page": per_page, "total": total}


def listar_pedidos_pagina(
    cur,
    id_tenant: int,
    *,
    status: str | None = None,
    atrasados: int = 0,
    desde: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    if not _eh_fornecedor(cur, id_tenant):
        raise LookupError("Fornecedor não encontrado.")
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 100))
    where = ["ped.id_tenant_fornecedor = %s"]
    params: list[Any] = [int(id_tenant)]
    if status:
        where.append(f"COALESCE(ped.{col_st}, '') = %s")
        params.append(status.strip().lower())
    if atrasados:
        where.append(_sql_atrasado(col_st))
    if desde:
        where.append("ped.criado_em >= %s::timestamptz")
        params.append(_parse_desde(desde))
    wh = " AND ".join(where)
    cur.execute(f"SELECT COUNT(*)::int FROM tbl_pedido ped WHERE {wh}", params)
    total = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute(
        _SQL_PEDIDO_SEL.format(col_st=col_st, atrasado=_sql_atrasado(col_st))
        + f" WHERE {wh} ORDER BY ped.criado_em DESC LIMIT %s OFFSET %s",
        (*params, per_page, (page - 1) * per_page),
    )
    itens = [_item_pedido(r) for r in cur.fetchall()]
    return {"itens": itens, "page": page, "per_page": per_page, "total": total}


def painel_resumo(cur) -> dict[str, Any]:
    from core.pedidos.servico import col_status_vendedor
    from sistema.planos.fornecedor_fundador import (
        VAGAS_DIVULGADAS,
        contar_fundadores_ativos,
    )

    col_st = col_status_vendedor(cur)
    col_fase = (
        "COALESCE(fornecedor_fase, 'sem_fase')"
        if _tem_coluna_tenant(cur, "fornecedor_fase")
        else "'sem_fase'"
    )
    cur.execute(
        f"""
        SELECT {col_fase}, COUNT(*)::int
          FROM tbl_tenant
         WHERE tipo_negocio IN ('fornecedor', 'hibrido')
         GROUP BY 1
        """
    )
    por_fase = {str(a): int(b or 0) for a, b in cur.fetchall()}
    usados = contar_fundadores_ativos(cur)
    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_tenant t
         WHERE t.tipo_negocio IN ('fornecedor', 'hibrido')
           AND COALESCE(t.eh_fornecedor_fundador, FALSE) = TRUE
           AND COALESCE(t.fornecedor_fundador_ativo, FALSE) = TRUE
           AND (SELECT COUNT(*) FROM tbl_produto p
                 WHERE p.id_tenant = t.id AND COALESCE(p.publicado, FALSE) = TRUE) < 20
        """
    )
    cat_baixo = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute(
        """
        SELECT COUNT(DISTINCT v.id_tenant_fornecedor)::int
          FROM tbl_vinculo_vendedor_fornecedor v
          JOIN tbl_tenant t ON t.id = v.id_tenant_fornecedor
         WHERE v.status = 'aguardando'
           AND t.tipo_negocio IN ('fornecedor', 'hibrido')
        """
    )
    aguard = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute(
        f"""
        SELECT COUNT(*)::int
          FROM tbl_pedido ped
          JOIN tbl_tenant t ON t.id = ped.id_tenant_fornecedor
         WHERE t.tipo_negocio IN ('fornecedor', 'hibrido')
           AND {_sql_atrasado(col_st)}
        """
    )
    atras = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute(
        f"""
        SELECT t.id, t.nome, COUNT(*)::int AS qtd
          FROM tbl_pedido ped
          JOIN tbl_tenant t ON t.id = ped.id_tenant_fornecedor
         WHERE t.tipo_negocio IN ('fornecedor', 'hibrido')
           AND {_sql_atrasado(col_st)}
         GROUP BY t.id, t.nome
         ORDER BY qtd DESC, t.nome
         LIMIT 50
        """
    )
    com_atraso = [
        {"id": int(a), "nome": b or "", "atrasados": int(c or 0)}
        for a, b, c in cur.fetchall()
    ]
    return {
        "por_fase": por_fase,
        "fundadores": {
            "ativos": usados,
            "vagas_max": VAGAS_DIVULGADAS,
            "vagas_restantes": max(0, VAGAS_DIVULGADAS - usados),
        },
        "fornecedores_catalogo_lt_20": cat_baixo,
        "fornecedores_com_vendedores_aguardando": aguard,
        "pedidos_atrasados_total": atras,
        "fornecedores_com_atraso": com_atraso,
    }


def post_contato(cur, id_tenant: int, body: dict, *, aprovado_por: str | None = None) -> dict:
    if not _eh_fornecedor(cur, id_tenant):
        raise LookupError("Fornecedor não encontrado.")
    if eh_indicado(cur, id_tenant):
        raise PermissionError("Fornecedor indicado por parceiro: contato não permitido pelo assistente")
    autor = "Assistente"
    if aprovado_por:
        autor = f"Assistente (aprovado por {str(aprovado_por).strip()[:80]})"
    return registrar_contato(
        cur,
        int(id_tenant),
        canal=body.get("canal") or "whatsapp",
        direcao=body.get("direcao") or "enviado",
        resumo=body.get("resumo") or "",
        fase_apos=body.get("fase_apos"),
        autor=autor,
        aplicar_fase=True,
    )


def post_fase(cur, id_tenant: int, body: dict, *, aprovado_por: str | None = None) -> dict:
    if not _eh_fornecedor(cur, id_tenant):
        raise LookupError("Fornecedor não encontrado.")
    if eh_indicado(cur, id_tenant):
        raise PermissionError("Fornecedor indicado por parceiro: contato não permitido pelo assistente")
    autor = "Assistente"
    if aprovado_por:
        autor = f"Assistente (aprovado por {str(aprovado_por).strip()[:80]})"
    return definir_fase(
        cur,
        int(id_tenant),
        body.get("fase"),
        autor=autor,
        motivo=(body.get("motivo") or "").strip() or None,
        registrar_historico=True,
    )
