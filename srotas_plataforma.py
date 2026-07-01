# DropNexo — plataforma: navegação (Fornecedor/Vendedor) e usuários por tenant
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta

from flask import render_template, session, url_for

from api.brevo.srotas_brevo import enviar_email
from global_utils import (
    PERFIL_LABEL,
    Var_ConectarBanco,
    agora_utc,
    gerar_hmac_token,
    obter_base_url,
    valida_email,
)

# ── Navegação ─────────────────────────────────────────────────────────

MODULO_FORNECEDOR = "fornecedor"
MODULO_VENDEDOR = "vendedor"
MODULOS_VALIDOS = (MODULO_FORNECEDOR, MODULO_VENDEDOR)


def modulos_disponiveis(tipo_negocio: str | None) -> list[str]:
    t = (tipo_negocio or "vendedor").strip().lower()
    if t == "hibrido":
        return [MODULO_FORNECEDOR, MODULO_VENDEDOR]
    if t == "fornecedor":
        return [MODULO_FORNECEDOR]
    return [MODULO_VENDEDOR]


def modulos_disponiveis_sessao() -> list[str]:
    """DEV sempre enxerga Fornecedor + Vendedor (mesmo impersonando tenant fornecedor)."""
    if session.get("eh_desenvolvedor"):
        return [MODULO_FORNECEDOR, MODULO_VENDEDOR]
    return modulos_disponiveis(session.get("tenant_tipo_negocio", "vendedor"))


def modulo_padrao(tipo_negocio: str | None) -> str:
    mods = modulos_disponiveis(tipo_negocio)
    t = (tipo_negocio or "vendedor").strip().lower()
    if t == "fornecedor":
        return MODULO_FORNECEDOR
    if t == "hibrido":
        return MODULO_VENDEDOR
    return MODULO_VENDEDOR if MODULO_VENDEDOR in mods else mods[0]


def garantir_modulo_sessao() -> str:
    tipo = session.get("tenant_tipo_negocio", "vendedor")
    mods = modulos_disponiveis_sessao()
    ativo = (session.get("modulo_ativo") or "").strip().lower()
    if ativo not in mods:
        ativo = modulo_padrao(tipo)
        session["modulo_ativo"] = ativo
    return ativo


def rotulo_modulo(codigo: str) -> str:
    return {"fornecedor": "Fornecedor", "vendedor": "Vendedor"}.get(codigo, codigo)


def icone_modulo(codigo: str) -> str:
    if codigo == MODULO_FORNECEDOR:
        return "truck"
    return "shopping-bag"


def resolver_url_menu(data_page: str, nav_codigo: str | None = None) -> str:
    page = (data_page or "/").strip()
    if not page.startswith("/"):
        page = "/" + page
    nav = (nav_codigo or "").strip().lower()
    rotas_por_nav = {
        "inicio": "dashboard.index",
        "fornecedores": "vd_fornecedores.pagina",
        "catalogos": "fn_catalogo.pagina",
        "vd_catalogo": "vd_catalogo.pagina",
        "produtos": "vd_meus_produtos.pagina",
        "vd_precificacao": "vd_precificacao.pagina",
        "vd_pedidos": "vd_pedidos.pedidos",
        "vd_expedicao": "vd_expedicao.expedicao",
        "vd_usuarios": "vd_usuarios.usuarios",
        "integracoes": "integracoes.pagina",
        "fn_parametros": "fn_parametros.parametros_pagina",
    }
    rotas = {
        "/index": "dashboard.index",
        "/fornecedores": "vd_fornecedores.pagina",
        "/catalogos": "fn_catalogo.pagina",
        "/meus-produtos": "vd_meus_produtos.pagina",
        "/integracoes": "integracoes.pagina",
        "/configuracoes": "config.configuracoes",
        "/fornecedor/depositos": "fn_depositos.depositos",
        "/meu-perfil": "perfil.meu_perfil",
        "/fornecedor/categorias": "fn_categorias.categorias",
        "/fornecedor/variacoes": "fn_variacoes.variacoes",
        "/fornecedor/vendedores": "fn_vendedores.vendedores",
        "/fornecedor/usuarios": "fn_usuarios.usuarios",
        "/fornecedor/integracoes": "integracoes.pagina",
        "/fornecedor/parametros": "fn_parametros.parametros_pagina",
        "/vendedor/catalogo": "vd_catalogo.pagina",
        "/vendedor/precificacao": "vd_precificacao.pagina",
        "/vendedor/pedidos": "vd_pedidos.pedidos",
        "/vendedor/expedicao": "vd_expedicao.expedicao",
        "/vendedor/usuarios": "vd_usuarios.usuarios",
        "/configuracoes/fornecedores-plataforma": "config.fornecedores_plataforma",
    }
    endpoint = rotas_por_nav.get(nav) or rotas.get(page)
    if endpoint:
        try:
            return url_for(endpoint)
        except Exception:
            pass
    return page


