# api/hubsupport/hubsupport_service.py — provisionamento, chamados, isolamento por tenant
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

from flask import session

from api.hubsupport.hubsupport_client import HubSupportClient, HubSupportError

logger = logging.getLogger(__name__)

PREFIX = "dropnexo"
CATEGORIAS = ("duvida", "sugestao", "problema")
PRIORIDADES = ("baixa", "normal", "alta", "urgente")
STATUS_SEM_RESPOSTA = ("fechado", "cancelado")

CATEGORIA_LABEL = {
    "duvida": "Dúvida",
    "sugestao": "Sugestão",
    "problema": "Problema",
}
PRIORIDADE_LABEL = {
    "baixa": "Baixa",
    "normal": "Normal",
    "alta": "Alta",
    "urgente": "Urgente",
}
STATUS_LABEL = {
    "aberto": "Aberto",
    "em_atendimento": "Em atendimento",
    "aguardando_cliente": "Aguardando você",
    "fechado": "Fechado",
    "cancelado": "Cancelado",
}

MSG_TABELAS_SQL = (
    "Integração HubSupport: execute o SQL "
    "__doc/sql/090_hubsupport_integracao.sql no banco."
)


def external_id_empresa(id_tenant: int) -> str:
    return f"{PREFIX}:empresa:{int(id_tenant)}"


def external_id_usuario(id_usuario: int) -> str:
    return f"{PREFIX}:usuario:{int(id_usuario)}"


def external_id_chamado(chamado_uuid: str | None = None) -> str:
    uid = (chamado_uuid or str(uuid.uuid4())).strip()
    return f"{PREFIX}:chamado:{uid}"


def uuid_de_external_id(external_id: str) -> str:
    m = re.match(rf"^{re.escape(PREFIX)}:chamado:(.+)$", external_id or "")
    return m.group(1) if m else (external_id or "")


def _portal_hubsupport() -> str:
    return (os.getenv("HUBSUPPORT_PORTAL") or "h74").strip() or "h74"


def _fmt_data_iso(val) -> str:
    if not val:
        return ""
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _usuario_ver_todos_do_tenant() -> bool:
    """Dono/admin do tenant vê todos os chamados DO MESMO tenant — nunca de outro."""
    perfil = (session.get("perfil_codigo") or session.get("papel") or "").strip().lower()
    if session.get("eh_desenvolvedor"):
        return True
    return perfil in ("dono", "administrador", "admin", "gestor")


def _log_api(conn, operacao: str, sucesso: bool, mensagem: str = "", http_status: int | None = None):
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tbl_hubsupport_api_log (operacao, sucesso, mensagem, http_status)
            VALUES (%s, %s, %s, %s)
            """,
            (operacao[:40], bool(sucesso), (mensagem or "")[:2000] or None, http_status),
        )
    except Exception:
        pass


def _extrair_hubsupport_id(resposta: dict) -> str | None:
    if not isinstance(resposta, dict):
        return None
    for key in ("id", "hubsupport_id", "chamado_id"):
        val = resposta.get(key)
        if val is not None:
            return str(val)
    data = resposta.get("data")
    if isinstance(data, dict):
        for key in ("id", "hubsupport_id", "chamado_id"):
            val = data.get(key)
            if val is not None:
                return str(val)
    return None


def _salvar_map(
    conn,
    tipo: str,
    id_local: int | None,
    id_tenant: int | None,
    external_id: str,
    hubsupport_id: str | None = None,
):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tbl_hubsupport_map (tipo, id_local, id_tenant, external_id, hubsupport_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (external_id) DO UPDATE SET
            hubsupport_id = COALESCE(EXCLUDED.hubsupport_id, tbl_hubsupport_map.hubsupport_id),
            id_tenant = COALESCE(EXCLUDED.id_tenant, tbl_hubsupport_map.id_tenant),
            updated_at = NOW()
        """,
        (tipo, id_local, id_tenant, external_id, hubsupport_id),
    )


