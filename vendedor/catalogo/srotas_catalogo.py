from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from fornecedor.catalogo.srotas_catalogo import _sanitizar_descricao_html
from fornecedor.parametros.servico_precificacao import (
    buscar_regra_fornecedor,
    calcular_preco_sugerido_revenda,
    pct_margem_revenda_efetiva,
)
from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio, url_imagem_produto
from srotas_plataforma import MODULO_VENDEDOR
from vendedor.fornecedores.srotas_fornecedores import (
    _agrupar_atributos_resumo,
    _ordem_atributos_produto,
    _parse_atributos_variante,
)

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


def _precificar_variante(cur, id_fornecedor: int, id_categoria: int | None, preco_drop: float) -> dict:
    regra_fn = buscar_regra_fornecedor(cur, id_fornecedor, id_categoria)
    pct = pct_margem_revenda_efetiva(regra_fn)
    preco_sug = calcular_preco_sugerido_revenda(preco_drop, pct)
    return {
        "preco_fornecedor": preco_drop,
        "preco_sugerido": preco_sug,
        "lucro_estimado": round(preco_sug - preco_drop, 2),
        "margem_revenda_pct": pct,
    }


def _where_catalogo(
    id_vendedor: int,
    busca: str,
    id_forn: str,
    id_seg: str,
    id_categoria: str,
    em_estoque: bool,
    conexao: str = "",
) -> tuple[list[str], list]:
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
    if id_categoria:
        where.append("p.id_categoria = %s")
        params.append(int(id_categoria))
    if busca:
        where.append("(p.nome ILIKE %s OR var.sku ILIKE %s OR t.nome ILIKE %s)")
        like = f"%{busca}%"
        params.extend([like, like, like])
    if em_estoque:
        where.append("COALESCE(e.quantidade, 0) > 0")
    conexao = (conexao or "").strip().lower()
    if conexao == "conectados":
        where.append(
            """(
            (SELECT COUNT(*) FROM tbl_produto_variante vx WHERE vx.id_produto = p.id AND vx.ativo = TRUE)
            =
            (SELECT COUNT(*) FROM tbl_produto_variante vx
             INNER JOIN tbl_produto_vendedor pvx ON pvx.id_variante = vx.id AND pvx.id_tenant_vendedor = %s
             WHERE vx.id_produto = p.id AND vx.ativo = TRUE)
            AND (SELECT COUNT(*) FROM tbl_produto_variante vx WHERE vx.id_produto = p.id AND vx.ativo = TRUE) > 0
            )"""
        )
        params.append(id_vendedor)
    elif conexao == "nao_conectados":
        where.append(
            """EXISTS (
            SELECT 1 FROM tbl_produto_variante vx
            WHERE vx.id_produto = p.id AND vx.ativo = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM tbl_produto_vendedor pvx
                WHERE pvx.id_variante = vx.id AND pvx.id_tenant_vendedor = %s
            )
            )"""
        )
        params.append(id_vendedor)
    return where, params


def _montar_produto_agrupado(cur, id_produto: int, base: dict, variantes: list[dict]) -> dict:
    ordem = _ordem_atributos_produto(cur, id_produto)
    atributos_resumo = _agrupar_atributos_resumo(variantes, ordem)
    tem_variacoes = (base.get("formato") or "S") == "E" or len(variantes) > 1
    drops = [float(v["preco_fornecedor"] or 0) for v in variantes]
    sugs = [float(v["preco_sugerido"] or 0) for v in variantes]
    preco_forn = min(drops) if drops else 0.0
    preco_sug_min = min(sugs) if sugs else 0.0
    preco_sug_max = max(sugs) if sugs else 0.0
    todos_ativados = all(v.get("ativado") for v in variantes)
    algum_ativado = any(v.get("ativado") for v in variantes)
    estoque_total = sum(int(v.get("estoque") or 0) for v in variantes)
    return {
        **base,
        "variantes": variantes,
        "atributos_resumo": atributos_resumo,
        "tem_variacoes": tem_variacoes,
        "preco_fornecedor": preco_forn,
        "preco_sugerido": preco_sug_min,
        "preco_sugerido_max": preco_sug_max,
        "lucro_estimado": round(preco_sug_min - preco_forn, 2),
        "estoque_total": estoque_total,
        "ativado": todos_ativados,
        "parcialmente_ativado": algum_ativado and not todos_ativados,
        "qtd_variantes": len(variantes),
    }


@vd_catalogo_bp.get("/vendedor/catalogo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_catalogo.ver")
def pagina():
    return render_template("frm_vd_catalogo.html", nav_ativo="vd_catalogo")


