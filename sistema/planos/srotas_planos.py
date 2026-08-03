from pathlib import Path

from flask import Blueprint, render_template, session

from global_utils import Var_ConectarBanco, login_obrigatorio, plano_slug_app

_MOD_DIR = Path(__file__).resolve().parent

planos_bp = Blueprint(
    "planos",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/sistema/planos",
)

_NOMES_PLANO_BANCO = {
    "starter": "Explorar",
    "professional": "Crescer",
    "scale": "Escalar",
    "enterprise": "Pro",
}

# Vitrine comercial → slug interno do tenant
_MAPA_VITRINE_PARA_BANCO = {
    "explorar": "starter",
    "crescer": "professional",
    "conectar": "professional",
    "ativo": "professional",  # legado fornecedor
    "escalar": "scale",
    "expandir": "scale",
    "rede": "scale",  # legado fornecedor
    "pro": "enterprise",
    "hub": "enterprise",
    "distribuidor": "enterprise",  # legado fornecedor
}


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

    integ_off = rec("Integração com ERP e Marketplace", False)
    integ_on = rec("Integração com ERP e Marketplace", True)
    import_off = rec("Importar planilha de produtos", False)
    import_on = rec("Importar planilha de produtos", True)
    email_off = rec("Aviso por e-mail (pedido e status)", False)
    email_on = rec("Aviso por e-mail (pedido e status)", True)

    vendedor = [
        plano(
            "explorar",
            "Explorar",
            0,
            [("25", "pedidos/mês"), ("1", "fornecedor"), ("50", "produtos")],
            [
                rec("Rede B2B e catálogo manual", True),
                rec("Pedidos na plataforma", True),
                integ_off,
                import_off,
                email_off,
                rec("Abrir chamado de suporte", True),
            ],
            destaque="Conheça a rede sem custo fixo",
            cta_gratis=True,
        ),
        plano(
            "crescer",
            "Crescer",
            79,
            [("150", "pedidos/mês"), ("3", "fornecedores"), ("500", "produtos")],
            [
                rec("Tudo do Explorar", True),
                integ_on,
                import_on,
                email_on,
                rec("Até 3 pessoas na equipe", True),
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
                rec("Até 8 pessoas na equipe", True),
            ],
            destaque="Operação com mais volume e equipe",
        ),
        plano(
            "pro",
            "Pro",
            349,
            [("2.000", "pedidos/mês"), ("80", "fornecedores"), ("10.000", "produtos")],
            [
                rec("Tudo do Escalar", True),
                rec("Equipe ampliada", True),
            ],
            destaque="Alto volume na operação",
        ),
    ]

    fornecedor = [
        plano(
            "explorar",
            "Explorar",
            0,
            [("40", "pedidos/mês"), ("5", "vendedores aprovados"), ("150", "produtos")],
            [
                rec("Catálogo e depósito manual", True, "1 depósito"),
                rec("Ver todas as solicitações de vendedores", True),
                integ_off,
                import_off,
                email_off,
                rec("Abrir chamado de suporte", True),
            ],
            destaque="Publique e receba pedidos manualmente",
            cta_gratis=True,
        ),
        plano(
            "conectar",
            "Conectar",
            99,
            [("200", "pedidos/mês"), ("20", "vendedores aprovados"), ("800", "produtos")],
            [
                rec("Tudo do Explorar", True),
                integ_on,
                import_on,
                email_on,
                rec("Até 2 depósitos", True),
            ],
            destaque="Conecte seu ERP e integre a operação",
            featured=True,
            tag="Recomendado",
        ),
        plano(
            "expandir",
            "Expandir",
            249,
            [("800", "pedidos/mês"), ("60", "vendedores aprovados"), ("3.000", "produtos")],
            [
                rec("Tudo do Conectar", True),
                rec("Até 5 depósitos", True),
            ],
            destaque="Mais vendedores e volume na rede",
        ),
        plano(
            "hub",
            "Hub",
            499,
            [("3.000", "pedidos/mês"), ("Ilimitados", "vendedores aprovados"), ("15.000", "produtos")],
            [
                rec("Tudo do Expandir", True),
                rec("Equipe ampliada", True),
                rec("Vários depósitos", True),
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


def _plano_atual_tenant(id_tenant: int, plano_sessao: str | None) -> dict:
    from sistema.planos.limites import limites_plano, tipo_negocio_sessao

    slug = plano_slug_app(plano_sessao or "starter")
    tipo = tipo_negocio_sessao()
    lim = limites_plano(plano=slug, tipo_negocio=tipo)
    out = {
        "slug": slug,
        "nome": lim.get("nome") or _NOMES_PLANO_BANCO.get(slug) or slug.title(),
        "valor_centavos": None,
        "periodicidade": None,
        "destaque": "",
        "email_cobranca": "",
    }
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT tc.plano_slug, p.nome, p.valor_centavos, p.periodicidade, p.descricao,
                   tc.email_cobranca
            FROM tbl_tenant_cobranca tc
            JOIN tbl_plano p ON p.slug = tc.plano_slug
            WHERE tc.id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                SELECT slug, nome, valor_centavos, periodicidade, descricao
                FROM tbl_plano WHERE slug = %s AND ativo = TRUE
                """,
                (slug if slug in ("starter", "professional", "scale", "enterprise") else "starter",),
            )
            p = cur.fetchone()
            if p:
                out.update(
                    {
                        "slug": p[0],
                        "valor_centavos": p[2],
                        "periodicidade": p[3],
                        "destaque": p[4] or "",
                    }
                )
        else:
            out.update(
                {
                    "slug": row[0],
                    "valor_centavos": row[2],
                    "periodicidade": row[3],
                    "destaque": row[4] or "",
                    "email_cobranca": row[5] or "",
                }
            )
        # Nome comercial sempre pelo perfil (vendedor/fornecedor), não pelo nome do banco
        slug_final = plano_slug_app(out.get("slug") or slug)
        out["slug"] = slug_final
        out["nome"] = limites_plano(plano=slug_final, tipo_negocio=tipo).get("nome") or out["nome"]
        cur.close()
        conn.close()
    except Exception:
        pass
    return out


def _marcar_plano_atual_vitrine(planos: list[dict], slug_banco: str) -> list[dict]:
    alvo = plano_slug_app(slug_banco)
    out = []
    for p in planos:
        item = dict(p)
        vit = _MAPA_VITRINE_PARA_BANCO.get((p.get("slug") or "").lower(), "")
        item["_eh_atual"] = plano_slug_app(vit) == alvo if vit else False
        out.append(item)
    return out


@planos_bp.get("/meu-plano")
@login_obrigatorio()
def meu_plano():
    id_tenant = session.get("id_tenant")
    tipo = (session.get("tenant_tipo_negocio") or "vendedor").strip().lower()
    plano_sessao = session.get("tenant_plano") or "starter"
    atual = _plano_atual_tenant(id_tenant, plano_sessao)

    home = catalogo_planos_home()
    segmentos: list[dict] = []
    if tipo in ("vendedor", "hibrido"):
        segmentos.append(
            {
                "titulo": "Planos para vendedores",
                "descricao": "Limites da vitrine comercial (pedidos, fornecedores e produtos).",
                "planos": _marcar_plano_atual_vitrine(home["vendedor"], atual["slug"]),
            }
        )
    if tipo in ("fornecedor", "hibrido"):
        segmentos.append(
            {
                "titulo": "Planos para fornecedores",
                "descricao": "Limites da vitrine comercial (pedidos, vendedores e SKUs).",
                "planos": _marcar_plano_atual_vitrine(home["fornecedor"], atual["slug"]),
            }
        )

    tipo_rotulo = {
        "vendedor": "Vendedor",
        "fornecedor": "Fornecedor",
        "hibrido": "Híbrido",
    }.get(tipo, tipo.title())

    pode_pagamento = bool(
        session.get("eh_desenvolvedor")
        or (session.get("perfil_codigo") or "").lower() in ("dono", "admin", "financeiro")
    )

    armazenamento = {"bytes_imagens": 0}
    uso_cotas: list[dict] = []
    try:
        from fornecedor.catalogo.catalogo import obter_bytes_imagens_tenant
        from sistema.planos.limites import uso_cotas_tenant

        conn = Var_ConectarBanco()
        cur = conn.cursor()
        armazenamento["bytes_imagens"] = obter_bytes_imagens_tenant(cur, int(id_tenant))
        uso_cotas = uso_cotas_tenant(cur, int(id_tenant), tipo)
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass

    efi_payee_code = ""
    efi_environment = "sandbox"
    try:
        from api.efi.efi import efi_front_config

        efi_cfg = efi_front_config()
        efi_payee_code = efi_cfg.get("payee_code") or ""
        efi_environment = efi_cfg.get("environment") or "sandbox"
    except Exception:
        pass

    return render_template(
        "frm_meu_plano.html",
        nav_ativo="",
        plano_atual=atual,
        segmentos=segmentos,
        tipo_rotulo=tipo_rotulo,
        pode_pagamento=pode_pagamento,
        armazenamento=armazenamento,
        uso_cotas=uso_cotas,
        efi_payee_code=efi_payee_code,
        efi_environment=efi_environment,
    )


@planos_bp.get("/abrir-chamado")
@login_obrigatorio()
def abrir_chamado():
    """Compat: redireciona para a Central de Chamados (HubSupport)."""
    from flask import redirect, url_for

    return redirect(url_for("demandas.demandas_pagina"))
