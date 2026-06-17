from __future__ import annotations

from flask import jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio, url_imagem_produto
from srotas_plataforma import MODULO_VENDEDOR
from srotas_negocio import buscar_regra_precificacao, calcular_preco_venda

from flask import Blueprint
from pathlib import Path

_MOD = Path(__file__).resolve().parent
vd_catalogo_bp = Blueprint(
    "vd_catalogo",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/catalogo",
)


def init_app(app):
    app.register_blueprint(vd_catalogo_bp)


@vd_catalogo_bp.get("/vendedor/catalogo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_catalogo.ver")
def pagina():
    return render_template("frm_vd_catalogo.html", nav_ativo="vd_catalogo")


@vd_catalogo_bp.get("/vendedor/catalogo/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_catalogo.ver")
def dados():
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403
    busca = (request.args.get("busca") or "").strip()
    id_forn = (request.args.get("id_fornecedor") or "").strip()
    id_seg = (request.args.get("id_segmento") or "").strip()
    em_estoque = (request.args.get("em_estoque") or "").strip() == "1"

    where = [
        "vinc.status = 'ativo'",
        "vinc.id_tenant_vendedor = %s",
        "p.publicado = TRUE",
        "p.ativo = TRUE",
        "var.ativo = TRUE",
    ]
    params: list = [id_vendedor]
    if id_forn:
        where.append("p.id_tenant = %s")
        params.append(int(id_forn))
    if id_seg:
        where.append("c.id_segmento = %s")
        params.append(int(id_seg))
    if busca:
        where.append("(p.nome ILIKE %s OR var.sku ILIKE %s)")
        like = f"%{busca}%"
        params.extend([like, like])
    if em_estoque:
        where.append("COALESCE(e.quantidade, 0) > 0")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT var.id, p.nome, var.nome_exibicao,
                   COALESCE(NULLIF(var.valor_drop, 0), NULLIF(p.valor_drop, 0), var.preco) AS preco_drop,
                   COALESCE(var.imagem_url, p.imagem_url), COALESCE(e.quantidade, 0),
                   t.nome, p.id, p.id_categoria, c.id_segmento,
                   pv.id AS id_pv
            FROM tbl_vinculo_vendedor_fornecedor vinc
            JOIN tbl_produto p ON p.id_tenant = vinc.id_tenant_fornecedor
            JOIN tbl_produto_variante var ON var.id_produto = p.id
            JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = var.id
            LEFT JOIN tbl_produto_vendedor pv
                ON pv.id_variante = var.id AND pv.id_tenant_vendedor = %s
            WHERE {' AND '.join(where)}
            ORDER BY t.nome, p.nome
            LIMIT 100
            """,
            [id_vendedor, id_vendedor] + params[1:],
        )
        itens = []
        for r in cur.fetchall():
            preco_forn = float(r[3] or 0)
            regra = buscar_regra_precificacao(cur, id_vendedor, r[9], r[8])
            preco_sug = calcular_preco_venda(preco_forn, regra) if regra else preco_forn
            itens.append(
                {
                    "id_variante": r[0],
                    "nome": f"{r[1]} — {r[2]}" if r[2] and r[2] != r[1] else r[1],
                    "preco_fornecedor": preco_forn,
                    "preco_sugerido": preco_sug,
                    "imagem_url": url_imagem_produto(r[4]),
                    "estoque": int(r[5] or 0),
                    "fornecedor_nome": r[6],
                    "id_produto": r[7],
                    "ativado": r[10] is not None,
                    "id_produto_vendedor": r[10],
                }
            )
        return jsonify(success=True, produtos=itens)
    finally:
        conn.close()


@vd_catalogo_bp.post("/vendedor/catalogo/ativar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_catalogo.editar")
def ativar():
    id_vendedor = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    try:
        id_variante = int(body.get("id_variante"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Produto inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT var.id, p.id, p.id_tenant,
                   COALESCE(NULLIF(var.valor_drop, 0), NULLIF(p.valor_drop, 0), var.preco) AS preco_drop,
                   c.id_segmento, p.id_categoria
            FROM tbl_produto_variante var
            JOIN tbl_produto p ON p.id = var.id_produto
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            JOIN tbl_vinculo_vendedor_fornecedor vinc
                ON vinc.id_tenant_fornecedor = p.id_tenant
               AND vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'
            WHERE var.id = %s AND p.publicado = TRUE AND var.ativo = TRUE
            """,
            (id_vendedor, id_variante),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Produto indisponível ou fornecedor não aprovado."), 404
        preco_forn = float(row[3] or 0)
        regra = buscar_regra_precificacao(cur, id_vendedor, row[4], row[5])
        preco_venda = calcular_preco_venda(preco_forn, regra) if regra else preco_forn
        cur.execute(
            """
            INSERT INTO tbl_produto_vendedor
                (id_tenant_vendedor, id_tenant_fornecedor, id_variante, id_produto,
                 preco_fornecedor, preco_venda, ativo, estoque_vitrine)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, 0)
            ON CONFLICT (id_tenant_vendedor, id_variante) DO UPDATE SET
                ativo = TRUE, preco_fornecedor = EXCLUDED.preco_fornecedor,
                preco_venda = CASE WHEN tbl_produto_vendedor.preco_manual THEN tbl_produto_vendedor.preco_venda
                              ELSE EXCLUDED.preco_venda END,
                atualizado_em = NOW()
            """,
            (id_vendedor, row[2], row[0], row[1], preco_forn, preco_venda),
        )
        conn.commit()
        return jsonify(success=True, message="Produto ativado em Meus vd_meus_produtos.", preco_venda=preco_venda)
    finally:
        conn.close()