@vd_catalogo_bp.get("/vendedor/catalogo/combos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_catalogo.ver")
def combos():
    """Fornecedores conectados e categorias folha (vinculadas a produtos)."""
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403

    id_forn = (request.args.get("id_fornecedor") or "").strip()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.id, COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), t.nome),
                   (SELECT COUNT(DISTINCT p.id)::int
                    FROM tbl_produto p
                    WHERE p.id_tenant = t.id AND p.publicado = TRUE AND p.ativo = TRUE)
            FROM tbl_vinculo_vendedor_fornecedor vinc
            JOIN tbl_tenant t ON t.id = vinc.id_tenant_fornecedor
            WHERE vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'
            ORDER BY 2
            """,
            (id_vendedor,),
        )
        fornecedores = [
            {"id": r[0], "nome": r[1], "qtd_produtos": int(r[2] or 0)}
            for r in cur.fetchall()
        ]

        cat_params: list = [id_vendedor]
        cat_extra = ""
        if id_forn:
            cat_extra = " AND p.id_tenant = %s"
            cat_params.append(int(id_forn))

        cur.execute(
            f"""
            SELECT c.id, c.nome, COUNT(DISTINCT p.id)::int
            FROM tbl_produto p
            JOIN tbl_categoria c ON c.id = p.id_categoria
            JOIN tbl_vinculo_vendedor_fornecedor vinc
                ON vinc.id_tenant_fornecedor = p.id_tenant
               AND vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'
            WHERE p.publicado = TRUE AND p.ativo = TRUE AND p.id_categoria IS NOT NULL{cat_extra}
            GROUP BY c.id, c.nome
            HAVING COUNT(DISTINCT p.id) > 0
            ORDER BY c.nome
            """,
            cat_params,
        )
        categorias = [{"id": r[0], "nome": r[1], "qtd": int(r[2] or 0)} for r in cur.fetchall()]

        return jsonify(success=True, fornecedores=fornecedores, categorias=categorias)
    finally:
        conn.close()


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
    id_categoria = (request.args.get("id_categoria") or "").strip()
    em_estoque = (request.args.get("em_estoque") or "").strip() == "1"
    conexao = (request.args.get("conexao") or "").strip()

    where, params = _where_catalogo(
        id_vendedor, busca, id_forn, id_seg, id_categoria, em_estoque, conexao
    )

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT var.id, p.nome, var.nome_exibicao, var.sku, var.atributos,
                   COALESCE(NULLIF(var.valor_drop, 0), NULLIF(p.valor_drop, 0), var.preco) AS preco_drop,
                   COALESCE(var.imagem_url, p.imagem_url), COALESCE(e.quantidade, 0),
                   t.nome, p.id, p.id_categoria, c.id_segmento, p.id_tenant,
                   LEFT(COALESCE(p.descricao, ''), 280), p.formato, pv.id AS id_pv,
                   c.nome AS categoria_nome
            FROM tbl_vinculo_vendedor_fornecedor vinc
            JOIN tbl_produto p ON p.id_tenant = vinc.id_tenant_fornecedor
            JOIN tbl_produto_variante var ON var.id_produto = p.id
            JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = var.id
            LEFT JOIN tbl_produto_vendedor pv
                ON pv.id_variante = var.id AND pv.id_tenant_vendedor = %s
            WHERE {' AND '.join(where)}
            ORDER BY t.nome, p.nome, var.nome_exibicao NULLS LAST, var.id
            LIMIT 500
            """,
            [id_vendedor, id_vendedor] + params[1:],
        )

        por_produto: dict[int, dict] = {}
        variantes_por_produto: dict[int, list[dict]] = {}

        for r in cur.fetchall():
            id_produto = int(r[9])
            id_fornecedor = int(r[12])
            preco_drop = float(r[5] or 0)
            precos = _precificar_variante(cur, id_fornecedor, r[10], preco_drop)
            atributos = _parse_atributos_variante(r[4])
            rotulo_var = ", ".join(f"{k}: {v}" for k, v in atributos.items()) if atributos else (r[2] or "")

            if id_produto not in por_produto:
                por_produto[id_produto] = {
                    "id_produto": id_produto,
                    "id_fornecedor": id_fornecedor,
                    "nome": r[1],
                    "descricao": (r[13] or "").strip(),
                    "imagem_url": url_imagem_produto(r[6]),
                    "fornecedor_nome": r[8],
                    "formato": r[14] or "S",
                    "id_categoria": r[10],
                    "categoria_nome": r[16] or "",
                }
                variantes_por_produto[id_produto] = []

            variantes_por_produto[id_produto].append(
                {
                    "id_variante": r[0],
                    "sku": r[3] or "",
                    "nome_exibicao": r[2] or "",
                    "rotulo": rotulo_var or r[2] or "Único",
                    "atributos": atributos,
                    "imagem_url": url_imagem_produto(r[6]),
                    "estoque": int(r[7] or 0),
                    "ativado": r[15] is not None,
                    "id_produto_vendedor": r[15],
                    **precos,
                }
            )

        produtos = []
        for id_produto, base in por_produto.items():
            vars_p = variantes_por_produto.get(id_produto, [])
            if not vars_p:
                continue
            if not base.get("imagem_url"):
                for v in vars_p:
                    if v.get("imagem_url"):
                        base["imagem_url"] = v["imagem_url"]
                        break
            produtos.append(_montar_produto_agrupado(cur, id_produto, base, vars_p))

        return jsonify(success=True, produtos=produtos, total=len(produtos))
    finally:
        conn.close()


