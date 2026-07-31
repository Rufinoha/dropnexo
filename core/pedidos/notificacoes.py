# core/pedidos/notificacoes.py — e-mails de pedido (dono do tenant)
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from flask import render_template

from api.brevo.srotas_brevo import enviar_email
from global_utils import obter_base_url
from sistema.planos.limites import limites_plano

log = logging.getLogger(__name__)

EMAIL_TESTE_LAYOUT = "hazael@h74.com.br"

STATUS_LABEL = {
    "rascunho": "Rascunho",
    "importado": "Importado",
    "aguardando_pagamento": "Aguardando pagamento",
    "pago": "Pago",
    "cancelado": "Cancelado",
    "em_expedicao": "Em expedição",
    "entregue": "Entregue",
}

EVENTO_ASSUNTO = {
    "confirmado": "Pedido confirmado • DropNexo",
    "aguardando_pagamento": "Pedido aguardando pagamento • DropNexo",
    "pago": "Pagamento confirmado • DropNexo",
    "cancelado": "Pedido cancelado • DropNexo",
    "expedido": "Pedido em expedição • DropNexo",
    "em_expedicao": "Pedido em expedição • DropNexo",
    "entregue": "Pedido entregue • DropNexo",
    "teste": "Teste de layout — pedido • DropNexo",
}

EVENTO_MENSAGEM = {
    "confirmado": "Um pedido foi confirmado e está aguardando pagamento.",
    "aguardando_pagamento": "Há um pedido aguardando pagamento.",
    "pago": "O pagamento de um pedido foi confirmado.",
    "cancelado": "Um pedido foi cancelado.",
    "expedido": "Um pedido entrou em expedição.",
    "em_expedicao": "Um pedido entrou em expedição.",
    "entregue": "Um pedido foi marcado como entregue.",
    "teste": "Este é um e-mail de teste de layout (DEV). O conteúdo abaixo usa dados reais do pedido.",
}


def _email_links_institucionais() -> dict:
    base = obter_base_url()
    return {
        "url_politica_privacidade": os.getenv("URL_POLITICA_PRIVACIDADE") or f"{base}/privacidade",
        "url_politica_interna": os.getenv("URL_POLITICA_INTERNA") or f"{base}/politica-interna",
        "url_dpo": os.getenv("URL_DPO") or f"{base}/dpo",
    }


