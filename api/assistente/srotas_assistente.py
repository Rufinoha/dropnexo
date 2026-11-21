# api/assistente/srotas_assistente.py — /api/v1/assistente/*
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from api.assistente import servico
from global_utils import Var_ConectarBanco

_log = logging.getLogger(__name__)

assistente_bp = Blueprint("assistente_api", __name__)


def init_app(app):
    app.register_blueprint(assistente_bp)


def _ip() -> str:
    xf = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return xf or (request.remote_addr or "")


def _int_arg(nome: str, padrao):
    bruto = request.args.get(nome)
    if bruto in (None, ""):
        return padrao
    try:
        return int(bruto)
    except (TypeError, ValueError):
        raise ValueError(f"Parâmetro inválido: {nome}.") from None


def _com_auth(id_tenant_alvo: int | None = None):
    """Autentica, devolve (conn, token_row) ou response de erro."""
    conn = Var_ConectarBanco()
    try:
        token_row, err = servico.autenticar(conn, request.headers.get("Authorization"))
        if err:
            status = 429 if "Limite" in err else 401
            servico.auditar(
                conn,
                rota=request.path,
                metodo=request.method,
                ip=_ip(),
                token_hint=None,
                http_status=status,
                id_tenant_alvo=id_tenant_alvo,
            )
            return None, None, (jsonify(servico.erro_generico(err)), status)
        return conn, token_row, None
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return None, None, (jsonify(servico.erro_generico()), 500)


def _fechar(conn, token_row, *, status: int, id_tenant_alvo: int | None = None):
    if conn and token_row:
        servico.auditar(
            conn,
            rota=request.path,
            metodo=request.method,
            ip=_ip(),
            token_hint=token_row.get("hint"),
            http_status=status,
            id_tenant_alvo=id_tenant_alvo,
        )
    try:
        if conn:
            conn.close()
    except Exception:
        pass


@assistente_bp.get("/api/v1/assistente/fornecedores")
def api_listar():
    conn, token, err = _com_auth()
    if err:
        return err
    try:
        cur = conn.cursor()
        data = servico.listar_fornecedores(
            cur,
            page=_int_arg("page", 1),
            per_page=_int_arg("per_page", 50),
            fundador=_int_arg("fundador", None),
            fase=(request.args.get("fase") or "").strip() or None,
            indicado=_int_arg("indicado", None),
            desde=(request.args.get("desde") or "").strip() or None,
        )
        _fechar(conn, token, status=200)
        return jsonify(success=True, **data)
    except ValueError as e:
        _fechar(conn, token, status=400)
        return jsonify(servico.erro_generico(str(e))), 400
    except Exception:
        _log.exception("assistente listar")
        _fechar(conn, token, status=500)
        return jsonify(servico.erro_generico()), 500


@assistente_bp.get("/api/v1/assistente/fornecedores/<int:id_tenant>")
def api_detalhe(id_tenant: int):
    conn, token, err = _com_auth(id_tenant)
    if err:
        return err
    try:
        cur = conn.cursor()
        data = servico.detalhe_fornecedor(cur, id_tenant)
        if not data:
            _fechar(conn, token, status=404, id_tenant_alvo=id_tenant)
            return jsonify(servico.erro_generico("Fornecedor não encontrado.")), 404
        _fechar(conn, token, status=200, id_tenant_alvo=id_tenant)
        return jsonify(success=True, **data)
    except Exception:
        _log.exception("assistente detalhe")
        _fechar(conn, token, status=500, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico()), 500


