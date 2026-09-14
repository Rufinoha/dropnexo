# sistema/plataforma/sessao.py — navegação (módulo fornecedor/vendedor) e usuários por tenant
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta

from flask import render_template, session, url_for

from api.brevo.srotas_brevo import enviar_email
from global_utils import (
    PERFIL_LABEL,
    Var_ConectarBanco,
    agora_utc,
    gerar_hmac_token,
    obter_base_url,
    valida_email,
)

# ── Navegação ─────────────────────────────────────────────────────────

MODULO_FORNECEDOR = "fornecedor"
MODULO_VENDEDOR = "vendedor"
MODULO_ARMAZEM = "armazem"
MODULOS_VALIDOS = (MODULO_FORNECEDOR, MODULO_VENDEDOR, MODULO_ARMAZEM)


def modulos_disponiveis(tipo_negocio: str | None) -> list[str]:
    """Um tipo de negócio = um módulo. Híbrido legado vira vendedor até migração."""
    t = (tipo_negocio or "vendedor").strip().lower()
    if t == "armazem":
        return [MODULO_ARMAZEM]
    if t == "fornecedor":
        return [MODULO_FORNECEDOR]
    # hibrido legado: um papel só (vendedor) — admin deve corrigir o tipo
    return [MODULO_VENDEDOR]


def modulos_disponiveis_sessao() -> list[str]:
    """Só o desenvolvedor enxerga todos os módulos."""
    if session.get("eh_desenvolvedor"):
        return [MODULO_FORNECEDOR, MODULO_VENDEDOR, MODULO_ARMAZEM]
    return modulos_disponiveis(session.get("tenant_tipo_negocio", "vendedor"))


def modulo_padrao(tipo_negocio: str | None) -> str:
    mods = modulos_disponiveis(tipo_negocio)
    t = (tipo_negocio or "vendedor").strip().lower()
    if t == "armazem":
        return MODULO_ARMAZEM
    if t == "fornecedor":
        return MODULO_FORNECEDOR
    return MODULO_VENDEDOR if MODULO_VENDEDOR in mods else mods[0]


def garantir_modulo_sessao() -> str:
    tipo = session.get("tenant_tipo_negocio", "vendedor")
    mods = modulos_disponiveis_sessao()
    ativo = (session.get("modulo_ativo") or "").strip().lower()
    if ativo not in mods:
        ativo = modulo_padrao(tipo)
        session["modulo_ativo"] = ativo
    return ativo


def rotulo_modulo(codigo: str) -> str:
    return {
        "fornecedor": "Fornecedor",
        "vendedor": "Vendedor",
        "armazem": "Armazém",
    }.get(codigo, codigo)


def icone_modulo(codigo: str) -> str:
    if codigo == MODULO_FORNECEDOR:
        return "truck"
    if codigo == MODULO_ARMAZEM:
        return "warehouse"
    return "shopping-bag"


def resolver_url_menu(data_page: str, nav_codigo: str | None = None) -> str:
    page = (data_page or "/").strip()
    if not page.startswith("/"):
        page = "/" + page
    nav = (nav_codigo or "").strip().lower()
    rotas_por_nav = {
        "inicio": "dashboard.index",
        "fornecedores": "vd_fornecedores.pagina",
        "catalogos": "fn_catalogo.pagina",
        "vd_catalogo": "vd_catalogo.pagina",
        "produtos": "vd_meus_produtos.pagina",
        "vd_precificacao": "vd_precificacao.pagina",
        "vd_pedidos": "vd_pedidos.pedidos",
        "fn_pedidos": "fn_pedidos.pedidos",
        "vd_expedicao": "vd_expedicao.expedicao",
        "vd_usuarios": "vd_usuarios.usuarios",
        "vd_depositos": "vd_depositos.depositos",
        "vd_categorias": "vd_categorias.categorias",
        "vd_loja_virtual": "vd_loja_virtual.pagina",
        "integracoes": "integracoes.pagina",
        "fn_parametros": "fn_parametros.parametros_pagina",
        "az_fornecedores": "az_fornecedores.pagina",
        "az_depositos": "az_depositos.depositos",
        "az_produtos": "az_produtos.pagina",
        "az_movimentacoes": "az_movimentacoes.pagina",
        "az_pedidos": "az_pedidos.pedidos",
        "az_parametros": "az_parametros.parametros_pagina",
        "az_usuarios": "az_usuarios.usuarios",
        "az_integracoes": "az_integracoes.pagina",
        "az_vendedores": "az_vendedores.vendedores",
    }
    rotas = {
        "/index": "dashboard.index",
        "/fornecedores": "vd_fornecedores.pagina",
        "/catalogos": "fn_catalogo.pagina",
        "/meus-produtos": "vd_meus_produtos.pagina",
        "/integracoes": "integracoes.pagina",
        "/configuracoes": "config.configuracoes",
        "/fornecedor/depositos": "fn_depositos.depositos",
        "/meu-perfil": "perfil.meu_perfil",
        "/fornecedor/categorias": "fn_categorias.categorias",
        "/fornecedor/variacoes": "fn_variacoes.variacoes",
        "/fornecedor/vendedores": "fn_vendedores.vendedores",
        "/fornecedor/usuarios": "fn_usuarios.usuarios",
        "/fornecedor/integracoes": "integracoes.pagina",
        "/fornecedor/parametros": "fn_parametros.parametros_pagina",
        "/vendedor/catalogo": "vd_catalogo.pagina",
        "/vendedor/precificacao": "vd_precificacao.pagina",
        "/vendedor/pedidos": "vd_pedidos.pedidos",
        "/fornecedor/pedidos": "fn_pedidos.pedidos",
        "/vendedor/expedicao": "vd_expedicao.expedicao",
        "/vendedor/usuarios": "vd_usuarios.usuarios",
        "/vendedor/depositos": "vd_depositos.depositos",
        "/vendedor/categorias": "vd_categorias.categorias",
        "/vendedor/loja-virtual": "vd_loja_virtual.pagina",
        "/configuracoes/fornecedores-plataforma": "config.fornecedores_plataforma",
        "/armazem/fornecedores": "az_fornecedores.pagina",
        "/armazem/depositos": "az_depositos.depositos",
        "/armazem/produtos": "az_produtos.pagina",
        "/armazem/movimentacoes": "az_movimentacoes.pagina",
        "/armazem/pedidos": "az_pedidos.pedidos",
        "/armazem/parametros": "az_parametros.parametros_pagina",
        "/armazem/usuarios": "az_usuarios.usuarios",
        "/armazem/integracoes": "az_integracoes.pagina",
        "/armazem/vendedores": "az_vendedores.vendedores",
    }
    endpoint = rotas_por_nav.get(nav) or rotas.get(page)
    if endpoint:
        try:
            return url_for(endpoint)
        except Exception:
            pass
    return page


