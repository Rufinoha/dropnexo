from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from global_utils import (
    Var_ConectarBanco,
    exigir_permissao,
    login_obrigatorio,
    usuario_tem_permissao,
)
from srotas_negocio import url_icone_integracao
from srotas_plataforma import (
    carregar_usuario_apoio,
    inativar_usuario_tenant,
    listar_perfis_combo,
    listar_usuarios_tenant,
    normalizar_bool,
    reenviar_convite_usuario,
    salvar_usuario_tenant,
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
        where.append("m.id_modulo = %s")
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
                   parent_id, status, obs, pai, id_modulo, nav_codigo
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
        )
    finally:
        conn.close()


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

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
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
            b.get("id_modulo"),
            (b.get("nav_codigo") or "").strip() or None,
        )
        if _id:
            cur.execute(
                """
                UPDATE tbl_menu SET nome_menu=%s, descricao=%s, data_page=%s, icone=%s,
                    tipo_abrir=%s, ordem=%s, parent_id=%s, status=%s, obs=%s, pai=%s,
                    id_modulo=%s, nav_codigo=%s
                WHERE id=%s
                """,
                campos + (_id,),
            )
            novo_id = _id
        else:
            cur.execute(
                """
                INSERT INTO tbl_menu (nome_menu, descricao, data_page, icone, tipo_abrir,
                    ordem, parent_id, status, obs, pai, id_modulo, nav_codigo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
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
        cur.execute("SELECT id, modulo FROM tbl_menu_modulo WHERE ativo = TRUE ORDER BY ordem, modulo")
        modulos = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(
            menus_pai=menus_pai,
            pais=pais,
            modulos=modulos,
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
    "plug": '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2"/>',
}


def _icone_svg_menu(nome: str | None) -> str:
    key = (nome or "layout-dashboard").strip().lower()
    return _ICONES_SVG.get(key, _ICONES_SVG["layout-dashboard"])


def carregar_menu_sidebar() -> list[dict]:
    from srotas_plataforma import garantir_modulo_sessao, resolver_url_menu

    if not session.get("id_usuario"):
        return []

    id_perfil = session.get("id_perfil")
    if not id_perfil and not session.get("eh_desenvolvedor"):
        return []

    mod_ativo = garantir_modulo_sessao()
    ctx_filtro = ["comum", mod_ativo]
    perfil_codigo = (session.get("perfil_codigo") or session.get("papel") or "").lower()
    acesso_total_menu = bool(session.get("eh_desenvolvedor")) or perfil_codigo in ("dono", "admin")

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()

        if acesso_total_menu:
            cur.execute(
                """
                SELECT m.id, m.nome_menu, m.data_page, m.icone, m.nav_codigo, m.parent_id, m.pai
                FROM tbl_menu m
                WHERE m.status = TRUE AND m.pai = TRUE AND m.parent_id IS NULL
                  AND COALESCE(m.contexto_modulo, 'comum') = ANY(%s)
                ORDER BY m.ordem NULLS LAST, m.nome_menu
                """,
                (list(ctx_filtro),),
            )
        else:
            cur.execute(
                """
                SELECT m.id, m.nome_menu, m.data_page, m.icone, m.nav_codigo, m.parent_id, m.pai
                FROM tbl_menu m
                JOIN tbl_perfil_menu pm ON pm.id_menu = m.id AND pm.exibir = TRUE
                WHERE pm.id_perfil = %s AND m.status = TRUE
                  AND m.pai = TRUE AND m.parent_id IS NULL
                  AND COALESCE(m.contexto_modulo, 'comum') = ANY(%s)
                ORDER BY m.ordem NULLS LAST, m.nome_menu
                """,
                (id_perfil, list(ctx_filtro)),
            )

        itens = []
        for row in cur.fetchall():
            mid, nome, data_page, icone, nav_codigo, parent_id, pai = row
            itens.append(
                {
                    "id": mid,
                    "nome": nome,
                    "url": resolver_url_menu(data_page),
                    "icone_svg": _icone_svg_menu(icone),
                    "nav_codigo": nav_codigo or "",
                    "parent_id": parent_id,
                    "pai": pai,
                }
            )
        return itens
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
    from srotas_plataforma import MODULO_FORNECEDOR, resolver_url_menu

    comum = [
        {"nome": "Dashboard", "url": url_for("dashboard.index"), "icone_svg": _ICONES_SVG["layout-dashboard"], "nav_codigo": "inicio"},
    ]
    if mod_ativo == MODULO_FORNECEDOR:
        return [
            {"nome": "Catálogo", "url": url_for("fn_catalogo.pagina"), "icone_svg": _ICONES_SVG["package"], "nav_codigo": "catalogos"},
        ]
    return comum + [
        {"nome": "Fornecedores", "url": url_for("vd_fornecedores.pagina"), "icone_svg": _ICONES_SVG["users"], "nav_codigo": "fornecedores"},
        {"nome": "Meus produtos", "url": url_for("vd_meus_produtos.pagina"), "icone_svg": _ICONES_SVG["shopping-bag"], "nav_codigo": "produtos"},
    ]


def obter_menu_sidebar_ctx() -> dict:
    from srotas_plataforma import ctx_navegacao

    base = ctx_navegacao()
    base["menu_sidebar"] = carregar_menu_sidebar() if session.get("id_usuario") else []
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
    from sistema.marktplace.servico_marktplace import SQL_LISTA, produto_dict

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

    from sistema.marktplace.servico_marktplace import produto_dict

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


# --- gestao fornecedores ---


def init_app(app):
    app.register_blueprint(config_bp)

    @app.context_processor
    def _inject_menu_sidebar():
        return obter_menu_sidebar_ctx()
