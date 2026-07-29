# api/brevo/srotas_brevo.py — e-mail Brevo (envio, mala direta, log, webhook)
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import Any, List, Optional, Tuple, Union

import requests
from flask import Blueprint, jsonify, request, session
from psycopg2.extras import Json

from global_utils import Var_ConectarBanco, login_obrigatorio, obter_url_site_publico, remover_tags_html

brevo_bp = Blueprint(
    "brevo",
    __name__,
)

ERROS_AMIGAVEIS = {
    "Mailbox full": "Caixa de e-mail cheia",
    "Temporary error": "Erro temporário no servidor do destinatário",
    "Email address does not exist": "Endereço de e-mail inválido",
    "User unknown": "Usuário de e-mail desconhecido",
    "Blocked due to spam": "Bloqueado por suspeita de spam",
    "Domain blacklisted": "Domínio bloqueado pelo provedor de destino",
    "Marked as spam": "Marcado como spam pelo destinatário",
    "Invalid email": "E-mail mal formatado",
    "Unsubscribed user": "Usuário descadastrado da lista",
}


def init_app(app):
    app.register_blueprint(brevo_bp)


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


def brevo_configurado() -> bool:
    return bool((os.getenv("BREVO_API_KEY") or "").strip() and _brevo_sender().get("email"))


def webhook_url_publico() -> str:
    base = (obter_url_site_publico() or "").rstrip("/")
    return f"{base}/email/webhook"


def _send_brevo_email(
    destinatarios: List[str],
    assunto: str,
    corpo_html: str,
    tag: str,
) -> requests.Response:
    payload = {
        "sender": _brevo_sender(),
        "to": [{"email": e.strip()} for e in destinatarios],
        "subject": assunto,
        "htmlContent": corpo_html,
        "tags": [tag] if tag else ["dropnexo"],
    }
    return requests.post(
        "https://api.brevo.com/v3/smtp/email",
        json=payload,
        headers=_brevo_headers(),
        timeout=25,
    )


def _agora():
    return datetime.now()