def ctx_navegacao() -> dict:
    if not session.get("id_usuario"):
        return {
            "menu_sidebar": [],
            "modulos_nav": [],
            "modulo_ativo": "",
            "modulo_ativo_rotulo": "",
            "exibir_seletor_modulo": False,
            "pode_config_plataforma": False,
            "header_navs": set(),
        }
    mods = modulos_disponiveis_sessao()
    ativo = garantir_modulo_sessao()
    header_navs: set[str] = set()
    try:
        tid = session.get("id_tenant")
        uid = session.get("id_usuario")
        if tid and uid:
            perfil = (session.get("perfil_codigo") or "").lower()
            acesso_total = bool(session.get("eh_desenvolvedor")) or perfil in ("dono", "admin")
            conn = Var_ConectarBanco()
            try:
                cur = conn.cursor()
                header_navs = navs_header_liberados(
                    cur,
                    id_usuario=int(uid),
                    id_tenant=int(tid),
                    acesso_total=acesso_total,
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:
        header_navs = {n[0] for n in MENUS_HEADER_PADRAO if _nav_default_ligado(n[0])}
    return {
        "menu_sidebar": [],
        "modulos_nav": [
            {"codigo": m, "rotulo": rotulo_modulo(m), "icone": icone_modulo(m)}
            for m in mods
        ],
        "modulo_ativo": ativo,
        "modulo_ativo_rotulo": rotulo_modulo(ativo),
        "exibir_seletor_modulo": len(mods) > 1,
        "pode_config_plataforma": bool(session.get("eh_desenvolvedor")),
        "header_navs": header_navs,
    }


# ── Usuários por tenant ───────────────────────────────────────────────

PERFIS_EQUIPE_FORNECEDOR = ("admin", "operador", "visualizador", "financeiro")
PERFIS_EQUIPE_VENDEDOR = ("admin", "operador", "visualizador", "financeiro")
PERFIS_EQUIPE_ARMAZEM = ("admin", "operador", "visualizador", "financeiro")


def filtrar_perfis_equipe(perfis: list | None, permitidos: tuple[str, ...]) -> list:
    """Mantém só perfis de equipe; aceita código em qualquer caixa."""
    lista = list(perfis or [])
    allow = {str(c).strip().lower() for c in permitidos}
    out = [p for p in lista if str(p.get("codigo") or "").strip().lower() in allow]
    if out:
        return out
    # Fallback: se o filtro zerar (legado/seed incompleto), não bloqueia a tela.
    return [
        p
        for p in lista
        if str(p.get("codigo") or "").strip().lower() not in ("dono",)
    ]


def montar_combos_equipe(
    *,
    permitidos: tuple[str, ...],
    excluir_codigos: tuple[str, ...] = ("dono", "vendedor"),
) -> dict:
    """Combo de perfis para convite de equipe + id padrão (operador/admin)."""
    from global_utils import id_perfil_por_codigo

    base = listar_perfis_combo(excluir_codigos=excluir_codigos)
    perfis = filtrar_perfis_equipe(base.get("perfis"), permitidos)

    conn = Var_ConectarBanco()
    try:
        id_padrao = id_perfil_por_codigo(conn, "operador") or id_perfil_por_codigo(conn, "admin")
        if id_padrao and not any(int(p.get("id") or 0) == int(id_padrao) for p in perfis):
            cur = conn.cursor()
            cur.execute(
                "SELECT id, codigo, nome FROM tbl_perfil WHERE id = %s AND ativo = TRUE",
                (int(id_padrao),),
            )
            row = cur.fetchone()
            if row:
                perfis = [{"id": row[0], "codigo": row[1], "nome": row[2]}, *perfis]
    finally:
        conn.close()

    return {
        "success": True,
        "perfis": perfis,
        "id_perfil_padrao": int(id_padrao) if id_padrao else None,
    }


def normalizar_bool(valor, padrao=True):
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "on", "yes", "sim")


