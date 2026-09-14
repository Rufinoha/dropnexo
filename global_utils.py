# DropNexo — utilitários globais
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import psycopg2
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from psycopg2 import OperationalError

# —— Marca DropNexo (H74 HUB) ——
MARCA_NOME = "DropNexo"
MARCA_FAMILIA = "H74 HUB"
MARCA_SLOGAN = "Conectar fornecedores e vendedores"
MARCA_COR_PRIMARIA = "#021F81"
MARCA_COR_HOVER = "#2C6BF3"
MARCA_COR_LIGHT = "#E8F0FF"
MARCA_ASSET_ICONE = "imge/icone_dropnexo.png"
MARCA_ASSET_LOGO = "imge/icone_dropnexo.png"
MARCA_ASSET_LOGO_NOME = "imge/logo_dropnexo_nome.png"

global_bp = Blueprint(
    "global",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


def registrar_templates_modulos(app):
    """
    Registra modulos/*/templates no Jinja da aplicação.
    Evita TemplateNotFound quando o loader do blueprint não é aplicado (ex.: reload em debug).
    """
    from jinja2 import ChoiceLoader, FileSystemLoader

    raiz_projeto = Path(__file__).resolve().parent
    loaders: list[FileSystemLoader] = []

    for pasta in ("fornecedor", "vendedor", "armazem", "sistema"):
        base = raiz_projeto / pasta
        if base.is_dir():
            for tpl_dir in base.rglob("templates"):
                if tpl_dir.is_dir():
                    loaders.append(FileSystemLoader(str(tpl_dir.resolve())))

    api_base = raiz_projeto / "api"
    if api_base.is_dir():
        for tpl_dir in api_base.rglob("templates"):
            if tpl_dir.is_dir():
                loaders.append(FileSystemLoader(str(tpl_dir.resolve())))

    tpl_app = raiz_projeto / "templates"
    if tpl_app.is_dir():
        loaders.append(FileSystemLoader(str(tpl_app.resolve())))

    if loaders:
        app.jinja_env.loader = ChoiceLoader(loaders)


def init_app(app):
    app.register_blueprint(global_bp)

    @app.context_processor
    def _inject_marca():
        return {
            "MARCA_NOME": MARCA_NOME,
            "MARCA_FAMILIA": MARCA_FAMILIA,
            "MARCA_SLOGAN": MARCA_SLOGAN,
            "marca_favicon_url": url_for("static", filename=MARCA_ASSET_ICONE),
            "marca_logo_url": url_for("static", filename=MARCA_ASSET_LOGO),
            "marca_logo_nome_url": url_for("static", filename=MARCA_ASSET_LOGO_NOME),
            "CONTATO_WHATSAPP": CONTATO_WHATSAPP,
            "CONTATO_EMAIL": CONTATO_EMAIL,
        }

    @app.context_processor
    def _inject_vinculo_alertas():
        from flask import session

        if not session.get("id_tenant") or not session.get("id_usuario"):
            return {"vinculo_alertas": []}
        try:
            from core.dominio import listar_alertas_vinculo_tenant

            conn = Var_ConectarBanco()
            cur = conn.cursor()
            alertas = listar_alertas_vinculo_tenant(cur, int(session["id_tenant"]))
            conn.close()
            return {"vinculo_alertas": alertas}
        except Exception:
            return {"vinculo_alertas": []}


def url_imagem_produto(imagem_url: str | None) -> str:
    """Converte caminho local (imge/produtos/..., upload/tenant...) ou URL externa para URL servível."""
    if not imagem_url:
        return ""
    s = str(imagem_url).strip()
    if s.lower().startswith(("http://", "https://")):
        return s
    rel = s.replace("\\", "/").lstrip("/")
    if rel.lower().startswith("static/"):
        rel = rel[7:]
    if rel.lower().startswith("upload/tenant"):
        # Mesma rota autenticada em DEV e PROD (ACL valida vínculo/tenant).
        return url_for("bling.api_produto_imagem_arquivo", caminho=rel)
    return url_for("static", filename=rel)


def is_modo_producao() -> bool:
    return str(os.getenv("MODO_PRODUCAO", "false")).strip().lower() in (
        "1",
        "true",
        "yes",
        "sim",
    )


def obter_base_url() -> str:
    """
    URL pública da aplicação (links em e-mail, etc.).
    MODO_PRODUCAO=false → BASE_HOM; true → BASE_PROD.
    """
    if is_modo_producao():
        base = (os.getenv("BASE_PROD") or "").strip().rstrip("/")
    else:
        base = (os.getenv("BASE_HOM") or "").strip().rstrip("/")

    if base:
        return base

    legado = (os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
    if legado:
        return legado

    porta = (os.getenv("PORTA") or "5260").strip()
    return f"http://127.0.0.1:{porta}"


def obter_url_site_publico() -> str:
    """
    URL do site em produção — manuais, rodapés e links para o cliente.
    Independente de MODO_PRODUCAO (em dev o manual ainda aponta para o site real).
    """
    base = (os.getenv("BASE_PROD") or "https://dropnexo.com.br").strip().rstrip("/")
    return base


def Var_ConectarBanco():
    suf = "PROD" if is_modo_producao() else "DEV"

    user = os.getenv(f"DB_USER_{suf}")
    pwd = os.getenv(f"DB_PASSWORD_{suf}")
    dbname = os.getenv(f"DB_NAME_{suf}")
    host = os.getenv(f"DB_HOST_{suf}", "127.0.0.1")
    port = os.getenv(f"DB_PORT_{suf}", "5432")
    schema = os.getenv(f"DB_SCHEMA_{suf}", "public")

    faltando = [n for n, v in [
        (f"DB_USER_{suf}", user),
        (f"DB_PASSWORD_{suf}", pwd),
        (f"DB_NAME_{suf}", dbname),
    ] if not str(v or "").strip()]
    if faltando:
        raise ValueError("Variáveis ausentes: " + ", ".join(faltando))

    try:
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=pwd,
            host=host,
            port=port,
            options=f"-c search_path={schema},public -c application_name=dropnexo",
        )
        conn.set_client_encoding("UTF8")
        return conn
    except OperationalError as e:
        raise RuntimeError(f"Erro ao conectar ao PostgreSQL ({suf}): {e}") from e


def agora_utc():
    return datetime.now(timezone.utc)


def gerar_hmac_token(raw_token: str) -> str:
    secret = (os.getenv("SECRET_KEY") or "dev-inseguro").encode()
    return hmac.new(secret, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


def valida_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    padrao = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", re.IGNORECASE)
    return bool(padrao.match(email))


def avaliar_politica_senha(senha: str, confirmar: str | None = None) -> dict:
    """
    Política: mín. 8 caracteres, 1 maiúscula, 1 minúscula, 1 número, 1 especial.
    Se confirmar for informado, exige igualdade.
    """
    s = senha or ""
    c = confirmar if confirmar is not None else ""

    regras = {
        "min8": len(s) >= 8,
        "maiuscula": bool(re.search(r"[A-Z]", s)),
        "minuscula": bool(re.search(r"[a-z]", s)),
        "numero": bool(re.search(r"[0-9]", s)),
        "especial": bool(re.search(r"[^A-Za-z0-9]", s)),
    }
    if confirmar is not None:
        regras["igual"] = len(s) > 0 and s == c
    else:
        regras["igual"] = True

    regras["ok"] = all(regras.values())
    regras["faltas"] = []
    rotulos = {
        "min8": "Mínimo de 8 caracteres",
        "maiuscula": "1 letra maiúscula",
        "minuscula": "1 letra minúscula",
        "numero": "1 número",
        "especial": "1 caractere especial (!@#$…)",
        "igual": "Senha e confirmação iguais",
    }
    for chave, ok in regras.items():
        if chave in ("ok", "faltas"):
            continue
        if not ok:
            regras["faltas"].append(rotulos[chave])
    return regras


def validar_politica_senha(senha: str, confirmar: str | None = None) -> tuple[bool, str]:
    r = avaliar_politica_senha(senha, confirmar)
    if r["ok"]:
        return True, ""
    return False, "A senha não atende aos requisitos: " + "; ".join(r["faltas"])


def remover_tags_html(texto: str) -> str:
    return re.sub(r"<[^<]+?>", "", texto or "")


def _is_ajax_json():
    return bool(
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )


def login_obrigatorio(_func=None, *, exigir_tenant: bool = True):
    """
    @login_obrigatorio
    ou
    @login_obrigatorio()
    ou
    @login_obrigatorio(exigir_tenant=False)
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            uid = session.get("id_usuario")
            if not uid:
                if _is_ajax_json():
                    return jsonify(success=False, message="Não autenticado."), 401
                return redirect(url_for("auth.pagina_login"))

            if exigir_tenant and not session.get("id_tenant"):
                if _is_ajax_json():
                    return jsonify(success=False, message="Sessão sem tenant."), 403
                return redirect(url_for("auth.pagina_login"))

            return func(*args, **kwargs)

        return wrapper

    if _func is not None and callable(_func):
        return decorator(_func)
    return decorator


def exigir_desenvolvedor(_func=None):
    """Apenas usuários com tbl_usuario.eh_desenvolvedor = true."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not session.get("eh_desenvolvedor"):
                if _is_ajax_json():
                    return jsonify(
                        success=False,
                        message="Acesso restrito a desenvolvedores da plataforma.",
                    ), 403
                return redirect(url_for("dashboard.index"))
            return func(*args, **kwargs)

        return wrapper

    if _func is not None and callable(_func):
        return decorator(_func)
    return decorator


# Limite mensal chamados — plano starter (sem tabela de planos dinâmica)
LIMITE_CHAMADOS_MES_STARTER = 40
LIMITE_USUARIOS_PORTAL_STARTER = 100
LIMITE_PORTAIS_STARTER = 1
LIMITE_AGENTES_STARTER = 1
LIMITE_AGENTES_PROFISSIONAL = 5
LIMITE_AGENTES_EMPRESARIAL = 20

# Previsão exibida para integrações ainda em rollout (landing e painel)
INTEGRACOES_CANAIS_PREVISAO = "em breve"

CONTATO_WHATSAPP = os.getenv("DROPNEXO_CONTATO_WHATSAPP", "")
CONTATO_EMAIL = os.getenv("DROPNEXO_CONTATO_EMAIL", "contato@dropnexo.com.br")

PERFIL_LABEL = {
    "dono": "Dono da conta",
    "equipe": "Equipe",
    # Legado (não expor na UI; labels só para dados antigos)
    "admin": "Equipe",
    "financeiro": "Equipe",
    "vendedor": "Equipe",
    "operador": "Equipe",
    "visualizador": "Equipe",
}

# Permissão (prefixo antes do ponto) → nav_codigo(s) do menu que liberam a ação.
# Equipe: se algum desses menus estiver ligado no tenant, a permissão passa.
_PERMISSAO_PARA_NAVS: dict[str, tuple[str, ...]] = {
    "dashboard": ("inicio",),
    "catalogos": ("catalogos", "vd_catalogo", "az_produtos"),
    "produtos": ("produtos", "az_produtos", "catalogos", "vd_catalogo"),
    "fornecedores": ("fornecedores", "az_fornecedores"),
    "integracoes": ("integracoes", "fn_integracoes", "az_integracoes"),
    "fn_integracoes": ("fn_integracoes", "integracoes", "az_integracoes"),
    "fn_pedidos": ("fn_pedidos",),
    "fn_categorias": ("fn_categorias",),
    "fn_variacoes": ("fn_variacoes",),
    "fn_parametros": ("fn_parametros",),
    "fn_segmentos": ("fn_parametros",),
    "fn_vendedores": ("fn_vendedores", "az_vendedores"),
    "fn_usuarios": ("fn_usuarios",),
    "fn_importacao": ("catalogos", "fn_integracoes"),
    "vd_pedidos": ("vd_pedidos", "az_pedidos"),
    "vd_catalogo": ("vd_catalogo", "catalogos"),
    "vd_categorias": ("vd_categorias",),
    "vd_depositos": ("vd_depositos", "fn_depositos", "az_depositos"),
    "vd_loja_virtual": ("vd_loja_virtual",),
    "vd_precificacao": ("vd_precificacao", "precificacao"),
    "vd_usuarios": ("vd_usuarios",),
    "precificacao": ("vd_precificacao", "precificacao"),
    "az_usuarios": ("az_usuarios",),
    "az_produtos": ("az_produtos", "catalogos"),
    "az_depositos": ("az_depositos", "fn_depositos", "vd_depositos"),
    "az_pedidos": ("az_pedidos", "vd_pedidos", "fn_pedidos"),
    "az_fornecedores": ("az_fornecedores", "fornecedores"),
    "az_vendedores": ("az_vendedores", "fn_vendedores"),
    "az_parametros": ("az_parametros",),
    "az_integracoes": ("az_integracoes", "fn_integracoes", "integracoes"),
    "az_movimentacoes": ("az_movimentacoes",),
    "financeiro": ("hdr_financeiro",),
    "planos": ("hdr_meu_plano",),
    "usuarios": ("fn_usuarios", "vd_usuarios", "az_usuarios", "usuarios"),
    # Só dono/dev — equipe nunca
    "configuracoes": (),
    "plataforma": (),
}


def navs_para_permissao(codigo: str) -> tuple[str, ...]:
    base = (codigo or "").strip().lower().split(".", 1)[0]
    if base in _PERMISSAO_PARA_NAVS:
        return _PERMISSAO_PARA_NAVS[base]
    # Fallback: o próprio prefixo costuma ser o nav_codigo
    return (base,) if base else ()


def id_perfil_por_codigo(conn, codigo: str) -> int | None:
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM tbl_perfil WHERE codigo = %s AND ativo = TRUE LIMIT 1",
        ((codigo or "").strip().lower(),),
    )
    row = cur.fetchone()
    cur.close()
    return int(row[0]) if row else None


def listar_permissoes_do_perfil(conn, id_perfil: int) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.codigo
        FROM tbl_perfil_permissao pp
        JOIN tbl_permissao p ON p.id = pp.id_permissao AND p.ativo = TRUE
        WHERE pp.id_perfil = %s
        ORDER BY p.codigo
        """,
        (id_perfil,),
    )
    codigos = [r[0] for r in cur.fetchall()]
    cur.close()
    return codigos


def carregar_menus_liberados_sessao(conn, *, id_usuario: int, id_tenant: int, acesso_total: bool) -> None:
    """Popula session['menus_liberados'] (nav_codigo). '*' = acesso total."""
    if acesso_total:
        session["menus_liberados"] = ["*"]
        return
    cur = conn.cursor()
    try:
        from sistema.plataforma.sessao import (
            NAV_DEFAULT_OFF,
            garantir_tabela_usuario_tenant_menu,
            _nav_default_ligado,
        )

        garantir_tabela_usuario_tenant_menu(cur)
        cur.execute(
            """
            SELECT COUNT(*)::int FROM tbl_usuario_tenant_menu
            WHERE id_usuario = %s AND id_tenant = %s
            """,
            (id_usuario, id_tenant),
        )
        tem = int(cur.fetchone()[0] or 0) > 0
        if tem:
            cur.execute(
                """
                SELECT COALESCE(m.nav_codigo, '')
                FROM tbl_usuario_tenant_menu um
                JOIN tbl_menu m ON m.id = um.id_menu
                WHERE um.id_usuario = %s AND um.id_tenant = %s AND um.exibir = TRUE
                """,
                (id_usuario, id_tenant),
            )
            session["menus_liberados"] = [r[0] for r in cur.fetchall() if r[0]]
        else:
            cur.execute(
                """
                SELECT COALESCE(nav_codigo, '')
                FROM tbl_menu
                WHERE status = TRUE AND pai = TRUE AND parent_id IS NULL
                  AND COALESCE(nav_codigo, '') <> 'config'
                """
            )
            session["menus_liberados"] = [
                r[0] for r in cur.fetchall() if r[0] and _nav_default_ligado(r[0])
            ]
        # evita import circular de unused
        _ = NAV_DEFAULT_OFF
    finally:
        cur.close()


def aplicar_permissoes_na_sessao(conn, *, id_perfil: int, eh_desenvolvedor: bool = False) -> None:
    """Carrega perfil e acesso na sessão após login ou troca de tenant."""
    cur = conn.cursor()
    cur.execute(
        "SELECT codigo, nome FROM tbl_perfil WHERE id = %s LIMIT 1",
        (id_perfil,),
    )
    row = cur.fetchone()
    cur.close()
    perfil_cod = (row[0] or "").strip().lower() if row else ""
    if row:
        session["id_perfil"] = id_perfil
        # Normaliza legados de equipe para o código canônico na sessão
        if perfil_cod in ("admin", "operador", "visualizador", "financeiro", "vendedor"):
            session["perfil_codigo"] = "equipe"
            session["perfil_nome"] = PERFIL_LABEL["equipe"]
            session["papel"] = "equipe"
        else:
            session["perfil_codigo"] = row[0]
            session["perfil_nome"] = row[1]
            session["papel"] = row[0]

    acesso_total = bool(eh_desenvolvedor) or perfil_cod == "dono" or session.get("perfil_codigo") == "dono"
    if eh_desenvolvedor:
        session["permissoes"] = ["*"]
    elif acesso_total:
        session["permissoes"] = ["*"]
    else:
        # Equipe: RBAC antigo deixa de ser fonte de verdade
        session["permissoes"] = []

    uid = session.get("id_usuario")
    tid = session.get("id_tenant")
    if uid and tid:
        carregar_menus_liberados_sessao(
            conn,
            id_usuario=int(uid),
            id_tenant=int(tid),
            acesso_total=acesso_total or bool(eh_desenvolvedor),
        )
    elif acesso_total or eh_desenvolvedor:
        session["menus_liberados"] = ["*"]
    else:
        session["menus_liberados"] = []


def usuario_tem_menu_liberado(*nav_codigos: str) -> bool:
    """True se o usuário tem algum dos nav_codigo ligados (ou acesso total)."""
    if session.get("eh_desenvolvedor"):
        return True
    papel = (session.get("perfil_codigo") or session.get("papel") or "").strip().lower()
    if papel == "dono":
        return True
    liberados = session.get("menus_liberados") or []
    if "*" in liberados:
        return True
    alvo = {(n or "").strip().lower() for n in nav_codigos if n}
    if not alvo:
        return False
    have = {(n or "").strip().lower() for n in liberados}
    return bool(alvo & have)


def usuario_tem_permissao(codigo: str) -> bool:
    """Desenvolvedor e Dono: total. Equipe: menu liberado correspondente."""
    if session.get("eh_desenvolvedor"):
        return True
    papel = (session.get("perfil_codigo") or session.get("papel") or "").strip().lower()
    if papel == "dono":
        return True
    perms = session.get("permissoes") or []
    if "*" in perms:
        return True
    navs = navs_para_permissao(codigo)
    if not navs:
        return False
    return usuario_tem_menu_liberado(*navs)


def exigir_permissao(_func=None, *, codigo: str | None = None, codigos: list[str] | None = None):
    """
    @exigir_permissao(codigo='catalogos.ver')
    ou @exigir_permissao(codigos=['catalogos.ver', 'catalogos.editar'])  # qualquer uma
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if session.get("eh_desenvolvedor"):
                return func(*args, **kwargs)
            alvo = list(codigos or [])
            if codigo:
                alvo.append(codigo)
            if not alvo:
                return func(*args, **kwargs)
            if any(usuario_tem_permissao(c) for c in alvo):
                return func(*args, **kwargs)
            if _is_ajax_json():
                return jsonify(success=False, message="Sem permissão para esta ação."), 403
            return redirect(url_for("dashboard.index"))

        return wrapper

    if _func is not None and callable(_func):
        return decorator(_func)
    return decorator


def exigir_modulo(*modulos: str):
    """Restringe rota ao módulo ativo na sidebar (fornecedor | vendedor)."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from sistema.plataforma.sessao import garantir_modulo_sessao

            ativo = garantir_modulo_sessao()
            if session.get("eh_desenvolvedor") or ativo in modulos:
                return func(*args, **kwargs)
            if _is_ajax_json():
                return jsonify(success=False, message="Módulo incorreto para esta tela."), 403
            return redirect(url_for("dashboard.index"))

        return wrapper

    return decorator


def coerce_text(val, default: str = "") -> str:
    """Converte valor de API/form/JSON para str (evita .strip() em dict)."""
    if val is None:
        return default
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, dict):
        for key in (
            "message",
            "error_description",
            "description",
            "custom_id",
            "plano",
            "slug",
            "value",
            "text",
        ):
            if key in val:
                nested = coerce_text(val[key], "")
                if nested:
                    return nested
        return default
    if isinstance(val, (list, tuple)):
        for item in val:
            nested = coerce_text(item, "")
            if nested:
                return nested
        return default
    return default


_PLANOS_BANCO = frozenset({"starter", "professional", "scale", "enterprise"})

_ALIASES_PLANO_BANCO = {
    "explorar": "starter",
    "crescer": "professional",
    "conectar": "professional",
    "ativo": "professional",  # legado fornecedor
    "profissional": "professional",
    "escalar": "scale",
    "expandir": "scale",
    "rede": "scale",  # legado fornecedor
    "escala": "scale",
    "pro": "enterprise",
    "hub": "enterprise",
    "distribuidor": "enterprise",  # legado fornecedor
    "empresarial": "enterprise",
}


def plano_slug_banco(plano: str | None) -> str:
    """Valor aceito por tbl_tenant.plano: starter | professional | scale | enterprise."""
    p = coerce_text(plano, "starter").lower().strip()
    p = _ALIASES_PLANO_BANCO.get(p, p)
    if p in _PLANOS_BANCO:
        return p
    return "starter"


def plano_slug_app(plano: str | None) -> str:
    """Alias legado; preferir plano_slug_banco."""
    return plano_slug_banco(plano)


def canais_resposta_por_plano(plano: str) -> list[str]:
    p = plano_slug_banco(plano)
    if p in ("scale", "enterprise"):
        return ["portal", "email", "whatsapp"]
    if p == "professional":
        return ["portal", "email"]
    return ["portal"]


def gerar_protocolo_chamado(conn, id_tenant: int) -> str:
    """
    Protocolo numérico: AA + id_tenant + sequencial de 6 dígitos (por tenant/ano).
    Ex.: tenant 15, 1º chamado de 2026 → 2615000001
    """
    agora = datetime.now(timezone.utc)
    ano = agora.year
    aa = ano % 100
    prefixo = f"{aa:02d}{int(id_tenant)}"

    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(
            MAX(
                CAST(RIGHT(protocolo, 6) AS INTEGER)
            ),
            0
        ) + 1
        FROM tbl_chamado
        WHERE id_tenant = %s
          AND protocolo ~ %s
        """,
        (id_tenant, f"^{prefixo}[0-9]{{6}}$"),
    )
    seq = int(cur.fetchone()[0] or 1)
    return f"{prefixo}{seq:06d}"


def contar_chamados_mes_corrente(conn, id_tenant: int) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM tbl_chamado
        WHERE id_tenant = %s
          AND EXTRACT(YEAR FROM data_abertura) = EXTRACT(YEAR FROM CURRENT_DATE)
          AND EXTRACT(MONTH FROM data_abertura) = EXTRACT(MONTH FROM CURRENT_DATE)
        """,
        (id_tenant,),
    )
    return int(cur.fetchone()[0] or 0)


@global_bp.get("/api/contexto")
@login_obrigatorio()
def api_contexto():
    return jsonify(
        id_usuario=session.get("id_usuario"),
        id_tenant=session.get("id_tenant"),
        id_perfil=session.get("id_perfil"),
        perfil_codigo=session.get("perfil_codigo"),
        permissoes=session.get("permissoes"),
        eh_desenvolvedor=session.get("eh_desenvolvedor"),
        nome=session.get("nome"),
        email=session.get("email"),
        tenant_nome=session.get("tenant_nome"),
        tenant_slug=session.get("tenant_slug"),
    )
