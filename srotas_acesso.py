# DropNexo — acesso público, autenticação e cadastro
from __future__ import annotations


# --- srotas_public ---
from flask import Blueprint, render_template, url_for

from global_utils import INTEGRACOES_CANAIS_PREVISAO, obter_base_url
from sistema.planos.srotas_planos import catalogo_planos_home, landing_perfil

public_bp = Blueprint("public", __name__)




@public_bp.get("/")
def home():
    planos_home = catalogo_planos_home()
    return render_template(
        "home.html",
        url_home=url_for("public.home"),
        integracoes_previsao=INTEGRACOES_CANAIS_PREVISAO,
        url_login=url_for("auth.pagina_login"),
        url_cadastro_fornecedor=url_for("cadastro.pagina_cadastro", tipo="fornecedor"),
        url_cadastro_vendedor=url_for("cadastro.pagina_cadastro", tipo="vendedor"),
        url_para_vendedores=url_for("public.para_vendedores"),
        url_para_fornecedores=url_for("public.para_fornecedores"),
    )


@public_bp.get("/para-vendedores")
def para_vendedores():
    planos_home = catalogo_planos_home()
    return render_template(
        "landing_perfil.html",
        landing=landing_perfil("vendedor"),
        planos=planos_home["vendedor"],
        url_home=url_for("public.home"),
        url_login=url_for("auth.pagina_login"),
        url_cadastro=url_for("cadastro.pagina_cadastro", tipo="vendedor"),
        url_para_vendedores=url_for("public.para_vendedores"),
        url_para_fornecedores=url_for("public.para_fornecedores"),
        url_outro_perfil=url_for("public.para_fornecedores"),
        outro_perfil_label="Para fornecedores",
        canonical_url=f"{obter_base_url().rstrip('/')}/para-vendedores",
    )


@public_bp.get("/para-fornecedores")
def para_fornecedores():
    planos_home = catalogo_planos_home()
    return render_template(
        "landing_perfil.html",
        landing=landing_perfil("fornecedor"),
        planos=planos_home["fornecedor"],
        url_home=url_for("public.home"),
        url_login=url_for("auth.pagina_login"),
        url_cadastro=url_for("cadastro.pagina_cadastro", tipo="fornecedor"),
        url_para_vendedores=url_for("public.para_vendedores"),
        url_para_fornecedores=url_for("public.para_fornecedores"),
        url_outro_perfil=url_for("public.para_vendedores"),
        outro_perfil_label="Para vendedores",
        canonical_url=f"{obter_base_url().rstrip('/')}/para-fornecedores",
    )


# --- srotas_auth ---
import logging

import bcrypt
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from global_utils import (
    PERFIL_LABEL,
    Var_ConectarBanco,
    agora_utc,
    aplicar_permissoes_na_sessao,
    gerar_hmac_token,
    is_modo_producao,
    login_obrigatorio,
    validar_politica_senha,
)

_log_auth = logging.getLogger(__name__)


def _aplicar_tenant_na_sessao(
    conn,
    *,
    id_usuario: int,
    id_tenant: int,
    tenant_nome: str,
    tenant_slug: str,
    plano: str,
    id_perfil: int,
    perfil_codigo: str,
    tipo_negocio: str = "vendedor",
    nome: str | None = None,
    email: str | None = None,
    eh_desenvolvedor: bool | None = None,
) -> None:
    session["id_usuario"] = id_usuario
    session["id_tenant"] = id_tenant
    session["tenant_nome"] = tenant_nome
    session["tenant_slug"] = tenant_slug
    session["tenant_plano"] = plano
    session["tenant_tipo_negocio"] = tipo_negocio
    from srotas_plataforma import modulo_padrao

    session["modulo_ativo"] = modulo_padrao(tipo_negocio)
    session["papel"] = (perfil_codigo or "visualizador").lower()
    if nome is not None:
        session["nome"] = nome
    if email is not None:
        session["email"] = email
    if eh_desenvolvedor is not None:
        session["eh_desenvolvedor"] = bool(eh_desenvolvedor)
    aplicar_permissoes_na_sessao(
        conn,
        id_perfil=id_perfil,
        eh_desenvolvedor=bool(session.get("eh_desenvolvedor")),
    )