def status_convite(cur, uid: int) -> str:
    cur.execute(
        """
        SELECT senha_hash, token_ativacao, token_expira_em, ativo
        FROM tbl_usuario WHERE id = %s
        """,
        (uid,),
    )
    row = cur.fetchone()
    if not row:
        return "SEM_CONVITE"
    senha_hash, token_ativacao, token_expira_em, ativo = row
    if senha_hash and ativo:
        return "ACEITO"
    if not token_ativacao:
        return "SEM_CONVITE"
    if token_expira_em and token_expira_em < agora_utc():
        return "EXPIRADO"
    return "PENDENTE"


def criar_token_ativacao(cur, uid: int) -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = gerar_hmac_token(raw)
    horas = int(os.getenv("TOKEN_ATIVACAO_HORAS", "24"))
    expira = agora_utc() + timedelta(hours=horas)
    cur.execute(
        """
        UPDATE tbl_usuario
        SET token_ativacao = %s, token_expira_em = %s, ativo = FALSE, senha_hash = NULL
        WHERE id = %s
        """,
        (token_hash, expira, uid),
    )
    return raw


def enviar_email_convite(*, email: str, nome: str, nome_tenant: str, token_bruto: str) -> tuple[bool, str]:
    horas = int(os.getenv("TOKEN_ATIVACAO_HORAS", "24"))
    link = f"{obter_base_url()}/definir-senha?token={token_bruto}"
    base = obter_base_url()
    html = render_template(
        "cadastro/emails/ativacao_conta.html",
        titulo_email="Convite de acesso • DropNexo",
        nome_usuario=nome,
        nome_conta=nome_tenant,
        link_ativacao=link,
        horas_validade=horas,
        ano=datetime.now().year,
        url_politica_privacidade=os.getenv("URL_POLITICA_PRIVACIDADE") or f"{base}/privacidade",
        url_politica_interna=os.getenv("URL_POLITICA_INTERNA") or f"{base}/politica-interna",
        url_dpo=os.getenv("URL_DPO") or f"{base}/dpo",
    )
    return enviar_email([email], "Convite de acesso • DropNexo", html, tag="dropnexo_convite_equipe")


def token_ativacao_horas() -> int:
    return int(os.getenv("TOKEN_ATIVACAO_HORAS", "24"))


