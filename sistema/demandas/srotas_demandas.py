# sistema/demandas/srotas_demandas.py — Central de Demandas + webhook HubSupport
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, login_obrigatorio

log = logging.getLogger(__name__)
_MOD_DIR = Path(__file__).resolve().parent

demandas_bp = Blueprint(
    "demandas",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/demandas",
)


def init_app(app):
    app.register_blueprint(demandas_bp)


def _ids_sessao():
    id_u = session.get("id_usuario")
    id_t = session.get("id_tenant")
    if not id_u or not id_t:
        return None, None
    return int(id_u), int(id_t)


def _json_erro(exc, status: int = 400):
    from api.hubsupport.hubsupport_client import HubSupportError

    if isinstance(exc, HubSupportError):
        code = exc.status_code or status
        if code >= 500:
            code = 502
        return jsonify(success=False, message=str(exc) or "Erro HubSupport."), code
    msg = str(exc) or "Erro inesperado."
    if "090_hubsupport" in msg or "UndefinedTable" in type(exc).__name__:
        msg = (
            "Tabelas HubSupport ausentes. Execute "
            "__doc/sql/090_hubsupport_integracao.sql no banco."
        )
    return jsonify(success=False, message=msg), status


def _validar_assinatura_webhook(body: bytes, assinatura: str) -> bool:
    from api.hubsupport.hubsupport_config import obter_credenciais

    secret = (obter_credenciais().get("webhook_secret") or "").strip()
    if not secret or not assinatura:
        return False
    recebido = assinatura.strip()
    if not recebido.lower().startswith("sha256="):
        recebido = f"sha256={recebido}"
    esperado = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, recebido)


@demandas_bp.get("/demandas")
@login_obrigatorio()
def demandas_pagina():
    return render_template(
        "frm_demandas.html",
        nav_ativo="demandas",
        tenant_nome=session.get("tenant_nome") or "",
        usuario_nome=session.get("nome") or "",
    )


@demandas_bp.get("/demandas/<path:ref>")
@login_obrigatorio()
def demandas_detalhe_pagina(ref: str):
    from flask import url_for

    return render_template(
        "frm_demanda_detalhe.html",
        nav_ativo="demandas",
        chamado_ref=ref,
        tenant_nome=session.get("tenant_nome") or "",
        usuario_nome=session.get("nome") or "",
        api_detalhe=url_for("demandas.api_detalhe", ref=ref),
        api_responder=url_for("demandas.api_responder", ref=ref),
    )


@demandas_bp.get("/api/demandas/listar")
@login_obrigatorio()
def api_listar():
    id_u, id_t = _ids_sessao()
    if not id_u:
        return jsonify(success=False, message="Sessão inválida."), 401
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 20, type=int) or 20
    conn = Var_ConectarBanco()
    try:
        from api.hubsupport.hubsupport_service import listar_chamados_tenant

        dados = listar_chamados_tenant(conn, id_u, id_t, page=page, per_page=per_page)
        return jsonify(success=True, **dados)
    except Exception as e:
        log.exception("listar demandas")
        return _json_erro(e, 500)
    finally:
        conn.close()


@demandas_bp.post("/api/demandas/abrir")
@login_obrigatorio()
def api_abrir():
    id_u, id_t = _ids_sessao()
    if not id_u:
        return jsonify(success=False, message="Sessão inválida."), 401

    body = request.get_json(silent=True) or {}
    # multipart: campos em form + arquivos
    if request.content_type and "multipart/form-data" in request.content_type:
        body = {
            "titulo": request.form.get("titulo"),
            "mensagem": request.form.get("mensagem") or request.form.get("descricao"),
            "categoria": request.form.get("categoria") or request.form.get("tipo"),
            "prioridade": request.form.get("prioridade"),
            "modulo": request.form.get("modulo"),
            "tela": request.form.get("tela"),
            "url": request.form.get("url"),
        }
        anexos = []
        for f in request.files.getlist("anexos") or request.files.getlist("arquivo"):
            if f and f.filename:
                anexos.append(
                    {
                        "nome": f.filename,
                        "conteudo": f.read(),
                        "content_type": f.mimetype,
                    }
                )
    else:
        anexos = None

    conn = Var_ConectarBanco()
    try:
        from api.hubsupport.hubsupport_service import abrir_chamado

        chamado = abrir_chamado(
            conn,
            id_u,
            id_t,
            titulo=body.get("titulo") or "",
            mensagem=body.get("mensagem") or body.get("descricao") or "",
            categoria=body.get("categoria") or body.get("tipo") or "duvida",
            prioridade=body.get("prioridade") or "normal",
            modulo=body.get("modulo") or "",
            url_origem=body.get("url") or "",
            tela=body.get("tela") or "",
            anexos=anexos,
        )
        conn.commit()
        return jsonify(success=True, message="Chamado aberto.", chamado=chamado)
    except Exception as e:
        conn.rollback()
        log.exception("abrir demanda")
        return _json_erro(e)
    finally:
        conn.close()