def _carregar_tenant(conn, id_tenant: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id,
               COALESCE(NULLIF(TRIM(nome_fantasia), ''), NULLIF(TRIM(nome), ''),
                        NULLIF(TRIM(nome_completo), ''), NULLIF(TRIM(razao_social), ''), '') AS nome,
               COALESCE(documento, '') AS documento,
               COALESCE(NULLIF(TRIM(email_comercial), ''), '') AS email,
               COALESCE(tipo_negocio, '') AS tipo_negocio,
               COALESCE(tipo_pessoa, '') AS tipo_pessoa
        FROM tbl_tenant
        WHERE id = %s
        LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        raise HubSupportError("Tenant não encontrado para integração.")
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def _carregar_usuario(conn, id_usuario: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, COALESCE(nome, '') AS nome, COALESCE(email, '') AS email
        FROM tbl_usuario
        WHERE id = %s
        LIMIT 1
        """,
        (int(id_usuario),),
    )
    row = cur.fetchone()
    if not row:
        raise HubSupportError("Usuário não encontrado para integração.")
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def _tipo_pessoa_hubsupport(tenant: dict) -> str:
    """
    HubSupport exige pf/pj coerente com o documento:
    - PJ → CNPJ 14 dígitos
    - PF → CPF 11 dígitos (ou sem documento)
    DropNexo grava tipo_pessoa como F/J.
    """
    doc = re.sub(r"\D", "", tenant.get("documento") or "")
    if len(doc) == 11:
        return "pf"
    if len(doc) == 14:
        return "pj"

    raw = (tenant.get("tipo_pessoa") or "").strip().upper()
    if raw in ("F", "PF"):
        return "pf"
    if raw in ("J", "PJ"):
        return "pj"
    # sem documento confiável: PF evita ck_cliente_pj_documento
    return "pf"


def _payload_cliente(tenant: dict, id_tenant: int, email_fallback: str = "") -> dict:
    nome = (tenant.get("nome") or f"Tenant {id_tenant}").strip()
    documento = re.sub(r"\D", "", tenant.get("documento") or "")
    email = (tenant.get("email") or email_fallback or "").strip()
    tipo = _tipo_pessoa_hubsupport(tenant)

    # HubSupport: PJ exige CNPJ 14 dígitos — senão cai para PF (evita ck_cliente_pj_documento)
    if tipo == "pj" and len(documento) != 14:
        tipo = "pf"
        if len(documento) != 11:
            documento = ""
    elif tipo == "pf" and documento and len(documento) != 11:
        documento = ""

    out = {
        "external_id": external_id_empresa(id_tenant),
        "tipo_pessoa": tipo,
        "nome": nome,
    }
    if documento:
        out["documento"] = documento
    if email:
        out["email"] = email
    return out


def _payload_usuario(usuario: dict, id_usuario: int, id_tenant: int) -> dict:
    return {
        "external_id": external_id_usuario(id_usuario),
        "cliente_external_id": external_id_empresa(id_tenant),
        "nome": (usuario.get("nome") or "Usuário").strip(),
        "email": usuario.get("email"),
        "ver_todos_chamados": _usuario_ver_todos_do_tenant(),
    }


def garantir_provisionamento(
    conn,
    id_usuario: int,
    id_tenant: int,
    client: HubSupportClient | None = None,
) -> None:
    """Garante que HubSupport recebe o tenant (nome) e o usuário (nome) corretos."""
    client = client or HubSupportClient(conn=conn)
    if not client.configurado():
        raise HubSupportError(
            "Integração HubSupport não configurada. "
            "Informe a chave de API em Configurações → HubSupport."
        )

    tenant = _carregar_tenant(conn, id_tenant)
    usuario = _carregar_usuario(conn, id_usuario)
    ext_empresa = external_id_empresa(id_tenant)
    ext_usuario = external_id_usuario(id_usuario)

    try:
        resp_cli = client.upsert_cliente(
            _payload_cliente(tenant, id_tenant, usuario.get("email") or "")
        )
        _salvar_map(
            conn,
            "empresa",
            id_tenant,
            id_tenant,
            ext_empresa,
            _extrair_hubsupport_id(resp_cli if isinstance(resp_cli, dict) else {}),
        )
        _log_api(conn, "provisionar_cliente", True, tenant.get("nome") or "")

        resp_usr = client.upsert_usuario(_payload_usuario(usuario, id_usuario, id_tenant))
        _salvar_map(
            conn,
            "usuario",
            id_usuario,
            id_tenant,
            ext_usuario,
            _extrair_hubsupport_id(resp_usr if isinstance(resp_usr, dict) else {}),
        )
        _log_api(conn, "provisionar_usuario", True, usuario.get("nome") or "")
    except HubSupportError as e:
        _log_api(conn, "provisionar", False, str(e), e.status_code)
        raise


def _row_para_chamado(cols, row) -> dict:
    d = dict(zip(cols, row))
    ext = d.get("external_id") or ""
    st = d.get("status") or "aberto"
    cat = d.get("categoria") or ""
    pri = d.get("prioridade") or "normal"
    return {
        "external_id": ext,
        "uuid": uuid_de_external_id(ext),
        "protocolo": d.get("protocolo") or "",
        "titulo": d.get("titulo") or "",
        "status": st,
        "status_label": STATUS_LABEL.get(st, st),
        "categoria": cat,
        "categoria_label": CATEGORIA_LABEL.get(cat, cat),
        "prioridade": pri,
        "prioridade_label": PRIORIDADE_LABEL.get(pri, pri),
        "data_abertura": _fmt_data_iso(d.get("criado_em")),
        "data_ultima_interacao": _fmt_data_iso(d.get("ultima_interacao_em") or d.get("atualizado_em")),
        "ultima_interacao_preview": d.get("ultima_interacao_preview") or "",
        "id_usuario": d.get("id_usuario"),
    }


def _chamado_autorizado(conn, id_usuario: int, id_tenant: int, external_id: str) -> bool:
    """Isolamento forte: chamado só é acessível se pertencer ao tenant da sessão."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id_usuario, id_tenant
        FROM tbl_hubsupport_chamado
        WHERE external_id = %s
        LIMIT 1
        """,
        (external_id,),
    )
    row = cur.fetchone()
    if not row:
        return False
    if int(row[1]) != int(id_tenant):
        return False
    if int(row[0]) == int(id_usuario):
        return True
    return _usuario_ver_todos_do_tenant()


def listar_chamados_tenant(
    conn,
    id_usuario: int,
    id_tenant: int,
    *,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Lista apenas chamados do tenant da sessão."""
    page = max(1, int(page or 1))
    per_page = min(50, max(5, int(per_page or 20)))
    cur = conn.cursor()
    ver_todos = _usuario_ver_todos_do_tenant()

    if ver_todos:
        cur.execute(
            "SELECT COUNT(*) FROM tbl_hubsupport_chamado WHERE id_tenant = %s",
            (int(id_tenant),),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*) FROM tbl_hubsupport_chamado
            WHERE id_tenant = %s AND id_usuario = %s
            """,
            (int(id_tenant), int(id_usuario)),
        )
    total = int(cur.fetchone()[0] or 0)
    offset = (page - 1) * per_page

    cols_sql = """
        SELECT external_id, protocolo, titulo, categoria, prioridade, status,
               ultima_interacao_preview, criado_em, ultima_interacao_em, atualizado_em, id_usuario
        FROM tbl_hubsupport_chamado
    """
    order = " ORDER BY atualizado_em DESC NULLS LAST LIMIT %s OFFSET %s"

    if ver_todos:
        cur.execute(cols_sql + " WHERE id_tenant = %s" + order, (int(id_tenant), per_page, offset))
    else:
        cur.execute(
            cols_sql + " WHERE id_tenant = %s AND id_usuario = %s" + order,
            (int(id_tenant), int(id_usuario), per_page, offset),
        )

    cols = [c[0] for c in cur.description]
    chamados = [_row_para_chamado(cols, r) for r in cur.fetchall()]
    return {
        "chamados": chamados,
        "page": page,
        "per_page": per_page,
        "total": total,
        "fonte": "local",
    }


def _append_interacao_cache(conn, external_id: str, item: dict) -> None:
    cur = conn.cursor()
    interacao_id = item.get("interacao_id") or item.get("id")
    anexos_json = json.dumps(item.get("anexos") or [], ensure_ascii=False)
    if interacao_id:
        cur.execute(
            """
            SELECT anexos_json FROM tbl_hubsupport_interacao
            WHERE external_id_chamado = %s AND interacao_id = %s
            LIMIT 1
            """,
            (external_id, str(interacao_id)),
        )
        row = cur.fetchone()
        if row:
            # Reentrega de webhook / sync: completa anexos se o cache local estava vazio.
            anexos_novos = item.get("anexos") or []
            if anexos_novos:
                atuais = row[0]
                try:
                    atuais_lista = json.loads(atuais or "[]") if not isinstance(atuais, list) else atuais
                except Exception:
                    atuais_lista = []
                if not atuais_lista:
                    cur.execute(
                        """
                        UPDATE tbl_hubsupport_interacao
                        SET anexos_json = %s
                        WHERE external_id_chamado = %s AND interacao_id = %s
                        """,
                        (anexos_json, external_id, str(interacao_id)),
                    )
            return
    cur.execute(
        """
        INSERT INTO tbl_hubsupport_interacao (
            external_id_chamado, interacao_id, tipo_autor, nome_autor, corpo,
            created_at_remoto, anexos_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            external_id,
            str(interacao_id) if interacao_id else None,
            (item.get("tipo_autor") or "cliente")[:20],
            (item.get("nome_autor") or "")[:120] or None,
            item.get("corpo") or "",
            item.get("created_at") or None,
            anexos_json,
        ),
    )


def _listar_interacoes_cache(conn, external_id: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT interacao_id, tipo_autor, nome_autor, corpo, created_at_remoto, anexos_json, synced_at
        FROM tbl_hubsupport_interacao
        WHERE external_id_chamado = %s
        ORDER BY COALESCE(created_at_remoto, synced_at) ASC, id ASC
        """,
        (external_id,),
    )
    out = []
    for row in cur.fetchall():
        anexos = []
        try:
            anexos = json.loads(row[5] or "[]")
        except Exception:
            anexos = []
        out.append(
            {
                "id": row[0],
                "tipo_autor": row[1],
                "nome_autor": row[2] or ("Suporte" if row[1] == "agente" else "Você"),
                "corpo": row[3] or "",
                "created_at": _fmt_data_iso(row[4] or row[6]),
                "anexos": anexos if isinstance(anexos, list) else [],
            }
        )
    return out


def abrir_chamado(
    conn,
    id_usuario: int,
    id_tenant: int,
    *,
    titulo: str,
    mensagem: str,
    categoria: str,
    prioridade: str,
    modulo: str = "",
    url_origem: str = "",
    tela: str = "",
    anexos: list | None = None,
) -> dict:
    titulo = (titulo or "").strip()
    mensagem = (mensagem or "").strip()
    categoria = (categoria or "duvida").strip().lower()
    prioridade = (prioridade or "normal").strip().lower()

    if len(titulo) < 3:
        raise HubSupportError("Informe um assunto com pelo menos 3 caracteres.")
    if len(mensagem) < 5:
        raise HubSupportError("Descreva sua demanda com pelo menos 5 caracteres.")
    if categoria not in CATEGORIAS:
        raise HubSupportError("Categoria inválida.")
    if prioridade not in PRIORIDADES:
        raise HubSupportError("Prioridade inválida.")

    client = HubSupportClient(conn=conn)
    tenant = _carregar_tenant(conn, id_tenant)
    usuario = _carregar_usuario(conn, id_usuario)
    garantir_provisionamento(conn, id_usuario, id_tenant, client)

    chamado_uuid = str(uuid.uuid4())
    ext_chamado = external_id_chamado(chamado_uuid)
    ext_usuario = external_id_usuario(id_usuario)

    tags = {
        "sistema_origem": "dropnexo",
        "id_tenant": int(id_tenant),
        "tenant_nome": (tenant.get("nome") or "").strip() or None,
        "modulo": (modulo or "").strip() or None,
        "tela": (tela or "").strip() or None,
        "url": (url_origem or "").strip() or None,
        "perfil": session.get("perfil_codigo") or session.get("papel"),
    }
    tags = {k: v for k, v in tags.items() if v is not None}

    payload = {
        "external_id": ext_chamado,
        "usuario_external_id": ext_usuario,
        "titulo": titulo,
        "mensagem": mensagem,
        "categoria": categoria,
        "prioridade": prioridade,
        "tags": tags,
        "cliente": _payload_cliente(tenant, id_tenant, usuario.get("email") or ""),
        "usuario": _payload_usuario(usuario, id_usuario, id_tenant),
        "canal": "api",
        "portal": _portal_hubsupport(),
    }

    try:
        resp = client.criar_chamado(payload, idempotency_key=ext_chamado)
    except HubSupportError as e:
        _log_api(conn, "abrir_chamado", False, str(e), e.status_code)
        raise

    from api.hubsupport.hubsupport_anexos import enviar_anexos_chamado

    try:
        anexos_meta = enviar_anexos_chamado(
            client,
            ext_chamado,
            anexos,
            enviado_por=(usuario.get("nome") or "").strip() or "Você",
        )
    except HubSupportError as e:
        _log_api(conn, "anexo_chamado", False, str(e), e.status_code)
        raise

    hs_id = _extrair_hubsupport_id(resp if isinstance(resp, dict) else {})
    protocolo = ""
    status = "aberto"
    if isinstance(resp, dict):
        data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
        protocolo = str(data.get("protocolo") or "")
        status = str(data.get("status") or "aberto")

    _log_api(conn, "abrir_chamado", True, f"protocolo={protocolo or '—'} tenant={id_tenant}", 200)
    _salvar_map(conn, "chamado", None, id_tenant, ext_chamado, hs_id)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tbl_hubsupport_chamado (
            external_id, hubsupport_id, protocolo, id_tenant, id_usuario,
            titulo, categoria, prioridade, status, tags_json, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            ext_chamado,
            hs_id,
            protocolo or None,
            int(id_tenant),
            int(id_usuario),
            titulo,
            categoria,
            prioridade,
            status,
            json.dumps(tags, ensure_ascii=False),
        ),
    )

    _append_interacao_cache(
        conn,
        ext_chamado,
        {
            "interacao_id": "abertura",
            "tipo_autor": "cliente",
            "nome_autor": (usuario.get("nome") or "").strip() or "Você",
            "corpo": mensagem,
            "anexos": anexos_meta,
        },
    )

    return {
        "external_id": ext_chamado,
        "uuid": chamado_uuid,
        "protocolo": protocolo,
        "titulo": titulo,
        "status": status,
        "status_label": STATUS_LABEL.get(status, status),
        "tenant_nome": tenant.get("nome"),
        "usuario_nome": usuario.get("nome"),
    }


def detalhar_chamado(conn, id_usuario: int, id_tenant: int, external_id: str) -> dict:
    external_id = (external_id or "").strip()
    if not external_id.startswith(f"{PREFIX}:chamado:"):
        external_id = external_id_chamado(external_id)

    if not _chamado_autorizado(conn, id_usuario, id_tenant, external_id):
        raise HubSupportError("Chamado não encontrado ou acesso negado.", status_code=403)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT protocolo, titulo, categoria, prioridade, status,
               id_usuario, criado_em, ultima_interacao_em
        FROM tbl_hubsupport_chamado
        WHERE external_id = %s AND id_tenant = %s
        LIMIT 1
        """,
        (external_id, int(id_tenant)),
    )
    row = cur.fetchone()
    if not row:
        raise HubSupportError("Chamado não encontrado.", status_code=404)

    # Detalhe = banco local + disco (padrão BARACAT). Sem GET HubSupport na abertura.
    protocolo, titulo, categoria, prioridade, status = (
        str(row[0] or ""),
        str(row[1] or ""),
        str(row[2] or ""),
        str(row[3] or "normal"),
        str(row[4] or "aberto"),
    )

    solicitante_nome = ""
    id_dono = int(row[5] or 0)
    if id_dono:
        try:
            dono = _carregar_usuario(conn, id_dono)
            solicitante_nome = (dono.get("nome") or "").strip()
        except HubSupportError:
            pass

    from api.hubsupport.hubsupport_anexos import (
        consolidar_anexos_thread,
        listar_anexos_disco,
        mesclar_anexos,
        ordenar_anexos_mais_recentes,
    )

    thread = _listar_interacoes_cache(conn, external_id)
    anexos_chamado = ordenar_anexos_mais_recentes(
        mesclar_anexos(consolidar_anexos_thread(thread), listar_anexos_disco(external_id))
    )

    return {
        "external_id": external_id,
        "uuid": uuid_de_external_id(external_id),
        "protocolo": protocolo,
        "titulo": titulo,
        "status": status,
        "status_label": STATUS_LABEL.get(status, status),
        "categoria": categoria,
        "categoria_label": CATEGORIA_LABEL.get(categoria, categoria),
        "prioridade": prioridade,
        "prioridade_label": PRIORIDADE_LABEL.get(prioridade, prioridade),
        "pode_responder": status not in STATUS_SEM_RESPOSTA,
        "solicitante_nome": solicitante_nome,
        "data_abertura": _fmt_data_iso(row[6]),
        "data_ultima_interacao": _fmt_data_iso(row[7]),
        "interacoes": thread,
        "anexos": anexos_chamado,
        "anexos_status": "ok" if anexos_chamado else "vazio",
        "fonte": "local",
    }


def baixar_anexo_local(
    conn, id_usuario: int, id_tenant: int, external_id: str, nome_armazenado: str
) -> tuple[str, str]:
    from api.hubsupport.hubsupport_anexos import resolver_caminho_anexo_local

    external_id = (external_id or "").strip()
    if not external_id.startswith(f"{PREFIX}:chamado:"):
        external_id = external_id_chamado(external_id)
    if not _chamado_autorizado(conn, id_usuario, id_tenant, external_id):
        raise HubSupportError("Chamado não encontrado ou acesso negado.", status_code=403)
    return resolver_caminho_anexo_local(external_id, nome_armazenado)


def responder_chamado(
    conn,
    id_usuario: int,
    id_tenant: int,
    external_id: str,
    corpo: str,
    *,
    anexos: list | None = None,
) -> dict:
    external_id = (external_id or "").strip()
    if not external_id.startswith(f"{PREFIX}:chamado:"):
        external_id = external_id_chamado(external_id)

    corpo = (corpo or "").strip()
    if len(corpo) < 2 and not (anexos or []):
        raise HubSupportError("Digite uma resposta válida ou anexe um arquivo.")

    if not _chamado_autorizado(conn, id_usuario, id_tenant, external_id):
        raise HubSupportError("Chamado não encontrado ou acesso negado.", status_code=403)

    garantir_provisionamento(conn, id_usuario, id_tenant)
    usuario = _carregar_usuario(conn, id_usuario)
    client = HubSupportClient(conn=conn)
    nome_autor = (usuario.get("nome") or "").strip() or "Você"

    if corpo:
        try:
            resp = client.criar_interacao(external_id, corpo)
        except HubSupportError as e:
            _log_api(conn, "responder_chamado", False, str(e), e.status_code)
            raise
    else:
        resp = {}
        corpo = "(anexo)"

    from api.hubsupport.hubsupport_anexos import enviar_anexos_chamado

    try:
        anexos_meta = enviar_anexos_chamado(
            client, external_id, anexos, enviado_por=nome_autor
        )
    except HubSupportError as e:
        _log_api(conn, "anexo_chamado", False, str(e), e.status_code)
        raise

    _append_interacao_cache(
        conn,
        external_id,
        {
            "interacao_id": _extrair_hubsupport_id(resp if isinstance(resp, dict) else {})
            or str(uuid.uuid4()),
            "tipo_autor": "cliente",
            "nome_autor": nome_autor,
            "corpo": corpo,
            "anexos": anexos_meta,
        },
    )
    preview = corpo if corpo != "(anexo)" else (
        anexos_meta[0]["nome"] if anexos_meta else corpo
    )
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_hubsupport_chamado
        SET status = CASE WHEN status IN ('aberto', 'aguardando_cliente') THEN 'em_atendimento' ELSE status END,
            ultima_interacao_preview = %s,
            ultima_interacao_em = NOW(),
            atualizado_em = NOW()
        WHERE external_id = %s AND id_tenant = %s
        """,
        (str(preview)[:240], external_id, int(id_tenant)),
    )
    _log_api(conn, "responder_chamado", True, external_id, 200)
    return {"ok": True, "external_id": external_id, "anexos": anexos_meta}


def webhook_delivery_processado(conn, delivery_id: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM tbl_hubsupport_webhook_entrega WHERE delivery_id = %s LIMIT 1",
        (delivery_id,),
    )
    return bool(cur.fetchone())


def webhook_registrar_entrega(conn, delivery_id: str, evento: str, ext: str | None) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tbl_hubsupport_webhook_entrega (delivery_id, evento, chamado_external_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (delivery_id) DO NOTHING
        """,
        (delivery_id, (evento or "")[:80], ext),
    )


