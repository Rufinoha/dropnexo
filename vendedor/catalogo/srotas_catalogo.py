from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from fornecedor.catalogo.srotas_catalogo import _sanitizar_descricao_html
from fornecedor.parametros.precificacao import (
    buscar_regra_fornecedor,
    calcular_preco_sugerido_revenda,
    pct_margem_revenda_efetiva,
)
from vendedor.precificacao.srotas_precificacao import precificar_na_integracao
from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio, url_imagem_produto
from sistema.plataforma.sessao import MODULO_VENDEDOR
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


def _descendentes_categoria(rows: list[tuple], raiz_id: int) -> list[int]:
    """ids da categoria e de todos os filhos (rows: id, parent_id)."""
    filhos: dict[int | None, list[int]] = {}
    for cid, pid in rows:
        filhos.setdefault(pid, []).append(int(cid))
    out: set[int] = {int(raiz_id)}
    pilha = [int(raiz_id)]
    while pilha:
        atual = pilha.pop()
        for ch in filhos.get(atual, []):
            if ch not in out:
                out.add(ch)
                pilha.append(ch)
    return list(out)


def _ids_categoria_filtro(cur, id_categoria: str) -> tuple[bool, list[int]]:
    """Retorna (sem_categoria, ids) para filtro no catálogo."""
    if id_categoria.strip().lower() == "sem":
        return True, []
    cid = int(id_categoria)
    cur.execute(
        "SELECT id, parent_id FROM tbl_categoria WHERE id_tenant = (SELECT id_tenant FROM tbl_categoria WHERE id = %s) AND ativo = TRUE",
        (cid,),
    )
    rows = [(int(r[0]), r[1]) for r in cur.fetchall()]
    if not rows:
        return False, [cid]
    return False, _descendentes_categoria(rows, cid)


def _contar_sem_categoria(cur, id_vendedor: int, id_forn: str | None) -> int:
    params: list = [id_vendedor]
    extra = ""
    if id_forn:
        extra = " AND p.id_tenant = %s"
        params.append(int(id_forn))
    cur.execute(
        f"""
        SELECT COUNT(DISTINCT p.id)::int
        FROM tbl_produto p
        JOIN tbl_vinculo_vendedor_fornecedor vinc
            ON vinc.id_tenant_fornecedor = p.id_tenant
           AND vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'
        WHERE p.publicado = TRUE AND p.ativo = TRUE AND p.id_categoria IS NULL{extra}
        """,
        params,
    )
    return int(cur.fetchone()[0] or 0)


def _listar_categorias_combos(cur, id_vendedor: int, id_forn: str | None) -> list[dict]:
    from core.dominio import flatten_arvore_com_caminho, montar_arvore_categorias

    fn_params: list = [id_vendedor]
    fn_extra = ""
    if id_forn:
        fn_extra = " AND vinc.id_tenant_fornecedor = %s"
        fn_params.append(int(id_forn))
    cur.execute(
        f"""
        SELECT t.id, COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), t.nome)
        FROM tbl_vinculo_vendedor_fornecedor vinc
        JOIN tbl_tenant t ON t.id = vinc.id_tenant_fornecedor
        WHERE vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'{fn_extra}
        ORDER BY 2
        """,
        fn_params,
    )
    fornecedores = cur.fetchall()
    categorias: list[dict] = []

    for id_fn, nome_fn in fornecedores:
        cur.execute(
            """
            SELECT id, nome, parent_id, ordem, COALESCE(nivel, 1), 0
            FROM tbl_categoria
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY ordem, nome
            """,
            (int(id_fn),),
        )
        rows_cat = cur.fetchall()
        if not rows_cat:
            continue

        cur.execute(
            """
            SELECT p.id_categoria, COUNT(DISTINCT p.id)::int
            FROM tbl_produto p
            JOIN tbl_vinculo_vendedor_fornecedor vinc
                ON vinc.id_tenant_fornecedor = p.id_tenant
               AND vinc.id_tenant_vendedor = %s AND vinc.status = 'ativo'
            WHERE p.id_tenant = %s
              AND p.publicado = TRUE AND p.ativo = TRUE
              AND p.id_categoria IS NOT NULL
            GROUP BY p.id_categoria
            """,
            (id_vendedor, int(id_fn)),
        )
        qtd_direta = {int(r[0]): int(r[1] or 0) for r in cur.fetchall()}

        rows_map = [(int(r[0]), r[2]) for r in rows_cat]
        arvore = montar_arvore_categorias(rows_cat)
        prefixo = "" if id_forn else f"{nome_fn} · "
        for c in flatten_arvore_com_caminho(arvore):
            ids_cat = _descendentes_categoria(rows_map, int(c["id"]))
            qtd = sum(qtd_direta.get(cid, 0) for cid in ids_cat)
            categorias.append(
                {
                    "id": int(c["id"]),
                    "nome": f"{prefixo}{c['caminho']}",
                    "qtd": qtd,
                    "id_fornecedor": int(id_fn),
                }
            )

    categorias.sort(key=lambda x: (x["nome"] or "").lower())
    return categorias


def _where_catalogo(
    id_vendedor: int,
    busca: str,
    id_forn: str,
    id_seg: str,
    id_categoria: str | list,
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
        if isinstance(id_categoria, str) and id_categoria.strip().lower() == "sem":
            where.append("p.id_categoria IS NULL")
        elif isinstance(id_categoria, list):
            where.append("p.id_categoria = ANY(%s)")
            params.append(id_categoria)
        else:
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
    """Fornecedores conectados e árvore de categorias dos fornecedores."""
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

        categorias = _listar_categorias_combos(cur, int(id_vendedor), id_forn or None)
        sem_cat = _contar_sem_categoria(cur, int(id_vendedor), id_forn or None)
        if sem_cat > 0:
            categorias.append({"id": "sem", "nome": "Sem categoria", "qtd": sem_cat, "id_fornecedor": None})

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

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cat_filtro: str | list = id_categoria
        if id_categoria and id_categoria.strip().lower() != "sem":
            sem_cat, ids_cat = _ids_categoria_filtro(cur, id_categoria)
            cat_filtro = ids_cat if ids_cat else id_categoria
        elif id_categoria.strip().lower() == "sem":
            cat_filtro = "sem"

        where, params = _where_catalogo(
            id_vendedor, busca, id_forn, id_seg, cat_filtro, em_estoque, conexao
        )
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
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria AND c.id_tenant = p.id_tenant
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
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria AND c.id_tenant = p.id_tenant
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

        id_fornecedor = int(rows[0][2])
        from vendedor.meus_produtos.servico_meus_produtos import espelhar_depositos_fornecedor

        espelhar_depositos_fornecedor(cur, int(id_vendedor), id_fornecedor, id_produto=id_produto)

        ativados = 0
        for row in rows:
            preco_forn = float(row[3] or 0)
            preco_venda = precificar_na_integracao(
                cur, int(id_vendedor), int(row[2]), row[4], preco_forn
            )
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
        from vendedor.meus_produtos.servico_meus_produtos import espelhar_depositos_fornecedor

        espelhar_depositos_fornecedor(cur, int(id_vendedor), int(row[2]), id_produto=int(row[1]))
        preco_forn = float(row[3] or 0)
        preco_venda = precificar_na_integracao(
            cur, int(id_vendedor), int(row[2]), row[4], preco_forn
        )
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