def ctx_navegacao() -> dict:
    if not session.get("id_usuario"):
        return {
            "menu_sidebar": [],
            "modulos_nav": [],
            "modulo_ativo": "",
            "modulo_ativo_rotulo": "",
            "exibir_seletor_modulo": False,
            "pode_config_plataforma": False,
        }
    mods = modulos_disponiveis_sessao()
    ativo = garantir_modulo_sessao()
    return {
        "menu_sidebar": [],
        "modulos_nav": [
            {"codigo": m, "rotulo": rotulo_modulo(m), "icone": icone_modulo(m)}
            for m in mods
        ],
        "modulo_ativo": ativo,
        "modulo_ativo_rotulo": rotulo_modulo(ativo),
        "exibir_seletor_modulo": len(mods) > 1,
        "pode_config_plataforma": bool(session.get("eh_desenvolvedor")),
    }


# ── Usuários por tenant ───────────────────────────────────────────────

PERFIS_EQUIPE_FORNECEDOR = ("admin", "operador", "visualizador", "financeiro")
PERFIS_EQUIPE_VENDEDOR = ("admin", "operador", "visualizador", "financeiro")


def normalizar_bool(valor, padrao=True):
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "on", "yes", "sim")


def status_convite(cur, uid: int) -> str:
    cur.execute(
        """
        SELECT senha_hash, token_ativacao, token_expira_em, ativo
        FROM tbl_usuario WHERE id = %s
        """,
        (uid,),
    )
    row = cur.fetchone()
    if not row:
        return "SEM_CONVITE"
    senha_hash, token_ativacao, token_expira_em, ativo = row
    if senha_hash and ativo:
        return "ACEITO"
    if not token_ativacao:
        return "SEM_CONVITE"
    if token_expira_em and token_expira_em < agora_utc():
        return "EXPIRADO"
    return "PENDENTE"


def criar_token_ativacao(cur, uid: int) -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = gerar_hmac_token(raw)
    horas = int(os.getenv("TOKEN_ATIVACAO_HORAS", "48"))
    expira = agora_utc() + timedelta(hours=horas)
    cur.execute(
        """
        UPDATE tbl_usuario
        SET token_ativacao = %s, token_expira_em = %s, ativo = FALSE, senha_hash = NULL
        WHERE id = %s
        """,
        (token_hash, expira, uid),
    )
    return raw


def enviar_email_convite(*, email: str, nome: str, nome_tenant: str, token_bruto: str) -> tuple[bool, str]:
    horas = int(os.getenv("TOKEN_ATIVACAO_HORAS", "48"))
    link = f"{obter_base_url()}/definir-senha?token={token_bruto}"
    base = obter_base_url()
    html = render_template(
        "cadastro/emails/ativacao_conta.html",
        titulo_email="Convite de acesso • DropNexo",
        nome_usuario=nome,
        nome_conta=nome_tenant,
        link_ativacao=link,
        horas_validade=horas,
        ano=datetime.now().year,
        url_politica_privacidade=os.getenv("URL_POLITICA_PRIVACIDADE") or f"{base}/privacidade",
        url_politica_interna=os.getenv("URL_POLITICA_INTERNA") or f"{base}/politica-interna",
        url_dpo=os.getenv("URL_DPO") or f"{base}/dpo",
    )
    return enviar_email([email], "Convite de acesso • DropNexo", html, tag="dropnexo_convite_equipe")


