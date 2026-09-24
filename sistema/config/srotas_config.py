from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from global_utils import (
    Var_ConectarBanco,
    exigir_permissao,
    login_obrigatorio,
    usuario_tem_permissao,
)

_log = logging.getLogger(__name__)
from sistema.integracoes.srotas_integracoes import url_icone_integracao
from sistema.plataforma.sessao import (
    carregar_usuario_apoio,
    inativar_usuario_tenant,
    listar_perfis_combo,
    listar_usuarios_tenant,
    normalizar_bool,
    reenviar_convite_usuario,
    salvar_usuario_tenant,
    status_convite,
)

_MOD_DIR = Path(__file__).resolve().parent

config_bp = Blueprint(
    "config",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/config",
)




def _exigir_config_escrita():
    if session.get("eh_desenvolvedor") or usuario_tem_permissao("configuracoes.editar"):
        return None
    return jsonify(success=False, message="Sem permissão para alterar configurações."), 403


def _exigir_usuarios_escrita():
    if session.get("eh_desenvolvedor") or usuario_tem_permissao("usuarios.editar"):
        return None
    return jsonify(success=False, message="Sem permissão para gerenciar usuários."), 403


# ─── Painel ───────────────────────────────────────────────────────────

@config_bp.get("/configuracoes")
@login_obrigatorio()
def configuracoes():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_configuracoes.html", nav_ativo="config")


TESTES_INTEGRACAO_PREFIX = "/configuracoes/testes-integracao"


@config_bp.get(TESTES_INTEGRACAO_PREFIX)
@login_obrigatorio()
def testes_integracao_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template(
        "frm_config_testes_integracao.html",
        nav_ativo="config",
        icone_bling=url_icone_integracao("bling"),
    )


@config_bp.get(f"{TESTES_INTEGRACAO_PREFIX}/bling")
@login_obrigatorio()
def teste_integracao_bling_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template(
        "frm_config_teste_bling.html",
        nav_ativo="config",
        icone_bling=url_icone_integracao("bling"),
    )


@config_bp.get("/configuracoes/fornecedores-plataforma")
@login_obrigatorio()
def fornecedores_plataforma():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template(
        "frm_fornecedores_gestao.html",
        nav_ativo="config",
        pode_gestao=True,
        url_base_api="/configuracoes/fornecedores-plataforma",
    )


# ─── Usuários (listagem tenant) ────────────────────────────────────────

@config_bp.get("/configuracoes/usuarios")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.ver")
def config_usuarios():
    return render_template("frm_config_usuarios.html", nav_ativo="config")


@config_bp.get("/configuracoes/usuarios/dados")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.ver")
def config_usuarios_dados():
    return jsonify(
        listar_usuarios_tenant(
            id_tenant=int(session["id_tenant"]),
            pagina=int(request.args.get("pagina", 1)),
            por_pagina=int(request.args.get("porPagina", 20)),
            busca=request.args.get("busca") or "",
            filtro_status=request.args.get("status") or "",
            filtro_convite=request.args.get("convite") or "",
            id_usuario_sessao=session.get("id_usuario"),
        )
    )


@config_bp.get("/configuracoes/usuarios/combos")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.ver")
def config_usuarios_combos():
    return jsonify(listar_perfis_combo(excluir_codigos=("dono",)))


@config_bp.get("/configuracoes/usuarios/incluir")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.editar")
def config_usuarios_incluir():
    return render_template("frm_config_usuarios_apoio.html")


@config_bp.get("/configuracoes/usuarios/editar")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.editar")
def config_usuarios_editar():
    return render_template("frm_config_usuarios_apoio.html")


@config_bp.post("/configuracoes/usuarios/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.ver")
def config_usuarios_apoio():
    uid = int((request.get_json(silent=True) or {}).get("id") or 0)
    if not uid:
        return jsonify(success=False, message="ID inválido."), 400
    payload, status = carregar_usuario_apoio(id_tenant=int(session["id_tenant"]), uid=uid)
    return jsonify(payload), status


@config_bp.post("/configuracoes/usuarios/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.editar")
def config_usuarios_salvar():
    if (resp := _exigir_usuarios_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    payload, status = salvar_usuario_tenant(
        id_tenant=int(session["id_tenant"]),
        uid=body.get("id"),
        email=body.get("email") or "",
        nome=body.get("nome") or "",
        whatsapp=body.get("whatsapp") or "",
        id_perfil=int(body.get("id_perfil") or 0),
        status=normalizar_bool(body.get("status"), True),
        enviar_convite=normalizar_bool(body.get("enviar_convite"), True),
    )
    return jsonify(payload), status


@config_bp.post("/configuracoes/usuarios/inativar")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.editar")
def config_usuarios_inativar():
    if (resp := _exigir_usuarios_escrita()) is not None:
        return resp
    uid = int((request.get_json(silent=True) or {}).get("id") or 0)
    payload, status = inativar_usuario_tenant(
        id_tenant=int(session["id_tenant"]),
        uid=uid,
        id_usuario_sessao=int(session.get("id_usuario") or 0),
    )
    return jsonify(payload), status


@config_bp.post("/configuracoes/usuarios/reenviar-convite")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.editar")
def config_usuarios_reenviar_convite():
    if (resp := _exigir_usuarios_escrita()) is not None:
        return resp
    uid = int((request.get_json(silent=True) or {}).get("id") or 0)
    payload, status = reenviar_convite_usuario(id_tenant=int(session["id_tenant"]), uid=uid)
    return jsonify(payload), status


# ─── Novidades (painel lateral — API pública autenticada) ─────────────

@config_bp.get("/api/novidades")
@login_obrigatorio()
def api_novidades_listar():
    id_usuario = session.get("id_usuario")
    if not id_usuario:
        return jsonify(novidades=[], nao_lidas=0)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COALESCE(id_ultima_novidade_lida, 0) FROM tbl_usuario WHERE id = %s",
                (id_usuario,),
            )
            ultima_lida = int((cur.fetchone() or [0])[0] or 0)
        except Exception:
            ultima_lida = 0

        cur.execute(
            """
            SELECT id, titulo, resumo, publicado_em
            FROM tbl_novidade
            WHERE ativo = TRUE
            ORDER BY ordem, publicado_em DESC, id DESC
            LIMIT 30
            """
        )
        novidades = []
        for r in cur.fetchall():
            emissao = r[3].isoformat() if r[3] else None
            novidades.append(
                {
                    "id": r[0],
                    "emissao": emissao,
                    "modulo": r[1],
                    "descricao": (r[2] or r[1] or "").strip(),
                    "link": None,
                    "lida": r[0] <= ultima_lida,
                }
            )
        nao_lidas = sum(1 for n in novidades if not n["lida"])
        return jsonify(novidades=novidades, nao_lidas=nao_lidas)
    finally:
        conn.close()


@config_bp.post("/api/novidades/marcar-lidas")
@login_obrigatorio()
def api_novidades_marcar_lidas():
    id_usuario = session.get("id_usuario")
    if not id_usuario:
        return jsonify(erro="Não autenticado."), 403
    ultimo_id = int((request.get_json(silent=True) or {}).get("ultimo_id") or 0)
    if not ultimo_id:
        return jsonify(erro="ultimo_id não informado."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tbl_usuario SET id_ultima_novidade_lida = %s WHERE id = %s",
            (ultimo_id, id_usuario),
        )
        conn.commit()
        return jsonify(ok=True)
    except Exception as e:
        conn.rollback()
        return jsonify(erro=str(e)), 500
    finally:
        conn.close()


# ─── Perfis + menus do perfil ─────────────────────────────────────────

@config_bp.get("/configuracoes/perfis")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.ver")
def config_perfis():
    return render_template("frm_config_perfis.html", nav_ativo="config")


@config_bp.get("/configuracoes/perfis/dados")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.ver")
def config_perfis_dados():
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, codigo, nome, descricao, nivel FROM tbl_perfil WHERE ativo = TRUE ORDER BY nivel DESC"
        )
        perfis = [
            {"id": r[0], "codigo": r[1], "nome": r[2], "descricao": r[3] or "", "nivel": r[4]}
            for r in cur.fetchall()
        ]
        return jsonify(success=True, perfis=perfis)
    finally:
        conn.close()