def _atualizar_chamado_webhook(
    conn,
    ext: str,
    *,
    status: str | None = None,
    protocolo: str | None = None,
    preview: str | None = None,
) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_hubsupport_chamado SET
            status = COALESCE(%s, status),
            protocolo = COALESCE(%s, protocolo),
            ultima_interacao_preview = COALESCE(%s, ultima_interacao_preview),
            ultima_interacao_em = NOW(),
            atualizado_em = NOW()
        WHERE external_id = %s
        """,
        (
            (status or None),
            (protocolo or None),
            (preview[:240] if preview else None),
            ext,
        ),
    )
    return cur.rowcount or 0


def processar_webhook(
    conn,
    payload: dict,
    *,
    delivery_id: str = "",
    event_header: str = "",
    client_ip: str = "",
) -> dict:
    from api.hubsupport.hubsupport_config import registrar_log_webhook

    if not isinstance(payload, dict):
        return {"message": "Payload ignorado.", "ignored": True}

    evento = str(payload.get("event") or event_header or "").strip()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    occurred_at = payload.get("occurred_at")
    ext = (data.get("chamado_external_id") or data.get("external_id") or "").strip()

    registrar_log_webhook(
        conn,
        evento or "desconhecido",
        ext or None,
        {
            **payload,
            "_meta": {
                "delivery_id": delivery_id or None,
                "event_header": event_header or None,
                "client_ip": client_ip or None,
            },
        },
    )

    if not evento:
        return {"message": "Evento ignorado."}

    # Só processa chamados DropNexo (prefixo) — ignora BARACAT e outros
    if ext and not ext.startswith(f"{PREFIX}:"):
        return {"message": "Evento de outro sistema — ignorado.", "evento": evento}

    from api.hubsupport.hubsupport_anexos import (
        _lista_anexos_raw,
        materializar_anexos_remotos,
        mesclar_anexos,
        normalizar_anexos_lista,
        resgatar_anexos_hubsupport,
    )

    if evento == "chamado.interacao.criada":
        tipo_autor = str(data.get("tipo_autor") or "").lower()
        corpo = (data.get("corpo") or "").strip()
        if tipo_autor == "cliente":
            return {"message": "Interação de cliente ignorada (origem local).", "evento": evento}
        if tipo_autor != "agente" or not ext:
            return {"message": "Interação ignorada.", "evento": evento}
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_hubsupport_chamado WHERE external_id = %s LIMIT 1", (ext,))
        if not cur.fetchone():
            return {
                "message": "Chamado local não encontrado (outro tenant/sistema).",
                "evento": evento,
                "chamado_external_id": ext,
            }
        nome_agente = str(data.get("nome_autor") or data.get("nome") or "Suporte").strip()
        anexos_brutos = _lista_anexos_raw(data) or normalizar_anexos_lista(data)
        for raw_a in anexos_brutos:
            if isinstance(raw_a, dict):
                raw_a.setdefault("enviado_por", nome_agente)
                if occurred_at and not raw_a.get("enviado_em"):
                    raw_a["enviado_em"] = occurred_at
        anexos_meta = materializar_anexos_remotos(
            conn, ext, anexos_brutos, log_fn=lambda c, op, ok, msg, st=None: _log_api(c, op, ok, msg, st)
        )
        resgate = resgatar_anexos_hubsupport(
            conn, ext, log_fn=lambda c, op, ok, msg, st=None: _log_api(c, op, ok, msg, st)
        )
        if resgate.get("ok") and resgate.get("anexos"):
            anexos_meta = mesclar_anexos(anexos_meta, resgate["anexos"])

        if not corpo and not anexos_meta:
            return {"message": "Interação sem conteúdo.", "evento": evento}

        _append_interacao_cache(
            conn,
            ext,
            {
                "interacao_id": data.get("interacao_id") or data.get("id"),
                "tipo_autor": "agente",
                "nome_autor": nome_agente,
                "corpo": corpo or "(anexo)",
                "created_at": occurred_at,
                "anexos": anexos_meta,
            },
        )
        _atualizar_chamado_webhook(
            conn,
            ext,
            status=data.get("status"),
            protocolo=data.get("protocolo"),
            preview=corpo or (anexos_meta[0].get("nome") if anexos_meta else None),
        )
        return {
            "message": "Resposta do suporte registrada.",
            "evento": evento,
            "chamado_external_id": ext,
            "anexos": len(anexos_meta),
        }

    if evento in ("chamado.anexo.criado", "chamado.anexo.adicionado", "chamado.anexos.atualizados"):
        if not ext:
            return {"message": "Anexo ignorado — sem external_id.", "evento": evento}
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_hubsupport_chamado WHERE external_id = %s LIMIT 1", (ext,))
        if not cur.fetchone():
            return {"message": "Chamado local não encontrado.", "evento": evento}
        anexos_brutos = _lista_anexos_raw(data) or normalizar_anexos_lista(data)
        metas = materializar_anexos_remotos(
            conn, ext, anexos_brutos, log_fn=lambda c, op, ok, msg, st=None: _log_api(c, op, ok, msg, st)
        )
        if not metas:
            resgate = resgatar_anexos_hubsupport(
                conn, ext, log_fn=lambda c, op, ok, msg, st=None: _log_api(c, op, ok, msg, st)
            )
            metas = resgate.get("anexos") or []
        if metas:
            _append_interacao_cache(
                conn,
                ext,
                {
                    "interacao_id": data.get("interacao_id") or data.get("id") or f"anexo-{uuid.uuid4().hex[:8]}",
                    "tipo_autor": "agente",
                    "nome_autor": str(data.get("nome_autor") or "Suporte"),
                    "corpo": "(anexo)",
                    "created_at": occurred_at,
                    "anexos": metas,
                },
            )
            _atualizar_chamado_webhook(conn, ext, preview=metas[0].get("nome"))
        return {
            "message": "Anexo espelhado." if metas else "Anexo sem conteúdo baixável.",
            "evento": evento,
            "anexos": len(metas),
        }

    if evento == "chamado.status_alterado":
        if not ext:
            return {"message": "Status sem chamado.", "evento": evento}
        rows = _atualizar_chamado_webhook(
            conn, ext, status=data.get("status") or data.get("novo_status"), protocolo=data.get("protocolo")
        )
        return {
            "message": "Status atualizado." if rows else "Chamado local não encontrado.",
            "evento": evento,
            "chamado_external_id": ext,
        }

    if evento == "chamado.criado":
        if ext:
            resgatar_anexos_hubsupport(
                conn, ext, log_fn=lambda c, op, ok, msg, st=None: _log_api(c, op, ok, msg, st)
            )
        return {"message": "Criação já tratada na abertura local.", "evento": evento}

    return {"message": "Evento recebido.", "evento": evento}