@assistente_bp.get("/api/v1/assistente/fornecedores/<int:id_tenant>/produtos")
def api_produtos(id_tenant: int):
    conn, token, err = _com_auth(id_tenant)
    if err:
        return err
    try:
        cur = conn.cursor()
        data = servico.listar_produtos_pagina(
            cur,
            id_tenant,
            status=(request.args.get("status") or "").strip() or None,
            page=_int_arg("page", 1),
            per_page=_int_arg("per_page", 50),
        )
        _fechar(conn, token, status=200, id_tenant_alvo=id_tenant)
        return jsonify(success=True, **data)
    except LookupError as e:
        _fechar(conn, token, status=404, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 404
    except ValueError as e:
        _fechar(conn, token, status=400, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 400
    except Exception:
        _log.exception("assistente produtos")
        _fechar(conn, token, status=500, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico()), 500


@assistente_bp.get("/api/v1/assistente/fornecedores/<int:id_tenant>/pedidos")
def api_pedidos(id_tenant: int):
    conn, token, err = _com_auth(id_tenant)
    if err:
        return err
    try:
        cur = conn.cursor()
        data = servico.listar_pedidos_pagina(
            cur,
            id_tenant,
            status=(request.args.get("status") or "").strip() or None,
            atrasados=1 if request.args.get("atrasados") in ("1", "true", "True") else 0,
            desde=(request.args.get("desde") or "").strip() or None,
            page=_int_arg("page", 1),
            per_page=_int_arg("per_page", 50),
        )
        _fechar(conn, token, status=200, id_tenant_alvo=id_tenant)
        return jsonify(success=True, **data)
    except LookupError as e:
        _fechar(conn, token, status=404, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 404
    except ValueError as e:
        _fechar(conn, token, status=400, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 400
    except Exception:
        _log.exception("assistente pedidos")
        _fechar(conn, token, status=500, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico()), 500


@assistente_bp.get("/api/v1/assistente/resumo")
def api_resumo():
    conn, token, err = _com_auth()
    if err:
        return err
    try:
        cur = conn.cursor()
        data = servico.painel_resumo(cur)
        _fechar(conn, token, status=200)
        return jsonify(success=True, **data)
    except Exception:
        _log.exception("assistente resumo")
        _fechar(conn, token, status=500)
        return jsonify(servico.erro_generico()), 500


@assistente_bp.post("/api/v1/assistente/fornecedores/<int:id_tenant>/contato")
def api_contato(id_tenant: int):
    conn, token, err = _com_auth(id_tenant)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    try:
        cur = conn.cursor()
        res = servico.post_contato(
            cur, id_tenant, body, aprovado_por=body.get("aprovado_por")
        )
        conn.commit()
        _fechar(conn, token, status=200, id_tenant_alvo=id_tenant)
        return jsonify(success=True, contato=res)
    except PermissionError as e:
        conn.rollback()
        _fechar(conn, token, status=403, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 403
    except LookupError as e:
        conn.rollback()
        _fechar(conn, token, status=404, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 404
    except ValueError as e:
        conn.rollback()
        _fechar(conn, token, status=400, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 400
    except Exception:
        conn.rollback()
        _log.exception("assistente contato")
        _fechar(conn, token, status=500, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico()), 500


@assistente_bp.post("/api/v1/assistente/fornecedores/<int:id_tenant>/fase")
def api_fase(id_tenant: int):
    conn, token, err = _com_auth(id_tenant)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    try:
        cur = conn.cursor()
        res = servico.post_fase(
            cur, id_tenant, body, aprovado_por=body.get("aprovado_por")
        )
        conn.commit()
        _fechar(conn, token, status=200, id_tenant_alvo=id_tenant)
        return jsonify(success=True, **res)
    except PermissionError as e:
        conn.rollback()
        _fechar(conn, token, status=403, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 403
    except LookupError as e:
        conn.rollback()
        _fechar(conn, token, status=404, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 404
    except ValueError as e:
        conn.rollback()
        _fechar(conn, token, status=400, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico(str(e))), 400
    except Exception:
        conn.rollback()
        _log.exception("assistente fase")
        _fechar(conn, token, status=500, id_tenant_alvo=id_tenant)
        return jsonify(servico.erro_generico()), 500
