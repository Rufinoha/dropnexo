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


def catalogo_planos_home():
    """Catálogo público da home — blocos vendedor e fornecedor (preview comercial)."""
    _check = (
        '<svg class="home-plan__check-svg" viewBox="0 0 16 16" fill="none" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M3 8l3.5 3.5L13 5"/></svg>'
    )
    _x = (
        '<svg class="home-plan__check-svg" viewBox="0 0 16 16" fill="none" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M4 4l8 8M12 4l-8 8"/></svg>'
    )

    def rec(label: str, on: bool, sub: str = "") -> dict:
        return {"label": label, "on": on, "sub": sub, "icon": _check if on else _x}

    def plano(
        slug: str,
        nome: str,
        preco: int | float,
        limites: list[tuple[str, str]],
        recursos: list[dict],
        *,
        destaque: str = "",
        featured: bool = False,
        tag: str = "",
        cta_gratis: bool = False,
    ) -> dict:
        return {
            "slug": slug,
            "nome": nome,
            "preco_mensal": preco,
            "destaque": destaque,
            "featured": featured,
            "tag": tag,
            "limites": [{"valor": v, "rotulo": r} for v, r in limites],
            "recursos": recursos,
            "cta_gratis": cta_gratis,
        }

    integ_off = rec("Integrações (Bling, ERP, marketplaces)", False)
    integ_on = rec("Integrações (Bling, ERP, marketplaces)", True)
    import_off = rec("Importação em massa (CSV / XLSX)", False)
    import_on = rec("Importação em massa (CSV / XLSX)", True)
    sync_off = rec("Sync automático agendado", False)
    sync_on = rec("Sync automático agendado", True)

    vendedor = [
        plano(
            "explorar",
            "Explorar",
            0,
            [("25", "pedidos/mês"), ("3", "fornecedores"), ("50", "produtos")],
            [
                rec("Rede B2B e catálogo manual", True),
                rec("Pedidos na plataforma", True),
                integ_off,
                import_off,
            ],
            destaque="Conheça a rede sem custo fixo",
            cta_gratis=True,
        ),
        plano(
            "crescer",
            "Crescer",
            79,
            [("150", "pedidos/mês"), ("10", "fornecedores"), ("500", "produtos")],
            [
                rec("Tudo do Explorar", True),
                integ_on,
                import_on,
                rec("Até 3 usuários na equipe", True),
            ],
            destaque="Primeira automação com ERP e lojas",
            featured=True,
            tag="Mais escolhido",
        ),
        plano(
            "escalar",
            "Escalar",
            179,
            [("600", "pedidos/mês"), ("30", "fornecedores"), ("2.000", "produtos")],
            [
                rec("Tudo do Crescer", True),
                sync_on,
                rec("Precificação em lote", True),
                rec("Até 8 usuários", True),
            ],
            destaque="Operação estável com sync recorrente",
        ),
        plano(
            "pro",
            "Pro",
            349,
            [("2.000", "pedidos/mês"), ("80", "fornecedores"), ("10.000", "produtos")],
            [
                rec("Tudo do Escalar", True),
                rec("API e webhooks", True),
                rec("Relatórios e exportações", True),
                rec("Usuários ampliados", True),
            ],
            destaque="Alto volume e integrações avançadas",
        ),
    ]

    fornecedor = [
        plano(
            "explorar",
            "Explorar",
            0,
            [("40", "pedidos/mês"), ("5", "vendedores"), ("150", "SKUs")],
            [
                rec("Catálogo e depósito manual", True, "1 depósito"),
                rec("Aprovar vendedores na rede", True),
                integ_off,
                import_off,
            ],
            destaque="Publique e receba pedidos manualmente",
            cta_gratis=True,
        ),
        plano(
            "ativo",
            "Ativo",
            99,
            [("200", "pedidos/mês"), ("20", "vendedores"), ("800", "SKUs")],
            [
                rec("Tudo do Explorar", True),
                integ_on,
                import_on,
                rec("Até 2 depósitos", True),
            ],
            destaque="Conecte seu ERP e escale a rede",
            featured=True,
            tag="Recomendado",
        ),
        plano(
            "rede",
            "Rede",
            249,
            [("800", "pedidos/mês"), ("60", "vendedores"), ("3.000", "SKUs")],
            [
                rec("Tudo do Ativo", True),
                sync_on,
                rec("Destaque na vitrine", True),
                rec("Até 5 depósitos", True),
            ],
            destaque="Distribuidor em expansão",
        ),
        plano(
            "distribuidor",
            "Distribuidor",
            499,
            [("3.000", "pedidos/mês"), ("150", "vendedores"), ("15.000", "SKUs")],
            [
                rec("Tudo da Rede", True),
                rec("API e webhooks", True),
                rec("Logs estendidos de integração", True),
                rec("Equipe ampliada", True),
            ],
            destaque="Indústria e multi-depósito",
        ),
    ]

    return {"vendedor": vendedor, "fornecedor": fornecedor}


