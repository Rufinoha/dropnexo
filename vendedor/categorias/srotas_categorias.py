from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from srotas_negocio import MAX_NIVEL_CATEGORIA, flatten_arvore_com_caminho, montar_arvore_categorias
from srotas_plataforma import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent

vd_categorias_bp = Blueprint(
    "vd_categorias",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/categorias",
)


def init_app(app):
    app.register_blueprint(vd_categorias_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_vendedor_tenant():
    if session.get("tenant_tipo_negocio") in ("vendedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é vendedor."), 403


@vd_categorias_bp.get("/vendedor/categorias")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_categorias.ver")
def categorias():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    return render_template("frm_vd_categorias.html", nav_ativo="vd_categorias")


@vd_categorias_bp.get("/vendedor/categorias/arvore")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_categorias.ver")
def arvore():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.nome, c.parent_id, c.ordem, c.nivel,
                   (SELECT COUNT(*)::int FROM tbl_produto p
                    WHERE p.id_categoria = c.id AND p.id_tenant = %s AND p.ativo = TRUE)
            FROM tbl_categoria c
            WHERE c.id_tenant = %s AND c.ativo = TRUE
            ORDER BY c.ordem, c.nome
            """,
            (id_tenant, id_tenant),
        )
        rows = cur.fetchall()
        arvore_data = montar_arvore_categorias(rows)
        flat = flatten_arvore_com_caminho(arvore_data)
        return jsonify(success=True, arvore=arvore_data, opcoes=flat, total_categorias=len(rows))
    finally:
        conn.close()


@vd_categorias_bp.post("/vendedor/categorias/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_categorias.editar")
def salvar():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome da categoria."), 400

    parent_id = body.get("parent_id")
    parent_id = int(parent_id) if parent_id not in (None, "", 0) else None

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if parent_id:
            cur.execute(
                "SELECT nivel FROM tbl_categoria WHERE id = %s AND id_tenant = %s",
                (parent_id, id_tenant),
            )
            pai = cur.fetchone()
            if not pai:
                return jsonify(success=False, message="Categoria pai não encontrada."), 404
            nivel = int(pai[0]) + 1
        else:
            nivel = 1

        if nivel > MAX_NIVEL_CATEGORIA:
            return jsonify(
                success=False,
                message=f"Máximo de {MAX_NIVEL_CATEGORIA} níveis.",
            ), 400

        cat_id = body.get("id")
        ordem = int(body.get("ordem") or 0)
        if cat_id:
            cur.execute(
                """
                UPDATE tbl_categoria SET nome=%s, ordem=%s, parent_id=%s, nivel=%s
                WHERE id=%s AND id_tenant=%s
                """,
                (nome, ordem, parent_id, nivel, int(cat_id), id_tenant),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_categoria (id_tenant, id_segmento, parent_id, nome, ordem, nivel, ativo)
                VALUES (%s, NULL, %s, %s, %s, %s, TRUE)
                RETURNING id
                """,
                (id_tenant, parent_id, nome, ordem, nivel),
            )
        conn.commit()
        return jsonify(success=True, message="Categoria salva.")
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            return jsonify(success=False, message="Já existe categoria com este nome no mesmo nível."), 409
        raise
    finally:
        conn.close()


@vd_categorias_bp.post("/vendedor/categorias/excluir")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_categorias.editar")
def excluir():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        cat_id = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Categoria inválida."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tbl_categoria WHERE parent_id = %s AND ativo = TRUE",
            (cat_id,),
        )
        if int(cur.fetchone()[0] or 0) > 0:
            return jsonify(success=False, message="Remova ou mova as subcategorias antes."), 409
        cur.execute(
            "SELECT COUNT(*) FROM tbl_produto WHERE id_categoria = %s AND id_tenant = %s",
            (cat_id, id_tenant),
        )
        if int(cur.fetchone()[0] or 0) > 0:
            return jsonify(success=False, message="Há produtos nesta categoria."), 409
        cur.execute(
            "DELETE FROM tbl_categoria WHERE id = %s AND id_tenant = %s",
            (cat_id, id_tenant),
        )
        conn.commit()
        return jsonify(success=True, message="Categoria removida.")
    finally:
        conn.close()
