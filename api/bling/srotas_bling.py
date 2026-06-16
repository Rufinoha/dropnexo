# api/bling/srotas_bling.py — rotas OAuth, config e sync Bling
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_file, session, url_for

from api.bling.cliente import (
    bling_configurado,
    gerar_state_oauth,
    redirect_uri_oauth,
    renovar_access_token,
    trocar_code_por_tokens,
    url_autorizacao,
    _salvar_tokens,
)
from api.bling.config_padrao import aplicar_defaults_conexao, garantir_config_contexto
from api.bling.homologacao import executar_homologacao
from api.bling.manual_conteudo import (
    MANUAL_BLING_BOTOES_FORNECEDOR,
    MANUAL_BLING_CONFIG_FORNECEDOR,
    MANUAL_BLING_PASSOS,
    MANUAL_IMAGENS_PERMITIDAS,
)
from api.bling.sync_categorias import listar_categorias_bling_flat
from api.bling.sync_produtos import importar_produtos
from api.bling.tokens import descriptografar_token
from global_utils import Var_ConectarBanco, agora_utc, login_obrigatorio, obter_url_site_publico, usuario_tem_permissao
from srotas_plataforma import garantir_modulo_sessao, rotulo_modulo

_MOD_BLING = Path(__file__).resolve().parent

bling_bp = Blueprint(
    "bling",
    __name__,
    root_path=str(_MOD_BLING),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/api/bling",
)


def init_app(app):
    app.register_blueprint(bling_bp)


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]


def _urls_manual_publico(base: str) -> dict[str, str]:
    return {
        "url_login": f"{base}/login",
        "url_cadastro_fornecedor": f"{base}/cadastro?tipo=fornecedor",
        "url_cadastro_vendedor": f"{base}/cadastro?tipo=vendedor",
        "url_home": f"{base}/",
    }


def _passos_manual_com_urls(base: str) -> list[dict]:
    urls = _urls_manual_publico(base)
    passos = []
    for p in MANUAL_BLING_PASSOS:
        item = {**p, "img_url": url_for("bling.ajuda_bling_imagem", nome=p["img"])}
        if "{" in item.get("texto", ""):
            item["texto"] = item["texto"].format(**urls)
        passos.append(item)
    return passos


@bling_bp.get("/ajuda/bling")
def ajuda_bling():
    """Manual público — conexão OAuth com o Bling."""
    base = obter_url_site_publico()
    urls = _urls_manual_publico(base)
    return render_template(
        "ajuda_bling.html",
        passos=_passos_manual_com_urls(base),
        config_fornecedor=MANUAL_BLING_CONFIG_FORNECEDOR,
        botoes_fornecedor=MANUAL_BLING_BOTOES_FORNECEDOR,
        url_home=url_for("public.home"),
        url_login=url_for("auth.pagina_login"),
        url_login_publico=urls["url_login"],
        url_cadastro_fornecedor=urls["url_cadastro_fornecedor"],
        url_cadastro_vendedor=urls["url_cadastro_vendedor"],
        css_url=url_for("bling.static", filename="style/ajuda_bling.css"),
    )


@bling_bp.get("/ajuda/bling/imagens/<path:nome>")
def ajuda_bling_imagem(nome: str):
    if nome not in MANUAL_IMAGENS_PERMITIDAS:
        abort(404)
    arquivo = _MOD_BLING / "manual" / nome
    if not arquivo.is_file():
        abort(404)
    mime, _ = mimetypes.guess_type(str(arquivo))
    return send_file(arquivo, mimetype=mime or "image/jpeg", max_age=86400)


def _pode_integracoes() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
    )


def _pode_bling_sync() -> bool:
    """Integrações ou edição de catálogo (importar do Bling na lista de produtos)."""
    return _pode_integracoes() or usuario_tem_permissao("catalogos.editar")


def _config_dict(row) -> dict:
    return {
        "contexto": row[0],
        "fonte_principal": row[1],
        "modo_imagem": row[2],
        "produtos_modo": row[3],
        "estoque_modo": row[4],
        "pedidos_modo": row[5],
        "ultima_sync_produtos": row[6].isoformat() if row[6] else None,
        "ultima_sync_estoque": row[7].isoformat() if row[7] else None,
        "ultima_sync_pedidos": row[8].isoformat() if row[8] else None,
    }