auth_bp = Blueprint("auth", __name__)




@auth_bp.get("/login")
def pagina_login():
    return render_template("login.html")


@auth_bp.get("/definir-senha")
def pagina_definir_senha():
    return render_template("definir_senha.html")


@auth_bp.post("/api/auth/login")
def api_login():
    dados = request.get_json(silent=True) or {}
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""

    if not email or not senha:
        return jsonify(success=False, message="Informe e-mail e senha."), 400

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id, u.senha_hash, u.ativo, u.nome, u.email, u.token_ativacao,
                   u.eh_desenvolvedor,
                   t.id, t.nome, t.slug, t.plano, t.tipo_negocio,
                   ut.id_perfil, pf.codigo, ut.id
            FROM tbl_usuario u
            JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.ativo = TRUE
            JOIN tbl_tenant t ON t.id = ut.id_tenant AND t.ativo = TRUE
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE u.email = %s
            ORDER BY ut.ultimo_acesso_em DESC NULLS LAST, t.id DESC
            LIMIT 1
            """,
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="E-mail ou senha inválidos."), 401

        (
            id_u,
            senha_hash,
            ativo,
            nome,
            email_db,
            token_ativacao,
            eh_desenvolvedor,
            id_tenant,
            tenant_nome,
            tenant_slug,
            plano,
            tipo_negocio,
            id_perfil,
            perfil_codigo,
            id_vinculo,
        ) = row

        if token_ativacao:
            return jsonify(
                success=False,
                message="Complete a ativação: use o link enviado por e-mail para criar sua senha.",
            ), 403

        if not ativo or not senha_hash:
            return jsonify(success=False, message="Conta inativa."), 403

        try:
            ok = bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
        except Exception:
            ok = False
        if not ok:
            return jsonify(success=False, message="E-mail ou senha inválidos."), 401

        session.clear()
        _aplicar_tenant_na_sessao(
            conn,
            id_usuario=id_u,
            id_tenant=id_tenant,
            tenant_nome=tenant_nome,
            tenant_slug=tenant_slug,
            plano=plano,
            id_perfil=id_perfil,
            perfil_codigo=perfil_codigo,
            tipo_negocio=tipo_negocio or "vendedor",
            nome=nome,
            email=email_db,
            eh_desenvolvedor=eh_desenvolvedor,
        )

        cur.execute(
            "UPDATE tbl_usuario_tenant SET ultimo_acesso_em = NOW() WHERE id = %s",
            (id_vinculo,),
        )
        conn.commit()
        return jsonify(success=True, redirect=url_for("dashboard.index"))
    except Exception as e:
        _log_auth.exception("api_login falhou")
        if is_modo_producao():
            msg = "Erro interno no servidor. Verifique banco de dados e logs (dropnexo.service)."
        else:
            msg = str(e) or "Erro interno no login."
        return jsonify(success=False, message=msg), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@auth_bp.get("/api/auth/validar-token")
def api_validar_token():
    raw = (request.args.get("token") or "").strip()
    if not raw:
        return jsonify(valido=False, message="Token ausente."), 400
    token_hash = gerar_hmac_token(raw)

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome, email FROM tbl_usuario
            WHERE token_ativacao = %s AND token_expira_em >= %s
            LIMIT 1
            """,
            (token_hash, agora_utc()),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(valido=False, message="Token inválido ou expirado."), 400
        _id, nome, email = row
        return jsonify(valido=True, nome=nome or "", email=email or "")
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@auth_bp.post("/api/auth/definir-senha")
def api_definir_senha():
    dados = request.get_json(silent=True) or {}
    raw = (dados.get("token") or "").strip()
    senha = dados.get("senha") or ""
    confirma = dados.get("confirmar") or ""

    if not raw:
        return jsonify(success=False, message="Token ausente."), 400
    ok_senha, msg_senha = validar_politica_senha(senha, confirma)
    if not ok_senha:
        return jsonify(success=False, message=msg_senha), 400

    token_hash = gerar_hmac_token(raw)
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_usuario
            SET senha_hash = %s, ativo = TRUE, token_ativacao = NULL, token_expira_em = NULL
            WHERE token_ativacao = %s AND token_expira_em >= %s
            RETURNING id
            """,
            (senha_hash, token_hash, agora_utc()),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Token inválido ou expirado."), 400
        id_usuario = row[0]
        cur.execute(
            """
            UPDATE tbl_tenant t SET ativo = TRUE
            FROM tbl_usuario_tenant ut
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil AND pf.codigo = 'dono'
            WHERE ut.id_tenant = t.id AND ut.id_usuario = %s
              AND ut.ativo = TRUE AND t.ativo = FALSE
            """,
            (id_usuario,),
        )
        conn.commit()
        return jsonify(success=True, redirect=url_for("auth.pagina_login"))
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify(success=False, message=str(e)), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@auth_bp.post("/api/auth/logout")
def api_logout():
    session.clear()
    return jsonify(success=True, redirect=url_for("public.home"))


def _redirect_seguro(valor) -> str:
    dest = (valor or "").strip()
    if dest.startswith("/") and not dest.startswith("//"):
        return dest
    return url_for("dashboard.index")


def _listar_fornecedores_dev(cur, id_tenant_atual: int | None) -> list[dict]:
    cur.execute(
        """
        SELECT t.id, t.nome, t.slug, t.plano, t.tipo_negocio, t.cidade, t.uf, t.documento
        FROM tbl_tenant t
        WHERE t.ativo = TRUE AND t.tipo_negocio IN ('fornecedor', 'hibrido')
        ORDER BY t.nome ASC
        """
    )
    itens = []
    for row in cur.fetchall():
        tid, nome, slug, plano, tipo_negocio, cidade, uf, documento = row
        meta_partes = []
        if cidade and uf:
            meta_partes.append(f"{cidade}/{uf}")
        elif cidade:
            meta_partes.append(str(cidade))
        if documento:
            meta_partes.append(str(documento))
        itens.append(
            {
                "id": tid,
                "nome": nome or "",
                "slug": slug or "",
                "plano": plano or "",
                "tipo_negocio": tipo_negocio or "",
                "papel": "dono",
                "papel_label": "Fornecedor",
                "perfil_codigo": "dono",
                "perfil_nome": "Dono da conta",
                "meta": " · ".join(meta_partes),
                "is_atual": tid == id_tenant_atual,
            }
        )
    return itens


@auth_bp.get("/api/auth/tenants")
@login_obrigatorio(exigir_tenant=False)
def api_listar_tenants():
    id_usuario = session["id_usuario"]
    id_tenant_atual = session.get("id_tenant")
    eh_dev = bool(session.get("eh_desenvolvedor"))

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()

        if eh_dev:
            itens = _listar_fornecedores_dev(cur, id_tenant_atual)
            return jsonify(
                success=True,
                itens=itens,
                id_tenant_atual=id_tenant_atual,
                modo_dev_fornecedor=True,
            )

        cur.execute(
            """
            SELECT t.id, t.nome, t.slug, t.plano, t.tipo_negocio, pf.codigo, pf.nome
            FROM tbl_usuario_tenant ut
            JOIN tbl_tenant t ON t.id = ut.id_tenant AND t.ativo = TRUE
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE ut.id_usuario = %s AND ut.ativo = TRUE
            ORDER BY ut.ultimo_acesso_em DESC NULLS LAST, t.nome ASC
            """,
            (id_usuario,),
        )
        itens = []
        for row in cur.fetchall():
            tid, nome, slug, plano, tipo_negocio, perfil_codigo, perfil_nome = row
            perfil_key = (perfil_codigo or "visualizador").lower()
            itens.append(
                {
                    "id": tid,
                    "nome": nome or "",
                    "slug": slug or "",
                    "plano": plano or "",
                    "tipo_negocio": tipo_negocio or "",
                    "papel": perfil_key,
                    "papel_label": PERFIL_LABEL.get(perfil_key, perfil_nome or perfil_key),
                    "perfil_codigo": perfil_key,
                    "perfil_nome": perfil_nome,
                    "is_atual": tid == id_tenant_atual,
                }
            )
        return jsonify(success=True, itens=itens, id_tenant_atual=id_tenant_atual)
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@auth_bp.post("/api/auth/trocar-tenant")
@login_obrigatorio(exigir_tenant=False)
def api_trocar_tenant():
    dados = request.get_json(silent=True) or {}
    try:
        id_tenant = int(dados.get("id_tenant"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Tenant inválido."), 400

    redirect = _redirect_seguro(dados.get("redirect"))
    id_usuario = session["id_usuario"]
    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.nome, u.email, u.eh_desenvolvedor,
                   t.id, t.nome, t.slug, t.plano, t.tipo_negocio,
                   ut.id_perfil, pf.codigo, ut.id
            FROM tbl_usuario u
            JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.ativo = TRUE
            JOIN tbl_tenant t ON t.id = ut.id_tenant AND t.ativo = TRUE
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE u.id = %s AND t.id = %s
            LIMIT 1
            """,
            (id_usuario, id_tenant),
        )
        row = cur.fetchone()

        if not row and session.get("eh_desenvolvedor"):
            cur.execute(
                """
                SELECT u.nome, u.email, u.eh_desenvolvedor,
                       t.id, t.nome, t.slug, t.plano, t.tipo_negocio
                FROM tbl_usuario u
                CROSS JOIN tbl_tenant t
                WHERE u.id = %s AND t.id = %s AND t.ativo = TRUE
                  AND t.tipo_negocio IN ('fornecedor', 'hibrido')
                LIMIT 1
                """,
                (id_usuario, id_tenant),
            )
            row_dev = cur.fetchone()
            if row_dev:
                nome, email, eh_dev, tid, tenant_nome, tenant_slug, plano, tipo_negocio = row_dev
                cur.execute("SELECT id FROM tbl_perfil WHERE codigo = 'dono' LIMIT 1")
                perfil_row = cur.fetchone()
                id_perfil = perfil_row[0] if perfil_row else 1
                _aplicar_tenant_na_sessao(
                    conn,
                    id_usuario=id_usuario,
                    id_tenant=tid,
                    tenant_nome=tenant_nome,
                    tenant_slug=tenant_slug,
                    plano=plano,
                    id_perfil=id_perfil,
                    perfil_codigo="dono",
                    tipo_negocio=tipo_negocio or "fornecedor",
                    nome=nome,
                    email=email,
                    eh_desenvolvedor=eh_dev,
                )
                conn.commit()
                return jsonify(success=True, redirect=redirect)

        if not row:
            return jsonify(success=False, message="Você não tem acesso a esta conta."), 403

        (
            nome,
            email,
            eh_dev,
            tid,
            tenant_nome,
            tenant_slug,
            plano,
            tipo_negocio,
            id_perfil,
            perfil_codigo,
            id_vinculo,
        ) = row

        _aplicar_tenant_na_sessao(
            conn,
            id_usuario=id_usuario,
            id_tenant=tid,
            tenant_nome=tenant_nome,
            tenant_slug=tenant_slug,
            plano=plano,
            id_perfil=id_perfil,
            perfil_codigo=perfil_codigo,
            tipo_negocio=tipo_negocio or "vendedor",
            nome=nome,
            email=email,
            eh_desenvolvedor=eh_dev,
        )

        cur.execute(
            "UPDATE tbl_usuario_tenant SET ultimo_acesso_em = NOW() WHERE id = %s",
            (id_vinculo,),
        )
        conn.commit()
        return jsonify(success=True, redirect=redirect)
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@auth_bp.post("/api/auth/trocar-modulo")
@login_obrigatorio()
def api_trocar_modulo():
    from srotas_plataforma import modulos_disponiveis_sessao, rotulo_modulo

    dados = request.get_json(silent=True) or {}
    codigo = (dados.get("modulo") or "").strip().lower()
    if codigo not in modulos_disponiveis_sessao():
        return jsonify(success=False, message="Módulo indisponível para esta conta."), 400
    session["modulo_ativo"] = codigo
    return jsonify(
        success=True,
        modulo=codigo,
        rotulo=rotulo_modulo(codigo),
        redirect=url_for("dashboard.index"),
    )


