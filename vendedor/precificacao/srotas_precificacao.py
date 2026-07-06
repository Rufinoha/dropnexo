from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from srotas_plataforma import MODULO_VENDEDOR
from vendedor.precificacao.servico_precificacao_vendedor import (
    MODO_MARGEM_DROP,
    MODO_SUGESTAO_FORNECEDOR,
    aplicar_precificacao_tenant,
    buscar_regra_precificacao,
    listar_alertas,
)

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


def _regra_dict(row) -> dict:
    return {
        "id": row[0],
        "escopo": row[1],
        "id_segmento": row[2],
        "id_categoria": row[3],
        "pct_margem_lucro": float(row[4] or 0),
        "modo": row[5] or MODO_SUGESTAO_FORNECEDOR,
        "arredondamento_centavos": int(row[6]) if row[6] is not None else None,
        "margem_minima_alerta": float(row[7] if row[7] is not None else 30),
    }


def _parse_body_salvar(body: dict) -> tuple[dict | str, int]:
    escopo = (body.get("escopo") or "global").strip().lower()
    if escopo not in ("global", "segmento", "categoria"):
        return "Escopo inválido.", 400

    modo = (body.get("modo") or MODO_SUGESTAO_FORNECEDOR).strip().lower()
    if modo not in (MODO_SUGESTAO_FORNECEDOR, MODO_MARGEM_DROP):
        return "Modo de precificação inválido.", 400

    arred = body.get("arredondamento_centavos")
    if arred in ("", None, "null"):
        arredondamento = None
    else:
        try:
            arredondamento = int(arred)
        except (TypeError, ValueError):
            return "Arredondamento inválido.", 400
        if arredondamento not in (0, 90, 99):
            return "Arredondamento inválido.", 400

    try:
        pct_margem = float(body.get("pct_margem_lucro") or 0)
        margem_min = float(body.get("margem_minima_alerta") or 30)
    except (TypeError, ValueError):
        return "Percentuais inválidos.", 400

    id_seg = body.get("id_segmento")
    id_cat = body.get("id_categoria")

    return {
        "escopo": escopo,
        "modo": modo,
        "arredondamento_centavos": arredondamento,
        "pct_margem_lucro": pct_margem,
        "margem_minima_alerta": margem_min,
        "id_segmento": int(id_seg) if id_seg else None,
        "id_categoria": int(id_cat) if id_cat else None,
    }, 200


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
                   pct_margem_lucro, modo, arredondamento_centavos, margem_minima_alerta
            FROM tbl_vendedor_precificacao
            WHERE id_tenant_vendedor = %s AND ativo = TRUE
            ORDER BY escopo, id
            """,
            (id_v,),
        )
        regras = [_regra_dict(r) for r in cur.fetchall()]
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

        regra_global = buscar_regra_precificacao(cur, id_v, None, None)
        alertas = listar_alertas(cur, id_v, regra_global)

        return jsonify(
            success=True,
            regras=regras,
            segmentos=segmentos,
            alertas=alertas,
            defaults={
                "modo": MODO_SUGESTAO_FORNECEDOR,
                "pct_margem_lucro": 30,
                "margem_minima_alerta": 30,
                "arredondamento_centavos": None,
            },
        )
    finally:
        conn.close()


@vd_precificacao_bp.get("/vendedor/precificacao/alertas")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
def alertas():
    id_v = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        regra = buscar_regra_precificacao(cur, id_v, None, None)
        return jsonify(success=True, alertas=listar_alertas(cur, id_v, regra))
    finally:
        conn.close()


@vd_precificacao_bp.post("/vendedor/precificacao/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="precificacao.editar")
def salvar():
    id_v = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    parsed, status = _parse_body_salvar(body)
    if status != 200:
        return jsonify(success=False, message=parsed), status

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
                parsed["escopo"],
                parsed["id_segmento"],
                parsed["id_segmento"],
                parsed["id_categoria"],
                parsed["id_categoria"],
            ),
        )
        cur.execute(
            """
            INSERT INTO tbl_vendedor_precificacao
                (id_tenant_vendedor, escopo, id_segmento, id_categoria,
                 pct_marketplace, pct_impostos, pct_taxas, pct_margem_lucro,
                 modo, arredondamento_centavos, margem_minima_alerta)
            VALUES (%s, %s, %s, %s, 0, 0, 0, %s, %s, %s, %s)
            """,
            (
                id_v,
                parsed["escopo"],
                parsed["id_segmento"],
                parsed["id_categoria"],
                parsed["pct_margem_lucro"],
                parsed["modo"],
                parsed["arredondamento_centavos"],
                parsed["margem_minima_alerta"],
            ),
        )
        conn.commit()
        regra = buscar_regra_precificacao(cur, id_v, None, None)
        res_alertas = listar_alertas(cur, id_v, regra)
        return jsonify(
            success=True,
            message="Regra de precificação salva.",
            alertas=res_alertas,
        )
    finally:
        conn.close()


@vd_precificacao_bp.post("/vendedor/precificacao/aplicar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="precificacao.editar")
def aplicar():
    id_v = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    escopo = (body.get("escopo") or "global").strip().lower()
    id_seg = body.get("id_segmento")
    id_cat = body.get("id_categoria")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        n = aplicar_precificacao_tenant(
            cur,
            id_v,
            escopo,
            int(id_seg) if id_seg else None,
            int(id_cat) if id_cat else None,
        )
        conn.commit()
        regra = buscar_regra_precificacao(cur, id_v, None, None)
        return jsonify(
            success=True,
            message=f"{n} produto(s) atualizado(s) em Meus produtos.",
            atualizados=n,
            alertas=listar_alertas(cur, id_v, regra),
        )
    finally:
        conn.close()
