"""Listagem de produtos próprios do vendedor (id_tenant = vendedor)."""

from __future__ import annotations

from fornecedor.catalogo.srotas_catalogo import (
    SQL_VARIANTE_LISTA,
    _catalogo_montar_linhas_pai,
    _imagem_url_resposta,
    variante_dict,
)


def buscar_produtos_proprios(
    cur,
    id_tenant: int,
    *,
    busca: str = "",
    id_categoria: str = "",
    filtro_tipo: str = "",
    somente_ativos: bool = True,
) -> tuple[list[dict], dict[int, list], list[dict]]:
    """Retorna (dados pais, variantes_por_produto, linhas planas)."""
    if filtro_tipo == "somente_variacoes":
        where = ["p.id_tenant = %s", "p.formato = 'E'"]
        params: list = [id_tenant]
        if busca:
            where.append("(p.nome ILIKE %s OR v.sku ILIKE %s OR v.nome_exibicao ILIKE %s)")
            like = f"%{busca}%"
            params.extend([like, like, like])
        if id_categoria:
            where.append("p.id_categoria = %s")
            params.append(int(id_categoria))
        if somente_ativos:
            where.append("p.ativo = TRUE")
            where.append("v.ativo = TRUE")
        where_sql = " AND ".join(where)
        cur.execute(
            f"""
            SELECT v.id, v.id_produto, v.sku, v.nome_exibicao, v.preco, v.ativo,
                   COALESCE(e.quantidade, 0),
                   COALESCE(v.imagem_url, vp.imagem_url, p.imagem_url),
                   p.nome, COALESCE(p.unidade, 'UN')
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            LEFT JOIN tbl_produto_variante vp ON vp.id = p.id_variante_padrao
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE {where_sql}
            ORDER BY p.nome, v.ordem, v.nome_exibicao
            """,
            params,
        )
        linhas = [
            {
                "tipo": "variante",
                "id": r[0],
                "id_produto": r[1],
                "sku": r[2] or "",
                "nome": r[3],
                "produto_pai": r[8],
                "unidade": r[9] or "UN",
                "formato": "E",
                "preco": float(r[4] or 0),
                "estoque": int(r[6] or 0),
                "ativo": bool(r[5]),
                "imagem_url": _imagem_url_resposta(r[7]),
                "origem": "proprio",
            }
            for r in cur.fetchall()
        ]
        return [], {}, linhas

    where = ["p.id_tenant = %s"]
    params = [id_tenant]
    if busca:
        where.append(
            """(
            p.nome ILIKE %s OR p.sku ILIKE %s
            OR EXISTS (
                SELECT 1 FROM tbl_produto_variante vx
                WHERE vx.id_produto = p.id AND (vx.sku ILIKE %s OR vx.nome_exibicao ILIKE %s)
            )
            )"""
        )
        like = f"%{busca}%"
        params.extend([like, like, like, like])
    if id_categoria:
        where.append("p.id_categoria = %s")
        params.append(int(id_categoria))
    if filtro_tipo == "simples":
        where.append("p.formato = 'S'")
    elif filtro_tipo == "com_variacoes":
        where.append("p.formato = 'E'")
    if somente_ativos:
        where.append("p.ativo = TRUE")

    where_sql = " AND ".join(where)
    filtro_var_ativo = " AND v.ativo" if somente_ativos else ""
    cur.execute(
        f"""
        SELECT p.id, p.sku, p.nome, p.formato, p.publicado, p.ativo,
               COALESCE(p.unidade, 'UN'),
               c.nome AS categoria,
               p.id_categoria,
               (SELECT COUNT(*) FROM tbl_produto_variante v WHERE v.id_produto = p.id{filtro_var_ativo}),
               (SELECT COALESCE(MIN(v.preco), 0) FROM tbl_produto_variante v WHERE v.id_produto = p.id{filtro_var_ativo}),
               (SELECT COALESCE(MAX(v.preco), 0) FROM tbl_produto_variante v WHERE v.id_produto = p.id{filtro_var_ativo}),
               (SELECT COALESCE(SUM(e2.quantidade), 0) FROM tbl_produto_variante v2
                LEFT JOIN tbl_produto_variante_estoque e2 ON e2.id_variante = v2.id
                WHERE v2.id_produto = p.id),
               COALESCE(vp.imagem_url, p.imagem_url),
               p.atualizado_em
        FROM tbl_produto p
        LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
        LEFT JOIN tbl_produto_variante vp ON vp.id = p.id_variante_padrao
        WHERE {where_sql}
        ORDER BY p.atualizado_em DESC, p.nome
        """,
        params,
    )
    dados = [
        {
            "id": r[0],
            "sku": r[1] or "",
            "nome": r[2],
            "formato": r[3] or "S",
            "publicado": bool(r[4]),
            "ativo": bool(r[5]),
            "unidade": r[6] or "UN",
            "categoria": r[7] or "",
            "id_categoria": r[8],
            "qtd_variantes": int(r[9] or 0),
            "preco_min": float(r[10] or 0),
            "preco_max": float(r[11] or 0),
            "preco": float(r[10] or 0),
            "estoque": int(r[12] or 0),
            "imagem_url": _imagem_url_resposta(r[13]),
            "origem": "proprio",
            "_sort_ts": r[14],
        }
        for r in cur.fetchall()
    ]

    expandir_variantes = filtro_tipo in ("", "com_variacoes")
    variantes_por_produto: dict[int, list] = {}
    if expandir_variantes:
        ids_var = [p["id"] for p in dados if p["formato"] == "E"]
        if ids_var:
            var_clause = "v.id_produto = ANY(%s)"
            var_params: list = [ids_var]
            if somente_ativos:
                var_clause += " AND v.ativo = TRUE"
            cur.execute(
                f"""
                {SQL_VARIANTE_LISTA}
                WHERE {var_clause}
                ORDER BY v.id_produto, v.ordem, v.nome_exibicao
                """,
                tuple(var_params),
            )
            for row in cur.fetchall():
                v = variante_dict(row)
                v["origem"] = "proprio"
                variantes_por_produto.setdefault(v["id_produto"], []).append(v)

    linhas = _catalogo_montar_linhas_pai(
        dados,
        variantes_por_produto,
        expandir_variantes=expandir_variantes,
        somente_ativos=somente_ativos,
    )
    for linha in linhas:
        linha["origem"] = "proprio"
    for p in dados:
        for linha in linhas:
            if linha.get("tipo") == "pai" and int(linha["id"]) == int(p["id"]):
                linha["categoria"] = p.get("categoria") or ""
                linha["id_categoria"] = p.get("id_categoria")
    return dados, variantes_por_produto, linhas
