from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session, url_for
from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from srotas_negocio import MAX_NIVEL_CATEGORIA, flatten_arvore_com_caminho, montar_arvore_categorias
from srotas_plataforma import MODULO_FORNECEDOR


_MOD = Path(__file__).resolve().parent

fn_categorias_bp = Blueprint(
    "fn_categorias",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/categorias",
)


def init_app(app):
    app.register_blueprint(fn_categorias_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_fornecedor_tenant():
    if session.get("tenant_tipo_negocio") in ("fornecedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é fornecedor."), 403


def _segmento_ativo(cur, id_tenant: int, id_segmento: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_fornecedor_segmento fs
        JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
        WHERE fs.id_tenant = %s AND fs.id_segmento = %s
        """,
        (id_tenant, id_segmento),
    )
    return cur.fetchone() is not None


def _nivel_pai(cur, parent_id: int | None) -> int:
    if not parent_id:
        return 0
    cur.execute("SELECT nivel FROM tbl_categoria WHERE id = %s", (parent_id,))
    row = cur.fetchone()
    return int(row[0]) if row else 0



@fn_categorias_bp.get("/fornecedor/categorias")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_categorias.ver")
def categorias():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_seg = (request.args.get("segmento") or "").strip()
    return render_template(
        "frm_fn_categorias.html",
        nav_ativo="fn_categorias",
        id_segmento_inicial=id_seg,
        url_segmentos=url_for("fn_segmentos.segmentos"),
    )

@fn_categorias_bp.get("/fornecedor/categorias/segmentos")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
def segmentos_ativos():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.id, s.nome, s.slug
            FROM tbl_fornecedor_segmento fs
            JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
            WHERE fs.id_tenant = %s
            ORDER BY s.ordem, s.nome
            """,
            (id_tenant,),
        )
        lista = [{"id": r[0], "nome": r[1], "slug": r[2] or ""} for r in cur.fetchall()]
        return jsonify(success=True, segmentos=lista)
    finally:
        conn.close()

@fn_categorias_bp.get("/fornecedor/categorias/arvore")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
def arvore():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    try:
        id_segmento = int(request.args.get("id_segmento"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Informe o segmento."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not _segmento_ativo(cur, id_tenant, id_segmento):
            return jsonify(success=False, message="Segmento não está ativo para sua conta."), 403

        cur.execute(
            """
            SELECT c.id, c.nome, c.parent_id, c.ordem, c.nivel,
                   (SELECT COUNT(*)::int FROM tbl_produto p
                    WHERE p.id_categoria = c.id AND p.id_tenant = %s AND p.ativo = TRUE)
            FROM tbl_categoria c
            WHERE c.id_tenant = %s AND c.id_segmento = %s AND c.ativo = TRUE
            ORDER BY c.ordem, c.nome
            """,
            (id_tenant, id_tenant, id_segmento),
        )
        rows = cur.fetchall()
        arvore_data = montar_arvore_categorias(rows)
        flat = flatten_arvore_com_caminho(arvore_data)
        return jsonify(
            success=True,
            arvore=arvore_data,
            opcoes=flat,
            total_categorias=len(rows),
        )
    finally:
        conn.close()

@fn_categorias_bp.post("/fornecedor/categorias/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_categorias.editar")
def salvar():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome da categoria."), 400
    try:
        id_segmento = int(body.get("id_segmento"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Segmento inválido."), 400

    parent_id = body.get("parent_id")
    parent_id = int(parent_id) if parent_id not in (None, "", 0) else None

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not _segmento_ativo(cur, id_tenant, id_segmento):
            return jsonify(success=False, message="Ative o segmento em Segmentos antes."), 403

        if parent_id:
            cur.execute(
                """
                SELECT id_segmento, nivel FROM tbl_categoria
                WHERE id = %s AND id_tenant = %s
                """,
                (parent_id, id_tenant),
            )
            pai = cur.fetchone()
            if not pai:
                return jsonify(success=False, message="Categoria pai não encontrada."), 404
            if int(pai[0]) != id_segmento:
                return jsonify(success=False, message="A categoria pai deve ser do mesmo segmento."), 400
            nivel = int(pai[1]) + 1
        else:
            nivel = 1

        if nivel > MAX_NIVEL_CATEGORIA:
            return jsonify(
                success=False,
                message=f"Máximo de {MAX_NIVEL_CATEGORIA} níveis (ex.: Segmento → N1 → N2 → N3).",
            ),
            400

        cat_id = body.get("id")
        ordem = int(body.get("ordem") or 0)
        if cat_id:
            cur.execute(
                """
                UPDATE tbl_categoria SET nome=%s, ordem=%s
                WHERE id=%s AND id_tenant=%s AND id_segmento=%s
                """,
                (nome, ordem, int(cat_id), id_tenant, id_segmento),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_categoria (id_tenant, id_segmento, parent_id, nome, ordem, nivel, ativo)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id
                """,
                (id_tenant, id_segmento, parent_id, nome, ordem, nivel),
            )
        conn.commit()
        return jsonify(success=True, message="Categoria salva.")
    except Exception as e:
        conn.rollback()
        if "uq_categoria" in str(e).lower() or "unique" in str(e).lower():
            return jsonify(
                success=False,
                message="Já existe categoria com este nome no mesmo nível.",
            ),
            409
        raise
    finally:
        conn.close()

@fn_categorias_bp.post("/fornecedor/categorias/excluir")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_categorias.editar")
def excluir():
    if (r := _exigir_fornecedor_tenant()) is not None:
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