def _fmt_brl(v: Any) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def email_dono_tenant(cur, id_tenant: int) -> tuple[str | None, str | None]:
    """E-mail do dono ativo; fallback: email_comercial; depois primeiro usuário ativo."""
    cur.execute(
        """
        SELECT u.email, COALESCE(NULLIF(trim(u.nome), ''), t.nome, t.nome_fantasia, '')
        FROM tbl_usuario_tenant ut
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        JOIN tbl_perfil pf ON pf.id = ut.id_perfil
        JOIN tbl_tenant t ON t.id = ut.id_tenant
        WHERE ut.id_tenant = %s AND ut.ativo = TRUE AND u.ativo = TRUE
          AND lower(pf.codigo) = 'dono'
          AND u.email IS NOT NULL AND trim(u.email) <> ''
        ORDER BY ut.id
        LIMIT 1
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if row and row[0]:
        return str(row[0]).strip().lower(), (row[1] or "").strip() or None

    cur.execute(
        "SELECT email_comercial, COALESCE(nome_fantasia, nome, '') FROM tbl_tenant WHERE id = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    if row:
        email = (row[0] or "").strip().lower()
        nome = (row[1] or "").strip() or None
        if email and "@" in email:
            return email, nome

    cur.execute(
        """
        SELECT u.email, COALESCE(NULLIF(trim(u.nome), ''), '')
        FROM tbl_usuario_tenant ut
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        WHERE ut.id_tenant = %s AND ut.ativo = TRUE AND u.ativo = TRUE
          AND u.email IS NOT NULL AND trim(u.email) <> ''
        ORDER BY ut.id
        LIMIT 1
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if row and row[0]:
        return str(row[0]).strip().lower(), (row[1] or "").strip() or None
    return None, None


def _tenant_meta(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT plano, tipo_negocio, COALESCE(nome_fantasia, nome, '')
        FROM tbl_tenant WHERE id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {"plano": None, "tipo_negocio": None, "nome": ""}
    return {
        "plano": row[0],
        "tipo_negocio": (row[1] or "").strip().lower() or None,
        "nome": (row[2] or "").strip(),
    }


def _tipo_limites(tipo_negocio: str | None, papel: str) -> str:
    t = (tipo_negocio or "").strip().lower()
    if t in ("vendedor", "fornecedor"):
        return t
    return papel if papel in ("vendedor", "fornecedor") else "vendedor"


def tenant_pode_email_pedidos(cur, id_tenant: int, papel: str) -> bool:
    meta = _tenant_meta(cur, id_tenant)
    lim = limites_plano(
        plano=meta.get("plano"),
        tipo_negocio=_tipo_limites(meta.get("tipo_negocio"), papel),
    )
    return bool(lim.get("email_pedidos"))


def _itens_email(ped: dict) -> list[dict]:
    out = []
    for it in ped.get("itens") or []:
        qtd = int(it.get("quantidade") or 0)
        subtotal = it.get("subtotal_drop")
        if subtotal is None:
            preco = float(it.get("valor_drop") or it.get("preco_unitario") or 0)
            subtotal = preco * qtd if qtd else preco
        out.append(
            {
                "nome": (it.get("nome_produto") or it.get("nome") or "Item").strip(),
                "sku": (it.get("sku") or "").strip(),
                "quantidade": qtd,
                "valor_fmt": _fmt_brl(subtotal),
            }
        )
    return out[:12]


def _status_atual(ped: dict) -> str:
    return (ped.get("status_vendedor") or ped.get("status") or "").strip()


def _contexto_email(
    cur,
    ped: dict,
    *,
    evento: str,
    papel: str,
    nome_destinatario: str | None,
    forcar_email: str | None = None,
    aviso_teste: str | None = None,
) -> dict:
    base = obter_base_url().rstrip("/")
    st = _status_atual(ped)
    numero = (ped.get("numero") or str(ped.get("id") or "")).strip()
    id_v = int(ped.get("id_tenant_vendedor") or 0)
    id_f = int(ped.get("id_tenant_fornecedor") or 0)

    if papel == "fornecedor":
        link = f"{base}/fornecedor/pedidos"
        papel_label = "Fornecedor"
        rotulo_contraparte = "Vendedor"
        meta_c = _tenant_meta(cur, id_v) if id_v else {"nome": ""}
        nome_contraparte = ped.get("vendedor_nome") or meta_c.get("nome") or ""
    else:
        link = f"{base}/vendedor/pedidos"
        papel_label = "Vendedor"
        rotulo_contraparte = "Fornecedor"
        meta_c = _tenant_meta(cur, id_f) if id_f else {"nome": ""}
        nome_contraparte = ped.get("fornecedor_nome") or meta_c.get("nome") or ""

    return {
        "titulo_email": EVENTO_ASSUNTO.get(evento) or "Atualização de pedido • DropNexo",
        "nome_destinatario": nome_destinatario or "",
        "mensagem_principal": EVENTO_MENSAGEM.get(evento) or "Há uma atualização em um pedido.",
        "numero_pedido": numero,
        "status_label": STATUS_LABEL.get(st, st or "—"),
        "papel_label": papel_label,
        "rotulo_contraparte": rotulo_contraparte,
        "nome_contraparte": nome_contraparte,
        "cliente_nome": (ped.get("cliente_nome") or "").strip(),
        "valor_total_fmt": _fmt_brl(ped.get("valor_total")),
        "itens": _itens_email(ped),
        "codigo_rastreio": (ped.get("codigo_rastreio") or "").strip(),
        "transportadora": (ped.get("transportadora") or "").strip(),
        "link_pedido": link,
        "aviso_teste": aviso_teste or "",
        "ano": datetime.now().year,
        "destinatario_email": forcar_email,
        **_email_links_institucionais(),
    }


def _render_html(ctx: dict) -> str:
    return render_template("pedidos/emails/evento_pedido.html", **ctx)


def _enviar_um(
    cur,
    ped: dict,
    *,
    evento: str,
    papel: str,
    id_tenant: int,
    forcar_destinatario: str | None = None,
    ignorar_plano: bool = False,
    aviso_teste: str | None = None,
    criado_por: int | None = None,
) -> tuple[bool, str]:
    if not ignorar_plano and not tenant_pode_email_pedidos(cur, id_tenant, papel):
        return False, "plano_sem_email_pedidos"

    if forcar_destinatario:
        email = forcar_destinatario.strip().lower()
        nome = None
    else:
        email, nome = email_dono_tenant(cur, id_tenant)
    if not email or "@" not in email:
        return False, "sem_destinatario"

    ctx = _contexto_email(
        cur,
        ped,
        evento=evento,
        papel=papel,
        nome_destinatario=nome,
        forcar_email=forcar_destinatario,
        aviso_teste=aviso_teste,
    )
    html = _render_html(ctx)
    assunto = EVENTO_ASSUNTO.get(evento) or "Atualização de pedido • DropNexo"
    ok, msg, _ = enviar_email(
        [email],
        assunto,
        html,
        tag="dropnexo_pedido",
        criado_por=criado_por,
    )
    return ok, msg


def notificar_evento_pedido(
    cur,
    id_pedido: int,
    evento: str,
    *,
    criado_por: int | None = None,
) -> None:
    """Best-effort: notifica donos do vendedor e do fornecedor (se o plano permitir)."""
    try:
        from core.pedidos.servico import obter_pedido

        ped = obter_pedido(cur, int(id_pedido))
        if not ped:
            return
        id_v = int(ped.get("id_tenant_vendedor") or 0)
        id_f = int(ped.get("id_tenant_fornecedor") or 0)
        if id_v:
            ok, msg = _enviar_um(
                cur, ped, evento=evento, papel="vendedor", id_tenant=id_v, criado_por=criado_por
            )
            if not ok and msg not in ("plano_sem_email_pedidos", "sem_destinatario"):
                log.warning("E-mail pedido %s (vendedor): %s", id_pedido, msg)
        if id_f:
            ok, msg = _enviar_um(
                cur, ped, evento=evento, papel="fornecedor", id_tenant=id_f, criado_por=criado_por
            )
            if not ok and msg not in ("plano_sem_email_pedidos", "sem_destinatario"):
                log.warning("E-mail pedido %s (fornecedor): %s", id_pedido, msg)
    except Exception:
        log.exception("Falha ao notificar pedido %s (%s)", id_pedido, evento)


def enviar_teste_layout(
    cur,
    id_pedido: int,
    *,
    criado_por: int | None = None,
) -> tuple[bool, str]:
    """Sempre envia para EMAIL_TESTE_LAYOUT (layout DEV). Ignora plano."""
    from core.pedidos.servico import obter_pedido

    ped = obter_pedido(cur, int(id_pedido))
    if not ped:
        return False, "Pedido não encontrado."
    id_v = int(ped.get("id_tenant_vendedor") or 0) or 0
    ok, msg = _enviar_um(
        cur,
        ped,
        evento="teste",
        papel="vendedor",
        id_tenant=id_v or int(ped.get("id_tenant_fornecedor") or 0),
        forcar_destinatario=EMAIL_TESTE_LAYOUT,
        ignorar_plano=True,
        aviso_teste=f"Teste DEV — destinatário forçado: {EMAIL_TESTE_LAYOUT}",
        criado_por=criado_por,
    )
    if ok:
        return True, f"E-mail de teste enviado para {EMAIL_TESTE_LAYOUT}."
    return False, msg or "Falha ao enviar."
