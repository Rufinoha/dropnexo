"""Rotas da API Externa (admin + card do fornecedor)."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session, url_for

from api.api_externa import cliente, docs, servico, sync
from global_utils import Var_ConectarBanco, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM, MODULO_FORNECEDOR, garantir_modulo_sessao

_MOD = Path(__file__).resolve().parent
api_externa_bp = Blueprint(
    "api_externa",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/api/api_externa",
)


def init_app(app):
    app.register_blueprint(api_externa_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_dev():
    if session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Acesso restrito ao desenvolvedor."), 403


def _exigir_fornecedor():
    if session.get("eh_desenvolvedor"):
        return None
    if garantir_modulo_sessao() in (MODULO_FORNECEDOR, MODULO_ARMAZEM):
        return None
    return jsonify(success=False, message="Apenas fornecedores e armazéns."), 403


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    return obj


# ── Admin (Configurações) ─────────────────────────────────────────────


@api_externa_bp.get("/api/configuracoes/api-externa/listar")
@login_obrigatorio()
def admin_listar():
    if (r := _exigir_dev()) is not None:
        return r
    termo = (request.args.get("termo") or "").strip()
    conn = Var_ConectarBanco()
    try:
        itens = servico.listar_liberacoes(conn, termo)
        return jsonify(success=True, dados=_json_safe(itens))
    finally:
        conn.close()


@api_externa_bp.get("/api/configuracoes/api-externa/buscar-tenants")
@login_obrigatorio()
def admin_buscar_tenants():
    """Compatível com busca antiga (?termo=) e combobox (?filtro=&limitar=)."""
    if (r := _exigir_dev()) is not None:
        return r
    termo = (request.args.get("filtro") or request.args.get("termo") or "").strip()
    try:
        limite = min(40, max(1, int(request.args.get("limitar") or 20)))
    except (TypeError, ValueError):
        limite = 20
    conn = Var_ConectarBanco()
    try:
        dados = servico.buscar_tenants(conn, termo, limitar=limite)
        # Combobox personalizada espera {sucesso, dados}.
        return jsonify(sucesso=True, success=True, dados=dados)
    except Exception as exc:
        return jsonify(sucesso=False, success=False, mensagem=str(exc), message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.get("/api/configuracoes/api-externa/combo-tenants")
@login_obrigatorio()
def admin_combo_tenants():
    """Combobox personalizada BARACAT — GET ?filtro=&limitar= → {sucesso, dados}."""
    if (r := _exigir_dev()) is not None:
        return r
    termo = (request.args.get("filtro") or "").strip()
    try:
        limite = min(40, max(1, int(request.args.get("limitar") or 20)))
    except (TypeError, ValueError):
        limite = 20
    conn = Var_ConectarBanco()
    try:
        return jsonify(
            sucesso=True,
            dados=servico.buscar_tenants(conn, termo, limitar=limite),
        )
    except Exception as exc:
        return jsonify(sucesso=False, mensagem=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.post("/api/configuracoes/api-externa/liberar")
@login_obrigatorio()
def admin_liberar():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id_tenant") or 0)
    except (TypeError, ValueError):
        id_tenant = 0
    if id_tenant <= 0:
        return jsonify(success=False, message="Informe o tenant."), 400
    conn = Var_ConectarBanco()
    try:
        cfg = servico.liberar_tenant(
            conn,
            id_tenant,
            id_usuario=session.get("id_usuario"),
            nome_parceiro=body.get("nome_parceiro") or "",
            contato_tecnico=body.get("contato_tecnico") or "",
            ambiente=body.get("ambiente") or "homologacao",
        )
        conn.commit()
        return jsonify(success=True, message="API Externa liberada para o tenant.", dados=_json_safe(cfg))
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.post("/api/configuracoes/api-externa/revogar")
@login_obrigatorio()
def admin_revogar():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id_tenant") or 0)
    except (TypeError, ValueError):
        id_tenant = 0
    if id_tenant <= 0:
        return jsonify(success=False, message="Informe o tenant."), 400
    conn = Var_ConectarBanco()
    try:
        cfg = servico.revogar_tenant(conn, id_tenant)
        conn.commit()
        return jsonify(success=True, message="Liberação revogada.", dados=_json_safe(cfg))
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 500
    finally:
        conn.close()


# ── Card do fornecedor ────────────────────────────────────────────────


@api_externa_bp.get("/api/integracoes/api-externa/status")
@login_obrigatorio()
def tenant_status():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cfg = servico.carregar(conn, id_t)
        if not cfg.get("liberado") and not session.get("eh_desenvolvedor"):
            return jsonify(success=False, message="API Externa não liberada."), 404
        return jsonify(success=True, dados=_json_safe(cfg), docs=docs.painel_docs())
    finally:
        conn.close()


@api_externa_bp.post("/api/integracoes/api-externa/salvar")
@login_obrigatorio()
def tenant_salvar():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cfg = servico.salvar_config_tenant(conn, id_t, body)
        conn.commit()
        return jsonify(success=True, message="Configuração salva.", dados=_json_safe(cfg))
    except PermissionError as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 403
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.post("/api/integracoes/api-externa/gerar-token")
@login_obrigatorio()
def tenant_gerar_token():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cfg = servico.carregar(conn, id_t)
        if not cfg.get("liberado"):
            return jsonify(success=False, message="API Externa não liberada."), 403
        cfg, token = servico.gerar_dn_token(conn, id_t)
        servico.registrar_log(
            conn, id_t, evento="token.gerado", sucesso=True, mensagem="Token DropNexo gerado.", direcao="local"
        )
        conn.commit()
        return jsonify(
            success=True,
            message="Token gerado. Copie agora — ele não será exibido de novo.",
            token=token,
            dados=_json_safe(cfg),
        )
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.post("/api/integracoes/api-externa/revogar-token")
@login_obrigatorio()
def tenant_revogar_token():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cfg = servico.carregar(conn, id_t)
        if not cfg.get("liberado"):
            return jsonify(success=False, message="API Externa não liberada."), 403
        cfg = servico.revogar_dn_token(conn, id_t)
        servico.registrar_log(
            conn, id_t, evento="token.revogado", sucesso=True, mensagem="Token DropNexo revogado.", direcao="local"
        )
        conn.commit()
        return jsonify(success=True, message="Token revogado.", dados=_json_safe(cfg))
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.post("/api/integracoes/api-externa/testar")
@login_obrigatorio()
def tenant_testar():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cfg = servico.carregar(conn, id_t)
        if not cfg.get("liberado"):
            return jsonify(success=False, message="API Externa não liberada."), 403
        resultado = cliente.testar_conexao(conn, id_t)
        servico.registrar_log(
            conn,
            id_t,
            evento="conexao.teste",
            sucesso=bool(resultado.get("ok")),
            mensagem=resultado.get("message") or "",
            direcao="pull",
            detalhe={"endpoint": resultado.get("endpoint")},
        )
        if resultado.get("ok"):
            servico.marcar_sync(conn, id_t, ok=True, mensagem=resultado.get("message") or "Conexão OK")
        else:
            servico.marcar_sync(conn, id_t, ok=False, mensagem=resultado.get("message") or "Falha")
        conn.commit()
        return jsonify(success=bool(resultado.get("ok")), **resultado, dados=_json_safe(servico.carregar(conn, id_t)))
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, ok=False, message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.post("/api/integracoes/api-externa/sync/produtos")
@login_obrigatorio()
def tenant_sync_produtos():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        resultado = sync.sincronizar_produtos(conn, id_t)
        conn.commit()
        return jsonify(success=bool(resultado.get("ok")), **resultado, dados=_json_safe(servico.carregar(conn, id_t)))
    except PermissionError as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 403
    except cliente.ApiExternaErro as exc:
        conn.rollback()
        try:
            servico.registrar_log(
                conn, id_t, evento="sync.produtos", sucesso=False, mensagem=str(exc),
                http_status=exc.http_status, direcao="pull",
            )
            servico.marcar_sync(conn, id_t, ok=False, mensagem=str(exc))
            conn.commit()
        except Exception:
            conn.rollback()
        return jsonify(success=False, message=str(exc)), 422
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.post("/api/integracoes/api-externa/sync/estoque")
@login_obrigatorio()
def tenant_sync_estoque():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        resultado = sync.sincronizar_estoque(conn, id_t)
        conn.commit()
        return jsonify(success=bool(resultado.get("ok")), **resultado, dados=_json_safe(servico.carregar(conn, id_t)))
    except PermissionError as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 403
    except cliente.ApiExternaErro as exc:
        conn.rollback()
        try:
            servico.registrar_log(
                conn, id_t, evento="sync.estoque", sucesso=False, mensagem=str(exc),
                http_status=exc.http_status, direcao="pull",
            )
            servico.marcar_sync(conn, id_t, ok=False, mensagem=str(exc))
            conn.commit()
        except Exception:
            conn.rollback()
        return jsonify(success=False, message=str(exc)), 422
    except Exception as exc:
        conn.rollback()
        return jsonify(success=False, message=str(exc)), 500
    finally:
        conn.close()


@api_externa_bp.get("/api/integracoes/api-externa/logs")
@login_obrigatorio()
def tenant_logs():
    if (r := _exigir_fornecedor()) is not None:
        return r
    id_t = _id_tenant()
    if not id_t:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cfg = servico.carregar(conn, id_t)
        if not cfg.get("liberado"):
            return jsonify(success=False, message="API Externa não liberada."), 403
        logs = servico.listar_logs(conn, id_t, limite=int(request.args.get("limite") or 50))
        return jsonify(success=True, dados=_json_safe(logs))
    finally:
        conn.close()


@api_externa_bp.get("/api/integracoes/api-externa/docs")
@login_obrigatorio()
def tenant_docs():
    if (r := _exigir_fornecedor()) is not None:
        return r
    return jsonify(success=True, **docs.painel_docs())


@api_externa_bp.get("/ajuda/api-externa")
def docs_html():
    """Documentação HTML pública para o time técnico do parceiro."""
    painel = docs.painel_docs()
    try:
        url_home = url_for("public.home")
    except Exception:
        url_home = "/"
    return render_template(
        "docs_api_externa.html",
        versao=painel.get("versao") or "1.0",
        url_home=url_home,
        css_url=url_for("api_externa.static", filename="style/docs_api_externa.css") + "?v=1",
    )