# --- srotas_cadastro ---
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from api.brevo.srotas_brevo import enviar_email
from global_utils import (
    Var_ConectarBanco,
    agora_utc,
    gerar_hmac_token,
    id_perfil_por_codigo,
    obter_base_url,
    valida_email,
)
from fornecedor.segmentos.servico_segmentos import listar_segmentos_plataforma, salvar_segmentos_fornecedor

cadastro_bp = Blueprint("cadastro", __name__)

TIPOS_NEGOCIO = frozenset({"fornecedor", "vendedor"})




def _email_links_institucionais() -> dict:
    base = obter_base_url()
    return {
        "url_politica_privacidade": os.getenv("URL_POLITICA_PRIVACIDADE") or f"{base}/privacidade",
        "url_politica_interna": os.getenv("URL_POLITICA_INTERNA") or f"{base}/politica-interna",
        "url_dpo": os.getenv("URL_DPO") or f"{base}/dpo",
    }


def _html_email_ativacao(*, nome_usuario: str, nome_conta: str, link_ativacao: str, horas_validade: int) -> str:
    return render_template(
        "cadastro/emails/ativacao_conta.html",
        titulo_email="Ativação de acesso • DropNexo",
        nome_usuario=nome_usuario,
        nome_conta=nome_conta,
        link_ativacao=link_ativacao,
        horas_validade=horas_validade,
        ano=datetime.now().year,
        **_email_links_institucionais(),
    )