def listar_usuarios_tenant(
    *,
    id_tenant: int,
    pagina: int = 1,
    por_pagina: int = 20,
    busca: str = "",
    filtro_status: str = "",
    filtro_convite: str = "",
    id_usuario_sessao: int | None = None,
) -> dict:
    pagina = max(1, pagina)
    por_pagina = max(1, min(por_pagina, 100))
    offset = (pagina - 1) * por_pagina
    busca = (busca or "").strip()
    filtro_status = (filtro_status or "").strip().lower()
    filtro_convite = (filtro_convite or "").strip().upper()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["ut.id_tenant = %s", "u.eh_desenvolvedor IS NOT TRUE"]
        params: list = [id_tenant]
        if busca:
            where.append("(u.nome ILIKE %s OR u.email ILIKE %s)")
            like = f"%{busca}%"
            params.extend([like, like])
        if filtro_status == "ativo":
            where.append("u.ativo = TRUE AND ut.ativo = TRUE")
        elif filtro_status == "inativo":
            where.append("(u.ativo = FALSE OR ut.ativo = FALSE)")

        where_sql = " AND ".join(where)
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            WHERE {where_sql}
            """,
            params,
        )
        total = int(cur.fetchone()[0] or 0)

        cur.execute(
            f"""
            SELECT u.id, u.nome, u.email, u.ativo, ut.ativo, pf.codigo, pf.nome, ut.ultimo_acesso_em
            FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE {where_sql}
            ORDER BY u.nome
            LIMIT %s OFFSET %s
            """,
            params + [por_pagina, offset],
        )
        dados = []
        for r in cur.fetchall():
            convite = status_convite(cur, r[0])
            if filtro_convite and convite != filtro_convite:
                continue
            dt_login = r[7].isoformat() if r[7] else None
            dados.append(
                {
                    "id": r[0],
                    "nome": r[1],
                    "email": r[2],
                    "status": bool(r[3]) and bool(r[4]),
                    "perfil_codigo": r[5],
                    "perfil_nome": PERFIL_LABEL.get(r[5], r[6]),
                    "convite_status": convite,
                    "dt_ultimo_login": dt_login,
                    "cannot_delete": r[0] == id_usuario_sessao,
                }
            )
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        return {
            "success": True,
            "dados": dados,
            "total": total,
            "pagina_atual": pagina,
            "total_paginas": total_paginas,
        }
    finally:
        conn.close()


def listar_perfis_combo(*, excluir_codigos: tuple[str, ...] = ("dono",)) -> dict:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if excluir_codigos:
            placeholders = ",".join(["%s"] * len(excluir_codigos))
            cur.execute(
                f"""
                SELECT id, codigo, nome FROM tbl_perfil
                WHERE ativo = TRUE AND codigo NOT IN ({placeholders})
                ORDER BY nivel DESC, nome
                """,
                list(excluir_codigos),
            )
        else:
            cur.execute(
                """
                SELECT id, codigo, nome FROM tbl_perfil
                WHERE ativo = TRUE
                ORDER BY nivel DESC, nome
                """
            )
        perfis = [{"id": r[0], "codigo": r[1], "nome": r[2]} for r in cur.fetchall()]
        return {"success": True, "perfis": perfis}
    finally:
        conn.close()


def carregar_usuario_apoio(*, id_tenant: int, uid: int) -> tuple[dict, int]:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id, u.nome, u.email, u.whatsapp, u.ativo, ut.id_perfil, ut.ativo
            FROM tbl_usuario u
            JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.id_tenant = %s
            WHERE u.id = %s AND u.eh_desenvolvedor IS NOT TRUE
            """,
            (id_tenant, uid),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Usuário não encontrado neste tenant."}, 404
        return (
            {
                "success": True,
                "dados": {
                    "id": row[0],
                    "nome": row[1],
                    "email": row[2],
                    "whatsapp": row[3] or "",
                    "status": bool(row[4]) and bool(row[6]),
                    "id_perfil": row[5],
                    "convite_status": status_convite(cur, row[0]),
                },
            },
            200,
        )
    finally:
        conn.close()


