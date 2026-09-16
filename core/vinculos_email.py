# core/vinculos_email.py — e-mails de solicitação e aprovação de vínculo
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from flask import render_template

from api.brevo.srotas_brevo import enviar_email
from core.pedidos.notificacoes import email_dono_tenant
from global_utils import obter_base_url

log = logging.getLogger(__name__)

ASSUNTO_SOLICITACAO = "Tem alguém querendo vender seus produtos no DropNexo"
ASSUNTO_APROVACAO_PREFIXO = "Parceria aprovada — você já pode revender os produtos de"


def _links_institucionais() -> dict:
    base = obter_base_url()
    return {
        "url_politica_privacidade": os.getenv("URL_POLITICA_PRIVACIDADE") or f"{base}/privacidade",
        "url_politica_interna": os.getenv("URL_POLITICA_INTERNA") or f"{base}/politica-interna",
        "url_dpo": os.getenv("URL_DPO") or f"{base}/dpo",
        "ano": datetime.now().year,
    }


def _nome_tenant(cur, id_tenant: int) -> str:
    cur.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(nome_fantasia), ''), NULLIF(TRIM(nome), ''), 'Conta')
        FROM tbl_tenant WHERE id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    return (row[0] or "Conta").strip() if row else "Conta"


def _tipo_negocio(cur, id_tenant: int) -> str:
    cur.execute("SELECT COALESCE(tipo_negocio, '') FROM tbl_tenant WHERE id = %s", (id_tenant,))
    row = cur.fetchone()
    return (row[0] or "").strip().lower() if row else ""


def _path_vendedores(cur, id_tenant_fn_az: int) -> str:
    if _tipo_negocio(cur, id_tenant_fn_az) == "armazem":
        return "/armazem/vendedores"
    return "/fornecedor/vendedores"


def link_vendedores_com_login(cur, id_tenant_fn_az: int) -> str:
    """URL absoluta da tela de vendedores (login redireciona com ?next= se necessário)."""
    base = obter_base_url().rstrip("/")
    path = _path_vendedores(cur, id_tenant_fn_az)
    return f"{base}{path}"


def link_fornecedores_vendedor() -> str:
    base = obter_base_url().rstrip("/")
    return f"{base}/fornecedores"