def _html_email_nova_conta_vinculada(*, nome_usuario: str, nome_conta: str, link_login: str) -> str:
    return render_template(
        "cadastro/emails/nova_conta_vinculada.html",
        titulo_email="Nova conta vinculada • DropNexo",
        nome_usuario=nome_usuario,
        nome_conta=nome_conta,
        link_login=link_login,
        ano=datetime.now().year,
        **_email_links_institucionais(),
    )


def _enviar_email_ativacao_conta(**kwargs) -> tuple[bool, str]:
    html = _html_email_ativacao(**kwargs)
    ok, msg, _ = enviar_email(
        [kwargs["email"]],
        "Ativação de acesso • DropNexo",
        html,
        tag="dropnexo_cadastro",
    )
    return ok, msg


def _enviar_email_nova_conta_vinculada(**kwargs) -> tuple[bool, str]:
    html = _html_email_nova_conta_vinculada(**kwargs)
    ok, msg, _ = enviar_email(
        [kwargs["email"]],
        "Nova conta vinculada • DropNexo",
        html,
        tag="dropnexo_cadastro_nova_conta",
    )
    return ok, msg


def _so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def _normalizar_slug(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64] if s else ""


def _valida_uf(uf: str) -> bool:
    ufs = {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
        "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
        "SP", "SE", "TO",
    }
    return (uf or "").strip().upper() in ufs


