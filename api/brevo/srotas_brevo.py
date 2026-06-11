# api/brevo/srotas_brevo.py — e-mail Brevo (envio, log, webhook)
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional, Tuple, Union

import requests
from flask import Blueprint, jsonify, request, session
from psycopg2.extras import Json

from global_utils import Var_ConectarBanco, login_obrigatorio, remover_tags_html

brevo_bp = Blueprint(
    "brevo",
    __name__,
)


def init_app(app):
    app.register_blueprint(brevo_bp)


# ==========================================================
# BREVO — TRANSPORTE HTTP
# ==========================================================

def _brevo_headers() -> dict:
    return {
        "accept": "application/json",
        "api-key": (os.getenv("BREVO_API_KEY") or "").strip(),
        "content-type": "application/json",
    }


def _brevo_sender() -> dict:
    return {
        "name": (os.getenv("BREVO_REMETENTE_NOME") or "DropNexo").strip(),
        "email": (os.getenv("BREVO_REMETENTE_EMAIL") or "").strip(),
    }


def _send_brevo_email(destinatarios: List[str], assunto: str, corpo_html: str, tag: str):
    payload = {
        "sender": _brevo_sender(),
        "to": [{"email": e.strip()} for e in destinatarios],
        "subject": assunto,
        "htmlContent": corpo_html,
        "tags": [tag] if tag else ["osb"],
    }
    return requests.post(
        "https://api.brevo.com/v3/smtp/email",
        json=payload,
        headers=_brevo_headers(),
        timeout=25,
    )


# ==========================================================
# BREVO — LOG NO BANCO
# ==========================================================