def _log_envio_email(
    destinatarios: List[str],
    assunto: str,
    corpo_html: str,
    tag: str,
    criado_por: Optional[int] = None,
    status: str = "Enviado",
    *,
    tipo_disparo: str = "sistema",
    filtro_tipo: str | None = None,
    dest_meta: list[dict] | None = None,
    message_ids: dict[str, str] | None = None,
) -> Tuple[bool, Union[int, str]]:
    conn = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        agora = _agora()
        corpo_txt = remover_tags_html(corpo_html)
        tag_norm = (tag or "sem_tag").strip()
        emails = [e.strip().lower() for e in destinatarios if e and str(e).strip()]

        cur.execute(
            """
            INSERT INTO tbl_email_envio (
                tag_email, assunto, corpo, dt_envio, criado_por,
                tipo_disparo, filtro_tipo, total_destinatarios
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_envio
            """,
            (
                tag_norm,
                assunto,
                corpo_txt,
                agora,
                criado_por,
                tipo_disparo,
                filtro_tipo,
                len(emails),
            ),
        )
        id_envio = int(cur.fetchone()[0])

        meta_por_email = {}
        for m in dest_meta or []:
            em = (m.get("email") or "").strip().lower()
            if em:
                meta_por_email[em] = m

        for email in emails:
            meta = meta_por_email.get(email) or {}
            mid = (message_ids or {}).get(email)
            cur.execute(
                """
                INSERT INTO tbl_email_destinatario (
                    id_envio, email, status_atual, dt_ultimo_evento, tag_email,
                    id_tenant, nome_tenant, message_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    id_envio,
                    email,
                    status,
                    agora,
                    tag_norm,
                    meta.get("id_tenant"),
                    (meta.get("nome_tenant") or "")[:200] or None,
                    mid,
                ),
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
                ", ".join(emails),
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


def enviar_email(
    destinatarios: List[str],
    assunto: str,
    corpo_html: str,
    tag: str = "dropnexo",
    criado_por: Optional[int] = None,
) -> Tuple[bool, str, Optional[int]]:
    emails = [e.strip().lower() for e in destinatarios if e and str(e).strip()]
    if not emails:
        return False, "Nenhum destinatário.", None
    if not (assunto or "").strip():
        return False, "Assunto vazio.", None
    if not (corpo_html or "").strip():
        return False, "Corpo vazio.", None
    if not brevo_configurado():
        return False, "Brevo não configurado (API key / remetente).", None

    tag_norm = (tag or "dropnexo").strip()
    try:
        resp = _send_brevo_email(emails, assunto.strip(), corpo_html, tag_norm)
    except requests.RequestException as e:
        _log_envio_email(emails, assunto, corpo_html, tag_norm, criado_por, status="Falha")
        return False, str(e), None

    if resp.status_code not in (200, 201):
        _log_envio_email(emails, assunto, corpo_html, tag_norm, criado_por, status="Falha")
        return False, f"Erro Brevo ({resp.status_code}): {resp.text}", None

    message_ids: dict[str, str] = {}
    try:
        mid = (resp.json() or {}).get("messageId")
        if mid and len(emails) == 1:
            message_ids[emails[0]] = str(mid)
    except Exception:
        pass

    ok_log, info = _log_envio_email(
        emails,
        assunto,
        corpo_html,
        tag_norm,
        criado_por,
        status="Enviado",
        message_ids=message_ids,
    )
    if not ok_log:
        return True, f"E-mail enviado, mas falhou ao registrar log: {info}", None
    return True, "ok", int(info)


def enviar_html(destinatarios: List[str], assunto: str, corpo_html: str, tag: str = "dropnexo") -> Tuple[bool, str]:
    ok, msg, _ = enviar_email(destinatarios, assunto, corpo_html, tag=tag)
    return ok, msg


def enviar_mala_direta(
    *,
    destinatarios: list[dict],
    assunto: str,
    corpo_html: str,
    filtro_tipo: str | None,
    criado_por: int | None,
) -> Tuple[bool, str, Optional[int], dict]:
    """
    Envia 1 e-mail por destinatário (melhor rastreio Brevo).
    destinatarios: [{email, id_tenant, nome_tenant}]
    """
    if not brevo_configurado():
        return False, "Brevo não configurado (API key / remetente).", None, {}
    assunto = (assunto or "").strip()
    corpo_html = (corpo_html or "").strip()
    if not assunto or not corpo_html:
        return False, "Assunto e mensagem são obrigatórios.", None, {}

    limpos: list[dict] = []
    vistos: set[str] = set()
    for d in destinatarios:
        email = (d.get("email") or "").strip().lower()
        if not email or "@" not in email or email in vistos:
            continue
        vistos.add(email)
        limpos.append(
            {
                "email": email,
                "id_tenant": d.get("id_tenant"),
                "nome_tenant": d.get("nome_tenant") or "",
            }
        )
    if not limpos:
        return False, "Nenhum e-mail válido nos tenants selecionados.", None, {}

    tag = f"mala-{uuid.uuid4().hex[:12]}"
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        agora = _agora()
        corpo_txt = remover_tags_html(corpo_html)
        cur.execute(
            """
            INSERT INTO tbl_email_envio (
                tag_email, assunto, corpo, dt_envio, criado_por,
                tipo_disparo, filtro_tipo, total_destinatarios
            )
            VALUES (%s, %s, %s, %s, %s, 'mala_direta', %s, %s)
            RETURNING id_envio
            """,
            (tag, assunto, corpo_txt, agora, criado_por, filtro_tipo, len(limpos)),
        )
        id_envio = int(cur.fetchone()[0])
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Falha ao criar disparo: {e}", None, {}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    ok_n = 0
    falha_n = 0
    for item in limpos:
        email = item["email"]
        status = "Enviado"
        mid = None
        err = None
        try:
            resp = _send_brevo_email([email], assunto, corpo_html, tag)
            if resp.status_code not in (200, 201):
                status = "Falha"
                falha_n += 1
                err = f"Brevo {resp.status_code}: {resp.text[:300]}"
            else:
                ok_n += 1
                try:
                    mid = str((resp.json() or {}).get("messageId") or "") or None
                except Exception:
                    mid = None
        except requests.RequestException as e:
            status = "Falha"
            falha_n += 1
            err = str(e)

        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            agora = _agora()
            cur.execute(
                """
                INSERT INTO tbl_email_destinatario (
                    id_envio, email, status_atual, dt_ultimo_evento, tag_email,
                    id_tenant, nome_tenant, message_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id_destinatario
                """,
                (
                    id_envio,
                    email,
                    status,
                    agora,
                    tag,
                    item.get("id_tenant"),
                    (item.get("nome_tenant") or "")[:200] or None,
                    mid,
                ),
            )
            id_dest = int(cur.fetchone()[0])
            if err:
                cur.execute(
                    """
                    INSERT INTO tbl_email_evento (
                        id_destinatario, tipo_evento, data_evento, mensagem_erro
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (id_dest, "error", agora, err),
                )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tbl_email_log (
                assunto, corpo, destinatario, status, tag, data_envio, criado_por
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                assunto,
                remover_tags_html(corpo_html),
                f"{ok_n} ok / {falha_n} falha — {len(limpos)} dest.",
                "Enviado" if ok_n else "Falha",
                tag,
                _agora(),
                criado_por,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    resumo = {"ok": ok_n, "falha": falha_n, "total": len(limpos), "tag": tag}
    if ok_n == 0:
        return False, "Nenhum e-mail foi aceito pelo Brevo.", id_envio, resumo
    return True, "ok", id_envio, resumo


def _motivo_amigavel(motivo: str | None) -> str | None:
    if not motivo:
        return None
    m = motivo.strip()
    return ERROS_AMIGAVEIS.get(m, m)


def _resolver_destinatario(cur, email: str, tag: str, message_id: str | None) -> int | None:
    email = (email or "").strip().lower()
    if message_id:
        cur.execute(
            """
            SELECT id_destinatario FROM tbl_email_destinatario
            WHERE message_id = %s
            ORDER BY id_destinatario DESC LIMIT 1
            """,
            (message_id,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
    if email and tag:
        cur.execute(
            """
            SELECT id_destinatario FROM tbl_email_destinatario
            WHERE lower(email) = %s AND tag_email = %s
            ORDER BY id_destinatario DESC LIMIT 1
            """,
            (email, tag),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
    if email:
        cur.execute(
            """
            SELECT id_destinatario FROM tbl_email_destinatario
            WHERE lower(email) = %s
            ORDER BY id_destinatario DESC LIMIT 1
            """,
            (email,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
    return None


# ── Rotas HTTP ────────────────────────────────────────────────────────

@brevo_bp.post("/email/enviar")
@login_obrigatorio()
def email_enviar():
    try:
        dados = request.get_json(silent=True) or {}
        destinatarios = dados.get("destinatarios", [])
        assunto = (dados.get("assunto") or "").strip()
        corpo_html = (dados.get("corpo_html") or "").strip()
        tag = (dados.get("tag") or "dropnexo").strip()

        if not isinstance(destinatarios, list) or not destinatarios:
            return jsonify(success=False, message="Destinatários são obrigatórios."), 400
        if not assunto or not corpo_html:
            return jsonify(success=False, message="Assunto e corpo são obrigatórios."), 400

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


@brevo_bp.get("/email/webhook-info")
@login_obrigatorio()
def email_webhook_info():
    return jsonify(
        success=True,
        webhook_url=webhook_url_publico(),
        configurado=brevo_configurado(),
        eventos_sugeridos=[
            "delivered",
            "opened",
            "click",
            "softBounce",
            "hardBounce",
            "spam",
            "blocked",
            "invalid",
            "error",
            "unsubscribed",
        ],
    )


@brevo_bp.post("/email/webhook")
def email_webhook():
    """Endpoint público para o Brevo — cadastre esta URL no painel Brevo (SMTP webhooks)."""
    token_cfg = (os.getenv("BREVO_WEBHOOK_TOKEN") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    token_hdr = (request.headers.get("token") or "").strip()
    token_q = (request.args.get("token") or "").strip()

    if token_cfg:
        ok = False
        if auth.lower().startswith("bearer "):
            ok = auth.split(" ", 1)[1].strip() == token_cfg
        for t in (token_hdr, token_q):
            if not t:
                continue
            if t.lower().startswith("bearer "):
                t = t.split(" ", 1)[1].strip()
            if t == token_cfg:
                ok = True
        if not ok:
            return jsonify(success=False, message="Não autorizado."), 401

    payload = request.get_json(silent=True) or {}
    # Brevo às vezes envia lista
    eventos = payload if isinstance(payload, list) else [payload]

    conn = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        for item in eventos:
            if not isinstance(item, dict):
                continue
            ev = (item.get("event") or item.get("type") or "").strip()
            email = (item.get("email") or "").strip().lower()
            tag_raw = item.get("tag") or item.get("tags") or ""
            if isinstance(tag_raw, list):
                tag = str(tag_raw[0]).strip() if tag_raw else ""
            else:
                tag = str(tag_raw).strip()
                if tag.startswith("["):
                    try:
                        import json as _json

                        arr = _json.loads(tag)
                        tag = str(arr[0]) if isinstance(arr, list) and arr else tag
                    except Exception:
                        pass
            tag = tag or "sem_tag"
            message_id = (
                item.get("message-id")
                or item.get("messageId")
                or item.get("message_id")
                or ""
            )
            message_id = str(message_id).strip() or None

            if not email and not message_id:
                continue
            if not ev:
                continue

            id_dest = _resolver_destinatario(cur, email, tag, message_id)
            if not id_dest:
                continue

            agora = _agora()
            try:
                raw_date = item.get("date") or item.get("ts")
                if isinstance(raw_date, str) and raw_date:
                    agora = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                agora = _agora()

            err_msg = _motivo_amigavel(
                item.get("reason") or item.get("message") or item.get("error")
            )

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
                (id_dest, ev, agora, err_msg, Json(item)),
            )
        conn.commit()
        return jsonify(success=True), 200
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        # Brevo reenvia se 5xx — preferimos 200 para não loop infinito em bug nosso
        return jsonify(success=True), 200
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