def landing_perfil(perfil: str) -> dict:
    """Conteúdo SEO e storytelling das landings /para-vendedores e /para-fornecedores."""
    perfis = {
        "vendedor": {
            "perfil": "vendedor",
            "segment_label": "Vendedor",
            "segment_mod": "vendedor",
            "page_title": "DropNexo para vendedores — Dropshipping B2B sem estoque",
            "meta_description": (
                "Venda sem estoque com fornecedores nacionais verificados. "
                "0% de comissão sobre vendas, plano grátis sem cartão e integrações Bling e marketplaces nos planos pagos."
            ),
            "h1": "Venda sem estoque conectado a fornecedores reais",
            "lead": (
                "Encontre parceiros B2B, ative produtos no seu catálogo e escale pedidos "
                "— sem percentual sobre o faturamento. Integrações liberadas a partir do primeiro plano pago."
            ),
            "beneficios": [
                "Rede de fornecedores nacionais com aprovação de parceria",
                "Catálogo próprio: você edita vitrine, preço e fotos",
                "Pedidos centralizados entre você e o fornecedor",
                "Plano Explorar grátis, sem cartão de crédito",
            ],
            "faq": [
                (
                    "Preciso de cartão para começar?",
                    "Não. O plano Explorar é gratuito e não exige cartão. Você só paga quando escolher um plano pago.",
                ),
                (
                    "A DropNexo cobra comissão sobre minhas vendas?",
                    "Não. Cobramos mensalidade conforme volume de pedidos e conexões, nunca percentual sobre faturamento.",
                ),
                (
                    "Quando posso integrar Bling ou marketplaces?",
                    "Integrações (Bling, ERPs, lojas) estão disponíveis a partir do primeiro plano pago.",
                ),
            ],
        },
        "fornecedor": {
            "perfil": "fornecedor",
            "segment_label": "Fornecedor",
            "segment_mod": "fornecedor",
            "page_title": "DropNexo para fornecedores — Venda via dropshipping B2B",
            "meta_description": (
                "Disponibilize seu catálogo para milhares de vendedores dropshipping. "
                "0% sobre vendas, plano Explorar grátis e integração Bling nos planos pagos."
            ),
            "h1": "Amplie canais com vendedores dropshipping",
            "lead": (
                "Publique catálogo, aprove revendedores e receba pedidos na plataforma. "
                "Sem comissão sobre faturamento — você escala conforme pedidos e rede de vendedores."
            ),
            "beneficios": [
                "Vendedores qualificados solicitam parceria — você aprova quem revende",
                "Catálogo mestre: o vendedor não altera seu cadastro de origem",
                "Operação manual no grátis; ERP e sync nos planos pagos",
                "Explorar sem mensalidade e sem cartão para testar a rede",
            ],
            "faq": [
                (
                    "Fornecedor paga comissão sobre vendas?",
                    "Não. A monetização é por plano mensal conforme pedidos e vendedores conectados, sem % sobre GMV.",
                ),
                (
                    "Posso usar sem integrar meu ERP?",
                    "Sim. No plano Explorar você opera manualmente na plataforma. Integrações exigem plano pago.",
                ),
                (
                    "Como entram vendedores no meu catálogo?",
                    "Eles encontram você na rede, solicitam vínculo e você aprova em Vendedores no painel.",
                ),
            ],
        },
    }
    return perfis.get(perfil, perfis["vendedor"])


def catalogo_planos():
    """Catálogo legado (lista única); preferir catalogo_planos_home na landing."""
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