def _log_envio_email(
    destinatarios: List[str],
    assunto: str,
    corpo_html: str,
    tag: str,
    criado_por: Optional[int] = None,
    status: str = "Enviado",
) -> Tuple[bool, Union[int, str]]:
    conn = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        agora = datetime.now()
        corpo_txt = remover_tags_html(corpo_html)
        tag_norm = (tag or "sem_tag").strip()

        cur.execute(
            """
            INSERT INTO tbl_email_envio (tag_email, assunto, corpo, dt_envio, criado_por)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id_envio
            """,
            (tag_norm, assunto, corpo_txt, agora, criado_por),
        )
        id_envio = cur.fetchone()[0]

        for email in destinatarios:
            cur.execute(
                """
                INSERT INTO tbl_email_destinatario (
                    id_envio, email, status_atual, dt_ultimo_evento, tag_email
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (id_envio, email.strip(), status, agora, tag_norm),
            )

        cur.execute(
            """
            INSERT INTO tbl_email_log (
                assunto, corpo, destinatario, status, tag, data_envio, criado_por
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                assunto,
                corpo_txt,
                ", ".join(e.strip() for e in destinatarios),
                status,
                tag_norm,
                agora,
                criado_por,
            ),
        )

        conn.commit()
        return True, id_envio
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False, str(e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ==========================================================
# BREVO — API PÚBLICA (MÓDULOS INTERNOS)
# ==========================================================

def enviar_email(
    destinatarios: List[str],
    assunto: str,
    corpo_html: str,
    tag: str = "osb",
    criado_por: Optional[int] = None,
) -> Tuple[bool, str, Optional[int]]:
    emails = [e.strip().lower() for e in destinatarios if e and str(e).strip()]
    if not emails:
        return False, "Nenhum destinatário.", None
    if not (assunto or "").strip():
        return False, "Assunto vazio.", None
    if not (corpo_html or "").strip():
        return False, "Corpo vazio.", None
    if not _brevo_sender().get("email"):
        return False, "BREVO_REMETENTE_EMAIL não configurado.", None
    if not (os.getenv("BREVO_API_KEY") or "").strip():
        return False, "BREVO_API_KEY não configurada.", None

    tag_norm = (tag or "osb").strip()
    try:
        resp = _send_brevo_email(emails, assunto.strip(), corpo_html, tag_norm)
    except requests.RequestException as e:
        _log_envio_email(emails, assunto, corpo_html, tag_norm, criado_por, status="Falha")
        return False, str(e), None

    if resp.status_code not in (200, 201):
        _log_envio_email(emails, assunto, corpo_html, tag_norm, criado_por, status="Falha")
        return False, f"Erro Brevo ({resp.status_code}): {resp.text}", None

    ok_log, info = _log_envio_email(emails, assunto, corpo_html, tag_norm, criado_por, status="Enviado")
    if not ok_log:
        return True, f"E-mail enviado, mas falhou ao registrar log: {info}", None
    return True, "ok", int(info)


def enviar_html(destinatarios: List[str], assunto: str, corpo_html: str, tag: str = "osb") -> Tuple[bool, str]:
    ok, msg, _ = enviar_email(destinatarios, assunto, corpo_html, tag=tag)
    return ok, msg


# ==========================================================
# BREVO — ROTAS HTTP
# ==========================================================

# Enviar e-mail (API interna)
@brevo_bp.post("/email/enviar")
@login_obrigatorio()
def email_enviar():
    try:
        dados = request.get_json(silent=True) or {}
        destinatarios = dados.get("destinatarios", [])
        assunto = (dados.get("assunto") or "").strip()
        corpo_html = (dados.get("corpo_html") or "").strip()
        tag = (dados.get("tag") or "osb").strip()

        if not isinstance(destinatarios, list) or not destinatarios:
            return jsonify(success=False, message="Destinatários são obrigatórios."), 400
        if not assunto:
            return jsonify(success=False, message="Assunto é obrigatório."), 400
        if not corpo_html:
            return jsonify(success=False, message="Corpo do e-mail é obrigatório."), 400

        ok, msg, id_envio = enviar_email(
            destinatarios,
            assunto,
            corpo_html,
            tag=tag,
            criado_por=session.get("id_usuario"),
        )
        if not ok:
            return jsonify(success=False, message=msg), 500
        return jsonify(
            success=True,
            message="E-mail enviado com sucesso!" if msg == "ok" else msg,
            id_envio=id_envio,
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


# Webhook de eventos Brevo
@brevo_bp.post("/email/webhook")
def email_webhook():
    token_cfg = (os.getenv("BREVO_WEBHOOK_TOKEN") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    token_hdr = (request.headers.get("token") or "").strip()

    if token_cfg:
        ok = False
        if auth.lower().startswith("bearer "):
            ok = auth.split(" ", 1)[1].strip() == token_cfg
        if not ok and token_hdr:
            t = token_hdr
            if t.lower().startswith("bearer "):
                t = t.split(" ", 1)[1].strip()
            ok = t == token_cfg
        if not ok:
            return jsonify(success=False, message="Não autorizado."), 401

    payload = request.get_json(silent=True) or {}
    ev = (payload.get("event") or payload.get("type") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    tag = payload.get("tag") or payload.get("tags") or ""
    if isinstance(tag, list):
        tag = tag[0] if tag else ""
    tag = str(tag).strip() or "sem_tag"

    if not email or not ev:
        return jsonify(success=True), 200

    conn = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id_destinatario
            FROM tbl_email_destinatario
            WHERE lower(email) = %s AND tag_email = %s
            ORDER BY id_destinatario DESC
            LIMIT 1
            """,
            (email, tag),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=True), 200

        id_dest = row[0]
        agora = datetime.now()
        err_msg = payload.get("reason") or payload.get("message") or payload.get("error")

        cur.execute(
            """
            UPDATE tbl_email_destinatario
            SET status_atual = %s, dt_ultimo_evento = %s
            WHERE id_destinatario = %s
            """,
            (ev, agora, id_dest),
        )
        cur.execute(
            """
            INSERT INTO tbl_email_evento (
                id_destinatario, tipo_evento, data_evento, mensagem_erro, payload_json
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (id_dest, ev, agora, err_msg, Json(payload)),
        )
        conn.commit()
        return jsonify(success=True), 200
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify(success=True), 200
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
