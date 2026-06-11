from pathlib import Path

from flask import Blueprint, render_template

from global_utils import Var_ConectarBanco, login_obrigatorio

_MOD_DIR = Path(__file__).resolve().parent

planos_bp = Blueprint(
    "planos",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/sistema/planos",
)


def init_app(app):
    app.register_blueprint(planos_bp)


def catalogo_planos():
    """Catálogo para home pública; usa tbl_plano se existir."""
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT slug, nome, valor_centavos, descricao
            FROM tbl_plano WHERE ativo = TRUE ORDER BY ordem, nome
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if rows:
            return [
                {
                    "slug": r[0],
                    "nome": r[1],
                    "preco_mensal": int(r[2] or 0) / 100,
                    "destaque": r[3] or "",
                    "recursos": [],
                }
                for r in rows
            ]
    except Exception:
        pass
    return [
        {
            "slug": "starter",
            "nome": "Starter",
            "preco_mensal": 0,
            "destaque": "Comece grátis",
            "recursos": [
                {"id": "catalogo", "label": "Publicar ou buscar catálogo", "ativo": True},
            ],
        },
        {
            "slug": "professional",
            "nome": "Profissional",
            "preco_mensal": 149,
            "destaque": "Operação em escala",
            "recursos": [
                {"id": "integracoes", "label": "Integrações", "ativo": True},
            ],
        },
        {
            "slug": "enterprise",
            "nome": "Enterprise",
            "preco_mensal": 499,
            "destaque": "Recursos avançados",
            "recursos": [],
        },
    ]


@planos_bp.get("/meu-plano")
@login_obrigatorio()
def meu_plano():
    return render_template(
        "em_breve.html",
        titulo_pagina="Meu Plano",
        descricao="Assinatura e limites da sua conta DropNexo.",
        nav_ativo="",
    )