@demandas_bp.get("/api/demandas/detalhe/<path:ref>")
@login_obrigatorio()
def api_detalhe(ref: str):
    id_u, id_t = _ids_sessao()
    if not id_u:
        return jsonify(success=False, message="Sessão inválida."), 401
    conn = Var_ConectarBanco()
    try:
        from api.hubsupport.hubsupport_service import detalhar_chamado

        dados = detalhar_chamado(conn, id_u, id_t, ref)
        conn.commit()
        return jsonify(success=True, **dados)
    except Exception as e:
        conn.rollback()
        return _json_erro(e)
    finally:
        conn.close()


@demandas_bp.post("/api/demandas/responder/<path:ref>")
@login_obrigatorio()
def api_responder(ref: str):
    id_u, id_t = _ids_sessao()
    if not id_u:
        return jsonify(success=False, message="Sessão inválida."), 401
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        from api.hubsupport.hubsupport_service import responder_chamado

        result = responder_chamado(conn, id_u, id_t, ref, body.get("corpo") or "")
        conn.commit()
        return jsonify(success=True, message="Resposta enviada.", **result)
    except Exception as e:
        conn.rollback()
        return _json_erro(e)
    finally:
        conn.close()


@demandas_bp.post("/webhooks/hubsupport")
def webhook_hubsupport():
    from api.hubsupport.hubsupport_config import registrar_log_webhook, webhook_habilitado
    from api.hubsupport.hubsupport_service import (
        processar_webhook,
        webhook_delivery_processado,
        webhook_registrar_entrega,
    )

    if not webhook_habilitado():
        return jsonify(success=False, message="Webhook HubSupport desabilitado."), 503

    body = request.get_data(cache=False) or b""
    assinatura = request.headers.get("X-HubSupport-Signature") or ""
    delivery_id = (request.headers.get("X-HubSupport-Delivery-Id") or "").strip()
    event_header = (request.headers.get("X-HubSupport-Event") or "").strip()
    client_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()

    if not _validar_assinatura_webhook(body, assinatura):
        try:
            conn = Var_ConectarBanco()
            registrar_log_webhook(
                conn,
                "webhook.assinatura_invalida",
                None,
                {
                    "client_ip": client_ip,
                    "delivery_id": delivery_id or None,
                    "event_header": event_header or None,
                    "signature_presente": bool(assinatura),
                },
            )
            conn.commit()
            conn.close()
        except Exception:
            log.exception("Falha ao logar webhook inválido")
        return jsonify(success=False, message="Assinatura inválida."), 401

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return jsonify(success=False, message="JSON inválido."), 400

    conn = Var_ConectarBanco()
    try:
        if delivery_id and webhook_delivery_processado(conn, delivery_id):
            conn.commit()
            return jsonify(success=True, message="Entrega já processada (idempotente)."), 200

        outcome = processar_webhook(
            conn,
            payload,
            delivery_id=delivery_id,
            event_header=event_header,
            client_ip=client_ip,
        )
        evento = str(payload.get("event") or event_header or "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        ext = data.get("chamado_external_id") or data.get("external_id")
        if delivery_id:
            webhook_registrar_entrega(conn, delivery_id, evento, ext)
        conn.commit()
        return jsonify(success=True, **{k: v for k, v in outcome.items() if v is not None}), 200
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log.exception("Webhook HubSupport")
        return jsonify(success=True, message="Recebido.", warning=str(e)[:500]), 200
    finally:
        conn.close()


@demandas_bp.get("/webhooks/hubsupport")
def webhook_hubsupport_health():
    return jsonify(success=True, service="hubsupport-webhook", ok=True)