def garantir_tabela_usuario_tenant_menu(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_usuario_tenant_menu (
            id_usuario BIGINT NOT NULL REFERENCES tbl_usuario(id) ON DELETE CASCADE,
            id_tenant BIGINT NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
            id_menu BIGINT NOT NULL REFERENCES tbl_menu(id) ON DELETE CASCADE,
            exibir BOOLEAN NOT NULL DEFAULT TRUE,
            PRIMARY KEY (id_usuario, id_tenant, id_menu)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_usuario_tenant_menu_tenant
          ON tbl_usuario_tenant_menu (id_tenant, id_usuario)
        """
    )


def _perfil_codigo_usuario(cur, id_tenant: int, uid: int) -> str | None:
    cur.execute(
        """
        SELECT lower(pf.codigo)
        FROM tbl_usuario_tenant ut
        JOIN tbl_perfil pf ON pf.id = ut.id_perfil
        WHERE ut.id_tenant = %s AND ut.id_usuario = %s
        """,
        (id_tenant, uid),
    )
    row = cur.fetchone()
    return (row[0] or "").strip().lower() if row else None


def listar_menus_acesso_modulo(cur, *, contexto_modulo: str, id_usuario: int | None, id_tenant: int) -> list[dict]:
    """Menus do módulo com flag de acesso (override do usuário ou padrão do perfil)."""
    garantir_tabela_usuario_tenant_menu(cur)
    base = listar_menus_do_modulo(cur, contexto_modulo=contexto_modulo)

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_usuario_tenant_menu
        WHERE id_usuario = %s AND id_tenant = %s
        """,
        (id_usuario or 0, id_tenant),
    )
    tem_override = bool(id_usuario) and int(cur.fetchone()[0] or 0) > 0

    if tem_override:
        cur.execute(
            """
            SELECT id_menu FROM tbl_usuario_tenant_menu
            WHERE id_usuario = %s AND id_tenant = %s AND exibir = TRUE
            """,
            (id_usuario, id_tenant),
        )
        liberados = {int(r[0]) for r in cur.fetchall()}
    else:
        cur.execute(
            """
            SELECT pm.id_menu
            FROM tbl_perfil_menu pm
            JOIN tbl_usuario_tenant ut ON ut.id_perfil = pm.id_perfil
            WHERE ut.id_usuario = %s AND ut.id_tenant = %s AND pm.exibir = TRUE
            """,
            (id_usuario or 0, id_tenant),
        )
        liberados = {int(r[0]) for r in cur.fetchall()}
        if not liberados:
            return aplicar_defaults_novo_usuario(base)

    for m in base:
        is_hdr = (m.get("nav_codigo") or "").startswith("hdr_")
        if is_hdr and not tem_override:
            m["exibir"] = _nav_default_ligado(m.get("nav_codigo"))
        else:
            m["exibir"] = m["id"] in liberados
        for f in m.get("filhos") or []:
            is_hdr_f = (f.get("nav_codigo") or "").startswith("hdr_")
            if is_hdr_f and not tem_override:
                f["exibir"] = _nav_default_ligado(f.get("nav_codigo"))
            else:
                f["exibir"] = f["id"] in liberados
    return base


def navs_header_liberados(
    cur,
    *,
    id_usuario: int,
    id_tenant: int,
    acesso_total: bool = False,
) -> set[str]:
    """Header = mesmos hdr_* da tbl_menu, só se liberados no nível de acesso do usuário."""
    garantir_menus_header(cur)
    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_usuario_tenant_menu
        WHERE id_usuario = %s AND id_tenant = %s
        """,
        (id_usuario, id_tenant),
    )
    tem_override = int(cur.fetchone()[0] or 0) > 0
    if tem_override:
        cur.execute(
            """
            SELECT m.nav_codigo
            FROM tbl_usuario_tenant_menu um
            JOIN tbl_menu m ON m.id = um.id_menu
            WHERE um.id_usuario = %s AND um.id_tenant = %s AND um.exibir = TRUE
              AND (
                    COALESCE(m.nav_codigo, '') LIKE 'hdr_%%'
                 OR COALESCE(m.contexto_modulo, '') = 'header'
              )
            """,
            (id_usuario, id_tenant),
        )
        return {(r[0] or "").strip() for r in cur.fetchall() if r[0]}

    if acesso_total:
        return {n[0] for n in MENUS_HEADER_PADRAO}

    # Sem override e sem acesso total: defaults de novo usuário
    return {n[0] for n in MENUS_HEADER_PADRAO if _nav_default_ligado(n[0])}


def salvar_menus_usuario_tenant(cur, *, id_usuario: int, id_tenant: int, ids_menus: list[int]) -> None:
    garantir_tabela_usuario_tenant_menu(cur)
    ids = sorted({int(x) for x in (ids_menus or []) if int(x) > 0})
    cur.execute(
        "DELETE FROM tbl_usuario_tenant_menu WHERE id_usuario = %s AND id_tenant = %s",
        (id_usuario, id_tenant),
    )
    for mid in ids:
        cur.execute(
            """
            INSERT INTO tbl_usuario_tenant_menu (id_usuario, id_tenant, id_menu, exibir)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (id_usuario, id_tenant, id_menu) DO UPDATE SET exibir = TRUE
            """,
            (id_usuario, id_tenant, mid),
        )


# Menus do header (exceto Configurações — exclusivo DEV).
MENUS_HEADER_PADRAO = (
    ("hdr_meu_plano", "Meu Plano", "/meu-plano", "credit-card"),
    ("hdr_financeiro", "Financeiro", "/financeiro", "landmark"),
    ("hdr_chamados", "Central de Chamados", "/demandas", "message-square"),
    ("hdr_marktplace", "Marktplace", "/marktplace", "shopping-bag"),
)

# Ao criar usuário: ligados por padrão, exceto estes.
NAV_DEFAULT_OFF = frozenset(
    {
        "az_usuarios",
        "vd_usuarios",
        "fn_usuarios",
        "usuarios",
        "hdr_financeiro",
        "hdr_meu_plano",
    }
)

NAV_HEADER_EXCLUSIVOS = frozenset(n[0] for n in MENUS_HEADER_PADRAO)
PAGES_HEADER_EXCLUSIVOS = frozenset(
    {
        "/meu-plano",
        "/financeiro",
        "/demandas",
        "/marktplace",
        "/marketplace",
    }
)
NOMES_HEADER_EXCLUSIVOS = frozenset(
    {
        "meu plano",
        "financeiro",
        "central de chamados",
        "marktplace",
        "marketplace",
    }
)


def _eh_menu_exclusivo_header(
    *,
    nav_codigo: str | None = None,
    data_page: str | None = None,
    nome: str | None = None,
    contexto_modulo: str | None = None,
    obs: str | None = None,
) -> bool:
    """True se o item deve existir só no header (nunca na sidebar)."""
    nav = (nav_codigo or "").strip().lower()
    page = (data_page or "").strip().lower().rstrip("/")
    if page and not page.startswith("/"):
        page = "/" + page
    nome_l = (nome or "").strip().lower()
    ctx = (contexto_modulo or "").strip().lower()
    obs_l = (obs or "").strip().lower()
    if ctx == "header" or obs_l == "header":
        return True
    if nav.startswith("hdr_") or nav in NAV_HEADER_EXCLUSIVOS:
        return True
    if page in PAGES_HEADER_EXCLUSIVOS:
        return True
    if nome_l in NOMES_HEADER_EXCLUSIVOS:
        return True
    return False


def garantir_menus_header(cur) -> None:
    """Garante itens do menu do header em tbl_menu (contexto 'header', nunca sidebar)."""
    for nav, nome, page, icone in MENUS_HEADER_PADRAO:
        cur.execute(
            """
            SELECT id FROM tbl_menu WHERE COALESCE(nav_codigo, '') = %s LIMIT 1
            """,
            (nav,),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE tbl_menu
                   SET contexto_modulo = 'header',
                       obs = 'header',
                       pai = TRUE,
                       parent_id = NULL,
                       status = TRUE,
                       data_page = COALESCE(NULLIF(data_page, ''), %s),
                       nome_menu = COALESCE(NULLIF(nome_menu, ''), %s)
                 WHERE id = %s
                """,
                (page, nome, row[0]),
            )
            continue
        cur.execute(
            """
            INSERT INTO tbl_menu (
              nome_menu, descricao, data_page, icone, tipo_abrir, ordem,
              parent_id, pai, status, obs, id_modulo, nav_codigo, contexto_modulo
            )
            VALUES (%s, %s, %s, %s, 'Mesma Janela', 900, NULL, TRUE, TRUE, 'header',
                    NULL, %s, 'header')
            """,
            (nome, f"Acesso no menu do header: {nome}", page, icone, nav),
        )


