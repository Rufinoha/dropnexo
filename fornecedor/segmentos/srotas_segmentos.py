from __future__ import annotations

import json
import re

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from srotas_plataforma import MODULO_FORNECEDOR
from srotas_negocio import inativar_vinculo


_MOD = Path(__file__).resolve().parent

fn_segmentos_bp = Blueprint(
    "fn_segmentos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/segmentos",
)


def init_app(app):
    app.register_blueprint(fn_segmentos_bp)

def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_fornecedor_tenant():
    if session.get("tenant_tipo_negocio") in ("fornecedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é fornecedor."), 403

def _stats_categorias_segmento(cur, id_tenant: int, id_segmento: int) -> tuple[list[dict], int, int]:
    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_categoria
        WHERE id_tenant = %s AND id_segmento = %s AND ativo = TRUE
        """,
        (id_tenant, id_segmento),
    )
    qtd_total = int(cur.fetchone()[0] or 0)
    cur.execute(
        """
        SELECT c.id, c.nome,
               (SELECT COUNT(*)::int FROM tbl_produto p
                WHERE p.id_categoria = c.id AND p.id_tenant = %s AND p.ativo = TRUE)
        FROM tbl_categoria c
        WHERE c.id_tenant = %s AND c.id_segmento = %s AND c.ativo = TRUE
          AND COALESCE(c.nivel, 1) = 1
        ORDER BY c.ordem, c.nome
        """,
        (id_tenant, id_tenant, id_segmento),
    )
    cats = []
    for cid, cnome, qtd in cur.fetchall():
        cats.append({"id": cid, "nome": cnome, "qtd_produtos": int(qtd or 0)})
    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_produto p
        JOIN tbl_categoria c ON c.id = p.id_categoria
        WHERE p.id_tenant = %s AND c.id_segmento = %s AND p.ativo = TRUE
        """,
        (id_tenant, id_segmento),
    )
    total_prod = int(cur.fetchone()[0] or 0)
    return cats, qtd_total, total_prod

@fn_segmentos_bp.get("/fornecedor/segmentos")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_segmentos.ver")
def segmentos():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_segmentos.html", nav_ativo="fn_segmentos")



@fn_segmentos_bp.get("/fornecedor/segmentos/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
def segmentos_dados():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.id, s.nome, s.slug, s.descricao,
                   EXISTS (
                       SELECT 1 FROM tbl_fornecedor_segmento fs
                       WHERE fs.id_tenant = %s AND fs.id_segmento = s.id
                   )
            FROM tbl_segmento s
            WHERE s.id_tenant IS NULL AND s.ativo = TRUE
            ORDER BY s.ordem, s.nome
            """,
            (id_tenant,),
        )
        disponiveis = []
        ativos = []
        for row in cur.fetchall():
            sid, nome, slug, desc, selecionado = row
            item = {
                "id": sid,
                "nome": nome,
                "slug": slug or "",
                "descricao": desc or "",
                "selecionado": bool(selecionado),
            }
            disponiveis.append(item)
            if selecionado:
                cats, qtd_cat, total_prod = _stats_categorias_segmento(cur, id_tenant, sid)
                ativos.append(
                    {
                        **item,
                        "qtd_categorias": qtd_cat,
                        "qtd_produtos": total_prod,
                        "categorias": cats,
                    }
                )
        return jsonify(success=True, disponiveis=disponiveis, ativos=ativos)
    finally:
        conn.close()



@fn_segmentos_bp.post("/fornecedor/segmentos/toggle")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_segmentos.editar")
def segmentos_toggle():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        id_segmento = int(body.get("id_segmento"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Segmento inválido."), 400
    ativo = bool(body.get("ativo", True))

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tbl_segmento WHERE id = %s AND id_tenant IS NULL AND ativo = TRUE",
            (id_segmento,),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Segmento não disponível na plataforma."), 404

        if ativo:
            cur.execute(
                """
                INSERT INTO tbl_fornecedor_segmento (id_tenant, id_segmento)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (id_tenant, id_segmento),
            )
        else:
            cur.execute(
                "DELETE FROM tbl_fornecedor_segmento WHERE id_tenant = %s AND id_segmento = %s",
                (id_tenant, id_segmento),
            )
        conn.commit()
        return jsonify(success=True, message="Segmento atualizado.")
    finally:
        conn.close()

