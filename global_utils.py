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

    for pasta in ("fornecedor", "vendedor", "sistema"):
        base = raiz_projeto / pasta
        if base.is_dir():
            for tpl_dir in base.rglob("templates"):
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
        if not is_modo_producao():
            return url_for("static", filename=MARCA_ASSET_ICONE)
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
    "admin": "Administrador",
    "financeiro": "Financeiro",
    "vendedor": "Vendedor",
    "operador": "Operador",
    "visualizador": "Visualizador",
}


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


def aplicar_permissoes_na_sessao(conn, *, id_perfil: int, eh_desenvolvedor: bool = False) -> None:
    """Carrega perfil e permissões na sessão após login ou troca de tenant."""
    cur = conn.cursor()
    cur.execute(
        "SELECT codigo, nome FROM tbl_perfil WHERE id = %s LIMIT 1",
        (id_perfil,),
    )
    row = cur.fetchone()
    cur.close()
    if row:
        session["id_perfil"] = id_perfil
        session["perfil_codigo"] = row[0]
        session["perfil_nome"] = row[1]
        session["papel"] = row[0]
    if eh_desenvolvedor:
        session["permissoes"] = ["*"]
    else:
        session["permissoes"] = listar_permissoes_do_perfil(conn, id_perfil)


def usuario_tem_permissao(codigo: str) -> bool:
    """Desenvolvedor (eh_desenvolvedor) ignora RBAC — acesso total."""
    if session.get("eh_desenvolvedor"):
        return True
    perms = session.get("permissoes") or []
    if "*" in perms:
        return True
    return (codigo or "").strip() in perms


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
            from srotas_plataforma import garantir_modulo_sessao

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


def plano_slug_app(plano: str | None) -> str:
    """Slug interno (sessão, billing, Efí): starter | profissional | empresarial."""
    p = coerce_text(plano, "starter").lower().strip()
    if p in ("professional",):
        return "profissional"
    if p in ("enterprise",):
        return "empresarial"
    if p in ("profissional", "empresarial", "starter"):
        return p
    return "starter"


def plano_slug_banco(plano: str | None) -> str:
    """Valor aceito por tbl_tenant.plano (CHECK): starter | professional | enterprise."""
    p = plano_slug_app(plano)
    if p == "profissional":
        return "professional"
    if p == "empresarial":
        return "enterprise"
    return "starter"


def canais_resposta_por_plano(plano: str) -> list[str]:
    p = (plano or "starter").lower()
    if p in ("empresarial", "enterprise"):
        return ["portal", "email", "whatsapp"]
    if p in ("profissional", "professional"):
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