def _nav_default_ligado(nav_codigo: str | None) -> bool:
    nav = (nav_codigo or "").strip().lower()
    if not nav:
        return True
    if nav in NAV_DEFAULT_OFF:
        return False
    if nav.endswith("_usuarios") or nav == "usuarios":
        return False
    return True


def aplicar_defaults_novo_usuario(menus: list[dict]) -> list[dict]:
    for m in menus:
        m["exibir"] = _nav_default_ligado(m.get("nav_codigo"))
        for f in m.get("filhos") or []:
            f["exibir"] = _nav_default_ligado(f.get("nav_codigo"))
    return menus


def listar_menus_do_modulo(cur, *, contexto_modulo: str) -> list[dict]:
    """Menus do módulo + header (sem Configurações)."""
    garantir_menus_header(cur)
    ctx = (contexto_modulo or "vendedor").strip().lower()
    prefix = {"armazem": "az_%", "vendedor": "vd_%", "fornecedor": "fn_%"}.get(ctx, "x_%")
    cur.execute(
        """
        SELECT m.id, m.nome_menu, m.nav_codigo, COALESCE(m.obs, '')
        FROM tbl_menu m
        WHERE m.status = TRUE AND m.pai = TRUE AND m.parent_id IS NULL
          AND COALESCE(m.nav_codigo, '') <> 'config'
          AND COALESCE(m.data_page, '') <> '/configuracoes'
          AND LOWER(COALESCE(m.nome_menu, '')) NOT LIKE 'configura%%'
          AND (
                COALESCE(m.contexto_modulo, '') = %s
             OR COALESCE(m.nav_codigo, '') LIKE %s
             OR COALESCE(m.data_page, '') LIKE %s
             OR COALESCE(m.nav_codigo, '') LIKE 'hdr_%%'
             OR COALESCE(m.contexto_modulo, '') = 'header'
          )
        ORDER BY
          CASE
            WHEN COALESCE(m.nav_codigo, '') LIKE 'hdr_%%'
              OR COALESCE(m.contexto_modulo, '') = 'header'
            THEN 1 ELSE 0
          END,
          m.ordem NULLS LAST,
          m.nome_menu
        """,
        (ctx, prefix, f"/{ctx}/%"),
    )
    pais = cur.fetchall()
    out = []
    for r in pais:
        mid = r[0]
        nav = r[2] or ""
        cur.execute(
            """
            SELECT m.id, m.nome_menu, m.nav_codigo
            FROM tbl_menu m
            WHERE m.status = TRUE AND m.parent_id = %s
              AND COALESCE(m.nav_codigo, '') <> 'config'
              AND COALESCE(m.data_page, '') <> '/configuracoes'
            ORDER BY m.ordem NULLS LAST, m.nome_menu
            """,
            (mid,),
        )
        filhos = [
            {
                "id": f[0],
                "nome": f[1],
                "nav_codigo": f[2] or "",
                "exibir": False,
                "grupo": "header" if (f[2] or "").startswith("hdr_") else "sidebar",
            }
            for f in cur.fetchall()
        ]
        out.append(
            {
                "id": mid,
                "nome": r[1],
                "nav_codigo": nav,
                "exibir": False,
        "grupo": "header"
                if nav.startswith("hdr_") or _eh_menu_exclusivo_header(nav_codigo=nav, nome=r[1])
                else "sidebar",
                "filhos": filhos,
            }
        )
    return out