@vd_catalogo_bp.get("/vendedor/catalogo/produto/<int:id_produto>")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_catalogo.ver")
def produto_detalhe(id_produto: int):
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id, p.nome, p.descricao, p.formato, p.imagem_url, p.id_categoria,
                   p.id_tenant, t.nome, c.nome
            FROM tbl_produto p
            JOIN tbl_tenant t ON t.id = p.id_tenant
            JOIN tbl_vinculo_vendedor_fornecedor vinc
                ON vinc.id_tenant_fornecedor = p.id_tenant
               AND vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            WHERE p.id = %s AND p.publicado = TRUE AND p.ativo = TRUE
            """,
            (id_vendedor, id_produto),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Produto não encontrado ou fornecedor não aprovado."), 404

        cur.execute(
            """
            SELECT var.id, var.sku, var.nome_exibicao, var.atributos,
                   COALESCE(NULLIF(var.valor_drop, 0), NULLIF(p.valor_drop, 0), var.preco) AS preco_drop,
                   COALESCE(var.imagem_url, p.imagem_url), COALESCE(e.quantidade, 0), pv.id
            FROM tbl_produto_variante var
            JOIN tbl_produto p ON p.id = var.id_produto
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = var.id
            LEFT JOIN tbl_produto_vendedor pv
                ON pv.id_variante = var.id AND pv.id_tenant_vendedor = %s
            WHERE p.id = %s AND var.ativo = TRUE
            ORDER BY var.nome_exibicao NULLS LAST, var.id
            """,
            (id_vendedor, id_produto),
        )
        variantes = []
        for vr in cur.fetchall():
            preco_drop = float(vr[4] or 0)
            precos = _precificar_variante(cur, int(row[6]), row[5], preco_drop)
            atributos = _parse_atributos_variante(vr[3])
            rotulo = ", ".join(f"{k}: {v}" for k, v in atributos.items()) if atributos else (vr[2] or "Único")
            variantes.append(
                {
                    "id_variante": vr[0],
                    "sku": vr[1] or "",
                    "nome_exibicao": vr[2] or "",
                    "rotulo": rotulo,
                    "atributos": atributos,
                    "imagem_url": url_imagem_produto(vr[5]),
                    "estoque": int(vr[6] or 0),
                    "ativado": vr[7] is not None,
                    **precos,
                }
            )

        base = {
            "id_produto": row[0],
            "nome": row[1],
            "descricao": row[2] or "",
            "descricao_html": _sanitizar_descricao_html(row[2] or ""),
            "formato": row[3] or "S",
            "imagem_url": url_imagem_produto(row[4]),
            "id_fornecedor": row[6],
            "fornecedor_nome": row[7],
            "categoria": row[8] or "",
            "id_categoria": row[5],
        }
        produto = _montar_produto_agrupado(cur, id_produto, base, variantes)
        return jsonify(success=True, produto=produto)
    finally:
        conn.close()


@vd_catalogo_bp.post("/vendedor/catalogo/ativar-produto")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_catalogo.editar")
def ativar_produto():
    """Integra o produto pai e todas as variações ativas (sem ativação parcial)."""
    id_vendedor = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    try:
        id_produto = int(body.get("id_produto"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Produto inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT v.id, p.id, p.id_tenant,
                   COALESCE(NULLIF(v.valor_drop, 0), NULLIF(p.valor_drop, 0), v.preco) AS preco_drop,
                   p.id_categoria
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            JOIN tbl_vinculo_vendedor_fornecedor vinc
                ON vinc.id_tenant_fornecedor = p.id_tenant
               AND vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'
            WHERE p.id = %s AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
            """,
            (id_vendedor, id_produto),
        )
        rows = cur.fetchall()
        if not rows:
            return jsonify(success=False, message="Produto indisponível ou fornecedor não aprovado."), 404

        ativados = 0
        for row in rows:
            preco_forn = float(row[3] or 0)
            precos = _precificar_variante(cur, int(row[2]), row[4], preco_forn)
            preco_venda = precos["preco_sugerido"]
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
            ativados += 1
        conn.commit()
        msg = (
            f"Produto integrado com {ativados} variação(ões) em Meus produtos."
            if ativados > 1
            else "Produto integrado em Meus produtos."
        )
        return jsonify(success=True, message=msg, ativados=ativados)
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
                   p.id_categoria
            FROM tbl_produto_variante var
            JOIN tbl_produto p ON p.id = var.id_produto
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
        precos = _precificar_variante(cur, int(row[2]), row[4], preco_forn)
        preco_venda = precos["preco_sugerido"]
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
        return jsonify(success=True, message="Produto ativado em Meus produtos.", preco_venda=preco_venda)
    finally:
        conn.close()