def _valida_documento(tipo_pessoa: str, documento: str) -> bool:
    if tipo_pessoa == "F":
        return len(documento) == 11
    if tipo_pessoa == "J":
        return len(documento) == 14
    return False


@cadastro_bp.get("/cadastro")
def pagina_cadastro():
    tipo = (request.args.get("tipo") or "").strip().lower()
    if tipo not in TIPOS_NEGOCIO:
        return redirect(url_for("public.home") + "#cadastro")
    return render_template(
        "frm_cadastro.html",
        tipo_negocio=tipo,
        titulo_tipo="Fornecedor" if tipo == "fornecedor" else "Vendedor",
    )


@cadastro_bp.get("/api/cadastro/segmentos")
def api_cadastro_segmentos():
    """Lista segmentos marketplace para o formulário de cadastro (público)."""
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(success=True, segmentos=listar_segmentos_plataforma(cur))
    finally:
        conn.close()


@cadastro_bp.post("/api/cadastro/novo")
def api_cadastro_novo():
    dados = request.get_json(silent=True) or {}

    tipo_negocio = (dados.get("tipo_negocio") or "").strip().lower()
    tipo_pessoa = (dados.get("tipo_pessoa") or "").strip().upper()
    documento = _so_digitos(dados.get("documento") or "")
    nome_completo = (dados.get("nome_completo") or "").strip()
    nome_tenant = (dados.get("nome") or "").strip()
    slug = _normalizar_slug(dados.get("slug") or "")
    nome_usuario = (dados.get("nome_usuario") or "").strip()
    email = (dados.get("email") or "").strip().lower()
    whatsapp = _so_digitos(dados.get("whatsapp") or "")
    cep = _so_digitos(dados.get("cep") or "")
    logradouro = (dados.get("logradouro") or "").strip()
    numero = (dados.get("numero") or "").strip()
    complemento = (dados.get("complemento") or "").strip() or None
    bairro = (dados.get("bairro") or "").strip()
    cidade = (dados.get("cidade") or "").strip()
    uf = (dados.get("uf") or "").strip().upper()

    if tipo_negocio not in TIPOS_NEGOCIO:
        return jsonify(success=False, message="Informe se você é fornecedor ou vendedor."), 400
    if tipo_pessoa not in ("F", "J"):
        return jsonify(success=False, message="Selecione Pessoa Física ou Jurídica."), 400
    if not _valida_documento(tipo_pessoa, documento):
        doc_label = "CPF" if tipo_pessoa == "F" else "CNPJ"
        return jsonify(success=False, message=f"{doc_label} inválido."), 400
    if len(nome_completo) < 2:
        return jsonify(success=False, message="Informe o nome completo ou razão social."), 400
    if len(nome_tenant) < 2:
        return jsonify(success=False, message="Informe o nome de exibição da conta."), 400
    if not slug or len(slug) < 2:
        return jsonify(success=False, message="Identificador (slug) inválido."), 400
    if len(nome_usuario) < 2:
        return jsonify(success=False, message="Informe o nome do responsável."), 400
    if not valida_email(email):
        return jsonify(success=False, message="E-mail inválido."), 400
    if len(whatsapp) < 10 or len(whatsapp) > 15:
        return jsonify(success=False, message="WhatsApp inválido."), 400
    if len(cep) != 8:
        return jsonify(success=False, message="CEP inválido."), 400
    if not logradouro or not numero or not bairro or not cidade:
        return jsonify(success=False, message="Preencha o endereço completo."), 400
    if not _valida_uf(uf):
        return jsonify(success=False, message="UF inválida."), 400

    ids_segmentos_nichos = dados.get("ids_segmentos_nichos") or []
    if tipo_negocio == "fornecedor":
        if not isinstance(ids_segmentos_nichos, list) or not ids_segmentos_nichos:
            return jsonify(
                success=False,
                message="Selecione ao menos um segmento (nicho) em que sua empresa atua.",
            ), 400

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM tbl_tenant WHERE slug = %s LIMIT 1", (slug,))
        if cur.fetchone():
            return jsonify(success=False, message="Este identificador (slug) já está em uso."), 409

        cur.execute("SELECT 1 FROM tbl_tenant WHERE documento = %s LIMIT 1", (documento,))
        if cur.fetchone():
            return jsonify(success=False, message="Este CPF/CNPJ já possui cadastro."), 409

        id_perfil_dono = id_perfil_por_codigo(conn, "dono")
        if not id_perfil_dono:
            return jsonify(success=False, message="Perfil 'dono' não configurado no sistema."), 500

        cur.execute(
            "SELECT id, ativo, senha_hash, token_ativacao FROM tbl_usuario WHERE email = %s LIMIT 1",
            (email,),
        )
        row_usuario = cur.fetchone()

        cur.execute(
            """
            INSERT INTO tbl_tenant (
                tipo_pessoa, tipo_negocio, documento, nome_completo, nome, slug, plano, ativo,
                cep, logradouro, numero, complemento, bairro, cidade, uf
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'starter', %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tipo_pessoa,
                tipo_negocio,
                documento,
                nome_completo,
                nome_tenant,
                slug,
                False,
                cep,
                logradouro,
                numero,
                complemento,
                bairro,
                cidade,
                uf,
            ),
        )
        id_tenant = cur.fetchone()[0]

        if tipo_negocio == "fornecedor":
            ids_parsed: list[int] = []
            for x in ids_segmentos_nichos:
                try:
                    ids_parsed.append(int(x))
                except (TypeError, ValueError):
                    continue
            salvar_segmentos_fornecedor(cur, id_tenant, ids_parsed, exigir_minimo=True)

        if row_usuario:
            id_usuario, usuario_ativo, senha_hash, token_ativacao = row_usuario
            usuario_ja_ativo = bool(usuario_ativo and senha_hash and not token_ativacao)

            cur.execute(
                "INSERT INTO tbl_usuario_tenant (id_usuario, id_tenant, id_perfil, ativo) VALUES (%s, %s, %s, TRUE)",
                (id_usuario, id_tenant, id_perfil_dono),
            )

            if usuario_ja_ativo:
                cur.execute("UPDATE tbl_tenant SET ativo = TRUE WHERE id = %s", (id_tenant,))
                cur.execute(
                    "UPDATE tbl_usuario SET nome = %s, whatsapp = %s WHERE id = %s",
                    (nome_usuario, whatsapp, id_usuario),
                )
                conn.commit()
                ok, msg = _enviar_email_nova_conta_vinculada(
                    email=email,
                    nome_usuario=nome_usuario,
                    nome_conta=nome_tenant,
                    link_login=f"{obter_base_url()}/login",
                )
                if not ok:
                    return jsonify(success=False, message=f"Conta criada, mas o e-mail falhou: {msg}"), 500
                return jsonify(
                    success=True,
                    message="Nova conta criada. Use seu e-mail e senha para entrar.",
                    redirect=url_for("auth.pagina_login"),
                )

            raw = secrets.token_urlsafe(32)
            token_hash = gerar_hmac_token(raw)
            expira = agora_utc() + timedelta(hours=int(os.getenv("TOKEN_ATIVACAO_HORAS", "48")))
            cur.execute(
                "UPDATE tbl_usuario SET nome = %s, whatsapp = %s, token_ativacao = %s, token_expira_em = %s WHERE id = %s",
                (nome_usuario, whatsapp, token_hash, expira, id_usuario),
            )
            conn.commit()
            link = f"{obter_base_url()}/definir-senha?token={raw}"
            horas = int(os.getenv("TOKEN_ATIVACAO_HORAS", "48"))
            ok, msg = _enviar_email_ativacao_conta(
                email=email,
                nome_usuario=nome_usuario,
                nome_conta=nome_tenant,
                link_ativacao=link,
                horas_validade=horas,
            )
            if not ok:
                return jsonify(success=False, message=f"Conta criada, mas o e-mail falhou: {msg}"), 500
            return jsonify(success=True, message="Enviamos um e-mail com o link para você definir sua senha.")

        raw = secrets.token_urlsafe(32)
        token_hash = gerar_hmac_token(raw)
        expira = agora_utc() + timedelta(hours=int(os.getenv("TOKEN_ATIVACAO_HORAS", "48")))

        cur.execute(
            """
            INSERT INTO tbl_usuario (nome, email, whatsapp, senha_hash, ativo, token_ativacao, token_expira_em)
            VALUES (%s, %s, %s, NULL, FALSE, %s, %s)
            RETURNING id
            """,
            (nome_usuario, email, whatsapp, token_hash, expira),
        )
        id_usuario = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO tbl_usuario_tenant (id_usuario, id_tenant, id_perfil, ativo) VALUES (%s, %s, %s, TRUE)",
            (id_usuario, id_tenant, id_perfil_dono),
        )
        conn.commit()

        link = f"{obter_base_url()}/definir-senha?token={raw}"
        horas = int(os.getenv("TOKEN_ATIVACAO_HORAS", "48"))
        ok, msg = _enviar_email_ativacao_conta(
            email=email,
            nome_usuario=nome_usuario,
            nome_conta=nome_tenant,
            link_ativacao=link,
            horas_validade=horas,
        )
        if not ok:
            return jsonify(success=False, message=f"Conta criada, mas o e-mail falhou: {msg}"), 500
        return jsonify(success=True, message="Enviamos um e-mail com o link para você definir sua senha.")
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        err = str(e).strip()
        if "uq_" in err and "dono" in err:
            return jsonify(success=False, message="Esta conta já possui um dono ativo."), 409
        return jsonify(success=False, message=err or "Erro ao processar cadastro."), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def init_app(app):
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cadastro_bp)