def menus_padrao_do_perfil(cur, *, id_perfil: int, contexto_modulo: str) -> list[dict]:
    """Defaults ao convidar usuário: tudo ligado, exceto Usuários / Financeiro / Meu Plano."""
    _ = id_perfil  # mantido por compatibilidade da API
    base = listar_menus_do_modulo(cur, contexto_modulo=contexto_modulo)
    return aplicar_defaults_novo_usuario(base)


def listar_usuarios_tenant(
    *,
    id_tenant: int,
    pagina: int = 1,
    por_pagina: int = 20,
    busca: str = "",
    filtro_status: str = "",
    filtro_convite: str = "",
    id_usuario_sessao: int | None = None,
) -> dict:
    pagina = max(1, pagina)
    por_pagina = max(1, min(por_pagina, 100))
    offset = (pagina - 1) * por_pagina
    busca = (busca or "").strip()
    filtro_status = (filtro_status or "").strip().lower()
    filtro_convite = (filtro_convite or "").strip().upper()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["ut.id_tenant = %s", "u.eh_desenvolvedor IS NOT TRUE"]
        params: list = [id_tenant]
        if busca:
            where.append("(u.nome ILIKE %s OR u.email ILIKE %s)")
            like = f"%{busca}%"
            params.extend([like, like])
        if filtro_status == "ativo":
            where.append("u.ativo = TRUE AND ut.ativo = TRUE")
        elif filtro_status == "inativo":
            where.append("(u.ativo = FALSE OR ut.ativo = FALSE)")

        where_sql = " AND ".join(where)
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            WHERE {where_sql}
            """,
            params,
        )
        total = int(cur.fetchone()[0] or 0)

        cur.execute(
            f"""
            SELECT u.id, u.nome, u.email, u.ativo, ut.ativo, pf.codigo, pf.nome, ut.ultimo_acesso_em
            FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE {where_sql}
            ORDER BY u.nome
            LIMIT %s OFFSET %s
            """,
            params + [por_pagina, offset],
        )
        dados = []
        for r in cur.fetchall():
            convite = status_convite(cur, r[0])
            if filtro_convite and convite != filtro_convite:
                continue
            dt_login = r[7].isoformat() if r[7] else None
            perfil_cod = (r[5] or "").strip().lower()
            is_dono = perfil_cod == "dono"
            dados.append(
                {
                    "id": r[0],
                    "nome": r[1],
                    "email": r[2],
                    "status": bool(r[3]) and bool(r[4]),
                    "perfil_codigo": r[5],
                    "perfil_nome": PERFIL_LABEL.get(r[5], r[6]),
                    "convite_status": convite,
                    "dt_ultimo_login": dt_login,
                    "is_dono": is_dono,
                    "cannot_delete": is_dono or r[0] == id_usuario_sessao,
                }
            )
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        return {
            "success": True,
            "dados": dados,
            "total": total,
            "pagina_atual": pagina,
            "total_paginas": total_paginas,
        }
    finally:
        conn.close()


def listar_perfis_combo(*, excluir_codigos: tuple[str, ...] = ("dono",)) -> dict:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if excluir_codigos:
            placeholders = ",".join(["%s"] * len(excluir_codigos))
            cur.execute(
                f"""
                SELECT id, codigo, nome FROM tbl_perfil
                WHERE ativo = TRUE AND codigo NOT IN ({placeholders})
                ORDER BY nivel DESC, nome
                """,
                list(excluir_codigos),
            )
        else:
            cur.execute(
                """
                SELECT id, codigo, nome FROM tbl_perfil
                WHERE ativo = TRUE
                ORDER BY nivel DESC, nome
                """
            )
        perfis = [{"id": r[0], "codigo": r[1], "nome": r[2]} for r in cur.fetchall()]
        return {"success": True, "perfis": perfis}
    finally:
        conn.close()


def carregar_usuario_apoio(*, id_tenant: int, uid: int, contexto_modulo: str | None = None) -> tuple[dict, int]:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id, u.nome, u.email, u.whatsapp, u.ativo, ut.id_perfil, ut.ativo, pf.codigo, pf.nome
            FROM tbl_usuario u
            JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.id_tenant = %s
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE u.id = %s AND u.eh_desenvolvedor IS NOT TRUE
            """,
            (id_tenant, uid),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Usuário não encontrado neste tenant."}, 404
        perfil_cod = (row[7] or "").strip().lower()
        ctx = (contexto_modulo or session.get("modulo_ativo") or "vendedor").strip().lower()
        menus = listar_menus_acesso_modulo(
            cur, contexto_modulo=ctx, id_usuario=int(row[0]), id_tenant=id_tenant
        )
        return (
            {
                "success": True,
                "dados": {
                    "id": row[0],
                    "nome": row[1],
                    "email": row[2],
                    "whatsapp": row[3] or "",
                    "status": bool(row[4]) and bool(row[6]),
                    "id_perfil": row[5],
                    "perfil_codigo": row[7],
                    "perfil_nome": PERFIL_LABEL.get(row[7], row[8]),
                    "is_dono": perfil_cod == "dono",
                    "convite_status": status_convite(cur, row[0]),
                    "token_horas": token_ativacao_horas(),
                    "menus": menus,
                },
            },
            200,
        )
    finally:
        conn.close()