@config_bp.get("/configuracoes/perfis/<int:id_perfil>/menus")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.ver")
def config_perfil_menus(id_perfil: int):
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.id, m.nome_menu, m.nav_codigo, COALESCE(pm.exibir, FALSE) AS exibir
            FROM tbl_menu m
            LEFT JOIN tbl_perfil_menu pm ON pm.id_menu = m.id AND pm.id_perfil = %s
            WHERE m.status = TRUE
            ORDER BY m.ordem NULLS LAST, m.nome_menu
            """,
            (id_perfil,),
        )
        itens = [
            {"id_menu": r[0], "nome": r[1], "nav_codigo": r[2], "exibir": r[3]}
            for r in cur.fetchall()
        ]
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@config_bp.post("/configuracoes/perfis/<int:id_perfil>/menus")
@login_obrigatorio()
@exigir_permissao(codigo="usuarios.editar")
def config_perfil_menus_salvar(id_perfil: int):
    if (resp := _exigir_config_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    itens = body.get("itens") or []

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_perfil_menu WHERE id_perfil = %s", (id_perfil,))
        for item in itens:
            if not item.get("exibir"):
                continue
            cur.execute(
                """
                INSERT INTO tbl_perfil_menu (id_perfil, id_menu, exibir)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (id_perfil, id_menu) DO UPDATE SET exibir = TRUE
                """,
                (id_perfil, int(item["id_menu"])),
            )
        conn.commit()
        return jsonify(success=True, message="Menus do perfil atualizados.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


# ─── Novidades ──────────────────────────────────────────────────────────

@config_bp.get("/configuracoes/novidades")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.ver")
def config_novidades():
    return render_template("frm_config_novidades.html", nav_ativo="config")


@config_bp.get("/configuracoes/novidades/dados")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.ver")
def config_novidades_dados():
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, titulo, resumo, conteudo, ordem, ativo, publicado_em
            FROM tbl_novidade
            ORDER BY ordem, id DESC
            """
        )
        dados = [
            {
                "id": r[0],
                "titulo": r[1],
                "resumo": r[2] or "",
                "conteudo": r[3] or "",
                "ordem": r[4],
                "ativo": r[5],
                "publicado_em": r[6].isoformat() if r[6] else None,
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@config_bp.post("/configuracoes/novidades/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.editar")
def config_novidades_salvar():
    if (resp := _exigir_config_escrita()) is not None:
        return resp
    b = request.get_json(silent=True) or {}
    titulo = (b.get("titulo") or "").strip()
    if not titulo:
        return jsonify(success=False, message="Informe o título."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        _id = b.get("id")
        if _id:
            cur.execute(
                """
                UPDATE tbl_novidade SET titulo=%s, resumo=%s, conteudo=%s, ordem=%s, ativo=%s
                WHERE id=%s
                """,
                (
                    titulo,
                    (b.get("resumo") or "").strip(),
                    (b.get("conteudo") or "").strip(),
                    int(b.get("ordem") or 0),
                    normalizar_bool(b.get("ativo"), True),
                    _id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_novidade (titulo, resumo, conteudo, ordem, ativo)
                VALUES (%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    titulo,
                    (b.get("resumo") or "").strip(),
                    (b.get("conteudo") or "").strip(),
                    int(b.get("ordem") or 0),
                    normalizar_bool(b.get("ativo"), True),
                ),
            )
        conn.commit()
        return jsonify(success=True, message="Novidade salva.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


# ─── Itens de menu ────────────────────────────────────────────────────

@config_bp.get("/configuracoes/itens-menu")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.ver")
def config_menu_pagina():
    return render_template(
        "frm_config_menu.html",
        nav_ativo="config",
        url_voltar=url_for("config.configuracoes"),
    )


@config_bp.get("/configuracoes/itens-menu/dados")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.ver")
def config_menu_dados():
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = max(1, min(100, int(request.args.get("porPagina", 20))))
    nome = (request.args.get("nome") or "").strip()
    menu_pai = (request.args.get("menu_pai") or "").strip()
    id_modulo = (request.args.get("id_modulo") or "").strip()

    where = ["1=1"]
    params: list = []
    if nome:
        where.append("LOWER(m.nome_menu) LIKE LOWER(%s)")
        params.append(f"%{nome}%")
    if menu_pai:
        where.append(
            "m.parent_id IN (SELECT id FROM tbl_menu WHERE pai = TRUE AND nome_menu = %s)"
        )
        params.append(menu_pai)
    if id_modulo:
        # Inclui Dashboard (comum) em qualquer filtro de módulo de negócio
        where.append(
            "(m.id_modulo = %s OR (COALESCE(m.contexto_modulo, '') = 'comum' AND COALESCE(m.nav_codigo, '') = 'inicio'))"
        )
        params.append(int(id_modulo))

    where_sql = " AND ".join(where)
    offset = (pagina - 1) * por_pagina

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM tbl_menu m WHERE {where_sql}", params)
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            f"""
            SELECT m.id, m.nome_menu, m.descricao, m.ordem, m.pai, m.data_page, mm.modulo
            FROM tbl_menu m
            LEFT JOIN tbl_menu_modulo mm ON mm.id = m.id_modulo
            WHERE {where_sql}
            ORDER BY m.ordem NULLS LAST, m.nome_menu
            LIMIT %s OFFSET %s
            """,
            params + [por_pagina, offset],
        )
        dados = [
            {
                "id": r[0],
                "nome_menu": r[1],
                "descricao": r[2] or "",
                "sequencia": r[3],
                "pai": bool(r[4]),
                "data_page": r[5],
                "modulo": r[6] or "",
            }
            for r in cur.fetchall()
        ]
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        return jsonify(dados=dados, total_paginas=total_paginas, pagina_atual=pagina)
    finally:
        conn.close()


@config_bp.get("/configuracoes/itens-menu/incluir")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.editar")
def config_menu_incluir():
    return render_template("frm_config_menu_apoio.html", url_voltar=url_for("config.config_menu_pagina"))


@config_bp.get("/configuracoes/itens-menu/editar")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.editar")
def config_menu_editar():
    return render_template("frm_config_menu_apoio.html", url_voltar=url_for("config.config_menu_pagina"))


@config_bp.post("/configuracoes/itens-menu/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.ver")
def config_menu_apoio():
    _id = (request.get_json(silent=True) or {}).get("id")
    if not _id:
        return jsonify(erro="ID não informado"), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome_menu, descricao, data_page, icone, tipo_abrir, ordem,
                   parent_id, status, obs, pai, id_modulo, nav_codigo, contexto_modulo
            FROM tbl_menu WHERE id = %s
            """,
            (_id,),
        )
        r = cur.fetchone()
        if not r:
            return jsonify(erro="Registro não encontrado"), 404
        return jsonify(
            id=r[0],
            nome_menu=r[1],
            descricao=r[2],
            data_page=r[3],
            icone=r[4],
            tipo_abrir=r[5],
            sequencia=r[6],
            parent_id=r[7],
            status=r[8],
            obs=r[9],
            pai=r[10],
            id_modulo=r[11],
            nav_codigo=r[12],
            contexto_modulo=r[13] or "comum",
        )
    finally:
        conn.close()


def _contexto_modulo_de_id(cur, id_modulo, nav_codigo: str | None, data_page: str | None, contexto_informado: str | None) -> str:
    """Deriva contexto_modulo sem misturar rotas entre módulos."""
    nav = (nav_codigo or "").strip().lower()
    page = (data_page or "").strip().lower()
    if nav == "inicio" or page in ("/index", "index"):
        return "comum"
    ctx = (contexto_informado or "").strip().lower()
    if ctx in ("fornecedor", "vendedor", "armazem", "comum"):
        return ctx
    if id_modulo:
        cur.execute("SELECT modulo FROM tbl_menu_modulo WHERE id = %s", (int(id_modulo),))
        row = cur.fetchone()
        nome = (row[0] or "").strip().lower() if row else ""
        if "armaz" in nome:
            return "armazem"
        if "fornecedor" in nome:
            return "fornecedor"
        if "vendedor" in nome:
            return "vendedor"
    if nav.startswith("fn_") or page.startswith("/fornecedor/") or page == "/catalogos" or nav == "catalogos":
        return "fornecedor"
    if nav.startswith("az_") or page.startswith("/armazem/"):
        return "armazem"
    if nav.startswith("vd_") or page.startswith("/vendedor/") or page in ("/fornecedores", "/meus-produtos", "/integracoes"):
        return "vendedor"
    return "comum"


@config_bp.post("/configuracoes/itens-menu/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.editar")
def config_menu_salvar():
    if (resp := _exigir_config_escrita()) is not None:
        return resp
    b = request.get_json(silent=True) or {}
    nome_menu = (b.get("nome_menu") or "").strip()
    if not nome_menu:
        return jsonify(erro="Nome do menu é obrigatório."), 400

    data_page = (b.get("data_page") or "").strip()
    if data_page and not data_page.startswith("/") and "://" not in data_page:
        data_page = "/" + data_page
    nav_codigo = (b.get("nav_codigo") or "").strip() or None
    id_modulo = b.get("id_modulo")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        contexto = _contexto_modulo_de_id(cur, id_modulo, nav_codigo, data_page, b.get("contexto_modulo"))
        if contexto == "comum":
            id_modulo = None
        _id = b.get("id")
        campos = (
            nome_menu,
            (b.get("descricao") or "").strip(),
            data_page or "/",
            (b.get("icone") or "").strip(),
            (b.get("tipo_abrir") or "Mesma Janela").strip(),
            b.get("sequencia"),
            b.get("parent_id"),
            normalizar_bool(b.get("status"), True),
            (b.get("obs") or "").strip(),
            normalizar_bool(b.get("pai"), False),
            id_modulo,
            nav_codigo,
            contexto,
        )
        if _id:
            cur.execute(
                """
                UPDATE tbl_menu SET nome_menu=%s, descricao=%s, data_page=%s, icone=%s,
                    tipo_abrir=%s, ordem=%s, parent_id=%s, status=%s, obs=%s, pai=%s,
                    id_modulo=%s, nav_codigo=%s, contexto_modulo=%s
                WHERE id=%s
                """,
                campos + (_id,),
            )
            novo_id = _id
        else:
            cur.execute(
                """
                INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir,
                    ordem, parent_id, status, obs, pai, id_modulo, nav_codigo, contexto_modulo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                campos,
            )
            novo_id = cur.fetchone()[0]
        conn.commit()
        return jsonify(ok=True, id=novo_id)
    except Exception as e:
        conn.rollback()
        return jsonify(erro=str(e)), 500
    finally:
        conn.close()


@config_bp.post("/configuracoes/itens-menu/delete")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.editar")
def config_menu_delete():
    if (resp := _exigir_config_escrita()) is not None:
        return resp
    _id = (request.get_json(silent=True) or {}).get("id")
    if not _id:
        return jsonify(erro="ID não informado"), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_menu WHERE id = %s", (_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(erro="Registro não encontrado"), 404
        return jsonify(ok=True)
    finally:
        conn.close()


@config_bp.get("/configuracoes/itens-menu/combos")
@login_obrigatorio()
@exigir_permissao(codigo="configuracoes.ver")
def config_menu_combos():
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT nome_menu FROM tbl_menu WHERE pai = TRUE ORDER BY 1")
        menus_pai = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT id, nome_menu FROM tbl_menu WHERE pai = TRUE ORDER BY nome_menu")
        pais = [{"id": r[0], "nome_menu": r[1]} for r in cur.fetchall()]
        cur.execute(
            """
            SELECT id, modulo FROM tbl_menu_modulo
            WHERE ativo = TRUE
              AND LOWER(TRIM(modulo)) IN ('fornecedor', 'vendedor', 'armazém', 'armazem')
            ORDER BY ordem, modulo
            """
        )
        modulos = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(
            menus_pai=menus_pai,
            pais=pais,
            modulos=modulos,
            contextos=["comum", "fornecedor", "vendedor", "armazem"],
            tipos_abrir=["Mesma Janela", "Nova Janela"],
            icones_em_uso=["layout-dashboard", "users", "package", "shopping-bag", "plug", "settings"],
        )
    finally:
        conn.close()


# ─── Menu dinâmico (sidebar) ───────────────────────────────────────────

_ICONES_SVG = {
    "layout-dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "package": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>',
    "shopping-bag": '<path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/>',
    "store": '<path d="M3 9l1-4h16l1 4"/><path d="M3 9v11a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9"/><path d="M3 9h18"/><path d="M10 13h4v8h-4z"/>',
    "plug": '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2"/>',
}

# Labels só para fallback de emergência (quando a query da sidebar falha).
_MENU_NOME_POR_NAV: dict[str, str] = {
    "az_depositos": "Dep\u00f3sitos",
    "az_categorias": "Categorias",
    "az_movimentacoes": "Movimenta\u00e7\u00f5es",
    "az_parametros": "Par\u00e2metros",
    "az_usuarios": "Usu\u00e1rios",
    "az_integracoes": "Integra\u00e7\u00f5es",
    "az_fornecedores": "Fornecedores",
    "az_produtos": "Produtos",
    "az_pedidos": "Pedidos",
    "az_vendedores": "Vendedores",
}


def _icone_svg_menu(nome: str | None) -> str:
    key = (nome or "layout-dashboard").strip().lower()
    return _ICONES_SVG.get(key, _ICONES_SVG["layout-dashboard"])


def _garantir_dashboard_primeiro(cur) -> None:
    """Garante Dashboard (inicio / comum) como primeiro item da sidebar (não altera nome_menu)."""
    cur.execute(
        """
        UPDATE tbl_menu
           SET ordem = 1,
               status = TRUE,
               pai = TRUE,
               parent_id = NULL,
               contexto_modulo = 'comum',
               data_page = '/index'
         WHERE COALESCE(nav_codigo, '') = 'inicio'
            OR COALESCE(data_page, '') IN ('/index', 'index')
        """
    )


def _dashboard_primeiro_na_lista(itens: list[dict]) -> list[dict]:
    dash = [i for i in itens if (i.get("nav_codigo") or "").lower() == "inicio"]
    if not dash:
        return itens
    outros = [i for i in itens if (i.get("nav_codigo") or "").lower() != "inicio"]
    return dash + outros


def carregar_menu_sidebar() -> list[dict]:
    """Sidebar = itens de tbl_menu do módulo, filtrados pelo acesso do usuário.

    Regra:
      - Desenvolvedor / Dono → todos os candidatos do módulo
      - Equipe → somente menus ligados em tbl_usuario_tenant_menu
        (sem linhas: aplica padrão dos switches)
    """
    from sistema.plataforma.sessao import (
        garantir_modulo_sessao,
        garantir_tabela_usuario_tenant_menu,
        resolver_url_menu,
        _eh_menu_exclusivo_header,
        _nav_default_ligado,
    )

    if not session.get("id_usuario"):
        return []

    id_perfil = session.get("id_perfil")
    if not id_perfil and not session.get("eh_desenvolvedor"):
        return []

    mod_ativo = garantir_modulo_sessao()
    ctx_filtro = ["comum", mod_ativo]
    perfil_codigo = (session.get("perfil_codigo") or session.get("papel") or "").lower()
    acesso_total = bool(session.get("eh_desenvolvedor")) or perfil_codigo == "dono"
    id_usuario = session.get("id_usuario")
    id_tenant = session.get("id_tenant")

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        try:
            _garantir_dashboard_primeiro(cur)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

        # 1) Candidatos da sidebar em tbl_menu (nunca header / config).
        cur.execute(
            """
            SELECT m.id, m.nome_menu, m.data_page, m.icone, m.nav_codigo, m.parent_id, m.pai,
                   COALESCE(m.contexto_modulo, ''), COALESCE(m.obs, '')
            FROM tbl_menu m
            WHERE m.status = TRUE
              AND m.pai = TRUE
              AND m.parent_id IS NULL
              AND COALESCE(m.contexto_modulo, 'comum') = ANY(%s)
              AND COALESCE(m.contexto_modulo, '') <> 'header'
              AND COALESCE(m.obs, '') <> 'header'
              AND COALESCE(m.nav_codigo, '') <> 'config'
              AND COALESCE(m.nav_codigo, '') NOT LIKE 'hdr_%%'
              AND COALESCE(m.data_page, '') <> '/configuracoes'
            ORDER BY m.ordem NULLS LAST, m.nome_menu
            """,
            (list(ctx_filtro),),
        )
        candidatos = cur.fetchall()

        # 2) Acesso do usuário.
        liberados: set[int] | None = None
        if not acesso_total:
            garantir_tabela_usuario_tenant_menu(cur)
            cur.execute(
                """
                SELECT COUNT(*)::int FROM tbl_usuario_tenant_menu
                WHERE id_usuario = %s AND id_tenant = %s
                """,
                (id_usuario, id_tenant),
            )
            tem_override = int(cur.fetchone()[0] or 0) > 0

            if tem_override:
                cur.execute(
                    """
                    SELECT id_menu FROM tbl_usuario_tenant_menu
                    WHERE id_usuario = %s AND id_tenant = %s AND exibir = TRUE
                    """,
                    (id_usuario, id_tenant),
                )
                liberados = {int(r[0]) for r in cur.fetchall()}
            else:
                # Sem override: padrão dos switches (não usa tbl_perfil_menu)
                liberados = {
                    int(r[0])
                    for r in candidatos
                    if _nav_default_ligado(r[4])
                }

        itens = []
        for row in candidatos:
            mid, nome, data_page, icone, nav_codigo, parent_id, pai, ctx_mod, obs = row
            if _eh_menu_exclusivo_header(
                nav_codigo=nav_codigo,
                data_page=data_page,
                nome=nome,
                contexto_modulo=ctx_mod,
                obs=obs,
            ):
                continue
            if liberados is not None and int(mid) not in liberados:
                continue
            itens.append(
                {
                    "id": mid,
                    "nome": (nome or "").strip() or (nav_codigo or "Menu"),
                    "url": resolver_url_menu(data_page, nav_codigo),
                    "icone_svg": _icone_svg_menu(icone),
                    "nav_codigo": nav_codigo or "",
                    "parent_id": parent_id,
                    "pai": pai,
                }
            )
        return _dashboard_primeiro_na_lista(itens)
    except Exception:
        return _menu_sidebar_fallback(mod_ativo)
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _menu_sidebar_fallback(mod_ativo: str = "vendedor") -> list[dict]:
    from sistema.plataforma.sessao import MODULO_ARMAZEM, MODULO_FORNECEDOR, resolver_url_menu

    comum = [
        {"nome": "Dashboard", "url": url_for("dashboard.index"), "icone_svg": _ICONES_SVG["layout-dashboard"], "nav_codigo": "inicio"},
    ]
    if mod_ativo == MODULO_FORNECEDOR:
        return comum + [
            {"nome": "Pedidos", "url": url_for("fn_pedidos.pedidos"), "icone_svg": _ICONES_SVG["shopping-bag"], "nav_codigo": "fn_pedidos"},
            {"nome": "Catálogo", "url": url_for("fn_catalogo.pagina"), "icone_svg": _ICONES_SVG["package"], "nav_codigo": "catalogos"},
        ]
    if mod_ativo == MODULO_ARMAZEM:
        return comum + [
            {"nome": _MENU_NOME_POR_NAV["az_fornecedores"], "url": resolver_url_menu("/armazem/fornecedores", "az_fornecedores"), "icone_svg": _ICONES_SVG["users"], "nav_codigo": "az_fornecedores"},
            {"nome": _MENU_NOME_POR_NAV["az_depositos"], "url": resolver_url_menu("/armazem/depositos", "az_depositos"), "icone_svg": _ICONES_SVG["package"], "nav_codigo": "az_depositos"},
            {"nome": _MENU_NOME_POR_NAV["az_categorias"], "url": resolver_url_menu("/armazem/categorias", "az_categorias"), "icone_svg": _ICONES_SVG["package"], "nav_codigo": "az_categorias"},
            {"nome": _MENU_NOME_POR_NAV["az_produtos"], "url": resolver_url_menu("/armazem/produtos", "az_produtos"), "icone_svg": _ICONES_SVG["package"], "nav_codigo": "az_produtos"},
            {"nome": _MENU_NOME_POR_NAV["az_movimentacoes"], "url": resolver_url_menu("/armazem/movimentacoes", "az_movimentacoes"), "icone_svg": _ICONES_SVG["package"], "nav_codigo": "az_movimentacoes"},
            {"nome": _MENU_NOME_POR_NAV["az_pedidos"], "url": resolver_url_menu("/armazem/pedidos", "az_pedidos"), "icone_svg": _ICONES_SVG["shopping-bag"], "nav_codigo": "az_pedidos"},
            {"nome": _MENU_NOME_POR_NAV["az_parametros"], "url": resolver_url_menu("/armazem/parametros", "az_parametros"), "icone_svg": _ICONES_SVG["settings"], "nav_codigo": "az_parametros"},
            {"nome": _MENU_NOME_POR_NAV["az_usuarios"], "url": resolver_url_menu("/armazem/usuarios", "az_usuarios"), "icone_svg": _ICONES_SVG["users"], "nav_codigo": "az_usuarios"},
            {"nome": _MENU_NOME_POR_NAV["az_integracoes"], "url": resolver_url_menu("/armazem/integracoes", "az_integracoes"), "icone_svg": _ICONES_SVG["plug"], "nav_codigo": "az_integracoes"},
        ]
    return comum + [
        {"nome": "Fornecedores", "url": url_for("vd_fornecedores.pagina"), "icone_svg": _ICONES_SVG["users"], "nav_codigo": "fornecedores"},
        {"nome": "Meus produtos", "url": url_for("vd_meus_produtos.pagina"), "icone_svg": _ICONES_SVG["shopping-bag"], "nav_codigo": "produtos"},
        {"nome": "Loja Virtual", "url": url_for("vd_loja_virtual.pagina"), "icone_svg": _ICONES_SVG["store"], "nav_codigo": "vd_loja_virtual"},
    ]


def obter_menu_sidebar_ctx() -> dict:
    from sistema.plataforma.sessao import ctx_navegacao

    base = ctx_navegacao()
    base["menu_sidebar"] = carregar_menu_sidebar() if session.get("id_usuario") else []
    base["menu_badges_nav"] = {}
    base["menu_badges_modulos"] = {}

    tid = session.get("id_tenant")
    if not tid or not session.get("id_usuario"):
        return base

    try:
        from core.menu_badges import contagens_menu_badges

        mods = [m.get("codigo") for m in (base.get("modulos_nav") or []) if m.get("codigo")]
        if not mods:
            ativo = (base.get("modulo_ativo") or "").strip()
            if ativo:
                mods = [ativo]
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            counts = contagens_menu_badges(cur, id_tenant=int(tid), modulos=mods)
            base["menu_badges_nav"] = counts.get("nav") or {}
            base["menu_badges_modulos"] = counts.get("modulos") or {}
        finally:
            conn.close()
    except Exception:
        pass
    return base

# --- segmentos plataforma ---
import re
import unicodedata

SEGMENTOS_PLATAFORMA_PREFIX = "/configuracoes/segmentos-plataforma"


def _slugify_segmento(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return (s[:56] or "segmento")


def _exigir_dev():
    if session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Acesso restrito ao desenvolvedor."), 403


@config_bp.get(SEGMENTOS_PLATAFORMA_PREFIX)
@login_obrigatorio()
def segmentos_plataforma_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_segmentos.html", nav_ativo="config")


@config_bp.get(f"{SEGMENTOS_PLATAFORMA_PREFIX}/dados")
@login_obrigatorio()
def segmentos_plataforma_dados():
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.id, s.nome, s.slug, s.descricao, s.ordem, s.ativo,
                   (SELECT COUNT(*)::int FROM tbl_fornecedor_segmento fs WHERE fs.id_segmento = s.id),
                   (SELECT COUNT(*)::int FROM tbl_categoria c WHERE c.id_segmento = s.id)
            FROM tbl_segmento s
            WHERE s.id_tenant IS NULL
            ORDER BY s.ordem, s.nome
            """
        )
        lista = [
            {
                "id": row[0],
                "nome": row[1],
                "slug": row[2] or "",
                "descricao": row[3] or "",
                "ordem": row[4],
                "ativo": bool(row[5]),
                "qtd_fornecedores": int(row[6] or 0),
                "qtd_categorias": int(row[7] or 0),
            }
            for row in cur.fetchall()
        ]
        return jsonify(success=True, segmentos=lista)
    finally:
        conn.close()


@config_bp.post(f"{SEGMENTOS_PLATAFORMA_PREFIX}/salvar")
@login_obrigatorio()
def segmentos_plataforma_salvar():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome do segmento."), 400
    slug = (body.get("slug") or "").strip() or _slugify_segmento(nome)
    sid = body.get("id")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if sid:
            cur.execute(
                """
                UPDATE tbl_segmento SET
                    nome=%s, slug=%s, descricao=%s, ordem=%s, ativo=%s
                WHERE id=%s AND id_tenant IS NULL
                RETURNING id
                """,
                (
                    nome,
                    slug,
                    (body.get("descricao") or "").strip() or None,
                    int(body.get("ordem") or 0),
                    bool(body.get("ativo", True)),
                    int(sid),
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_segmento (id_tenant, nome, slug, descricao, ordem, ativo)
                VALUES (NULL, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    nome,
                    slug,
                    (body.get("descricao") or "").strip() or None,
                    int(body.get("ordem") or 0),
                    bool(body.get("ativo", True)),
                ),
            )
        row = cur.fetchone()
        conn.commit()
        return jsonify(success=True, id=row[0], message="Segmento salvo.")
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower() or "uq_segmento" in str(e).lower():
            return jsonify(success=False, message="Nome ou slug já cadastrado."), 409
        raise
    finally:
        conn.close()


@config_bp.post(f"{SEGMENTOS_PLATAFORMA_PREFIX}/excluir")
@login_obrigatorio()
def segmentos_plataforma_excluir():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        sid = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Segmento inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tbl_fornecedor_segmento WHERE id_segmento = %s",
            (sid,),
        )
        if int(cur.fetchone()[0] or 0) > 0:
            return jsonify(
                success=False,
                message="Há fornecedores usando este segmento. Inative em vez de excluir.",
            ), 409
        cur.execute(
            "UPDATE tbl_categoria SET id_segmento = NULL WHERE id_segmento = %s",
            (sid,),
        )
        cur.execute("DELETE FROM tbl_segmento WHERE id = %s AND id_tenant IS NULL", (sid,))
        conn.commit()
        return jsonify(success=True, message="Segmento removido.")
    finally:
        conn.close()


# --- Marktplace (catálogo dinâmico) ---

MARKTPLACE_ADMIN_PREFIX = "/configuracoes/marktplace-produtos"


@config_bp.get(MARKTPLACE_ADMIN_PREFIX)
@login_obrigatorio()
def marktplace_produtos_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_marktplace.html", nav_ativo="config")


@config_bp.get(f"{MARKTPLACE_ADMIN_PREFIX}/dados")
@login_obrigatorio()
def marktplace_produtos_dados():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.marktplace.srotas_marktplace import SQL_LISTA, produto_dict

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(SQL_LISTA)
        lista = [produto_dict(r) for r in cur.fetchall()]
        return jsonify(success=True, produtos=lista)
    finally:
        conn.close()


@config_bp.post(f"{MARKTPLACE_ADMIN_PREFIX}/salvar")
@login_obrigatorio()
def marktplace_produtos_salvar():
    if (r := _exigir_dev()) is not None:
        return r
    import json as _json

    from sistema.marktplace.srotas_marktplace import produto_dict

    body = request.get_json(silent=True) or {}
    titulo = (body.get("titulo") or "").strip()
    if not titulo:
        return jsonify(success=False, message="Informe o título do produto."), 400
    slug = (body.get("slug") or "").strip() or _slugify_segmento(titulo)
    try:
        valor_centavos = int(round(float(body.get("valor_reais") or 0) * 100))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Valor inválido."), 400
    meta = body.get("meta")
    if isinstance(meta, str):
        try:
            meta = _json.loads(meta) if meta.strip() else {}
        except _json.JSONDecodeError:
            return jsonify(success=False, message="Meta JSON inválido."), 400
    elif not isinstance(meta, dict):
        meta = {}

    pid = body.get("id")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        params = (
            titulo,
            slug,
            (body.get("resumo") or "").strip() or None,
            body.get("descricao") or "",
            valor_centavos,
            (body.get("tipo_pagamento") or "unico").strip(),
            (body.get("publico") or "ambos").strip(),
            (body.get("categoria") or "geral").strip(),
            (body.get("tipo_acao") or "").strip() or None,
            _json.dumps(meta),
            (body.get("icone") or "shopping-bag").strip(),
            (body.get("cor_topo") or "#5b57f5").strip(),
            int(body.get("ordem") or 0),
            bool(body.get("ativo", True)),
        )
        if pid:
            cur.execute(
                """
                UPDATE tbl_marktplace_produto SET
                    titulo=%s, slug=%s, resumo=%s, descricao=%s, valor_centavos=%s,
                    tipo_pagamento=%s, publico=%s, categoria=%s, tipo_acao=%s, meta=%s::jsonb,
                    icone=%s, cor_topo=%s, ordem=%s, ativo=%s, atualizado_em=NOW()
                WHERE id=%s
                RETURNING id, slug, titulo, resumo, descricao, valor_centavos, tipo_pagamento,
                          publico, categoria, tipo_acao, meta, icone, cor_topo, ordem, ativo
                """,
                (*params, int(pid)),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_marktplace_produto (
                    titulo, slug, resumo, descricao, valor_centavos, tipo_pagamento,
                    publico, categoria, tipo_acao, meta, icone, cor_topo, ordem, ativo
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
                RETURNING id, slug, titulo, resumo, descricao, valor_centavos, tipo_pagamento,
                          publico, categoria, tipo_acao, meta, icone, cor_topo, ordem, ativo
                """,
                params,
            )
        row = cur.fetchone()
        conn.commit()
        return jsonify(success=True, produto=produto_dict(row), message="Produto salvo.")
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower() or "slug" in str(e).lower():
            return jsonify(success=False, message="Slug já cadastrado."), 409
        raise
    finally:
        conn.close()


@config_bp.post(f"{MARKTPLACE_ADMIN_PREFIX}/excluir")
@login_obrigatorio()
def marktplace_produtos_excluir():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        pid = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Produto inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_marktplace_produto WHERE id = %s", (pid,))
        conn.commit()
        return jsonify(success=True, message="Produto removido.")
    finally:
        conn.close()


# --- manutenção de tenant (DEV) ---

MANUTENCAO_TENANT_PREFIX = "/configuracoes/manutencao-tenant"
_TIPOS_NEGOCIO_OK = frozenset({"vendedor", "fornecedor", "armazem"})
_PLANOS_OK = frozenset({"starter", "professional", "scale", "enterprise"})


def _contagens_tenant(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT
          (SELECT COUNT(*)::int FROM tbl_produto WHERE id_tenant = %s),
          (SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor WHERE id_tenant_fornecedor = %s),
          (SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor WHERE id_tenant_vendedor = %s),
          (SELECT COUNT(*)::int FROM tbl_pedido WHERE id_tenant_fornecedor = %s),
          (SELECT COUNT(*)::int FROM tbl_pedido WHERE id_tenant_vendedor = %s),
          (SELECT COUNT(*)::int FROM tbl_fornecedor_segmento WHERE id_tenant = %s)
        """,
        (id_tenant, id_tenant, id_tenant, id_tenant, id_tenant, id_tenant),
    )
    row = cur.fetchone() or (0, 0, 0, 0, 0, 0)
    return {
        "produtos": int(row[0] or 0),
        "vinculos_como_fornecedor": int(row[1] or 0),
        "vinculos_como_vendedor": int(row[2] or 0),
        "pedidos_como_fornecedor": int(row[3] or 0),
        "pedidos_como_vendedor": int(row[4] or 0),
        "segmentos": int(row[5] or 0),
    }


def _tem_relacionamento(contagens: dict) -> bool:
    """Vínculo ou pedido impede exclusão — só desativa."""
    return bool(
        int(contagens.get("vinculos_como_fornecedor") or 0)
        + int(contagens.get("vinculos_como_vendedor") or 0)
        + int(contagens.get("pedidos_como_fornecedor") or 0)
        + int(contagens.get("pedidos_como_vendedor") or 0)
    )


@config_bp.get(MANUTENCAO_TENANT_PREFIX)
@login_obrigatorio()
def manutencao_tenant_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_manutencao_tenant.html", nav_ativo="config")


@config_bp.get(f"{MANUTENCAO_TENANT_PREFIX}/editar")
@login_obrigatorio()
def manutencao_tenant_editar():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_manutencao_tenant_apoio.html")


@config_bp.get(f"{MANUTENCAO_TENANT_PREFIX}/dados")
@login_obrigatorio()
def manutencao_tenant_dados():
    if (r := _exigir_dev()) is not None:
        return r
    q = (request.args.get("q") or "").strip()
    tipo = (request.args.get("tipo") or "").strip().lower()
    ativo = (request.args.get("ativo") or "").strip().lower()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["TRUE"]
        params: list = []
        if q:
            where.append(
                "(t.nome ILIKE %s OR t.slug ILIKE %s OR COALESCE(t.documento,'') ILIKE %s "
                "OR CAST(t.id AS TEXT) = %s)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, q])
        if tipo in _TIPOS_NEGOCIO_OK:
            where.append("t.tipo_negocio = %s")
            params.append(tipo)
        if ativo in ("1", "true", "sim"):
            where.append("t.ativo = TRUE")
        elif ativo in ("0", "false", "nao", "não"):
            where.append("t.ativo = FALSE")
        cur.execute(
            f"""
            SELECT t.id, t.nome, t.slug, t.tipo_negocio, t.plano, t.ativo, t.documento,
                   t.cidade, t.uf, t.tipo_pessoa,
                   COALESCE(NULLIF(TRIM(t.razao_social), ''), NULLIF(TRIM(t.nome_completo), ''), ''),
                   t.criado_em,
                   (
                     SELECT ut.ultimo_acesso_em
                     FROM tbl_usuario_tenant ut
                     JOIN tbl_perfil pf ON pf.id = ut.id_perfil
                     WHERE ut.id_tenant = t.id
                       AND LOWER(COALESCE(pf.codigo, '')) = 'dono'
                     ORDER BY ut.ultimo_acesso_em DESC NULLS LAST, ut.id
                     LIMIT 1
                   ) AS dono_ultimo_acesso,
                   (
                     SELECT COUNT(*)::int FROM tbl_pedido p
                     WHERE p.id_tenant_fornecedor = t.id OR p.id_tenant_vendedor = t.id
                   ) AS n_pedidos,
                   (
                     SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor v
                     WHERE v.id_tenant_fornecedor = t.id OR v.id_tenant_vendedor = t.id
                   ) AS n_vinculos
            FROM tbl_tenant t
            WHERE {" AND ".join(where)}
            ORDER BY t.id DESC
            LIMIT 200
            """,
            params,
        )
        from sistema.config.servico_manutencao_tenant import slug_protegido

        itens = []
        for r in cur.fetchall():
            slug = r[2] or ""
            documento = (r[6] or "").strip()
            digitos = "".join(ch for ch in documento if ch.isdigit())
            tipo_pessoa = (r[9] or "").strip().upper()
            if not tipo_pessoa:
                if len(digitos) == 14:
                    tipo_pessoa = "J"
                elif len(digitos) == 11:
                    tipo_pessoa = "F"
            razao = (r[10] or "").strip() if tipo_pessoa == "J" else ""
            criado = r[11]
            dono_acesso = r[12]
            n_pedidos = int(r[13] or 0)
            n_vinculos = int(r[14] or 0)
            itens.append(
                {
                    "id": int(r[0]),
                    "nome": r[1] or "",
                    "slug": slug,
                    "tipo_negocio": (r[3] or "vendedor").lower(),
                    "plano": (r[4] or "starter").lower(),
                    "ativo": bool(r[5]),
                    "documento": documento,
                    "cidade": r[7] or "",
                    "uf": r[8] or "",
                    "tipo_pessoa": tipo_pessoa,
                    "razao_social": razao,
                    "criado_em": criado.isoformat() if criado else None,
                    "dono_ultimo_acesso": dono_acesso.isoformat() if dono_acesso else None,
                    "n_pedidos": n_pedidos,
                    "n_vinculos": n_vinculos,
                    "tem_relacionamento": (n_pedidos + n_vinculos) > 0,
                    "eh_tenant_sessao": int(session.get("id_tenant") or 0) == int(r[0]),
                    "protegido": slug_protegido(slug),
                }
            )
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@config_bp.get(f"{MANUTENCAO_TENANT_PREFIX}/metricas")
@login_obrigatorio()
def manutencao_tenant_metricas():
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.config.servico_manutencao_tenant import metricas_tenants

        return jsonify(success=True, metricas=metricas_tenants(cur))
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:400]), 500
    finally:
        conn.close()


@config_bp.get(f"{MANUTENCAO_TENANT_PREFIX}/metricas/lista")
@login_obrigatorio()
def manutencao_tenant_metricas_lista():
    if (r := _exigir_dev()) is not None:
        return r
    tipo = (request.args.get("tipo") or "").strip().lower()
    filtro = (request.args.get("filtro") or "total").strip().lower()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.config.servico_manutencao_tenant import listar_tenants_metricas

        payload = listar_tenants_metricas(cur, tipo=tipo or None, filtro=filtro)
        return jsonify(success=True, **payload)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:400]), 500
    finally:
        conn.close()


def _log_convite_email(cur, email: str) -> list[dict]:
    """Envios de convite/ativação desse e-mail, com o status que o webhook do Brevo gravou."""
    email_n = (email or "").strip().lower()
    if not email_n or "@" not in email_n:
        return []
    try:
        cur.execute("SAVEPOINT sp_log_convite")
        cur.execute(
            """
            SELECT d.id_destinatario, d.status_atual, d.dt_ultimo_evento,
                   e.dt_envio, e.assunto, d.tag_email,
                   (
                     SELECT ev.mensagem_erro
                     FROM tbl_email_evento ev
                     WHERE ev.id_destinatario = d.id_destinatario
                       AND NULLIF(TRIM(COALESCE(ev.mensagem_erro, '')), '') IS NOT NULL
                     ORDER BY ev.data_evento DESC, ev.id_evento DESC
                     LIMIT 1
                   )
            FROM tbl_email_destinatario d
            JOIN tbl_email_envio e ON e.id_envio = d.id_envio
            WHERE lower(d.email) = %s
              AND d.tag_email IN ('dropnexo_cadastro', 'dropnexo_convite_equipe')
            ORDER BY COALESCE(d.dt_ultimo_evento, e.dt_envio) DESC, d.id_destinatario DESC
            LIMIT 8
            """,
            (email_n,),
        )
        rows = cur.fetchall()
        cur.execute("RELEASE SAVEPOINT sp_log_convite")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sp_log_convite")
        except Exception:
            pass
        return []
    out = []
    for row in rows:
        out.append(
            {
                "id": int(row[0]),
                "status": row[1] or "",
                "atualizado_em": row[2].isoformat() if row[2] else None,
                "enviado_em": row[3].isoformat() if row[3] else None,
                "assunto": row[4] or "",
                "tag": row[5] or "",
                "erro": row[6] or "",
            }
        )
    return out


def _tenant_payload(cur, id_tenant: int) -> dict | None:
    cur.execute(
        """
        SELECT id, nome, slug, tipo_negocio, plano, ativo, documento,
               tipo_pessoa, nome_completo, cidade, uf, email_comercial, telefone_comercial
        FROM tbl_tenant WHERE id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return None
    contagens = _contagens_tenant(cur, id_tenant)
    from sistema.config.servico_manutencao_tenant import slug_protegido

    slug = (row[2] or "").strip().lower()
    email_comercial = (row[11] or "").strip()
    telefone_comercial = (row[12] or "").strip()

    # Contato do dono (whatsapp/e-mail do cadastro) — fallback útil no suporte.
    dono = {
        "id": None,
        "nome": "",
        "email": "",
        "whatsapp": "",
        "ativo": None,
        "eh_desenvolvedor": False,
        "perfil_codigo": "",
        "perfil_nome": "",
        "vinculo_ativo": None,
        "ultimo_acesso_em": None,
        "criado_em": None,
    }
    try:
        cur.execute(
            """
            SELECT u.id, u.nome, u.email, u.whatsapp, COALESCE(u.ativo, TRUE),
                   COALESCE(u.eh_desenvolvedor, FALSE),
                   LOWER(COALESCE(pf.codigo, '')), COALESCE(pf.nome, ''),
                   ut.ativo, ut.ultimo_acesso_em, u.criado_em
            FROM tbl_usuario_tenant ut
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            WHERE ut.id_tenant = %s
              AND LOWER(pf.codigo) = 'dono'
            ORDER BY ut.ativo DESC NULLS LAST, ut.id
            LIMIT 1
            """,
            (id_tenant,),
        )
        row_dono = cur.fetchone()
        if row_dono:
            dono = {
                "id": int(row_dono[0]),
                "nome": (row_dono[1] or "").strip(),
                "email": (row_dono[2] or "").strip(),
                "whatsapp": (row_dono[3] or "").strip(),
                "ativo": bool(row_dono[4]),
                "eh_desenvolvedor": bool(row_dono[5]),
                "perfil_codigo": (row_dono[6] or "").strip(),
                "perfil_nome": (row_dono[7] or "").strip(),
                "vinculo_ativo": bool(row_dono[8]) if row_dono[8] is not None else None,
                "ultimo_acesso_em": row_dono[9].isoformat() if row_dono[9] else None,
                "criado_em": row_dono[10].isoformat() if row_dono[10] else None,
            }
    except Exception:
        try:
            cur.execute(
                """
                SELECT u.id, u.nome, u.email, u.whatsapp, COALESCE(u.ativo, TRUE),
                       COALESCE(u.eh_desenvolvedor, FALSE),
                       LOWER(COALESCE(pf.codigo, '')), COALESCE(pf.nome, ''),
                       ut.ativo, ut.ultimo_acesso_em
                FROM tbl_usuario_tenant ut
                JOIN tbl_usuario u ON u.id = ut.id_usuario
                JOIN tbl_perfil pf ON pf.id = ut.id_perfil
                WHERE ut.id_tenant = %s
                  AND LOWER(pf.codigo) = 'dono'
                ORDER BY ut.ativo DESC NULLS LAST, ut.id
                LIMIT 1
                """,
                (id_tenant,),
            )
            row_dono = cur.fetchone()
            if row_dono:
                dono = {
                    "id": int(row_dono[0]),
                    "nome": (row_dono[1] or "").strip(),
                    "email": (row_dono[2] or "").strip(),
                    "whatsapp": (row_dono[3] or "").strip(),
                    "ativo": bool(row_dono[4]),
                    "eh_desenvolvedor": bool(row_dono[5]),
                    "perfil_codigo": (row_dono[6] or "").strip(),
                    "perfil_nome": (row_dono[7] or "").strip(),
                    "vinculo_ativo": bool(row_dono[8]) if row_dono[8] is not None else None,
                    "ultimo_acesso_em": row_dono[9].isoformat() if row_dono[9] else None,
                    "criado_em": None,
                }
        except Exception:
            pass

    if dono.get("id"):
        try:
            cur.execute("SAVEPOINT sp_convite_status")
            dono["convite_status"] = status_convite(cur, int(dono["id"]))
            cur.execute("RELEASE SAVEPOINT sp_convite_status")
        except Exception:
            dono["convite_status"] = ""
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_convite_status")
            except Exception:
                pass
        dono["convite_log"] = _log_convite_email(cur, dono.get("email") or "")
    else:
        dono["convite_status"] = ""
        dono["convite_log"] = []

    dono_email = dono.get("email") or ""
    dono_whatsapp = dono.get("whatsapp") or ""
    dono_nome = dono.get("nome") or ""

    email = email_comercial or dono_email
    whatsapp = dono_whatsapp or telefone_comercial

    return {
        "id": int(row[0]),
        "nome": row[1] or "",
        "slug": row[2] or "",
        "tipo_negocio": (row[3] or "vendedor").lower(),
        "plano": (row[4] or "starter").lower(),
        "ativo": bool(row[5]),
        "documento": row[6] or "",
        "tipo_pessoa": row[7] or "",
        "nome_completo": row[8] or "",
        "cidade": row[9] or "",
        "uf": row[10] or "",
        "email_comercial": email_comercial,
        "telefone_comercial": telefone_comercial,
        "email": email,
        "whatsapp": whatsapp,
        "dono_nome": dono_nome,
        "dono_email": dono_email,
        "dono_whatsapp": dono_whatsapp,
        "dono": dono,
        "contagens": contagens,
        "tem_relacionamento": _tem_relacionamento(contagens),
        "eh_tenant_sessao": int(session.get("id_tenant") or 0) == int(row[0]),
        "protegido": slug_protegido(slug),
    }


@config_bp.get(f"{MANUTENCAO_TENANT_PREFIX}/<int:id_tenant>")
@login_obrigatorio()
def manutencao_tenant_detalhe(id_tenant: int):
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        tenant = _tenant_payload(cur, id_tenant)
        if not tenant:
            return jsonify(success=False, message="Tenant não encontrado."), 404
        return jsonify(success=True, tenant=tenant)
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/apoio")
@login_obrigatorio()
def manutencao_tenant_apoio():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Tenant inválido."), 400
    if id_tenant <= 0:
        return jsonify(success=False, message="Informe o tenant para editar."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        tenant = _tenant_payload(cur, id_tenant)
        if not tenant:
            return jsonify(success=False, message="Tenant não encontrado."), 404
        return jsonify(success=True, tenant=tenant)
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/<int:id_tenant>/reenviar-convite")
@login_obrigatorio()
def manutencao_tenant_reenviar_convite(id_tenant: int):
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        tenant = _tenant_payload(cur, id_tenant)
        if not tenant:
            return jsonify(success=False, message="Tenant não encontrado."), 404
        dono = tenant.get("dono") or {}
        uid = int(dono.get("id") or 0)
        if uid <= 0:
            return jsonify(success=False, message="Este tenant não tem dono para receber o convite."), 400
        if (dono.get("convite_status") or "") == "ACEITO":
            return jsonify(success=False, message="Este dono já definiu a senha. O convite não é reenviado."), 400
    finally:
        conn.close()

    payload, status = reenviar_convite_usuario(id_tenant=id_tenant, uid=uid)
    if status != 200:
        return jsonify(payload), status

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        tenant = _tenant_payload(cur, id_tenant)
        return jsonify(
            success=True,
            message=payload.get("message") or "Convite reenviado.",
            tenant=tenant,
        )
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/excluir")
@login_obrigatorio()
def manutencao_tenant_excluir():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.config.servico_manutencao_tenant import excluir_tenant_completo

    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Tenant inválido."), 400
    confirm_slug = (body.get("confirm_slug") or "").strip().lower()
    if id_tenant <= 0:
        return jsonify(success=False, message="Tenant inválido."), 400
    if int(session.get("id_tenant") or 0) == id_tenant:
        return (
            jsonify(
                success=False,
                message="Não é possível excluir o tenant da sessão atual. "
                "Troque de tenant (DEV) e tente de novo.",
            ),
            400,
        )

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT slug FROM tbl_tenant WHERE id = %s", (id_tenant,))
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Tenant não encontrado."), 404
        slug = (row[0] or "").strip().lower()
        if confirm_slug and confirm_slug != slug:
            return (
                jsonify(
                    success=False,
                    message="Confirmação inválida. Digite o slug exatamente como cadastrado.",
                ),
                400,
            )
        contagens = _contagens_tenant(cur, id_tenant)
        if _tem_relacionamento(contagens):
            return (
                jsonify(
                    success=False,
                    message="Este tenant tem vínculo ou pedido. Desative em vez de excluir.",
                ),
                400,
            )
        resultado = excluir_tenant_completo(cur, id_tenant)
        conn.commit()
        _log.warning(
            "DEV excluiu tenant #%s slug=%s linhas=%s user=%s",
            id_tenant,
            slug,
            resultado.get("linhas_removidas"),
            session.get("id_usuario"),
        )
        return jsonify(
            success=True,
            message=f"Tenant «{resultado.get('nome')}» excluído "
            f"({resultado.get('linhas_removidas')} linha(s) removidas).",
            resultado=resultado,
        )
    except Exception as e:
        conn.rollback()
        _log.exception("Falha ao excluir tenant #%s", id_tenant)
        return jsonify(success=False, message=str(e)[:400]), 400
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/desativar")
@login_obrigatorio()
def manutencao_tenant_desativar():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.config.servico_manutencao_tenant import slug_protegido

    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Tenant inválido."), 400
    if id_tenant <= 0:
        return jsonify(success=False, message="Tenant inválido."), 400
    if int(session.get("id_tenant") or 0) == id_tenant:
        return jsonify(success=False, message="Não desative o tenant da sessão atual."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT slug, ativo, nome FROM tbl_tenant WHERE id = %s", (id_tenant,))
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Tenant não encontrado."), 404
        if slug_protegido((row[0] or "").strip().lower()):
            return jsonify(success=False, message="Tenant protegido."), 400
        if not row[1]:
            return jsonify(success=True, message="Tenant já estava inativo.")
        cur.execute(
            "UPDATE tbl_tenant SET ativo = FALSE WHERE id = %s",
            (id_tenant,),
        )
        conn.commit()
        return jsonify(success=True, message=f"«{row[2] or 'Tenant'}» desativado.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:400]), 400
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/salvar")
@login_obrigatorio()
def manutencao_tenant_salvar():
    if (r := _exigir_dev()) is not None:
        return r
    from global_utils import plano_slug_banco

    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Tenant inválido."), 400
    if id_tenant <= 0:
        return jsonify(success=False, message="Tenant inválido."), 400

    tipo = (body.get("tipo_negocio") or "").strip().lower()
    if tipo not in _TIPOS_NEGOCIO_OK:
        return jsonify(success=False, message="Tipo de negócio inválido."), 400

    nome = (body.get("nome") or "").strip()
    if not nome or len(nome) < 2:
        return jsonify(success=False, message="Informe o nome do tenant."), 400

    slug = (body.get("slug") or "").strip().lower()
    slug = re.sub(r"[^a-z0-9\-]+", "-", slug).strip("-")
    if not slug or len(slug) < 2:
        return jsonify(success=False, message="Slug inválido."), 400

    plano = plano_slug_banco(body.get("plano"))
    if plano not in _PLANOS_OK:
        plano = "starter"

    ativo = bool(body.get("ativo"))
    documento = re.sub(r"\D+", "", str(body.get("documento") or ""))
    limpar_segmentos = bool(body.get("limpar_segmentos_fornecedor"))

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tipo_negocio FROM tbl_tenant WHERE id = %s FOR UPDATE",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Tenant não encontrado."), 404
        tipo_antigo = (row[0] or "").lower()

        cur.execute(
            "SELECT id FROM tbl_tenant WHERE slug = %s AND id <> %s LIMIT 1",
            (slug, id_tenant),
        )
        if cur.fetchone():
            return jsonify(success=False, message="Slug já em uso por outro tenant."), 400

        if documento:
            cur.execute(
                "SELECT id FROM tbl_tenant WHERE documento = %s AND id <> %s LIMIT 1",
                (documento, id_tenant),
            )
            if cur.fetchone():
                return jsonify(success=False, message="Documento já em uso por outro tenant."), 400

        contagens = _contagens_tenant(cur, id_tenant)
        avisos: list[str] = []
        if tipo != tipo_antigo:
            if tipo == "vendedor" and (
                contagens["produtos"]
                or contagens["vinculos_como_fornecedor"]
                or contagens["pedidos_como_fornecedor"]
            ):
                avisos.append(
                    "Tenant tinha dados de fornecedor; o tipo foi alterado mesmo assim. "
                    "Produtos/vínculos/pedidos continuam no banco, mas o menu passa a ser de vendedor."
                )
            if tipo == "fornecedor" and contagens["vinculos_como_vendedor"]:
                avisos.append(
                    "Tenant já tem vínculos como vendedor; confira se o tipo correto é só fornecedor."
                )
            if tipo == "armazem" and tipo_antigo in ("fornecedor", "hibrido"):
                avisos.append(
                    "Parâmetros de rede/aprovação serão copiados para o módulo Armazém. "
                    "Peça logout/login e confira Parâmetros do armazém."
                )
            if tipo == "armazem" and (
                contagens["produtos"] or contagens["vinculos_como_fornecedor"]
            ):
                avisos.append(
                    "Produtos e vínculos existentes permanecem. "
                    "No modo B, associe cada produto a um fornecedor local."
                )

        cur.execute(
            """
            UPDATE tbl_tenant SET
                nome = %s,
                slug = %s,
                tipo_negocio = %s,
                plano = %s,
                ativo = %s,
                documento = NULLIF(%s, '')
            WHERE id = %s
            """,
            (nome, slug, tipo, plano, ativo, documento, id_tenant),
        )

        segmentos_removidos = 0
        if limpar_segmentos and tipo == "vendedor":
            cur.execute(
                "DELETE FROM tbl_fornecedor_segmento WHERE id_tenant = %s",
                (id_tenant,),
            )
            segmentos_removidos = int(cur.rowcount or 0)

        mig_az = None
        if tipo != tipo_antigo and tipo == "armazem" and tipo_antigo in ("fornecedor", "hibrido"):
            from sistema.config.servico_manutencao_tenant import migrar_fornecedor_para_armazem

            mig_az = migrar_fornecedor_para_armazem(cur, id_tenant)

        conn.commit()

        sessao_atualizada = False
        if int(session.get("id_tenant") or 0) == id_tenant:
            from sistema.plataforma.sessao import modulo_padrao

            session["tenant_nome"] = nome
            session["tenant_slug"] = slug
            session["tenant_plano"] = plano
            session["tenant_tipo_negocio"] = tipo
            session["modulo_ativo"] = modulo_padrao(tipo)
            sessao_atualizada = True

        msg = "Tenant atualizado."
        if tipo != tipo_antigo:
            msg = f"Tipo alterado de «{tipo_antigo}» para «{tipo}». Peça ao usuário para sair e entrar de novo."
        if mig_az is not None:
            if mig_az.get("visivel_rede_vendedor"):
                msg += " Visibilidade na rede do vendedor mantida (parâmetros do armazém)."
            else:
                msg += " Abra Parâmetros do armazém para exibir na rede (ainda estava oculto)."
        if segmentos_removidos:
            msg += f" {segmentos_removidos} segmento(s) de fornecedor removido(s)."

        return jsonify(
            success=True,
            message=msg,
            avisos=avisos,
            sessao_atualizada=sessao_atualizada,
            migracao_armazem=mig_az,
            tenant={
                "id": id_tenant,
                "nome": nome,
                "slug": slug,
                "tipo_negocio": tipo,
                "plano": plano,
                "ativo": ativo,
                "documento": documento,
            },
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


# --- mala direta (DEV) ---

MALA_DIRETA_PREFIX = "/configuracoes/mala-direta"
MALA_DIRETA_EMAIL_TESTE = "hazael@h74.com.br"


def _normalizar_corpo_mala_direta(corpo_html: str) -> str:
    """Mantém HTML do editor; texto puro vira <p> com <br>."""
    corpo = (corpo_html or "").strip()
    if not corpo:
        return ""
    if "<" not in corpo:
        import html as _html

        return "<p>" + _html.escape(corpo).replace("\n", "<br>") + "</p>"
    return corpo


def _filtro_cadastro_tenant(args) -> tuple[list[str], list]:
    """Filtro por data de cadastro do tenant (tbl_tenant.criado_em).

    Aceita `de`/`ate` em ISO (YYYY-MM-DD). Sem datas = todos.
    """
    from datetime import date as date_cls

    where: list[str] = []
    params: list = []
    de = (args.get("de") or "").strip()[:10]
    ate = (args.get("ate") or "").strip()[:10]

    def _ok(s: str) -> str | None:
        if not s or len(s) != 10:
            return None
        try:
            date_cls.fromisoformat(s)
            return s
        except ValueError:
            return None

    de_ok = _ok(de)
    ate_ok = _ok(ate)
    if de_ok and ate_ok and de_ok > ate_ok:
        de_ok, ate_ok = ate_ok, de_ok
    if de_ok:
        where.append("t.criado_em::date >= %s::date")
        params.append(de_ok)
    if ate_ok:
        where.append("t.criado_em::date <= %s::date")
        params.append(ate_ok)
    return where, params


def _email_destinatario_tenant(cur, id_tenant: int) -> tuple[str | None, str | None]:
    """Preferência: email_comercial do tenant → e-mail do dono ativo."""
    cur.execute(
        "SELECT email_comercial, nome FROM tbl_tenant WHERE id = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return None, None
    nome = row[1] or ""
    email = (row[0] or "").strip().lower()
    if email and "@" in email:
        return email, nome
    cur.execute(
        """
        SELECT u.email
        FROM tbl_usuario_tenant ut
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        JOIN tbl_perfil pf ON pf.id = ut.id_perfil
        WHERE ut.id_tenant = %s AND ut.ativo = TRUE AND u.ativo = TRUE
          AND lower(pf.codigo) = 'dono'
        ORDER BY ut.id
        LIMIT 1
        """,
        (id_tenant,),
    )
    r2 = cur.fetchone()
    if r2 and r2[0]:
        return str(r2[0]).strip().lower(), nome
    cur.execute(
        """
        SELECT u.email
        FROM tbl_usuario_tenant ut
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        WHERE ut.id_tenant = %s AND ut.ativo = TRUE AND u.ativo = TRUE
          AND u.email IS NOT NULL AND trim(u.email) <> ''
        ORDER BY ut.id
        LIMIT 1
        """,
        (id_tenant,),
    )
    r3 = cur.fetchone()
    if r3 and r3[0]:
        return str(r3[0]).strip().lower(), nome
    return None, nome


@config_bp.get(MALA_DIRETA_PREFIX)
@login_obrigatorio()
def mala_direta_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    from api.brevo.srotas_brevo import brevo_configurado, webhook_url_publico

    return render_template(
        "frm_config_mala_direta.html",
        nav_ativo="config",
        webhook_url=webhook_url_publico(),
        brevo_ok=brevo_configurado(),
    )


@config_bp.get(f"{MALA_DIRETA_PREFIX}/tenants")
@login_obrigatorio()
def mala_direta_tenants():
    if (r := _exigir_dev()) is not None:
        return r
    q = (request.args.get("q") or "").strip()
    tipo = (request.args.get("tipo") or "").strip().lower()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["t.ativo = TRUE"]
        params: list = []
        if tipo == "vendedor":
            where.append("t.tipo_negocio IN ('vendedor', 'hibrido')")
        elif tipo == "fornecedor":
            where.append("t.tipo_negocio IN ('fornecedor', 'hibrido')")
        elif tipo == "ambos":
            pass
        elif tipo in _TIPOS_NEGOCIO_OK:
            where.append("t.tipo_negocio = %s")
            params.append(tipo)
        where_cad, params_cad = _filtro_cadastro_tenant(request.args)
        where.extend(where_cad)
        params.extend(params_cad)
        if q:
            where.append(
                "(t.nome ILIKE %s OR t.slug ILIKE %s OR COALESCE(t.documento,'') ILIKE %s "
                "OR CAST(t.id AS TEXT) = %s)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, q])
        cur.execute(
            f"""
            SELECT t.id, t.nome, t.slug, t.tipo_negocio, t.email_comercial, t.criado_em
            FROM tbl_tenant t
            WHERE {" AND ".join(where)}
            ORDER BY t.criado_em DESC NULLS LAST, t.nome ASC
            LIMIT 500
            """,
            params,
        )
        itens = []
        for row in cur.fetchall():
            tid = int(row[0])
            email, _ = _email_destinatario_tenant(cur, tid)
            criado = row[5]
            itens.append(
                {
                    "id": tid,
                    "nome": row[1] or "",
                    "slug": row[2] or "",
                    "tipo_negocio": (row[3] or "").lower(),
                    "email": email or "",
                    "sem_email": not bool(email),
                    "criado_em": criado.isoformat() if criado else "",
                }
            )
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@config_bp.post(f"{MALA_DIRETA_PREFIX}/enviar")
@login_obrigatorio()
def mala_direta_enviar():
    if (r := _exigir_dev()) is not None:
        return r
    from api.brevo.srotas_brevo import enviar_mala_direta

    body = request.get_json(silent=True) or {}
    assunto = (body.get("assunto") or "").strip()
    corpo_html = _normalizar_corpo_mala_direta(
        body.get("corpo_html") or body.get("mensagem") or ""
    )
    filtro = (body.get("filtro_tipo") or "ambos").strip().lower()
    ids_raw = body.get("ids_tenant") or []
    selecionar_todos = bool(body.get("selecionar_todos"))

    if not assunto or not corpo_html:
        return jsonify(success=False, message="Informe assunto e mensagem."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["t.ativo = TRUE"]
        params: list = []
        if filtro == "vendedor":
            where.append("t.tipo_negocio IN ('vendedor', 'hibrido')")
        elif filtro == "fornecedor":
            where.append("t.tipo_negocio IN ('fornecedor', 'hibrido')")
        if not selecionar_todos:
            ids: list[int] = []
            for x in ids_raw:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    pass
            if not ids:
                return jsonify(success=False, message="Selecione ao menos um tenant."), 400
            where.append("t.id = ANY(%s)")
            params.append(ids)
        cur.execute(
            f"SELECT t.id, t.nome FROM tbl_tenant t WHERE {' AND '.join(where)} ORDER BY t.id",
            params,
        )
        rows = cur.fetchall()
        dest = []
        for tid, nome in rows:
            email, _ = _email_destinatario_tenant(cur, int(tid))
            if email:
                dest.append(
                    {
                        "email": email,
                        "id_tenant": int(tid),
                        "nome_tenant": nome or "",
                    }
                )
    finally:
        conn.close()

    if not dest:
        return jsonify(
            success=False,
            message="Nenhum destinatário com e-mail válido nos tenants escolhidos.",
        ), 400

    ok, msg, id_envio, resumo = enviar_mala_direta(
        destinatarios=dest,
        assunto=assunto,
        corpo_html=corpo_html,
        filtro_tipo=filtro,
        criado_por=session.get("id_usuario"),
    )
    if not ok:
        return jsonify(success=False, message=msg, id_envio=id_envio, resumo=resumo), 500
    return jsonify(
        success=True,
        message=f"Disparo concluído: {resumo.get('ok')} enviados, {resumo.get('falha')} falhas.",
        id_envio=id_envio,
        resumo=resumo,
    )


@config_bp.post(f"{MALA_DIRETA_PREFIX}/enviar-teste")
@login_obrigatorio()
def mala_direta_enviar_teste():
    """Envia a mensagem atual só para o e-mail de validação do desenvolvedor."""
    if (r := _exigir_dev()) is not None:
        return r
    from api.brevo.srotas_brevo import enviar_email

    body = request.get_json(silent=True) or {}
    assunto = (body.get("assunto") or "").strip()
    corpo_html = _normalizar_corpo_mala_direta(
        body.get("corpo_html") or body.get("mensagem") or ""
    )
    if not assunto or not corpo_html:
        return jsonify(success=False, message="Informe assunto e mensagem."), 400

    assunto_teste = assunto if assunto.upper().startswith("[TESTE]") else f"[TESTE] {assunto}"
    ok, msg, _id = enviar_email(
        [MALA_DIRETA_EMAIL_TESTE],
        assunto_teste,
        corpo_html,
        tag="mala-teste",
        criado_por=session.get("id_usuario"),
    )
    if not ok:
        return jsonify(success=False, message=msg or "Falha ao enviar teste."), 500
    return jsonify(
        success=True,
        message=f"E-mail teste enviado para {MALA_DIRETA_EMAIL_TESTE}.",
    )


@config_bp.get(f"{MALA_DIRETA_PREFIX}/disparos")
@login_obrigatorio()
def mala_direta_disparos():
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT e.id_envio, e.assunto, e.tag_email, e.dt_envio, e.filtro_tipo,
                   e.total_destinatarios, e.criado_por,
                   (SELECT COUNT(*) FROM tbl_email_destinatario d
                    WHERE d.id_envio = e.id_envio AND lower(d.status_atual) IN ('opened','unique_opened','first_opening')),
                   (SELECT COUNT(*) FROM tbl_email_destinatario d
                    WHERE d.id_envio = e.id_envio AND lower(d.status_atual) LIKE '%%bounce%%'),
                   (SELECT COUNT(*) FROM tbl_email_destinatario d
                    WHERE d.id_envio = e.id_envio AND lower(d.status_atual) IN ('delivered','request')),
                   (SELECT COUNT(*) FROM tbl_email_destinatario d
                    WHERE d.id_envio = e.id_envio AND lower(d.status_atual) IN ('falha','error','blocked','invalid','spam'))
            FROM tbl_email_envio e
            WHERE e.tipo_disparo = 'mala_direta'
            ORDER BY e.dt_envio DESC
            LIMIT 50
            """
        )
        itens = []
        for r in cur.fetchall():
            itens.append(
                {
                    "id_envio": int(r[0]),
                    "assunto": r[1] or "",
                    "tag": r[2] or "",
                    "dt_envio": r[3].isoformat() if r[3] else None,
                    "filtro_tipo": r[4] or "",
                    "total": int(r[5] or 0),
                    "abertos": int(r[7] or 0),
                    "bounces": int(r[8] or 0),
                    "entregues": int(r[9] or 0),
                    "erros": int(r[10] or 0),
                }
            )
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@config_bp.get(f"{MALA_DIRETA_PREFIX}/disparo/apoio")
@login_obrigatorio()
def mala_direta_disparo_apoio_pagina():
    """Apoio nível 1 — destinatários e último status do disparo."""
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    try:
        id_envio = int(request.args.get("id_envio") or 0)
    except (TypeError, ValueError):
        id_envio = 0
    return render_template(
        "frm_config_mala_direta_disparo_apoio.html",
        id_envio=id_envio,
    )


@config_bp.get(f"{MALA_DIRETA_PREFIX}/destinatario/apoio")
@login_obrigatorio()
def mala_direta_destinatario_apoio_pagina():
    """Apoio nível 2 — linha do tempo de eventos do destinatário."""
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    try:
        id_destinatario = int(request.args.get("id_destinatario") or 0)
    except (TypeError, ValueError):
        id_destinatario = 0
    return render_template(
        "frm_config_mala_direta_evento_apoio.html",
        id_destinatario=id_destinatario,
    )


@config_bp.get(f"{MALA_DIRETA_PREFIX}/disparos/<int:id_envio>")
@login_obrigatorio()
def mala_direta_disparo_detalhe(id_envio: int):
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id_envio, assunto, corpo, tag_email, dt_envio, filtro_tipo,
                   total_destinatarios, tipo_disparo
            FROM tbl_email_envio WHERE id_envio = %s
            """,
            (id_envio,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Disparo não encontrado."), 404
        cur.execute(
            """
            SELECT id_destinatario, email, status_atual, dt_ultimo_evento,
                   id_tenant, nome_tenant, message_id
            FROM tbl_email_destinatario
            WHERE id_envio = %s
            ORDER BY nome_tenant NULLS LAST, email
            """,
            (id_envio,),
        )
        dests = []
        for d in cur.fetchall():
            dests.append(
                {
                    "id_destinatario": int(d[0]),
                    "email": d[1] or "",
                    "status": d[2] or "",
                    "dt_ultimo_evento": d[3].isoformat() if d[3] else None,
                    "id_tenant": int(d[4]) if d[4] else None,
                    "nome_tenant": d[5] or "",
                    "message_id": d[6] or "",
                }
            )
        return jsonify(
            success=True,
            disparo={
                "id_envio": int(row[0]),
                "assunto": row[1] or "",
                "corpo": row[2] or "",
                "tag": row[3] or "",
                "dt_envio": row[4].isoformat() if row[4] else None,
                "filtro_tipo": row[5] or "",
                "total": int(row[6] or 0),
                "tipo_disparo": row[7] or "",
                "destinatarios": dests,
            },
        )
    finally:
        conn.close()


@config_bp.get(f"{MALA_DIRETA_PREFIX}/destinatarios/<int:id_destinatario>/eventos")
@login_obrigatorio()
def mala_direta_destinatario_eventos(id_destinatario: int):
    """Timeline completa de eventos Brevo de um destinatário do disparo."""
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.id_destinatario, d.email, d.status_atual, d.dt_ultimo_evento,
                   d.nome_tenant, d.id_tenant, d.id_envio, e.assunto
            FROM tbl_email_destinatario d
            JOIN tbl_email_envio e ON e.id_envio = d.id_envio
            WHERE d.id_destinatario = %s
            """,
            (id_destinatario,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Destinatário não encontrado."), 404

        cur.execute(
            """
            SELECT id_evento, tipo_evento, data_evento, mensagem_erro
            FROM tbl_email_evento
            WHERE id_destinatario = %s
            ORDER BY data_evento ASC, id_evento ASC
            """,
            (id_destinatario,),
        )
        eventos = []
        for ev in cur.fetchall():
            eventos.append(
                {
                    "id_evento": int(ev[0]),
                    "tipo": ev[1] or "",
                    "data": ev[2].isoformat() if ev[2] else None,
                    "mensagem": ev[3] or "",
                }
            )
        return jsonify(
            success=True,
            destinatario={
                "id_destinatario": int(row[0]),
                "email": row[1] or "",
                "status_atual": row[2] or "",
                "dt_ultimo_evento": row[3].isoformat() if row[3] else None,
                "nome_tenant": row[4] or "",
                "id_tenant": int(row[5]) if row[5] else None,
                "id_envio": int(row[6]),
                "assunto": row[7] or "",
            },
            eventos=eventos,
        )
    finally:
        conn.close()


# --- Cupom de Desconto ---
CUPOM_PREFIX = "/configuracoes/cupons-desconto"


@config_bp.get(CUPOM_PREFIX)
@login_obrigatorio()
def cupons_desconto_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_cupons.html", nav_ativo="config")


@config_bp.get(f"{CUPOM_PREFIX}/incluir")
@login_obrigatorio()
def cupons_desconto_incluir():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_cupons_apoio.html")


@config_bp.get(f"{CUPOM_PREFIX}/editar")
@login_obrigatorio()
def cupons_desconto_editar():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_cupons_apoio.html")


@config_bp.post(f"{CUPOM_PREFIX}/apoio")
@login_obrigatorio()
def cupons_desconto_apoio():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        id_cupom = int(body.get("id") or 0)
    except (TypeError, ValueError):
        id_cupom = 0
    if id_cupom <= 0:
        return jsonify(success=False, message="ID inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cupom import (
            listar_planos_para_cupom,
            listar_tenants_para_cupom,
            obter_cupom_por_id,
            periodos_opcoes,
        )

        cupom = obter_cupom_por_id(cur, id_cupom)
        if not cupom:
            return jsonify(success=False, message="Cupom não encontrado."), 404
        return jsonify(
            success=True,
            dados=cupom,
            tenants=listar_tenants_para_cupom(cur),
            planos=listar_planos_para_cupom(cur),
            periodos=periodos_opcoes(),
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.get(f"{CUPOM_PREFIX}/combos")
@login_obrigatorio()
def cupons_desconto_combos():
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cupom import (
            listar_planos_para_cupom,
            listar_tenants_para_cupom,
            periodos_opcoes,
        )

        return jsonify(
            success=True,
            tenants=listar_tenants_para_cupom(cur),
            planos=listar_planos_para_cupom(cur),
            periodos=periodos_opcoes(),
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.get(f"{CUPOM_PREFIX}/combo-tenants")
@login_obrigatorio()
def cupons_desconto_combo_tenants():
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
        cur = conn.cursor()
        from sistema.financeiro.cupom import combobox_tenants_para_cupom

        return jsonify(
            sucesso=True,
            dados=combobox_tenants_para_cupom(cur, termo, limitar=limite),
        )
    except Exception as e:
        return jsonify(sucesso=False, mensagem=str(e)), 500
    finally:
        conn.close()


@config_bp.get(f"{CUPOM_PREFIX}/dados")
@login_obrigatorio()
def cupons_desconto_dados():
    if (r := _exigir_dev()) is not None:
        return r
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cupom import (
            listar_cupons,
            listar_planos_para_cupom,
            listar_tenants_para_cupom,
            periodos_opcoes,
        )

        return jsonify(
            success=True,
            cupons=listar_cupons(cur),
            periodos=periodos_opcoes(),
            tenants=listar_tenants_para_cupom(cur),
            planos=listar_planos_para_cupom(cur),
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.post(f"{CUPOM_PREFIX}/salvar")
@login_obrigatorio()
def cupons_desconto_salvar():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    id_cupom = body.get("id")
    try:
        id_cupom = int(id_cupom) if id_cupom not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        id_cupom = None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cupom import salvar_cupom

        cupom = salvar_cupom(cur, body, id_cupom=id_cupom)
        conn.commit()
        return jsonify(success=True, message="Cupom salvo.", cupom=cupom)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.post(f"{CUPOM_PREFIX}/excluir")
@login_obrigatorio()
def cupons_desconto_excluir():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        id_cupom = int(body.get("id") or 0)
    except (TypeError, ValueError):
        id_cupom = 0
    if not id_cupom:
        return jsonify(success=False, message="Cupom inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        # soft delete — desativa
        cur.execute(
            """
            UPDATE tbl_cupom_desconto
            SET ativo = FALSE, atualizado_em = NOW()
            WHERE id = %s
            RETURNING id
            """,
            (id_cupom,),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Cupom não encontrado."), 404
        conn.commit()
        return jsonify(success=True, message="Cupom desativado.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.get(f"{CUPOM_PREFIX}/usos")
@login_obrigatorio()
def cupons_desconto_usos():
    """Lista tenants que utilizaram o cupom."""
    if (r := _exigir_dev()) is not None:
        return r
    try:
        id_cupom = int(request.args.get("id") or 0)
    except (TypeError, ValueError):
        id_cupom = 0
    if id_cupom <= 0:
        return jsonify(success=False, message="Cupom inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cupom import listar_usos_cupom, obter_cupom_por_id

        cupom = obter_cupom_por_id(cur, id_cupom)
        if not cupom:
            return jsonify(success=False, message="Cupom não encontrado."), 404
        usos = listar_usos_cupom(cur, id_cupom)
        tenants_unicos = sorted(
            {
                int(u["id_tenant"])
                for u in usos
                if u.get("id_tenant")
            }
        )
        return jsonify(
            success=True,
            cupom={"id": cupom.get("id"), "codigo": cupom.get("codigo")},
            usos=usos,
            total_usos=len(usos),
            total_tenants=len(tenants_unicos),
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


# --- Assinaturas e faturamento (painel SaaS) ---
ASSINATURAS_PREFIX = "/configuracoes/assinaturas-faturamento"


@config_bp.get(ASSINATURAS_PREFIX)
@login_obrigatorio()
def assinaturas_faturamento_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_assinaturas.html", nav_ativo="config")


@config_bp.get(f"{ASSINATURAS_PREFIX}/dados")
@login_obrigatorio()
def assinaturas_faturamento_dados():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.financeiro.assinaturas_painel import painel_assinaturas

    try:
        ano = int(request.args.get("ano") or 0) or None
    except (TypeError, ValueError):
        ano = None
    try:
        mes = int(request.args.get("mes") or 0) or None
    except (TypeError, ValueError):
        mes = None

    conn = Var_ConectarBanco()
    try:
        painel = painel_assinaturas(conn, ano=ano, mes=mes)
        return jsonify(success=True, **painel)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


# --- HubSupport (Central de Chamados) ---
HS_PREFIX = "/configuracoes/hubsupport"


@config_bp.get(HS_PREFIX)
@login_obrigatorio()
def hubsupport_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_hubsupport.html", nav_ativo="config")


@config_bp.get(f"{HS_PREFIX}/dados")
@login_obrigatorio()
def hubsupport_dados():
    if (r := _exigir_dev()) is not None:
        return r
    from global_utils import obter_base_url
    from api.hubsupport.hubsupport_config import obter_painel_config

    conn = Var_ConectarBanco()
    try:
        painel = obter_painel_config(conn, obter_base_url())
        return jsonify(success=True, **painel)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.post(f"{HS_PREFIX}/salvar")
@login_obrigatorio()
def hubsupport_salvar():
    if (r := _exigir_dev()) is not None:
        return r
    from global_utils import obter_base_url
    from api.hubsupport.hubsupport_config import obter_painel_config, salvar_config_admin

    payload = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        salvar_config_admin(conn, payload)
        conn.commit()
        painel = obter_painel_config(conn, obter_base_url())
        return jsonify(success=True, message="Configuração HubSupport salva.", **painel)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.post(f"{HS_PREFIX}/testar")
@login_obrigatorio()
def hubsupport_testar():
    if (r := _exigir_dev()) is not None:
        return r
    from api.hubsupport.hubsupport_config import testar_conexao

    conn = Var_ConectarBanco()
    try:
        resultado = testar_conexao(conn)
        return jsonify(success=bool(resultado.get("ok")), **resultado)
    except Exception as e:
        return jsonify(success=False, ok=False, message=str(e)), 500
    finally:
        conn.close()


# --- gestao fornecedores ---


# ─── Tarefas secundárias ─────────────────────────────────────────────

@config_bp.get("/configuracoes/tarefas-secundarias")
@login_obrigatorio()
def tarefas_secundarias_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_tarefas_secundarias.html", nav_ativo="config")


@config_bp.get("/configuracoes/tarefas-secundarias/dados")
@login_obrigatorio()
def tarefas_secundarias_dados():
    if not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Sem permissão."), 403
    from sistema.tarefas_secundarias.servico import listar_tarefas_secundarias

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        itens = listar_tarefas_secundarias(cur)
        conn.commit()
        return jsonify(success=True, itens=itens)
    except Exception as e:
        conn.rollback()
        _log.exception("Erro ao listar tarefas secundárias")
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@config_bp.get("/configuracoes/tarefas-secundarias/<int:id_tarefa>/execucoes")
@login_obrigatorio()
def tarefas_secundarias_execucoes(id_tarefa: int):
    if not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Sem permissão."), 403
    from sistema.tarefas_secundarias.servico import listar_execucoes_tarefa

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        itens = listar_execucoes_tarefa(cur, id_tarefa, limit=25)
        return jsonify(success=True, itens=itens)
    except Exception as e:
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@config_bp.post("/configuracoes/tarefas-secundarias/<codigo>/executar")
@login_obrigatorio()
def tarefas_secundarias_executar(codigo: str):
    if not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Sem permissão."), 403
    from sistema.tarefas_secundarias.servico import disparar_tarefa_async

    try:
        res = disparar_tarefa_async(codigo, disparado_por="manual")
        return jsonify(success=True, **res)
    except Exception as e:
        return jsonify(success=False, message=str(e)[:300]), 400


@config_bp.post("/configuracoes/tarefas-secundarias/<codigo>/agenda")
@login_obrigatorio()
def tarefas_secundarias_salvar_agenda(codigo: str):
    if not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Sem permissão."), 403
    from sistema.tarefas_secundarias.servico import salvar_agenda_tarefa

    body = request.get_json(silent=True) or {}
    agendamento = (body.get("agendamento") or request.form.get("agendamento") or "").strip()
    hora_local = (body.get("hora_local") or request.form.get("hora_local") or "").strip()
    horas_raw = body.get("horas_local")
    if horas_raw is None and body.get("horas"):
        horas_raw = body.get("horas")
    if isinstance(horas_raw, str):
        horas_local = [p.strip() for p in horas_raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(horas_raw, (list, tuple)):
        horas_local = list(horas_raw)
    else:
        horas_local = None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        item = salvar_agenda_tarefa(
            cur,
            codigo,
            agendamento=agendamento,
            hora_local=hora_local or None,
            horas_local=horas_local,
        )
        conn.commit()
        return jsonify(success=True, item=item)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@config_bp.post("/api/tarefas-secundarias/job")
def tarefas_secundarias_job_cron():
    """Cron horário: cada tarefa roda no dia+hora configurados (janela de 60 min, America/Sao_Paulo)."""
    secret = (os.getenv("CRON_SECRET") or os.getenv("EFI_WEBHOOK_SECRET") or "").strip()
    token = (request.headers.get("X-Cron-Token") or request.args.get("token") or "").strip()
    if not secret or token != secret:
        return jsonify(success=False, message="Não autorizado."), 401
    from sistema.tarefas_secundarias.servico import (
        executar_tarefa,
        executar_tarefas_agendadas,
    )

    force = str(request.args.get("force") or "").lower() in ("1", "true", "sim")
    codigo = (request.args.get("codigo") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if codigo:
            res = executar_tarefa(
                cur,
                codigo,
                disparado_por="cron",
                forcar=force,
                conn=conn,
            )
        else:
            res = executar_tarefas_agendadas(
                cur,
                disparado_por="cron",
                forcar=force,
                conn=conn,
            )
        conn.commit()
        return jsonify(success=True, **res)
    except Exception as e:
        conn.rollback()
        _log.exception("Job tarefas secundárias falhou")
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


# --- Status de integração (padrão global) ---
ISP_PREFIX = "/configuracoes/integracao-status-padrao"


@config_bp.get(ISP_PREFIX)
@login_obrigatorio()
def integracao_status_padrao_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_status_padrao.html", nav_ativo="config")


@config_bp.get(f"{ISP_PREFIX}/incluir")
@login_obrigatorio()
def integracao_status_padrao_incluir():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_status_padrao_apoio.html")


@config_bp.get(f"{ISP_PREFIX}/editar")
@login_obrigatorio()
def integracao_status_padrao_editar():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_status_padrao_apoio.html")


@config_bp.get(f"{ISP_PREFIX}/dados")
@login_obrigatorio()
def integracao_status_padrao_dados():
    if (r := _exigir_dev()) is not None:
        return r
    aplicacao = (request.args.get("aplicacao") or "").strip().lower() or None
    contexto = (request.args.get("contexto") or "").strip().lower() or None
    apenas_ativos = request.args.get("todos") not in ("1", "true", "sim")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from core.integracoes.status_padrao import seed_padrao_se_vazio, _row_to_dict, _COLS

        seed_padrao_se_vazio(cur)
        clauses = ["1=1"]
        params: list = []
        if aplicacao:
            clauses.append("aplicacao = %s")
            params.append(aplicacao)
        if contexto:
            clauses.append("contexto = %s")
            params.append(contexto)
        if apenas_ativos:
            clauses.append("ativo = TRUE")
        cur.execute(
            f"""
            SELECT {_COLS}
            FROM tbl_integracao_status_padrao
            WHERE {' AND '.join(clauses)}
            ORDER BY aplicacao, contexto, ordem, id
            """,
            params,
        )
        linhas = [_row_to_dict(r) for r in cur.fetchall()]
        conn.commit()
        return jsonify(success=True, linhas=linhas)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.post(f"{ISP_PREFIX}/apoio")
@login_obrigatorio()
def integracao_status_padrao_apoio():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        sid = int(body.get("id") or 0)
    except (TypeError, ValueError):
        sid = 0
    if sid <= 0:
        return jsonify(success=False, message="ID inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from core.integracoes.status_padrao import obter_status_padrao

        dados = obter_status_padrao(cur, sid)
        if not dados:
            return jsonify(success=False, message="Registro não encontrado."), 404
        conn.commit()
        return jsonify(success=True, dados=dados)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.post(f"{ISP_PREFIX}/salvar")
@login_obrigatorio()
def integracao_status_padrao_salvar():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from core.integracoes.status_padrao import salvar_status_padrao

        new_id = salvar_status_padrao(cur, body)
        conn.commit()
        return jsonify(success=True, id=new_id, message="Salvo.")
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        msg = str(e)
        if "uq_isp" in msg.lower() or "unique" in msg.lower():
            return jsonify(
                success=False,
                message="Já existe mapeamento para esta aplicação/contexto/evento.",
            ), 409
        return jsonify(success=False, message=msg), 500
    finally:
        conn.close()


@config_bp.post(f"{ISP_PREFIX}/excluir")
@login_obrigatorio()
def integracao_status_padrao_excluir():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        sid = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="ID inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from core.integracoes.status_padrao import excluir_status_padrao

        excluir_status_padrao(cur, sid)
        conn.commit()
        return jsonify(success=True, message="Removido.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()




@config_bp.get(f"{MANUTENCAO_TENANT_PREFIX}/fundador")
@login_obrigatorio()
def manutencao_tenant_fundador_lista():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.planos.fornecedor_fundador import listar_fundadores, status_programa

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(
            success=True,
            status=status_programa(cur),
            itens=listar_fundadores(cur),
        )
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/fundador/toggle")
@login_obrigatorio()
def manutencao_tenant_fundador_toggle():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.planos.fornecedor_fundador import (
        atribuir_fundador,
        desativar_fundador,
        notificar_se_novo_fundador,
    )

    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Tenant inválido."), 400
    ativo = bool(body.get("ativo"))
    obs = (body.get("obs") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if ativo:
            res = atribuir_fundador(cur, id_tenant, forcar=True, obs=obs)
        else:
            res = desativar_fundador(cur, id_tenant, obs=obs)
        if not res.get("ok"):
            conn.rollback()
            return jsonify(success=False, message=res.get("message") or "Falha."), 400
        conn.commit()
        email_info = notificar_se_novo_fundador(cur, res) if ativo else None
        out = dict(success=True, **res)
        if email_info is not None:
            out["email"] = email_info
        return jsonify(out)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.get(f"{MANUTENCAO_TENANT_PREFIX}/fundador/candidatos")
@login_obrigatorio()
def manutencao_tenant_fundador_candidatos():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.planos.fornecedor_fundador import listar_candidatos_fundador

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(success=True, itens=listar_candidatos_fundador(cur))
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/fundador/migrar")
@login_obrigatorio()
def manutencao_tenant_fundador_migrar():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.planos.fornecedor_fundador import (
        atribuir_fundador,
        notificar_se_novo_fundador,
        status_programa,
    )

    body = request.get_json(silent=True) or {}
    try:
        id_tenant = int(body.get("id") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Fornecedor inválido."), 400
    if not id_tenant:
        return jsonify(success=False, message="Selecione um fornecedor."), 400
    obs = (body.get("obs") or "").strip() or "Migracao manual DEV"
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = atribuir_fundador(cur, id_tenant, forcar=True, obs=obs)
        if not res.get("ok"):
            conn.rollback()
            return jsonify(success=False, message=res.get("message") or "Falha."), 400
        conn.commit()
        email_info = notificar_se_novo_fundador(cur, res)
        out = dict(success=True, **res, status=status_programa(cur))
        if email_info is not None:
            out["email"] = email_info
        return jsonify(out)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@config_bp.post(f"{MANUTENCAO_TENANT_PREFIX}/fundador/testar-email")
@login_obrigatorio()
def manutencao_tenant_fundador_testar_email():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.planos.fornecedor_fundador import EMAIL_TESTE, enviar_convite_fundador_teste

    body = request.get_json(silent=True) or {}
    id_tenant = None
    try:
        raw = body.get("id")
        if raw not in (None, ""):
            id_tenant = int(raw)
    except (TypeError, ValueError):
        id_tenant = None

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = enviar_convite_fundador_teste(cur, id_tenant)
        if not res.get("ok"):
            return jsonify(success=False, message=res.get("message") or "Falha."), 500
        return jsonify(success=True, message=res.get("message"), email=EMAIL_TESTE)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()

STATUS_PEDIDO_PREFIX = "/configuracoes/status-pedido"


@config_bp.get(STATUS_PEDIDO_PREFIX)
@login_obrigatorio()
def status_pedido_pagina():
    if not session.get("eh_desenvolvedor"):
        return redirect(url_for("dashboard.index"))
    return render_template("frm_config_status_pedido.html", nav_ativo="config")


@config_bp.get(f"{STATUS_PEDIDO_PREFIX}/tenants")
@login_obrigatorio()
def status_pedido_tenants():
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.config.servico_status_pedido import listar_tenants_pedido

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(success=True, tenants=listar_tenants_pedido(cur, request.args.get("q") or ""))
    finally:
        conn.close()


@config_bp.get(f"{STATUS_PEDIDO_PREFIX}/pedidos")
@login_obrigatorio()
def status_pedido_lista():
    if (r := _exigir_dev()) is not None:
        return r
    try:
        id_vendedor = int(request.args.get("id_tenant") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Tenant inválido."), 400
    if id_vendedor <= 0:
        return jsonify(success=False, message="Selecione o tenant."), 400
    from sistema.config.servico_status_pedido import listar_pedidos_tenant

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(
            success=True,
            pedidos=listar_pedidos_tenant(cur, id_vendedor, request.args.get("q") or ""),
        )
    finally:
        conn.close()


@config_bp.get(f"{STATUS_PEDIDO_PREFIX}/pedido/<int:id_pedido>")
@login_obrigatorio()
def status_pedido_detalhe(id_pedido: int):
    if (r := _exigir_dev()) is not None:
        return r
    from sistema.config.servico_status_pedido import detalhe_pedido_status

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(success=True, pedido=detalhe_pedido_status(cur, id_pedido))
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@config_bp.post(f"{STATUS_PEDIDO_PREFIX}/aplicar")
@login_obrigatorio()
def status_pedido_aplicar():
    if (r := _exigir_dev()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    try:
        id_pedido = int(body.get("id_pedido") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Pedido inválido."), 400
    from sistema.config.servico_status_pedido import aplicar_status_pedido_dev

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = aplicar_status_pedido_dev(
            cur,
            id_pedido,
            (body.get("status") or "").strip(),
            id_usuario=session.get("id_usuario"),
            motivo=body.get("motivo") or "",
        )
        conn.commit()
        return jsonify(success=True, message="Status atualizado.", resultado=res)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        conn.rollback()
        _log.exception("Falha ao ajustar status do pedido %s", id_pedido)
        return jsonify(success=False, message="Erro interno ao alterar o status."), 500
    finally:
        conn.close()


def init_app(app):
    app.register_blueprint(config_bp)

    @app.context_processor
    def _inject_menu_sidebar():
        return obter_menu_sidebar_ctx()
