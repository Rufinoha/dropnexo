from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from srotas_plataforma import MODULO_VENDEDOR
from srotas_negocio import aplicar_precificacao_tenant

_MOD = Path(__file__).resolve().parent
vd_precificacao_bp = Blueprint(
    "vd_precificacao",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/precificacao",
)


def init_app(app):
    app.register_blueprint(vd_precificacao_bp)


@vd_precificacao_bp.get("/vendedor/precificacao")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="precificacao.ver")
def pagina():
    return render_template("frm_vd_precificacao.html", nav_ativo="vd_precificacao")


@vd_precificacao_bp.get("/vendedor/precificacao/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
def dados():
    id_v = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, escopo, id_segmento, id_categoria,
                   pct_marketplace, pct_impostos, pct_taxas, pct_margem_lucro
            FROM tbl_vendedor_precificacao
            WHERE id_tenant_vendedor = %s AND ativo = TRUE
            ORDER BY escopo, id
            """,
            (id_v,),
        )
        regras = [
            {
                "id": r[0],
                "escopo": r[1],
                "id_segmento": r[2],
                "id_categoria": r[3],
                "pct_marketplace": float(r[4] or 0),
                "pct_impostos": float(r[5] or 0),
                "pct_taxas": float(r[6] or 0),
                "pct_margem_lucro": float(r[7] or 0),
            }
            for r in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT DISTINCT s.id, s.nome
            FROM tbl_vinculo_vendedor_fornecedor v
            JOIN tbl_fornecedor_segmento fs ON fs.id_tenant = v.id_tenant_fornecedor
            JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
            WHERE v.id_tenant_vendedor = %s AND v.status = 'ativo'
            ORDER BY s.nome
            """,
            (id_v,),
        )
        segmentos = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(success=True, regras=regras, segmentos=segmentos)
    finally:
        conn.close()


@vd_precificacao_bp.post("/vendedor/precificacao/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="precificacao.editar")
def salvar():
    id_v = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    escopo = (body.get("escopo") or "global").strip().lower()
    if escopo not in ("global", "segmento", "categoria"):
        return jsonify(success=False, message="Escopo inválido."), 400

    def pct(k):
        try:
            return float(body.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0

    id_seg = body.get("id_segmento")
    id_cat = body.get("id_categoria")
    aplicar = bool(body.get("aplicar_agora", True))

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_vendedor_precificacao SET ativo = FALSE
            WHERE id_tenant_vendedor = %s AND escopo = %s
              AND (%s IS NULL OR id_segmento IS NOT DISTINCT FROM %s)
              AND (%s IS NULL OR id_categoria IS NOT DISTINCT FROM %s)
            """,
            (
                id_v,
                escopo,
                int(id_seg) if id_seg else None,
                int(id_seg) if id_seg else None,
                int(id_cat) if id_cat else None,
                int(id_cat) if id_cat else None,
            ),
        )
        cur.execute(
            """
            INSERT INTO tbl_vendedor_precificacao
                (id_tenant_vendedor, escopo, id_segmento, id_categoria,
                 pct_marketplace, pct_impostos, pct_taxas, pct_margem_lucro)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                id_v,
                escopo,
                int(id_seg) if id_seg else None,
                int(id_cat) if id_cat else None,
                pct("pct_marketplace"),
                pct("pct_impostos"),
                pct("pct_taxas"),
                pct("pct_margem_lucro"),
            ),
        )
        n = 0
        if aplicar:
            n = aplicar_precificacao_tenant(
                cur,
                id_v,
                escopo,
                int(id_seg) if id_seg else None,
                int(id_cat) if id_cat else None,
            )
        conn.commit()
        return jsonify(
            success=True,
            message=f"Regra salva. {n} produto(s) atualizado(s) em Meus vd_meus_produtos.",
        )
    finally:
        conn.close()