def salvar_usuario_tenant(
    *,
    id_tenant: int,
    uid: int | None,
    email: str,
    nome: str,
    whatsapp: str,
    id_perfil: int,
    status: bool,
    enviar_convite: bool,
    ids_menus: list[int] | None = None,
    contexto_modulo: str | None = None,
) -> tuple[dict, int]:
    from global_utils import id_perfil_por_codigo

    email = (email or "").strip().lower()
    nome = (nome or "").strip()
    whatsapp = (whatsapp or "").strip()

    if not valida_email(email):
        return {"success": False, "message": "E-mail inválido."}, 400
    if not nome:
        return {"success": False, "message": "Informe o nome."}, 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not id_perfil:
            id_perfil = id_perfil_por_codigo(conn, "operador") or id_perfil_por_codigo(conn, "admin")
        if not id_perfil:
            return {"success": False, "message": "Selecione um perfil."}, 400

        cur.execute("SELECT nome FROM tbl_tenant WHERE id = %s", (id_tenant,))
        row_t = cur.fetchone()
        nome_tenant = row_t[0] if row_t else "DropNexo"

        cur.execute("SELECT lower(codigo) FROM tbl_perfil WHERE id = %s", (int(id_perfil),))
        perfil_alvo = cur.fetchone()
        if perfil_alvo and (perfil_alvo[0] or "") == "dono":
            return {"success": False, "message": "O perfil Dono não pode ser atribuído por esta tela."}, 403

        if uid:
            cur.execute(
                """
                SELECT u.eh_desenvolvedor, lower(pf.codigo)
                FROM tbl_usuario u
                JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.id_tenant = %s
                JOIN tbl_perfil pf ON pf.id = ut.id_perfil
                WHERE u.id = %s
                """,
                (id_tenant, int(uid)),
            )
            alvo = cur.fetchone()
            if not alvo:
                return {"success": False, "message": "Usuário não encontrado."}, 404
            if alvo[0]:
                return {"success": False, "message": "Usuário desenvolvedor não pode ser alterado aqui."}, 403
            if (alvo[1] or "") == "dono":
                # Dono: só atualiza dados pessoais; perfil/status/menus ficam intactos
                cur.execute(
                    "UPDATE tbl_usuario SET nome=%s, whatsapp=%s WHERE id=%s",
                    (nome, whatsapp, int(uid)),
                )
                conn.commit()
                return {
                    "success": True,
                    "message": "Dados do Dono atualizados. Perfil e menus do Dono não podem ser alterados.",
                    "id": int(uid),
                }, 200

            cur.execute(
                "UPDATE tbl_usuario SET nome=%s, email=%s, whatsapp=%s, ativo=%s WHERE id=%s",
                (nome, email, whatsapp, status, int(uid)),
            )
            cur.execute(
                """
                UPDATE tbl_usuario_tenant SET id_perfil=%s, ativo=%s
                WHERE id_usuario=%s AND id_tenant=%s
                """,
                (int(id_perfil), status, int(uid), id_tenant),
            )
            if ids_menus is not None:
                salvar_menus_usuario_tenant(
                    cur, id_usuario=int(uid), id_tenant=id_tenant, ids_menus=ids_menus
                )
            conn.commit()
            return {"success": True, "message": "Usuário atualizado.", "id": int(uid)}, 200

        cur.execute("SELECT id FROM tbl_usuario WHERE lower(email) = %s LIMIT 1", (email,))
        existente = cur.fetchone()
        token_bruto = None

        if existente:
            uid_novo = existente[0]
            cur.execute(
                "SELECT 1 FROM tbl_usuario_tenant WHERE id_usuario=%s AND id_tenant=%s",
                (uid_novo, id_tenant),
            )
            if cur.fetchone():
                return {"success": False, "message": "Usuário já vinculado a este tenant."}, 409
            cur.execute(
                "UPDATE tbl_usuario SET nome=%s, whatsapp=%s WHERE id=%s",
                (nome, whatsapp, uid_novo),
            )
            cur.execute(
                """
                INSERT INTO tbl_usuario_tenant (id_usuario, id_tenant, id_perfil, ativo)
                VALUES (%s,%s,%s,%s)
                """,
                (uid_novo, id_tenant, int(id_perfil), status),
            )
            if enviar_convite:
                cur.execute("SELECT senha_hash FROM tbl_usuario WHERE id=%s", (uid_novo,))
                sh = cur.fetchone()
                if sh and not sh[0]:
                    token_bruto = criar_token_ativacao(cur, uid_novo)
        else:
            cur.execute(
                """
                INSERT INTO tbl_usuario (nome, email, whatsapp, ativo)
                VALUES (%s,%s,%s,%s) RETURNING id
                """,
                (nome, email, whatsapp, False),
            )
            uid_novo = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO tbl_usuario_tenant (id_usuario, id_tenant, id_perfil, ativo)
                VALUES (%s,%s,%s,%s)
                """,
                (uid_novo, id_tenant, int(id_perfil), status),
            )
            if enviar_convite:
                token_bruto = criar_token_ativacao(cur, uid_novo)

        if ids_menus is not None:
            salvar_menus_usuario_tenant(
                cur, id_usuario=int(uid_novo), id_tenant=id_tenant, ids_menus=ids_menus
            )

        conn.commit()
        msg = "Usuário criado."
        if token_bruto:
            ok, msg_email = enviar_email_convite(
                email=email,
                nome=nome,
                nome_tenant=nome_tenant,
                token_bruto=token_bruto,
            )
            msg = "Usuário criado e convite enviado." if ok else f"Usuário criado, mas falhou o e-mail: {msg_email}"
        elif enviar_convite:
            msg = "Usuário criado. Convite não enviado (usuário já possui senha)."
        return {"success": True, "message": msg, "id": uid_novo}, 200
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": str(e)}, 500
    finally:
        conn.close()


def inativar_usuario_tenant(*, id_tenant: int, uid: int, id_usuario_sessao: int) -> tuple[dict, int]:
    if not uid:
        return {"success": False, "message": "ID inválido."}, 400
    if uid == id_usuario_sessao:
        return {"success": False, "message": "Você não pode inativar a si mesmo."}, 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cod = _perfil_codigo_usuario(cur, id_tenant, uid)
        if cod == "dono":
            return {
                "success": False,
                "message": "O usuário Dono do tenant não pode ser excluído nem inativado.",
            }, 403

        cur.execute(
            """
            UPDATE tbl_usuario_tenant SET ativo = FALSE
            WHERE id_usuario = %s AND id_tenant = %s AND id_usuario IN (
                SELECT id FROM tbl_usuario WHERE eh_desenvolvedor IS NOT TRUE
            )
            """,
            (uid, id_tenant),
        )
        if cur.rowcount == 0:
            return {"success": False, "message": "Usuário não encontrado."}, 404

        cur.execute(
            """
            SELECT COUNT(*) FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            WHERE ut.id_usuario = %s AND ut.ativo = TRUE AND u.eh_desenvolvedor IS NOT TRUE
            """,
            (uid,),
        )
        ativos = int(cur.fetchone()[0] or 0)
        if ativos == 0:
            cur.execute(
                "UPDATE tbl_usuario SET ativo = FALSE WHERE id = %s AND eh_desenvolvedor IS NOT TRUE",
                (uid,),
            )
        conn.commit()
        return {"success": True, "message": "Usuário inativado neste tenant."}, 200
    finally:
        conn.close()


def reenviar_convite_usuario(*, id_tenant: int, uid: int) -> tuple[dict, int]:
    if not uid:
        return {"success": False, "message": "ID inválido."}, 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.email, u.nome, t.nome
            FROM tbl_usuario u
            JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.id_tenant = %s
            JOIN tbl_tenant t ON t.id = ut.id_tenant
            WHERE u.id = %s AND u.eh_desenvolvedor IS NOT TRUE
            """,
            (id_tenant, uid),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Usuário não encontrado."}, 404
        token_bruto = criar_token_ativacao(cur, uid)
        conn.commit()
        ok, msg = enviar_email_convite(
            email=row[0],
            nome=row[1],
            nome_tenant=row[2],
            token_bruto=token_bruto,
        )
        if not ok:
            return {"success": False, "message": msg}, 500
        return {"success": True, "message": "Convite reenviado por e-mail."}, 200
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": str(e)}, 500
    finally:
        conn.close()