@bling_bp.get("/api/integracoes/bling/status")
@login_obrigatorio()
def api_status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status, conectado_em, ultimo_erro, token_expires_em
            FROM tbl_integracao_bling WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        conectado = bool(row and row[0] == "conectado")
        contexto = garantir_modulo_sessao()
        if conectado:
            garantir_config_contexto(cur, id_tenant, contexto)
            conn.commit()
        cur.execute(
            """
            SELECT contexto, fonte_principal, modo_imagem, produtos_modo, estoque_modo, pedidos_modo,
                   ultima_sync_produtos, ultima_sync_estoque, ultima_sync_pedidos
            FROM tbl_integracao_bling_config WHERE id_tenant = %s ORDER BY contexto
            """,
            (id_tenant,),
        )
        configs = [_config_dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT status, resumo, criado_em FROM tbl_integracao_log
            WHERE id_tenant = %s AND provedor = 'bling'
            ORDER BY criado_em DESC LIMIT 8
            """,
            (id_tenant,),
        )
        logs = [
            {
                "status": r[0],
                "resumo": r[1],
                "criado_em": r[2].isoformat() if r[2] else None,
            }
            for r in cur.fetchall()
        ]

        return jsonify(
            success=True,
            app_configurado=bling_configurado(),
            redirect_uri=redirect_uri_oauth(),
            conectado=conectado,
            contexto_modulo=garantir_modulo_sessao(),
            contexto_modulo_rotulo=rotulo_modulo(garantir_modulo_sessao()),
            conectado_em=row[1].isoformat() if row and row[1] else None,
            ultimo_erro=row[2] if row else None,
            token_expires_em=row[3].isoformat() if row and row[3] else None,
            configs=configs,
            logs=logs,
        )
    finally:
        conn.close()


@bling_bp.get("/api/integracoes/bling/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if not bling_configurado():
        return redirect(url_for("integracoes.pagina", erro="Integração Bling indisponível. Tente novamente mais tarde."))

    state = gerar_state_oauth()
    session["bling_oauth_state"] = state
    session["bling_oauth_tenant"] = session.get("id_tenant")
    session["bling_oauth_contexto"] = garantir_modulo_sessao()
    return redirect(url_autorizacao(state))


@bling_bp.get("/api/integracoes/bling/oauth/callback")
@login_obrigatorio()
def oauth_callback():
    if not _pode_integracoes():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = request.args.get("error")
    if erro:
        return redirect(url_for("integracoes.pagina", erro=erro))

    state = request.args.get("state") or ""
    code = request.args.get("code") or ""
    if not code or state != session.get("bling_oauth_state"):
        return redirect(url_for("integracoes.pagina", erro="state_invalido"))

    id_tenant = session.get("bling_oauth_tenant") or session.get("id_tenant")
    if not id_tenant:
        return redirect(url_for("integracoes.pagina", erro="sessao"))

    try:
        tokens = trocar_code_por_tokens(code)
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            from api.bling.cliente import _salvar_tokens

            _salvar_tokens(cur, int(id_tenant), tokens)
            contexto = session.get("bling_oauth_contexto") or garantir_modulo_sessao()
            aplicar_defaults_conexao(cur, int(id_tenant), contexto)
            conn.commit()
        finally:
            conn.close()
        session.pop("bling_oauth_state", None)
        session.pop("bling_oauth_contexto", None)
        return redirect(url_for("integracoes.pagina", conectado="bling"))
    except Exception as e:
        return redirect(url_for("integracoes.pagina", erro=str(e)[:120]))


@bling_bp.post("/api/integracoes/bling/desconectar")
@login_obrigatorio()
def desconectar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_integracao_bling SET
                status = 'desconectado',
                access_token_enc = NULL,
                refresh_token_enc = NULL,
                token_expires_em = NULL,
                ultimo_erro = NULL,
                atualizado_em = %s
            WHERE id_tenant = %s
            """,
            (agora_utc(), id_tenant),
        )
        conn.commit()
        return jsonify(success=True, message="Bling desconectado.")
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/config/salvar")
@login_obrigatorio()
def salvar_config():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or garantir_modulo_sessao() or "").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    def modo(campo: str, padrao: str) -> str:
        v = (body.get(campo) or padrao).strip()
        return v if v in ("importar", "exportar", "atualizar") else padrao

    fonte = (body.get("fonte_principal") or "bling").strip()
    if fonte not in ("bling", "dropnexo"):
        fonte = "bling"
    modo_img = (body.get("modo_imagem") or "link").strip()
    if modo_img not in ("link", "download"):
        modo_img = "link"

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        agora = agora_utc()
        cur.execute(
            """
            INSERT INTO tbl_integracao_bling_config (
                id_tenant, contexto, fonte_principal, modo_imagem,
                produtos_modo, estoque_modo, pedidos_modo, atualizado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
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
                contexto,
                fonte,
                modo_img,
                modo("produtos_modo", "importar"),
                modo("estoque_modo", "importar"),
                modo("pedidos_modo", "importar"),
                agora,
            ),
        )
        cur.execute(
            """
            UPDATE tbl_integracao_bling_config
            SET modo_imagem = %s, atualizado_em = %s
            WHERE id_tenant = %s
            """,
            (modo_img, agora, id_tenant),
        )
        conn.commit()
        return jsonify(success=True, message="Configuração salva.")
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/homologacao/executar")
@login_obrigatorio()
def homologacao_executar():
    """Executa o fluxo de homologação exigido pelo Bling (5 passos API)."""
    if not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Somente desenvolvedor."), 403
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if not bling_configurado():
        return jsonify(success=False, message="Credenciais Bling não configuradas."), 400

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status, access_token_enc, refresh_token_enc
            FROM tbl_integracao_bling WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de executar a homologação."), 400

        from api.bling.cliente import renovar_access_token

        access = descriptografar_token(row[1])
        refresh = descriptografar_token(row[2]) if row[2] else None
        refresh_holder = {"token": refresh}

        def refresh_fn() -> str:
            rt = refresh_holder["token"]
            if not rt:
                raise RuntimeError("Refresh token ausente. Reconecte o Bling.")
            payload = renovar_access_token(rt)
            refresh_holder["token"] = payload.get("refresh_token") or rt
            _salvar_tokens(cur, int(id_tenant), payload)
            conn.commit()
            return payload["access_token"]

        resultado = executar_homologacao(
            access,
            refresh_token_fn=refresh_fn if refresh else None,
        )
        return jsonify(success=resultado.sucesso, message=resultado.mensagem, dados=resultado.to_dict())
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/sync/produtos")
@login_obrigatorio()
def sync_produtos():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or garantir_modulo_sessao() or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    id_categoria_bling = (body.get("id_categoria_bling") or "").strip() or None
    raw_ids = body.get("ids_categorias_bling")
    ids_categorias_bling: list[str] | None = None
    if isinstance(raw_ids, list):
        ids_categorias_bling = [str(c).strip() for c in raw_ids if str(c or "").strip()]
    elif raw_ids:
        ids_categorias_bling = [str(raw_ids).strip()]
    incluir_subcategorias = body.get("incluir_subcategorias", True)
    if isinstance(incluir_subcategorias, str):
        incluir_subcategorias = incluir_subcategorias.lower() in ("1", "true", "sim", "yes")

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de sincronizar."), 400

        resultado = importar_produtos(
            cur,
            int(id_tenant),
            contexto,
            id_categoria_bling=id_categoria_bling,
            ids_categorias_bling=ids_categorias_bling,
            incluir_subcategorias=bool(incluir_subcategorias),
        )
        conn.commit()
        return jsonify(success=True, message=resultado["resumo"], dados=resultado)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.get("/api/integracoes/bling/categorias")
@login_obrigatorio()
def api_categorias_bling():
    """Lista categorias de produtos do Bling (árvore) para importação seletiva."""
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de listar categorias."), 400
    finally:
        conn.close()

    try:
        categorias = listar_categorias_bling_flat(int(id_tenant))
        return jsonify(success=True, categorias=categorias)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


@bling_bp.get("/api/produto-imagem/arquivo")
@login_obrigatorio()
def api_produto_imagem_arquivo():
    caminho = (request.args.get("caminho") or "").strip().replace("\\", "/")
    if not caminho or ".." in caminho.split("/"):
        return jsonify(success=False, message="Caminho inválido."), 400
    if not caminho.lower().startswith("upload/tenant"):
        return jsonify(success=False, message="Caminho não permitido."), 403

    id_tenant = session.get("id_tenant")
    prefixo = f"upload/tenant{id_tenant}/produtos/"
    if not caminho.lower().startswith(prefixo.lower()):
        return jsonify(success=False, message="Arquivo de outro tenant."), 403

    arquivo = _raiz_projeto() / caminho.replace("/", os.sep)
    if not arquivo.is_file():
        return jsonify(success=False, message="Arquivo não encontrado."), 404

    mime, _ = mimetypes.guess_type(str(arquivo))
    return send_file(arquivo, mimetype=mime or "application/octet-stream", max_age=3600)