def salvar_usuario_tenant(
    *,
    id_tenant: int,
    uid: int | None,
    email: str,
    nome: str,
    whatsapp: str,
    id_perfil: int,
    status: bool,
    enviar_convite: bool,
) -> tuple[dict, int]:
    email = (email or "").strip().lower()
    nome = (nome or "").strip()
    whatsapp = (whatsapp or "").strip()

    if not valida_email(email):
        return {"success": False, "message": "E-mail inválido."}, 400
    if not nome:
        return {"success": False, "message": "Informe o nome."}, 400
    if not id_perfil:
        return {"success": False, "message": "Selecione um perfil."}, 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT nome FROM tbl_tenant WHERE id = %s", (id_tenant,))
        row_t = cur.fetchone()
        nome_tenant = row_t[0] if row_t else "DropNexo"

        if uid:
            cur.execute(
                """
                SELECT u.eh_desenvolvedor FROM tbl_usuario u
                JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.id_tenant = %s
                WHERE u.id = %s
                """,
                (id_tenant, int(uid)),
            )
            alvo = cur.fetchone()
            if not alvo:
                return {"success": False, "message": "Usuário não encontrado."}, 404
            if alvo[0]:
                return {"success": False, "message": "Usuário desenvolvedor não pode ser alterado aqui."}, 403

            cur.execute(
                "UPDATE tbl_usuario SET nome=%s, email=%s, whatsapp=%s, ativo=%s WHERE id=%s",
                (nome, email, whatsapp, status, int(uid)),
            )
            cur.execute(
                """
                UPDATE tbl_usuario_tenant SET id_perfil=%s, ativo=%s
                WHERE id_usuario=%s AND id_tenant=%s
                """,
                (int(id_perfil), status, int(uid), id_tenant),
            )
            conn.commit()
            return {"success": True, "message": "Usuário atualizado.", "id": int(uid)}, 200

        cur.execute("SELECT id FROM tbl_usuario WHERE lower(email) = %s LIMIT 1", (email,))
        existente = cur.fetchone()
        token_bruto = None

        if existente:
            uid_novo = existente[0]
            cur.execute(
                "SELECT 1 FROM tbl_usuario_tenant WHERE id_usuario=%s AND id_tenant=%s",
                (uid_novo, id_tenant),
            )
            if cur.fetchone():
                return {"success": False, "message": "Usuário já vinculado a este tenant."}, 409
            cur.execute(
                "UPDATE tbl_usuario SET nome=%s, whatsapp=%s WHERE id=%s",
                (nome, whatsapp, uid_novo),
            )
            cur.execute(
                """
                INSERT INTO tbl_usuario_tenant (id_usuario, id_tenant, id_perfil, ativo)
                VALUES (%s,%s,%s,%s)
                """,
                (uid_novo, id_tenant, int(id_perfil), status),
            )
            if enviar_convite:
                cur.execute("SELECT senha_hash FROM tbl_usuario WHERE id=%s", (uid_novo,))
                sh = cur.fetchone()
                if sh and not sh[0]:
                    token_bruto = criar_token_ativacao(cur, uid_novo)
        else:
            cur.execute(
                """
                INSERT INTO tbl_usuario (nome, email, whatsapp, ativo)
                VALUES (%s,%s,%s,%s) RETURNING id
                """,
                (nome, email, whatsapp, False),
            )
            uid_novo = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO tbl_usuario_tenant (id_usuario, id_tenant, id_perfil, ativo)
                VALUES (%s,%s,%s,%s)
                """,
                (uid_novo, id_tenant, int(id_perfil), status),
            )
            if enviar_convite:
                token_bruto = criar_token_ativacao(cur, uid_novo)

        conn.commit()
        msg = "Usuário criado."
        if token_bruto:
            ok, msg_email = enviar_email_convite(
                email=email,
                nome=nome,
                nome_tenant=nome_tenant,
                token_bruto=token_bruto,
            )
            msg = "Usuário criado e convite enviado." if ok else f"Usuário criado, mas falhou o e-mail: {msg_email}"
        return {"success": True, "message": msg, "id": uid_novo}, 200
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": str(e)}, 500
    finally:
        conn.close()


def inativar_usuario_tenant(*, id_tenant: int, uid: int, id_usuario_sessao: int) -> tuple[dict, int]:
    if not uid:
        return {"success": False, "message": "ID inválido."}, 400
    if uid == id_usuario_sessao:
        return {"success": False, "message": "Você não pode inativar a si mesmo."}, 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_usuario_tenant SET ativo = FALSE
            WHERE id_usuario = %s AND id_tenant = %s AND id_usuario IN (
                SELECT id FROM tbl_usuario WHERE eh_desenvolvedor IS NOT TRUE
            )
            """,
            (uid, id_tenant),
        )
        if cur.rowcount == 0:
            return {"success": False, "message": "Usuário não encontrado."}, 404

        cur.execute(
            """
            SELECT COUNT(*) FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            WHERE ut.id_usuario = %s AND ut.ativo = TRUE AND u.eh_desenvolvedor IS NOT TRUE
            """,
            (uid,),
        )
        ativos = int(cur.fetchone()[0] or 0)
        if ativos == 0:
            cur.execute(
                "UPDATE tbl_usuario SET ativo = FALSE WHERE id = %s AND eh_desenvolvedor IS NOT TRUE",
                (uid,),
            )
        conn.commit()
        return {"success": True, "message": "Usuário inativado neste tenant."}, 200
    finally:
        conn.close()


def reenviar_convite_usuario(*, id_tenant: int, uid: int) -> tuple[dict, int]:
    if not uid:
        return {"success": False, "message": "ID inválido."}, 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.email, u.nome, t.nome
            FROM tbl_usuario u
            JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.id_tenant = %s
            JOIN tbl_tenant t ON t.id = ut.id_tenant
            WHERE u.id = %s AND u.eh_desenvolvedor IS NOT TRUE
            """,
            (id_tenant, uid),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Usuário não encontrado."}, 404
        token_bruto = criar_token_ativacao(cur, uid)
        conn.commit()
        ok, msg = enviar_email_convite(
            email=row[0],
            nome=row[1],
            nome_tenant=row[2],
            token_bruto=token_bruto,
        )
        if not ok:
            return {"success": False, "message": msg}, 500
        return {"success": True, "message": "Convite reenviado por e-mail."}, 200
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": str(e)}, 500
    finally:
        conn.close()