def _dados_vendedor_para_email(cur, id_vendedor: int, snapshot: dict | None = None) -> dict[str, str]:
    snap = snapshot if isinstance(snapshot, dict) else {}
    cur.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(nome_fantasia), ''), NULLIF(TRIM(nome), ''), ''),
               COALESCE(NULLIF(TRIM(razao_social), ''), ''),
               COALESCE(NULLIF(TRIM(cidade), ''), ''),
               COALESCE(NULLIF(TRIM(uf), ''), '')
        FROM tbl_tenant WHERE id = %s
        """,
        (id_vendedor,),
    )
    row = cur.fetchone()
    nome = (snap.get("nome_fantasia") or snap.get("tenant_nome") or (row[0] if row else "") or "Vendedor").strip()
    empresa = (snap.get("razao_social") or (row[1] if row else "") or "").strip()
    if empresa and empresa.lower() == nome.lower():
        empresa = ""
    cidade = (snap.get("cidade") or (row[2] if row else "") or "").strip()
    uf = (snap.get("uf") or (row[3] if row else "") or "").strip()
    if cidade and uf:
        local = f"{cidade} / {uf}"
    else:
        local = cidade or uf or ""
    return {"nome_vendedor": nome, "empresa_vendedor": empresa, "local_vendedor": local}


def _parse_snapshot(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            import json

            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _carregar_vinculo_email(cur, id_vinculo: int) -> dict | None:
    cur.execute(
        """
        SELECT id, id_tenant_vendedor, id_tenant_fornecedor, status, snapshot_vendedor
        FROM tbl_vinculo_vendedor_fornecedor
        WHERE id = %s
        """,
        (id_vinculo,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "id_tenant_vendedor": int(row[1]),
        "id_tenant_fornecedor": int(row[2]),
        "status": (row[3] or "").strip().lower(),
        "snapshot": _parse_snapshot(row[4]),
    }


def notificar_solicitacao_vinculo(
    cur,
    id_vinculo: int,
    *,
    criado_por: int | None = None,
) -> tuple[bool, str]:
    """E-mail 1x para o dono do FN/AZ: há vendedor querendo parceria."""
    vinc = _carregar_vinculo_email(cur, id_vinculo)
    if not vinc:
        return False, "Vínculo não encontrado."

    id_fn = vinc["id_tenant_fornecedor"]
    id_vd = vinc["id_tenant_vendedor"]
    email, nome_dest = email_dono_tenant(cur, id_fn)
    if not email:
        return False, "Dono do fornecedor/armazém sem e-mail."

    dados_vd = _dados_vendedor_para_email(cur, id_vd, vinc.get("snapshot"))
    link = link_vendedores_com_login(cur, id_fn)
    assunto = ASSUNTO_SOLICITACAO
    try:
        html = render_template(
            "vinculos/emails/solicitacao_vinculo.html",
            titulo_email=assunto,
            nome_destinatario=nome_dest or "",
            nome_vendedor=dados_vd["nome_vendedor"],
            empresa_vendedor=dados_vd["empresa_vendedor"] or None,
            local_vendedor=dados_vd["local_vendedor"] or None,
            link_acao=link,
            texto_botao="Ver solicitação",
            **_links_institucionais(),
        )
        ok, msg, _ = enviar_email(
            [email],
            assunto,
            html,
            tag="dropnexo_vinculo_solicitacao",
            criado_por=criado_por,
        )
        if not ok:
            return False, msg or "Falha ao enviar e-mail."
        return True, f"E-mail enviado para {email}."
    except Exception as e:
        log.exception("Falha e-mail solicitação vínculo %s", id_vinculo)
        return False, str(e)[:200]


def notificar_aprovacao_vinculo(
    cur,
    id_vinculo: int,
    *,
    criado_por: int | None = None,
) -> tuple[bool, str]:
    """E-mail para o dono do vendedor: parceria aprovada."""
    vinc = _carregar_vinculo_email(cur, id_vinculo)
    if not vinc:
        return False, "Vínculo não encontrado."

    id_fn = vinc["id_tenant_fornecedor"]
    id_vd = vinc["id_tenant_vendedor"]
    email, nome_dest = email_dono_tenant(cur, id_vd)
    if not email:
        return False, "Dono do vendedor sem e-mail."

    nome_parceiro = _nome_tenant(cur, id_fn)
    assunto = f"{ASSUNTO_APROVACAO_PREFIXO} {nome_parceiro}"
    link = link_fornecedores_vendedor()
    try:
        html = render_template(
            "vinculos/emails/aprovacao_vinculo.html",
            titulo_email=assunto,
            nome_destinatario=nome_dest or "",
            nome_parceiro=nome_parceiro,
            link_acao=link,
            texto_botao="Ver fornecedores",
            **_links_institucionais(),
        )
        ok, msg, _ = enviar_email(
            [email],
            assunto,
            html,
            tag="dropnexo_vinculo_aprovacao",
            criado_por=criado_por,
        )
        if not ok:
            return False, msg or "Falha ao enviar e-mail."
        return True, f"E-mail enviado para {email}."
    except Exception as e:
        log.exception("Falha e-mail aprovação vínculo %s", id_vinculo)
        return False, str(e)[:200]


def id_vinculo_por_pares(
    cur,
    *,
    id_vendedor: int,
    id_fornecedor: int,
    id_armazem_fornecedor: int | None = None,
) -> int | None:
    cur.execute(
        """
        SELECT id FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
          AND COALESCE(id_armazem_fornecedor, 0) = COALESCE(%s, 0)
        LIMIT 1
        """,
        (id_vendedor, id_fornecedor, id_armazem_fornecedor),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None
