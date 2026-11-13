"""CRUD e tokens da API Externa."""
from __future__ import annotations

import hashlib
import secrets
from base64 import urlsafe_b64encode
from typing import Any

from api.api_externa.schema import garantir_tabelas

PREFIXO_ENC = "fernet:"


def _cifrar(texto: str) -> str:
    from sistema.fiscal.nfse.crypto_certificado import criptografar

    bruto = criptografar((texto or "").encode("utf-8"))
    return PREFIXO_ENC + urlsafe_b64encode(bruto).decode("ascii")


def _decifrar(valor: str) -> str:
    from base64 import urlsafe_b64decode

    from sistema.fiscal.nfse.crypto_certificado import descriptografar

    v = (valor or "").strip()
    if not v:
        return ""
    if not v.startswith(PREFIXO_ENC):
        return v
    blob = urlsafe_b64decode(v[len(PREFIXO_ENC) :].encode("ascii"))
    return descriptografar(blob).decode("utf-8")


def _hint(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return ""
    if len(t) <= 8:
        return "••••••••"
    return f"{t[:4]}…{t[-4:]}"


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def mascarar(valor: str) -> str:
    return _hint(valor)


def garantir_linha(conn, id_tenant: int) -> dict:
    garantir_tabelas(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM tbl_integracao_api_externa WHERE id_tenant = %s LIMIT 1",
        (int(id_tenant),),
    )
    if not cur.fetchone():
        cur.execute(
            """
            INSERT INTO tbl_integracao_api_externa (id_tenant)
            VALUES (%s)
            ON CONFLICT (id_tenant) DO NOTHING
            """,
            (int(id_tenant),),
        )
    return carregar(conn, id_tenant)


def carregar(conn, id_tenant: int) -> dict:
    garantir_tabelas(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, id_tenant, liberado, liberado_em, liberado_por, nome_parceiro, contato_tecnico,
               ambiente, base_url, auth_tipo, token_parceiro_enc, token_parceiro_hint,
               webhook_url, webhook_secret_enc, dn_token_hash, dn_token_hint, dn_token_gerado_em,
               ativo, cap_produtos_cadastrar, cap_produtos_atualizar, cap_estoque_atualizar,
               cap_pedidos_enviar, cap_pedidos_status, status, ultima_sync_em, ultima_sync_ok,
               ultima_mensagem, opcoes, dt_criacao, dt_atualizacao
          FROM tbl_integracao_api_externa
         WHERE id_tenant = %s
         LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        return {
            "id_tenant": int(id_tenant),
            "liberado": False,
            "ativo": False,
            "status": "desligado",
            "conectado": False,
        }
    cols = [
        "id", "id_tenant", "liberado", "liberado_em", "liberado_por", "nome_parceiro",
        "contato_tecnico", "ambiente", "base_url", "auth_tipo", "token_parceiro_enc",
        "token_parceiro_hint", "webhook_url", "webhook_secret_enc", "dn_token_hash",
        "dn_token_hint", "dn_token_gerado_em", "ativo", "cap_produtos_cadastrar",
        "cap_produtos_atualizar", "cap_estoque_atualizar", "cap_pedidos_enviar",
        "cap_pedidos_status", "status", "ultima_sync_em", "ultima_sync_ok",
        "ultima_mensagem", "opcoes", "dt_criacao", "dt_atualizacao",
    ]
    d = dict(zip(cols, row))
    d["token_parceiro_configurado"] = bool(d.pop("token_parceiro_enc", None))
    d["webhook_secret_configurado"] = bool(d.pop("webhook_secret_enc", None))
    d["dn_token_configurado"] = bool(d.get("dn_token_hash"))
    d["conectado"] = bool(d.get("liberado") and d.get("ativo") and d.get("base_url"))
    return d


def liberado_para_tenant(conn, id_tenant: int) -> bool:
    garantir_tabelas(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT liberado FROM tbl_integracao_api_externa WHERE id_tenant = %s LIMIT 1",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def listar_liberacoes(conn, termo: str = "") -> list[dict]:
    garantir_tabelas(conn)
    cur = conn.cursor()
    params: list[Any] = []
    where = "WHERE a.liberado = TRUE"
    if (termo or "").strip():
        where = """
        WHERE a.liberado = TRUE
          AND (
            CAST(t.id AS TEXT) ILIKE %s
            OR COALESCE(t.nome, '') ILIKE %s
            OR COALESCE(t.razao_social, '') ILIKE %s
            OR COALESCE(a.nome_parceiro, '') ILIKE %s
          )
        """
        like = f"%{termo.strip()}%"
        params.extend([like, like, like, like])
    cur.execute(
        f"""
        SELECT a.id_tenant, a.nome_parceiro, a.contato_tecnico, a.ativo, a.status, a.ambiente,
               a.base_url, a.liberado_em, a.ultima_sync_em, a.ultima_sync_ok, a.ultima_mensagem,
               COALESCE(NULLIF(TRIM(t.razao_social), ''), NULLIF(TRIM(t.nome), ''), 'Tenant') AS tenant_nome,
               t.documento
          FROM tbl_integracao_api_externa a
          JOIN tbl_tenant t ON t.id = a.id_tenant
          {where}
         ORDER BY a.dt_atualizacao DESC NULLS LAST, a.id_tenant
         LIMIT 200
        """,
        tuple(params),
    )
    cols = [
        "id_tenant", "nome_parceiro", "contato_tecnico", "ativo", "status", "ambiente",
        "base_url", "liberado_em", "ultima_sync_em", "ultima_sync_ok", "ultima_mensagem",
        "tenant_nome", "documento",
    ]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def liberar_tenant(
    conn,
    id_tenant: int,
    *,
    id_usuario: int | None,
    nome_parceiro: str = "",
    contato_tecnico: str = "",
    ambiente: str = "homologacao",
) -> dict:
    garantir_linha(conn, id_tenant)
    amb = "producao" if str(ambiente).lower() == "producao" else "homologacao"
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_integracao_api_externa
           SET liberado = TRUE,
               liberado_em = COALESCE(liberado_em, NOW()),
               liberado_por = COALESCE(%s, liberado_por),
               nome_parceiro = %s,
               contato_tecnico = %s,
               ambiente = %s,
               dt_atualizacao = NOW()
         WHERE id_tenant = %s
        """,
        (
            id_usuario,
            (nome_parceiro or "").strip() or None,
            (contato_tecnico or "").strip() or None,
            amb,
            int(id_tenant),
        ),
    )
    return carregar(conn, id_tenant)


def revogar_tenant(conn, id_tenant: int) -> dict:
    garantir_linha(conn, id_tenant)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_integracao_api_externa
           SET liberado = FALSE,
               ativo = FALSE,
               status = 'desligado',
               dt_atualizacao = NOW()
         WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    return carregar(conn, id_tenant)


def gerar_dn_token(conn, id_tenant: int) -> tuple[dict, str]:
    """Gera token DropNexo para o parceiro. Retorna (cfg, token_plain) — plain só nesta resposta."""
    garantir_linha(conn, id_tenant)
    token = secrets.token_urlsafe(32)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_integracao_api_externa
           SET dn_token_hash = %s,
               dn_token_hint = %s,
               dn_token_gerado_em = NOW(),
               dt_atualizacao = NOW()
         WHERE id_tenant = %s
        """,
        (_hash_token(token), _hint(token), int(id_tenant)),
    )
    return carregar(conn, id_tenant), token


def revogar_dn_token(conn, id_tenant: int) -> dict:
    """Remove o token DropNexo do tenant (hash/hint)."""
    garantir_linha(conn, id_tenant)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_integracao_api_externa
           SET dn_token_hash = NULL,
               dn_token_hint = NULL,
               dn_token_gerado_em = NULL,
               dt_atualizacao = NOW()
         WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    return carregar(conn, id_tenant)


def token_parceiro_plain(conn, id_tenant: int) -> str:
    garantir_tabelas(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT token_parceiro_enc FROM tbl_integracao_api_externa WHERE id_tenant = %s",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return ""
    try:
        return _decifrar(row[0])
    except Exception:
        return ""


def webhook_secret_plain(conn, id_tenant: int) -> str:
    garantir_tabelas(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT webhook_secret_enc FROM tbl_integracao_api_externa WHERE id_tenant = %s",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return ""
    try:
        return _decifrar(row[0])
    except Exception:
        return ""


def salvar_config_tenant(conn, id_tenant: int, payload: dict) -> dict:
    garantir_linha(conn, id_tenant)
    cfg = carregar(conn, id_tenant)
    if not cfg.get("liberado"):
        raise PermissionError("API Externa não liberada para este tenant.")

    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    auth_tipo = str(payload.get("auth_tipo") or "bearer").strip().lower()
    if auth_tipo not in ("bearer", "api_key"):
        auth_tipo = "bearer"
    ambiente = "producao" if str(payload.get("ambiente") or "").lower() == "producao" else "homologacao"
    webhook_url = str(payload.get("webhook_url") or "").strip()
    contato = str(payload.get("contato_tecnico") or "").strip()
    nome = str(payload.get("nome_parceiro") or "").strip()
    ativo = bool(payload.get("ativo"))

    sets = [
        "base_url = %s",
        "auth_tipo = %s",
        "ambiente = %s",
        "webhook_url = %s",
        "contato_tecnico = COALESCE(NULLIF(%s, ''), contato_tecnico)",
        "nome_parceiro = COALESCE(NULLIF(%s, ''), nome_parceiro)",
        "ativo = %s",
        "cap_produtos_cadastrar = %s",
        "cap_produtos_atualizar = %s",
        "cap_estoque_atualizar = %s",
        "cap_pedidos_enviar = %s",
        "cap_pedidos_status = %s",
        "dt_atualizacao = NOW()",
    ]
    params: list[Any] = [
        base_url,
        auth_tipo,
        ambiente,
        webhook_url,
        contato,
        nome,
        ativo,
        bool(payload.get("cap_produtos_cadastrar", True)),
        bool(payload.get("cap_produtos_atualizar", True)),
        bool(payload.get("cap_estoque_atualizar", True)),
        bool(payload.get("cap_pedidos_enviar", False)),
        bool(payload.get("cap_pedidos_status", False)),
    ]

    token_novo = str(payload.get("token_parceiro") or "").strip()
    if token_novo and token_novo != "****************":
        sets.append("token_parceiro_enc = %s")
        sets.append("token_parceiro_hint = %s")
        params.extend([_cifrar(token_novo), _hint(token_novo)])

    secret_novo = str(payload.get("webhook_secret") or "").strip()
    if secret_novo and secret_novo != "****************":
        sets.append("webhook_secret_enc = %s")
        params.append(_cifrar(secret_novo))

    status = "ativo" if ativo and base_url else "desligado"
    if ativo and not base_url:
        status = "atencao"
    sets.append("status = %s")
    params.append(status)
    params.append(int(id_tenant))

    cur = conn.cursor()
    cur.execute(
        f"UPDATE tbl_integracao_api_externa SET {', '.join(sets)} WHERE id_tenant = %s",
        tuple(params),
    )
    return carregar(conn, id_tenant)


def registrar_log(
    conn,
    id_tenant: int,
    *,
    evento: str,
    sucesso: bool,
    mensagem: str = "",
    direcao: str = "pull",
    referencia: str | None = None,
    http_status: int | None = None,
    detalhe: dict | None = None,
) -> None:
    import json

    garantir_tabelas(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tbl_integracao_api_externa_log (
            id_tenant, evento, direcao, referencia, http_status, sucesso, mensagem, detalhe
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            int(id_tenant),
            evento,
            direcao,
            referencia,
            http_status,
            bool(sucesso),
            (mensagem or "")[:2000],
            json.dumps(detalhe or {}, ensure_ascii=False),
        ),
    )


def listar_logs(conn, id_tenant: int, limite: int = 50) -> list[dict]:
    garantir_tabelas(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, evento, direcao, referencia, http_status, sucesso, mensagem, detalhe, dt_criacao
          FROM tbl_integracao_api_externa_log
         WHERE id_tenant = %s
         ORDER BY id DESC
         LIMIT %s
        """,
        (int(id_tenant), max(1, min(200, int(limite)))),
    )
    cols = [
        "id", "evento", "direcao", "referencia", "http_status",
        "sucesso", "mensagem", "detalhe", "dt_criacao",
    ]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def marcar_sync(conn, id_tenant: int, *, ok: bool, mensagem: str) -> None:
    status = "ativo" if ok else "erro"
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_integracao_api_externa
           SET ultima_sync_em = NOW(),
               ultima_sync_ok = %s,
               ultima_mensagem = %s,
               status = CASE WHEN ativo THEN %s ELSE status END,
               dt_atualizacao = NOW()
         WHERE id_tenant = %s
        """,
        (bool(ok), (mensagem or "")[:2000], status, int(id_tenant)),
    )


def buscar_tenants(conn, termo: str = "", limitar: int = 20) -> list[dict]:
    """Lista para combobox personalizada (padrão {sucesso,dados})."""
    garantir_tabelas(conn)
    cur = conn.cursor()
    termo = (termo or "").strip()
    try:
        limite = min(40, max(1, int(limitar or 20)))
    except (TypeError, ValueError):
        limite = 20

    params: list[Any] = []
    where_extra = ""
    if termo:
        if termo.isdigit():
            where_extra = """
              AND (
                    t.id = %s
                 OR COALESCE(t.nome, '') ILIKE %s
                 OR COALESCE(t.razao_social, '') ILIKE %s
                 OR COALESCE(t.slug, '') ILIKE %s
                 OR COALESCE(t.documento, '') ILIKE %s
              )
            """
            like = f"%{termo}%"
            params.extend([int(termo), like, like, like, like])
        else:
            where_extra = """
              AND (
                    COALESCE(t.nome, '') ILIKE %s
                 OR COALESCE(t.razao_social, '') ILIKE %s
                 OR COALESCE(t.slug, '') ILIKE %s
                 OR COALESCE(t.documento, '') ILIKE %s
              )
            """
            like = f"%{termo}%"
            params.extend([like, like, like, like])

    cur.execute(
        f"""
        SELECT t.id,
               COALESCE(NULLIF(TRIM(t.razao_social), ''), NULLIF(TRIM(t.nome), ''), 'Tenant') AS nome,
               COALESCE(t.slug, '') AS slug,
               COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'fornecedor') AS tipo_negocio,
               COALESCE(t.documento, '') AS documento,
               COALESCE(a.liberado, FALSE) AS liberado
          FROM tbl_tenant t
          LEFT JOIN tbl_integracao_api_externa a ON a.id_tenant = t.id
         WHERE COALESCE(t.ativo, TRUE) = TRUE
           AND COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'fornecedor')
               IN ('fornecedor', 'hibrido', 'armazem')
           {where_extra}
         ORDER BY t.nome NULLS LAST, t.id
         LIMIT %s
        """,
        (*params, limite),
    )
    out = []
    for r in cur.fetchall():
        tid = int(r[0])
        nome = r[1] or f"Tenant #{tid}"
        slug = r[2] or ""
        tipo = str(r[3] or "fornecedor").lower()
        doc = r[4] or ""
        liberado = bool(r[5])
        titulo = f"#{tid} — {nome}"
        if liberado:
            titulo += " (já liberado)"
        out.append(
            {
                "id": tid,
                "nome": nome,
                "titulo": titulo,
                "slug": slug,
                "tipo_negocio": tipo,
                "documento": doc,
                "liberado": liberado,
            }
        )
    return out
