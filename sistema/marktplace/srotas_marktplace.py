# sistema/marktplace/srotas_marktplace.py — catálogo Marktplace e rotas HTTP
from __future__ import annotations

# ── servico_marktplace ────────────────────────────────

"""Catálogo Marktplace — listagem e regras de visibilidade."""

import json
from typing import Any


def produto_dict(row) -> dict[str, Any]:
    meta = row[10]
    if isinstance(meta, str):
        try:
            meta = json.loads(meta) if meta else {}
        except json.JSONDecodeError:
            meta = {}
    elif meta is None:
        meta = {}
    return {
        "id": row[0],
        "slug": row[1] or "",
        "titulo": row[2] or "",
        "resumo": row[3] or "",
        "descricao": row[4] or "",
        "valor_centavos": int(row[5] or 0),
        "tipo_pagamento": row[6] or "unico",
        "publico": row[7] or "ambos",
        "categoria": row[8] or "geral",
        "tipo_acao": row[9] or "",
        "meta": meta,
        "icone": row[11] or "shopping-bag",
        "cor_topo": row[12] or "#5b57f5",
        "ordem": int(row[13] or 0),
        "ativo": bool(row[14]),
    }


SQL_LISTA = """
    SELECT id, slug, titulo, resumo, descricao, valor_centavos, tipo_pagamento,
           publico, categoria, tipo_acao, meta, icone, cor_topo, ordem, ativo
    FROM tbl_marktplace_produto
    ORDER BY ordem, titulo
"""

SQL_LISTA_ATIVOS = SQL_LISTA.replace(
    "FROM tbl_marktplace_produto",
    "FROM tbl_marktplace_produto\n    WHERE ativo = TRUE",
)


def _publico_ok(publico: str, tipo_negocio: str) -> bool:
    p = (publico or "ambos").lower()
    t = (tipo_negocio or "vendedor").lower()
    if p == "ambos":
        return True
    if t == "hibrido":
        return True
    return p == t


def _acao_visivel(tipo_acao: str, tipo_negocio: str, plano: str, meta: dict) -> bool:
    acao = (tipo_acao or "").lower()
    t = (tipo_negocio or "vendedor").lower()
    if acao == "modulo_vendedor" and t in ("vendedor", "hibrido"):
        return False
    if acao == "modulo_fornecedor" and t in ("fornecedor", "hibrido"):
        return False
    apenas_plano = (meta or {}).get("apenas_plano")
    if apenas_plano and (plano or "").lower() != str(apenas_plano).lower():
        return False
    return True


def filtrar_para_tenant(produtos: list[dict], *, tipo_negocio: str, plano: str) -> list[dict]:
    out = []
    for p in produtos:
        if not p.get("ativo", True):
            continue
        if not _publico_ok(p.get("publico", "ambos"), tipo_negocio):
            continue
        if not _acao_visivel(p.get("tipo_acao", ""), tipo_negocio, plano, p.get("meta") or {}):
            continue
        out.append(p)
    return out


def formatar_preco(valor_centavos: int, tipo_pagamento: str) -> str:
    v = (valor_centavos or 0) / 100.0
    txt = f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if (tipo_pagamento or "unico") == "mensal":
        return f"Por {txt}/mês"
    return f"Por {txt}"


# ── srotas_marktplace ─────────────────────────────────

"""Marktplace — vitrine de add-ons e treinamentos."""

from pathlib import Path

from flask import Blueprint, jsonify, render_template, session

from global_utils import Var_ConectarBanco, login_obrigatorio

_MOD_DIR = Path(__file__).resolve().parent

marktplace_bp = Blueprint(
    "marktplace",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/marktplace",
)


def init_app(app):
    app.register_blueprint(marktplace_bp)


@marktplace_bp.get("/marktplace")
@login_obrigatorio()
def pagina():
    return render_template("frm_marktplace.html", nav_ativo="marktplace")


@marktplace_bp.get("/marktplace/catalogo")
@login_obrigatorio()
def catalogo():
    tipo = session.get("tenant_tipo_negocio", "vendedor")
    plano = session.get("tenant_plano", "starter")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(SQL_LISTA_ATIVOS)
        rows = [produto_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    lista = filtrar_para_tenant(rows, tipo_negocio=tipo, plano=plano)
    for p in lista:
        p["preco_label"] = formatar_preco(p["valor_centavos"], p["tipo_pagamento"])
    return jsonify(
        success=True,
        produtos=lista,
        tipo_negocio=tipo,
        plano=plano,
    )
