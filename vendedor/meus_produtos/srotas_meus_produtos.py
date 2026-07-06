from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import (
    Var_ConectarBanco,
    agora_utc,
    exigir_modulo,
    exigir_permissao,
    login_obrigatorio,
    url_imagem_produto,
    usuario_tem_permissao,
)
from srotas_plataforma import MODULO_VENDEDOR
from fornecedor.catalogo.srotas_catalogo import (
    SQL_VARIANTE_LISTA,
    _catalogo_montar_linhas_pai,
    _imagem_url_resposta,
    descricao_efetiva_variante,
    estoque_kit_componentes,
    merge_variante_exibicao,
    preco_sugerido_kit,
    produto_pai_dict,
    variante_dict,
    variante_rede_valida,
)
from fornecedor.catalogo.servico_estoque_deposito import listar_estoque_por_deposito
from fornecedor.catalogo.servico_imagens import (
    listar_imagens_galeria_pai,
    listar_imagens_variante_selecionadas,
    listar_regras_atributo_imagem,
    obter_imagem_modo,
)
from srotas_negocio import flatten_arvore_com_caminho, montar_arvore_categorias
from vendedor.meus_produtos.servico_fornecedor_apoio import montar_fornecedor_produto_apoio
from vendedor.meus_produtos.servico_listagem_proprio import buscar_produtos_proprios
from vendedor.meus_produtos.servico_vitrine_vendedor import (
    CAMPOS_READONLY_INTEGRADO,
    avaliar_pausa_variante,
    estoque_efetivo,
    estoque_real_variante,
    produto_integrado,
    restaurar_vitrine_produto,
    restaurar_vitrine_variante,
)

_MOD_DIR = Path(__file__).resolve().parent

vd_meus_produtos_bp = Blueprint(
    "vd_meus_produtos",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/meus_produtos",
)


def init_app(app):
    app.register_blueprint(vd_meus_produtos_bp)


def _id_tenant_sessao() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _pode_editar_favoritos():
    return session.get("eh_desenvolvedor") or usuario_tem_permissao("produtos.editar")


def _resolver_id_variante(cur, id_tenant: int, id_variante: int = 0, id_produto: int = 0) -> int | None:
    if id_variante and variante_rede_valida(cur, id_variante, id_tenant):
        return id_variante
    if id_produto:
        cur.execute(
            """
            SELECT v.id FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE p.id = %s AND p.id_tenant <> %s AND p.publicado = TRUE AND v.ativo = TRUE
            ORDER BY CASE WHEN v.id = p.id_variante_padrao THEN 0 ELSE 1 END, v.id
            LIMIT 1
            """,
            (id_produto, id_tenant),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None
    return None


@vd_meus_produtos_bp.get("/meus-produtos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="produtos.ver")
def pagina():
    return render_template("frm_meus_produtos.html", nav_ativo="produtos")


def _kit_id_negativo(kit_id: int) -> int:
    """ID negativo na listagem para distinguir kits de produtos."""
    return -abs(int(kit_id))


def _enriquecer_meta_pausa(cur, id_tenant: int, id_variante: int) -> dict:
    pausado, motivo, msg = avaliar_pausa_variante(cur, id_tenant, id_variante)
    return {
        "pausado": pausado,
        "pausado_motivo": motivo,
        "pausado_msg": msg,
        "estoque_real": estoque_real_variante(cur, id_variante),
        "estoque": estoque_efetivo(cur, id_tenant, id_variante),
    }


def _enriquecer_variantes_vitrine(cur, id_tenant: int, variantes_por_produto: dict[int, list]) -> None:
    for vars_p in variantes_por_produto.values():
        for v in vars_p:
            meta = _enriquecer_meta_pausa(cur, id_tenant, int(v["id"]))
            v.update(meta)
            if v.get("preco") is None and "preco_venda" in v:
                v["preco"] = float(v["preco_venda"] or 0)


def _enriquecer_estoque_produto_simples(cur, id_tenant: int, produto: dict) -> None:
    if produto.get("formato") == "E":
        return
    cur.execute("SELECT id_variante_padrao FROM tbl_produto WHERE id = %s", (produto["id"],))
    row = cur.fetchone()
    if not row or not row[0]:
        return
    meta = _enriquecer_meta_pausa(cur, id_tenant, int(row[0]))
    produto.update(meta)


def _exigir_produto_vitrine(cur, id_tenant_vendedor: int, id_produto: int) -> dict | None:
    cur.execute(
        """
        SELECT 1 FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_produto = %s
        LIMIT 1
        """,
        (id_tenant_vendedor, id_produto),
    )
    if not cur.fetchone():
        return None
    cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    if not row:
        return None
    id_owner = int(row[0])
    return {
        "integrado": id_owner != id_tenant_vendedor,
        "id_fornecedor": id_owner,
    }


def _montar_linhas_kits(cur, id_tenant: int, busca: str, somente_ativos: bool) -> list[dict]:
    where = ["k.id_tenant = %s"]
    params: list = [id_tenant]
    if busca:
        where.append("k.nome ILIKE %s")
        params.append(f"%{busca}%")
    if somente_ativos:
        where.append("k.ativo = TRUE")
    cur.execute(
        f"""
        SELECT k.id, k.nome, k.preco_venda, k.ativo,
               (SELECT COUNT(*) FROM tbl_kit_vendedor_item i WHERE i.id_kit = k.id)
        FROM tbl_kit_vendedor k
        WHERE {" AND ".join(where)}
        ORDER BY k.atualizado_em DESC, k.nome
        """,
        params,
    )
    linhas: list[dict] = []
    for r in cur.fetchall():
        kid = int(r[0])
        cur.execute(
            """
            SELECT i.id_variante, i.quantidade
            FROM tbl_kit_vendedor_item i
            WHERE i.id_kit = %s
            ORDER BY i.ordem, i.id
            """,
            (kid,),
        )
        comp = [(int(x[0]), int(x[1])) for x in cur.fetchall()]
        estoque = estoque_kit_componentes(cur, comp) if comp else 0
        linhas.append(
            {
                "tipo": "pai",
                "id": _kit_id_negativo(kid),
                "id_produto": _kit_id_negativo(kid),
                "id_kit": kid,
                "sku": f"KIT-{kid}",
                "nome": r[1],
                "formato": "K",
                "unidade": "UN",
                "preco": float(r[2] or 0),
                "preco_min": float(r[2] or 0),
                "preco_max": float(r[2] or 0),
                "estoque": estoque,
                "estoque_total": estoque,
                "qtd_variantes": 0,
                "ativo": bool(r[3]),
                "publicado": True,
                "imagem_url": "",
            }
        )
    return linhas


@vd_meus_produtos_bp.get("/meus-produtos/dados")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def dados():
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = max(1, min(int(request.args.get("porPagina", 100)), 100))
    busca = (request.args.get("busca") or "").strip()
    id_categoria = (request.args.get("id_categoria") or "").strip()
    filtro_tipo = (request.args.get("tipo") or "").strip().lower()
    filtro_origem = (request.args.get("origem") or "").strip().lower()
    somente_ativos = (request.args.get("ativos") or "sim").strip().lower() != "nao"
    offset = (pagina - 1) * por_pagina

    if filtro_tipo == "kit" or filtro_origem == "kit":
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            linhas_kits = _montar_linhas_kits(cur, id_tenant, busca, somente_ativos)
            total = len(linhas_kits)
            linhas_pag = linhas_kits[offset : offset + por_pagina]
            total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
            return jsonify(
                success=True,
                dados=[],
                linhas=linhas_pag,
                total=total,
                pagina_atual=pagina,
                total_paginas=total_paginas,
            )
        finally:
            conn.close()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()

        if filtro_origem == "proprio" and filtro_tipo != "kit":
            _, _, linhas_prop = buscar_produtos_proprios(
                cur,
                id_tenant,
                busca=busca,
                id_categoria=id_categoria,
                filtro_tipo=filtro_tipo,
                somente_ativos=somente_ativos,
            )
            if filtro_tipo in ("", "kit"):
                linhas_kits = _montar_linhas_kits(cur, id_tenant, busca, somente_ativos) if filtro_tipo in ("", "kit") else []
                linhas_prop = linhas_kits + linhas_prop
            total = len(linhas_prop)
            linhas_pag = linhas_prop[offset : offset + por_pagina]
            total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
            return jsonify(
                success=True,
                dados=[],
                linhas=linhas_pag,
                total=total,
                pagina_atual=pagina,
                total_paginas=total_paginas,
            )

        if filtro_tipo == "somente_variacoes":
            where = ["pv.id_tenant_vendedor = %s", "p.formato = 'E'"]
            params: list = [id_tenant]
            if busca:
                where.append("(p.nome ILIKE %s OR v.sku ILIKE %s OR v.nome_exibicao ILIKE %s OR pv.nome_vitrine ILIKE %s)")
                like = f"%{busca}%"
                params.extend([like, like, like, like])
            if id_categoria:
                where.append("p.id_categoria = %s")
                params.append(int(id_categoria))
            if somente_ativos:
                where.append("pv.ativo = TRUE")
            where_sql = " AND ".join(where)

            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM tbl_produto_vendedor pv
                JOIN tbl_produto_variante v ON v.id = pv.id_variante
                JOIN tbl_produto p ON p.id = pv.id_produto
                WHERE {where_sql}
                """,
                params,
            )
            total = int(cur.fetchone()[0] or 0)
            cur.execute(
                f"""
                SELECT v.id, v.id_produto, v.sku,
                       COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), v.nome_exibicao),
                       pv.preco_venda, pv.ativo,
                       COALESCE(e.quantidade, 0),
                       COALESCE(NULLIF(TRIM(pv.imagem_url_vitrine), ''), v.imagem_url, p.imagem_url),
                       p.nome, COALESCE(p.unidade, 'UN'), v.atributos
                FROM tbl_produto_vendedor pv
                JOIN tbl_produto_variante v ON v.id = pv.id_variante
                JOIN tbl_produto p ON p.id = pv.id_produto
                LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
                WHERE {where_sql}
                ORDER BY p.nome, v.ordem, v.nome_exibicao
                LIMIT %s OFFSET %s
                """,
                params + [por_pagina, offset],
            )
            linhas = [
                {
                    "tipo": "variante",
                    "id": r[0],
                    "id_produto": r[1],
                    "sku": r[2] or "",
                    "nome": r[3],
                    "produto_pai": r[8],
                    "atributos": r[10] if isinstance(r[10], dict) else {},
                    "unidade": r[9] or "UN",
                    "formato": "E",
                    "preco": float(r[4] or 0),
                    "estoque": int(r[6] or 0),
                    "ativo": bool(r[5]),
                    "imagem_url": _imagem_url_resposta(r[7]),
                }
                for r in cur.fetchall()
            ]
            for linha in linhas:
                meta = _enriquecer_meta_pausa(cur, id_tenant, int(linha["id"]))
                linha.update(meta)
            total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
            return jsonify(
                success=True,
                dados=[],
                linhas=linhas,
                total=total,
                pagina_atual=pagina,
                total_paginas=total_paginas,
            )

        where = ["pv.id_tenant_vendedor = %s", "p.id_tenant <> %s"]
        params = [id_tenant, id_tenant]
        if busca:
            where.append(
                """(
                p.nome ILIKE %s OR p.sku ILIKE %s OR pv.nome_vitrine ILIKE %s
                OR EXISTS (
                    SELECT 1 FROM tbl_produto_variante vx
                    JOIN tbl_produto_vendedor pv2 ON pv2.id_variante = vx.id AND pv2.id_tenant_vendedor = %s
                    WHERE vx.id_produto = p.id AND (vx.sku ILIKE %s OR vx.nome_exibicao ILIKE %s)
                )
                )"""
            )
            like = f"%{busca}%"
            params.extend([like, like, like, id_tenant, like, like])
        if id_categoria:
            where.append("p.id_categoria = %s")
            params.append(int(id_categoria))
        if filtro_tipo == "simples":
            where.append("p.formato = 'S'")
        elif filtro_tipo == "com_variacoes":
            where.append("p.formato = 'E'")
        if somente_ativos:
            where.append("pv.ativo = TRUE")

        where_sql = " AND ".join(where)
        filtro_var_ativo = " AND pv2.ativo = TRUE" if somente_ativos else ""

        cur.execute(
            f"""
            SELECT COUNT(DISTINCT p.id)
            FROM tbl_produto p
            INNER JOIN tbl_produto_vendedor pv ON pv.id_produto = p.id AND pv.id_tenant_vendedor = %s
            WHERE {where_sql}
            """,
            [id_tenant] + params,
        )
        total_produtos = int(cur.fetchone()[0] or 0)

        paginar_sql = ""
        paginar_params: list = []
        if filtro_origem != "":
            paginar_sql = " LIMIT %s OFFSET %s"
            paginar_params = [por_pagina, offset]

        cur.execute(
            f"""
            SELECT p.id, p.sku,
                   COALESCE(
                       (SELECT NULLIF(TRIM(pv_n.nome_vitrine), '')
                        FROM tbl_produto_vendedor pv_n
                        WHERE pv_n.id_produto = p.id AND pv_n.id_tenant_vendedor = %s
                          AND pv_n.nome_vitrine IS NOT NULL AND TRIM(pv_n.nome_vitrine) <> ''
                        ORDER BY pv_n.id LIMIT 1),
                       p.nome
                   ),
                   p.formato,
                   BOOL_OR(pv.ativo),
                   COALESCE(p.unidade, 'UN'),
                   c.nome,
                   (SELECT COUNT(*) FROM tbl_produto_vendedor pv2
                    WHERE pv2.id_produto = p.id AND pv2.id_tenant_vendedor = %s{filtro_var_ativo}),
                   (SELECT COALESCE(MIN(pv3.preco_venda), 0) FROM tbl_produto_vendedor pv3
                    WHERE pv3.id_produto = p.id AND pv3.id_tenant_vendedor = %s{filtro_var_ativo.replace('pv2', 'pv3')}),
                   (SELECT COALESCE(MAX(pv4.preco_venda), 0) FROM tbl_produto_vendedor pv4
                    WHERE pv4.id_produto = p.id AND pv4.id_tenant_vendedor = %s{filtro_var_ativo.replace('pv2', 'pv4')}),
                   (SELECT COALESCE(SUM(e2.quantidade), 0)
                    FROM tbl_produto_vendedor pv5
                    JOIN tbl_produto_variante v2 ON v2.id = pv5.id_variante
                    LEFT JOIN tbl_produto_variante_estoque e2 ON e2.id_variante = v2.id
                    WHERE pv5.id_produto = p.id AND pv5.id_tenant_vendedor = %s{filtro_var_ativo.replace('pv2', 'pv5')}),
                   COALESCE(
                       (SELECT NULLIF(TRIM(pv_i.imagem_url_vitrine), '')
                        FROM tbl_produto_vendedor pv_i
                        WHERE pv_i.id_produto = p.id AND pv_i.id_tenant_vendedor = %s
                          AND pv_i.imagem_url_vitrine IS NOT NULL AND TRIM(pv_i.imagem_url_vitrine) <> ''
                        ORDER BY pv_i.id LIMIT 1),
                       vp.imagem_url, p.imagem_url
                   )
            FROM tbl_produto p
            INNER JOIN tbl_produto_vendedor pv ON pv.id_produto = p.id AND pv.id_tenant_vendedor = %s
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante vp ON vp.id = p.id_variante_padrao
            WHERE {where_sql}
            GROUP BY p.id, p.sku, p.nome, p.formato, p.unidade, c.nome, vp.imagem_url, p.imagem_url
            ORDER BY MAX(pv.atualizado_em) DESC, p.nome
            {paginar_sql}
            """,
            [id_tenant, id_tenant, id_tenant, id_tenant, id_tenant, id_tenant, id_tenant] + params + paginar_params,
        )
        dados = [
            {
                "id": r[0],
                "sku": r[1] or "",
                "nome": r[2],
                "formato": r[3] or "S",
                "publicado": True,
                "ativo": bool(r[4]),
                "unidade": r[5] or "UN",
                "categoria": r[6] or "",
                "qtd_variantes": int(r[7] or 0),
                "preco_min": float(r[8] or 0),
                "preco_max": float(r[9] or 0),
                "preco": float(r[8] or 0),
                "estoque": int(r[10] or 0),
                "imagem_url": _imagem_url_resposta(r[11]),
            }
            for r in cur.fetchall()
        ]

        expandir_variantes = filtro_tipo in ("", "com_variacoes")
        variantes_por_produto: dict[int, list] = {}
        if expandir_variantes:
            ids_var = [p["id"] for p in dados if p["formato"] == "E"]
            if ids_var:
                var_clause = "v.id_produto = ANY(%s) AND pv.id_tenant_vendedor = %s"
                var_params: list = [ids_var, id_tenant]
                if somente_ativos:
                    var_clause += " AND pv.ativo = TRUE"
                cur.execute(
                    f"""
                    SELECT v.id, v.id_produto, v.sku,
                           COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), v.nome_exibicao),
                           pv.preco_venda, v.preco_promocional,
                           v.preco_custo, v.atributos,
                           COALESCE(NULLIF(TRIM(pv.imagem_url_vitrine), ''), img.caminho, v.imagem_url),
                           pv.ativo, v.ordem,
                           COALESCE(e.quantidade, 0),
                           v.herda_pai, v.peso_liquido_kg, v.peso_bruto_kg, v.altura_cm, v.largura_cm,
                           v.profundidade_cm, v.gtin, v.ncm, v.id_imagem_principal, v.descricao,
                           v.valor_drop, COALESCE(v.valor_drop_manual, FALSE), v.promocao_validade,
                           v.promocao_ate_zerar_estoque
                    FROM tbl_produto_vendedor pv
                    JOIN tbl_produto_variante v ON v.id = pv.id_variante
                    LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
                    LEFT JOIN tbl_produto_imagem img ON img.id = v.id_imagem_principal
                    WHERE {var_clause}
                    ORDER BY v.id_produto, v.ordem, v.nome_exibicao
                    """,
                    tuple(var_params),
                )
                for row in cur.fetchall():
                    v = variante_dict(row)
                    v["preco"] = float(row[4] or 0)
                    variantes_por_produto.setdefault(v["id_produto"], []).append(v)

        for p in dados:
            _enriquecer_estoque_produto_simples(cur, id_tenant, p)
        _enriquecer_variantes_vitrine(cur, id_tenant, variantes_por_produto)

        linhas = _catalogo_montar_linhas_pai(
            dados,
            variantes_por_produto,
            expandir_variantes=expandir_variantes,
            somente_ativos=somente_ativos,
        )

        if filtro_tipo in ("", "kit"):
            linhas_kits = _montar_linhas_kits(cur, id_tenant, busca, somente_ativos)
            if filtro_tipo == "":
                linhas = linhas_kits + linhas
                total_produtos += len(linhas_kits)
            else:
                linhas = linhas_kits
                total_produtos = len(linhas_kits)

        for linha in linhas:
            linha.setdefault("origem", "integrado")
            if linha.get("tipo") == "variante" and "pausado" not in linha:
                meta = _enriquecer_meta_pausa(cur, id_tenant, int(linha["id"]))
                linha.update(meta)
            elif linha.get("tipo") == "pai" and linha.get("formato") == "E":
                vars_p = variantes_por_produto.get(int(linha["id"]), [])
                linha["pausado"] = any(v.get("pausado") for v in vars_p)
                if linha["pausado"]:
                    motivos = [v.get("pausado_msg") for v in vars_p if v.get("pausado_msg")]
                    linha["pausado_msg"] = motivos[0] if motivos else "Produto pausado na vitrine."
            elif linha.get("tipo") == "pai" and linha.get("formato") == "S":
                p = next((x for x in dados if x["id"] == linha["id"]), None)
                if p:
                    linha["pausado"] = bool(p.get("pausado"))
                    linha["pausado_msg"] = p.get("pausado_msg") or ""

        if filtro_origem == "" and filtro_tipo != "kit":
            _, _, linhas_prop = buscar_produtos_proprios(
                cur,
                id_tenant,
                busca=busca,
                id_categoria=id_categoria,
                filtro_tipo=filtro_tipo,
                somente_ativos=somente_ativos,
            )
            linhas = linhas + linhas_prop

        if filtro_origem == "" and filtro_tipo not in ("kit", "somente_variacoes"):
            linhas.sort(key=lambda x: str(x.get("nome") or "").lower())
            total_produtos = len(linhas)
            linhas = linhas[offset : offset + por_pagina]

        total_paginas = max(1, (total_produtos + por_pagina - 1) // por_pagina)
        return jsonify(
            success=True,
            dados=dados,
            linhas=linhas,
            total=total_produtos,
            pagina_atual=pagina,
            total_paginas=total_paginas,
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/combos")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def combos():
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome, parent_id, ordem, COALESCE(nivel, 1), 0
            FROM tbl_categoria
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY ordem, nome
            """,
            (id_tenant,),
        )
        arvore = montar_arvore_categorias(cur.fetchall())
        categorias = [
            {"id": c["id"], "nome": c["caminho"], "caminho": c["caminho"], "nivel": c["nivel"]}
            for c in flatten_arvore_com_caminho(arvore)
        ]
        depositos = []
        try:
            cur.execute(
                """
                SELECT id, nome, cep, cidade, uf, espelho_somente_leitura
                FROM tbl_deposito_expedicao
                WHERE id_tenant = %s AND ativo = TRUE
                ORDER BY principal DESC, nome
                """,
                (id_tenant,),
            )
            depositos = [
                {
                    "id": r[0],
                    "nome": r[1] + (" (espelho)" if len(r) > 5 and r[5] else ""),
                    "cep": r[2],
                    "cidade": r[3],
                    "uf": r[4],
                }
                for r in cur.fetchall()
            ]
        except Exception:
            depositos = []
        return jsonify(
            success=True,
            categorias=categorias,
            depositos=depositos,
            unidades=["UN", "CX", "KG", "PC", "PAR"],
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/incluir")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def incluir():
    return render_template("frm_catalogo_apoio.html", apoio_modo="vendedor")


@vd_meus_produtos_bp.get("/meus-produtos/editar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def editar():
    return render_template("frm_catalogo_apoio.html", apoio_modo="vendedor")


@vd_meus_produtos_bp.post("/meus-produtos/delete")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def excluir_produto():
    if (resp := _exigir_edicao()) is not None:
        return resp
    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    pid = int(body.get("id") or 0)
    if not id_tenant or not pid:
        return jsonify(success=False, message="Dados inválidos."), 400

    if pid < 0:
        kid = abs(pid)
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM tbl_kit_vendedor WHERE id = %s AND id_tenant = %s", (kid, id_tenant))
            conn.commit()
            if cur.rowcount == 0:
                return jsonify(success=False, message="Kit não encontrado."), 404
            return jsonify(success=True, message="Kit excluído.")
        finally:
            conn.close()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (pid,))
        row_owner = cur.fetchone()
        if row_owner and int(row_owner[0]) == id_tenant:
            cur.execute("DELETE FROM tbl_produto WHERE id = %s AND id_tenant = %s", (pid, id_tenant))
            conn.commit()
            if cur.rowcount == 0:
                return jsonify(success=False, message="Produto não encontrado."), 404
            return jsonify(success=True, message="Produto excluído.")
        cur.execute(
            "DELETE FROM tbl_produto_vendedor WHERE id_tenant_vendedor = %s AND id_produto = %s",
            (id_tenant, pid),
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(success=False, message="Produto não encontrado."), 404
        return jsonify(success=True, message="Produto removido da vitrine.")
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def apoio_produto():
    """Carrega produto integrado (vitrine) ou próprio (cadastro completo)."""
    id_tenant = _id_tenant_sessao()
    pid = int((request.get_json(silent=True) or {}).get("id") or 0)
    if not id_tenant or not pid:
        return jsonify(success=False, message="ID inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (pid,))
        owner_row = cur.fetchone()
        if not owner_row:
            return jsonify(success=False, message="Produto não encontrado."), 404
        if int(owner_row[0]) == id_tenant:
            cur.execute(
                """
                SELECT p.id, p.sku, p.nome, p.descricao, p.preco, p.preco_promocional,
                       p.unidade, p.id_categoria, p.imagem_url, p.ativo, p.publicado,
                       p.formato, p.tipo, p.preco_custo, p.gtin, p.ncm, p.referencia,
                       p.peso_liquido_kg, p.peso_bruto_kg, p.altura_cm, p.largura_cm, p.profundidade_cm,
                       p.prazo_envio_dias, p.moq, p.id_variante_padrao,
                       COALESCE(ve.quantidade, 0),
                       p.marca, p.grupo, p.valor_atacado, p.valor_dropshipping,
                       p.reposicao_estoque, p.dimensao_caixa_cm, p.peso_gramas, p.id_deposito_expedicao,
                       p.condicao, p.cest, p.origem_fiscal, p.frete_gratis, p.volumes, p.producao, p.valor_drop,
                       COALESCE(p.valor_drop_manual, FALSE)
                FROM tbl_produto p
                LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = p.id_variante_padrao
                WHERE p.id = %s AND p.id_tenant = %s
                """,
                (pid, id_tenant),
            )
            r = cur.fetchone()
            return jsonify(
                success=True,
                dados={
                    "id": r[0],
                    "sku": r[1] or "",
                    "nome": r[2],
                    "descricao": r[3] or "",
                    "preco": float(r[4] or 0),
                    "preco_promocional": float(r[5]) if r[5] is not None else None,
                    "unidade": r[6] or "UN",
                    "id_categoria": r[7],
                    "imagem_url": _imagem_url_resposta(r[8]),
                    "imagem_caminho": r[8] or "",
                    "ativo": bool(r[9]),
                    "publicado": bool(r[10]),
                    "formato": r[11] or "S",
                    "tipo": r[12] or "P",
                    "preco_custo": float(r[13]) if r[13] is not None else None,
                    "gtin": r[14] or "",
                    "ncm": r[15] or "",
                    "referencia": r[16] or "",
                    "condicao": r[34] or r[16] or "",
                    "peso_liquido_kg": float(r[17]) if r[17] is not None else None,
                    "peso_bruto_kg": float(r[18]) if r[18] is not None else None,
                    "altura_cm": float(r[19]) if r[19] is not None else None,
                    "largura_cm": float(r[20]) if r[20] is not None else None,
                    "profundidade_cm": float(r[21]) if r[21] is not None else None,
                    "prazo_envio_dias": r[22],
                    "moq": int(r[23] or 1),
                    "id_variante_padrao": r[24],
                    "quantidade": int(r[25] or 0),
                    "marca": r[26] or "",
                    "grupo": r[27] or "",
                    "valor_atacado": float(r[28]) if r[28] is not None else float(r[4] or 0),
                    "valor_dropshipping": float(r[29]) if r[29] is not None else None,
                    "reposicao_estoque": bool(r[30]),
                    "dimensao_caixa_cm": r[31] or "",
                    "peso_gramas": int(r[32]) if r[32] is not None else None,
                    "id_deposito": r[33],
                    "cest": r[35] or "",
                    "origem_fiscal": r[36] or "",
                    "frete_gratis": bool(r[37]),
                    "volumes": int(r[38]) if r[38] is not None else None,
                    "producao": r[39] or "",
                    "valor_drop": float(r[40]) if r[40] is not None else None,
                    "valor_drop_manual": bool(r[41]),
                    "status_promocao": r[5] is not None and r[4] and float(r[5]) < float(r[4]),
                    "modo_vendedor": True,
                    "integrado": False,
                    "campos_readonly": [],
                },
            )

        cur.execute(
            """
            SELECT 1 FROM tbl_produto_vendedor
            WHERE id_tenant_vendedor = %s AND id_produto = %s
            LIMIT 1
            """,
            (id_tenant, pid),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não está na sua vitrine."), 404

        cur.execute(
            """
            SELECT p.id, p.sku, p.nome, p.descricao, p.preco, p.preco_promocional,
                   p.unidade, p.id_categoria, p.imagem_url, p.ativo, p.publicado,
                   p.formato, p.tipo, p.preco_custo, p.gtin, p.ncm, p.referencia,
                   p.peso_liquido_kg, p.peso_bruto_kg, p.altura_cm, p.largura_cm, p.profundidade_cm,
                   p.prazo_envio_dias, p.moq, p.id_variante_padrao,
                   COALESCE(ve.quantidade, 0),
                   p.marca, p.grupo, p.valor_atacado, p.valor_dropshipping,
                   p.reposicao_estoque, p.dimensao_caixa_cm, p.peso_gramas, p.id_deposito_expedicao,
                   p.condicao, p.cest, p.origem_fiscal, p.frete_gratis, p.volumes, p.producao, p.valor_drop,
                   COALESCE(p.valor_drop_manual, FALSE)
            FROM tbl_produto p
            LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = p.id_variante_padrao
            WHERE p.id = %s
            """,
            (pid,),
        )
        r = cur.fetchone()
        if not r:
            return jsonify(success=False, message="Produto não encontrado."), 404

        cur.execute(
            """
            SELECT nome_vitrine, descricao_vitrine, imagem_url_vitrine, preco_venda, ativo
            FROM tbl_produto_vendedor
            WHERE id_tenant_vendedor = %s AND id_produto = %s
            ORDER BY id
            LIMIT 1
            """,
            (id_tenant, pid),
        )
        vit = cur.fetchone()

        nome = (vit[0] or "").strip() if vit and vit[0] else r[2]
        descricao = (vit[1] or "").strip() if vit and vit[1] else (r[3] or "")
        img_vit = (vit[2] or "").strip() if vit and vit[2] else ""
        preco_venda = float(vit[3]) if vit and vit[3] is not None else float(r[4] or 0)
        ativo_vit = bool(vit[4]) if vit else bool(r[9])
        integrado = produto_integrado(cur, id_tenant, pid)
        fornecedor_apoio = None
        if integrado:
            cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (pid,))
            id_forn = int(cur.fetchone()[0])
            fornecedor_apoio = montar_fornecedor_produto_apoio(cur, id_tenant, id_forn)
        estoque_meta: dict = {}
        if r[24]:
            estoque_meta = _enriquecer_meta_pausa(cur, id_tenant, int(r[24]))
        quantidade = estoque_meta.get("estoque", int(r[25] or 0))

        return jsonify(
            success=True,
            dados={
                "id": r[0],
                "sku": r[1] or "",
                "nome": nome,
                "descricao": descricao,
                "preco": preco_venda,
                "preco_promocional": float(r[5]) if r[5] is not None else None,
                "unidade": r[6] or "UN",
                "id_categoria": r[7],
                "imagem_url": _imagem_url_resposta(img_vit or r[8]),
                "imagem_caminho": img_vit or r[8] or "",
                "ativo": ativo_vit,
                "publicado": True,
                "formato": r[11] or "S",
                "tipo": r[12] or "P",
                "preco_custo": float(r[13]) if r[13] is not None else None,
                "gtin": r[14] or "",
                "ncm": r[15] or "",
                "referencia": r[16] or "",
                "condicao": r[34] or r[16] or "",
                "peso_liquido_kg": float(r[17]) if r[17] is not None else None,
                "peso_bruto_kg": float(r[18]) if r[18] is not None else None,
                "altura_cm": float(r[19]) if r[19] is not None else None,
                "largura_cm": float(r[20]) if r[20] is not None else None,
                "profundidade_cm": float(r[21]) if r[21] is not None else None,
                "prazo_envio_dias": r[22],
                "moq": int(r[23] or 1),
                "id_variante_padrao": r[24],
                "quantidade": quantidade,
                "estoque_real": estoque_meta.get("estoque_real", int(r[25] or 0)),
                "pausado": estoque_meta.get("pausado", False),
                "pausado_motivo": estoque_meta.get("pausado_motivo"),
                "pausado_msg": estoque_meta.get("pausado_msg", ""),
                "marca": r[26] or "",
                "grupo": r[27] or "",
                "valor_atacado": float(r[28]) if r[28] is not None else float(r[4] or 0),
                "valor_dropshipping": float(r[29]) if r[29] is not None else None,
                "reposicao_estoque": bool(r[30]),
                "dimensao_caixa_cm": r[31] or "",
                "peso_gramas": int(r[32]) if r[32] is not None else None,
                "id_deposito": r[33],
                "cest": r[35] or "",
                "origem_fiscal": r[36] or "",
                "frete_gratis": bool(r[37]),
                "volumes": int(r[38]) if r[38] is not None else None,
                "producao": r[39] or "",
                "valor_drop": float(r[40]) if r[40] is not None else None,
                "valor_drop_manual": bool(r[41]),
                "status_promocao": r[5] is not None and r[4] and float(r[5]) < float(r[4]),
                "modo_vendedor": True,
                "integrado": integrado,
                "campos_readonly": sorted(CAMPOS_READONLY_INTEGRADO) if integrado else [],
                "fornecedor": fornecedor_apoio,
            },
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def salvar_vitrine():
    """Salva apenas campos de vitrine — não altera cadastro do fornecedor."""
    if (resp := _exigir_edicao()) is not None:
        return resp
    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    pid = int(body.get("id") or 0)
    if not id_tenant or not pid:
        return jsonify(success=False, message="Dados inválidos."), 400

    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome do produto."), 400

    preco_venda = Decimal(str(body.get("preco") or 0))
    descricao = (body.get("descricao") or "").strip()
    imagem = (body.get("imagem_url") or "").strip()
    ativo = str(body.get("ativo", "true")).lower() in ("1", "true", "t", "yes", "sim")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_produto_vendedor SET
                nome_vitrine = %s,
                descricao_vitrine = %s,
                imagem_url_vitrine = NULLIF(%s, ''),
                preco_venda = CASE WHEN preco_manual THEN preco_venda ELSE %s END,
                ativo = %s,
                atualizado_em = %s
            WHERE id_tenant_vendedor = %s AND id_produto = %s
            """,
            (nome, descricao, imagem, preco_venda, ativo, agora_utc(), id_tenant, pid),
        )
        if cur.rowcount == 0:
            return jsonify(success=False, message="Produto não está na sua vitrine."), 404
        conn.commit()
        return jsonify(success=True, message="Vitrine atualizada.", id=pid)
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/variantes/lista")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def variantes_lista_vitrine():
    id_tenant = _id_tenant_sessao()
    pid = int(request.args.get("id_produto") or 0)
    if not id_tenant or not pid:
        return jsonify(success=False, message="Parâmetros inválidos."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (pid,))
        owner = cur.fetchone()
        if owner and int(owner[0]) == id_tenant:
            from fornecedor.catalogo.srotas_catalogo import variantes_lista as fn_variantes_lista

            return fn_variantes_lista()

        cur.execute(
            f"""
            SELECT v.id, v.id_produto, v.sku,
                   COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), v.nome_exibicao),
                   pv.preco_venda, v.preco_promocional,
                   v.preco_custo, v.atributos,
                   COALESCE(NULLIF(TRIM(pv.imagem_url_vitrine), ''), img.caminho, v.imagem_url),
                   pv.ativo, v.ordem,
                   COALESCE(e.quantidade, 0),
                   v.herda_pai, v.peso_liquido_kg, v.peso_bruto_kg, v.altura_cm, v.largura_cm,
                   v.profundidade_cm, v.gtin, v.ncm, v.id_imagem_principal, v.descricao,
                   v.valor_drop, COALESCE(v.valor_drop_manual, FALSE), v.promocao_validade,
                   v.promocao_ate_zerar_estoque
            FROM tbl_produto_vendedor pv
            JOIN tbl_produto_variante v ON v.id = pv.id_variante
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            LEFT JOIN tbl_produto_imagem img ON img.id = v.id_imagem_principal
            WHERE pv.id_tenant_vendedor = %s AND pv.id_produto = %s
            ORDER BY v.ordem, v.nome_exibicao
            """,
            (id_tenant, pid),
        )
        variantes = []
        for row in cur.fetchall():
            v = variante_dict(row)
            v["preco"] = float(row[4] or 0)
            v.update(_enriquecer_meta_pausa(cur, id_tenant, int(v["id"])))
            variantes.append(v)
        return jsonify(success=True, variantes=variantes, atributos=[])
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/variante/editar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def variante_editar_pagina():
    return render_template("frm_catalogo_variante_apoio.html", apoio_modo="vendedor")


@vd_meus_produtos_bp.post("/meus-produtos/variante/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def variante_apoio_vitrine():
    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    vid = int(body.get("id") or body.get("id_variante") or 0)
    if not id_tenant or not vid:
        return jsonify(success=False, message="ID inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id_tenant FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE v.id = %s
            """,
            (vid,),
        )
        owner_row = cur.fetchone()
        if owner_row and int(owner_row[0]) == id_tenant:
            from fornecedor.catalogo.srotas_catalogo import variante_apoio as fn_variante_apoio

            return fn_variante_apoio()

        cur.execute(
            f"""
            {SQL_VARIANTE_LISTA}
            INNER JOIN tbl_produto_vendedor pv ON pv.id_variante = v.id AND pv.id_tenant_vendedor = %s
            WHERE v.id = %s
            """,
            (id_tenant, vid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Variação não está na sua vitrine."), 404

        cur.execute(
            """
            SELECT nome_vitrine, descricao_vitrine, imagem_url_vitrine, preco_venda, ativo
            FROM tbl_produto_vendedor
            WHERE id_tenant_vendedor = %s AND id_variante = %s
            """,
            (id_tenant, vid),
        )
        vit = cur.fetchone()
        variante = variante_dict(row)
        id_produto = int(variante["id_produto"])
        integrado = produto_integrado(cur, id_tenant, id_produto)

        nome_vit = (vit[0] or "").strip() if vit and vit[0] else ""
        desc_vit = (vit[1] or "").strip() if vit and vit[1] else ""
        img_vit = (vit[2] or "").strip() if vit and vit[2] else ""
        preco_venda = float(vit[3]) if vit and vit[3] is not None else float(variante.get("preco") or 0)
        ativo_vit = bool(vit[4]) if vit else bool(variante.get("ativo"))

        cur.execute(
            """
            SELECT id, sku, nome, descricao, preco, preco_promocional, preco_custo,
                   gtin, ncm, peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm,
                   profundidade_cm, imagem_url, referencia, formato,
                   valor_dropshipping, valor_drop, COALESCE(valor_drop_manual, FALSE)
            FROM tbl_produto WHERE id = %s
            """,
            (id_produto,),
        )
        pai = produto_pai_dict(cur.fetchone())
        variante["descricao_propria"] = (variante.get("descricao") or "").strip()
        variante["descricao"] = descricao_efetiva_variante(
            variante.get("descricao_propria"),
            herda_pai=variante.get("herda_pai", True),
            pai_descricao=pai.get("descricao", ""),
            atributos=variante.get("atributos"),
        )
        variante = merge_variante_exibicao(variante, pai)
        variante["imagens_pai"] = listar_imagens_galeria_pai(cur, id_produto)
        variante["imagens_selecionadas"] = listar_imagens_variante_selecionadas(cur, vid, id_produto)
        if img_vit:
            variante["imagens_selecionadas"] = [
                {
                    "id": None,
                    "caminho": img_vit,
                    "url": _imagem_url_resposta(img_vit),
                    "ordem": 0,
                    "principal": True,
                }
            ]

        variante["nome_exibicao"] = nome_vit or variante.get("nome_exibicao") or ""
        if desc_vit:
            variante["descricao"] = desc_vit
        if img_vit:
            variante["imagem_url"] = _imagem_url_resposta(img_vit)
            variante["imagem_caminho"] = img_vit
        variante["preco"] = preco_venda
        variante["ativo"] = ativo_vit
        variante.update(_enriquecer_meta_pausa(cur, id_tenant, vid))
        variante["quantidade"] = variante["estoque"]

        return jsonify(
            success=True,
            dados={
                **variante,
                "modo_vendedor": True,
                "integrado": integrado,
                "campos_readonly": sorted(CAMPOS_READONLY_INTEGRADO) if integrado else [],
                "estoque_somente_leitura": integrado,
            },
            pai=pai,
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/variante/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def salvar_variante_vitrine():
    if (resp := _exigir_edicao()) is not None:
        return resp
    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    vid = int(body.get("id_variante") or body.get("id") or 0)
    if not id_tenant or not vid:
        return jsonify(success=False, message="Dados inválidos."), 400

    nome = (body.get("nome_exibicao") or body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome da variação."), 400

    preco_venda = Decimal(str(body.get("preco") or 0))
    descricao = (body.get("descricao") or "").strip()
    imagem = (body.get("imagem_url") or body.get("imagem_caminho") or "").strip()
    ativo = str(body.get("ativo", "true")).lower() in ("1", "true", "t", "yes", "sim")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pv.id_produto FROM tbl_produto_vendedor pv
            WHERE pv.id_tenant_vendedor = %s AND pv.id_variante = %s
            """,
            (id_tenant, vid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Variação não está na sua vitrine."), 404

        integrado = produto_integrado(cur, id_tenant, int(row[0]))
        if integrado:
            cur.execute(
                """
                UPDATE tbl_produto_vendedor SET
                    nome_vitrine = %s,
                    descricao_vitrine = %s,
                    imagem_url_vitrine = NULLIF(%s, ''),
                    preco_venda = CASE WHEN preco_manual THEN preco_venda ELSE %s END,
                    ativo = %s,
                    atualizado_em = %s
                WHERE id_tenant_vendedor = %s AND id_variante = %s
                """,
                (nome, descricao, imagem, preco_venda, ativo, agora_utc(), id_tenant, vid),
            )
        else:
            return jsonify(success=False, message="Edição completa de variação própria ainda não disponível."), 501

        conn.commit()
        return jsonify(success=True, message="Variação atualizada na vitrine.", id_variante=vid)
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/imagens/lista")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def imagens_lista_vitrine():
    id_tenant = _id_tenant_sessao()
    id_produto = int(request.args.get("id_produto") or 0)
    if not id_tenant or not id_produto:
        return jsonify(success=False, message="Produto inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        ctx = _exigir_produto_vitrine(cur, id_tenant, id_produto)
        if not ctx:
            return jsonify(success=False, message="Produto não está na sua vitrine."), 404

        imagens = listar_imagens_galeria_pai(cur, id_produto)
        if not imagens:
            cur.execute("SELECT imagem_url FROM tbl_produto WHERE id = %s", (id_produto,))
            row = cur.fetchone()
            if row and row[0]:
                cam = row[0]
                imagens.append(
                    {
                        "id": None,
                        "caminho": cam,
                        "url": _imagem_url_resposta(cam),
                        "ordem": 0,
                        "principal": True,
                    }
                )
        return jsonify(
            success=True,
            imagens=imagens,
            total=len(imagens),
            somente_leitura=ctx["integrado"],
            imagem_modo=obter_imagem_modo(cur, id_produto),
            regras_atributo=listar_regras_atributo_imagem(cur, id_produto),
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/estoque/depositos")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def estoque_depositos_vitrine():
    id_tenant = _id_tenant_sessao()
    id_produto = int(request.args.get("id_produto") or 0)
    id_variante = int(request.args.get("id_variante") or 0)
    if not id_tenant or (not id_produto and not id_variante):
        return jsonify(success=False, message="Produto ou variante inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_variante:
            cur.execute(
                """
                SELECT v.id_produto, p.id_tenant
                FROM tbl_produto_variante v
                JOIN tbl_produto p ON p.id = v.id_produto
                JOIN tbl_produto_vendedor pv ON pv.id_variante = v.id AND pv.id_tenant_vendedor = %s
                WHERE v.id = %s
                """,
                (id_tenant, id_variante),
            )
            row = cur.fetchone()
            if not row:
                return jsonify(success=False, message="Variação não está na sua vitrine."), 404
            id_produto = int(row[0])
            id_fornecedor = int(row[1])
        else:
            ctx = _exigir_produto_vitrine(cur, id_tenant, id_produto)
            if not ctx:
                return jsonify(success=False, message="Produto não está na sua vitrine."), 404
            id_fornecedor = int(ctx["id_fornecedor"])

        pausado = False
        if id_variante:
            pausado, _, _ = avaliar_pausa_variante(cur, id_tenant, id_variante)

        vid, depositos, integrado_bling = listar_estoque_por_deposito(
            cur,
            id_fornecedor,
            id_produto,
            id_variante=id_variante or None,
        )
        if pausado:
            for d in depositos:
                d["quantidade"] = 0

        return jsonify(
            success=True,
            id_variante=vid,
            integrado_bling=integrado_bling,
            depositos=depositos,
            somente_leitura=True,
            pausado=pausado,
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/restaurar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def restaurar_vitrine():
    if (resp := _exigir_edicao()) is not None:
        return resp
    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    pid = int(body.get("id_produto") or body.get("id") or 0)
    vid = int(body.get("id_variante") or 0)
    if not id_tenant or (not pid and not vid):
        return jsonify(success=False, message="Dados inválidos."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if vid:
            ok = restaurar_vitrine_variante(cur, id_tenant, vid)
            if not ok:
                return jsonify(success=False, message="Não foi possível restaurar a variação."), 404
            msg = "Variação restaurada ao padrão do fornecedor."
        else:
            n = restaurar_vitrine_produto(cur, id_tenant, pid)
            if n == 0:
                return jsonify(success=False, message="Produto não integrado ou não encontrado."), 404
            msg = f"Produto restaurado ({n} variação(ões))."
        conn.commit()
        return jsonify(success=True, message=msg)
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/ids")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def ids_favoritos():
    """IDs de produtos já salvos pelo tenant (para marcar na rede)."""
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(id_variante, id_produto) FROM tbl_produto_favorito WHERE id_tenant = %s",
            (id_tenant,),
        )
        ids = [r[0] for r in cur.fetchall()]
        return jsonify(success=True, ids=ids)
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/favoritar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def favoritar():
    if not _pode_editar_favoritos():
        return jsonify(success=False, message="Sem permissão para salvar produtos."), 403

    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    id_variante = int(body.get("id_variante") or body.get("id") or 0)
    id_produto = int(body.get("id_produto") or 0)
    if not id_tenant:
        return jsonify(success=False, message="Dados inválidos."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        vid = _resolver_id_variante(cur, id_tenant, id_variante, id_produto)
        if not vid:
            return jsonify(success=False, message="Produto indisponível na rede."), 404
        cur.execute("SELECT id_produto FROM tbl_produto_variante WHERE id = %s", (vid,))
        pid_row = cur.fetchone()
        id_produto = pid_row[0] if pid_row else id_produto

        cur.execute(
            """
            INSERT INTO tbl_produto_favorito (id_tenant, id_produto, id_variante)
            VALUES (%s, %s, %s)
            ON CONFLICT (id_tenant, id_produto) DO UPDATE SET id_variante = EXCLUDED.id_variante
            """,
            (id_tenant, id_produto, vid),
        )
        conn.commit()
        return jsonify(success=True, message="Produto salvo em Meus produtos.")
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/desfavoritar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def desfavoritar():
    if not _pode_editar_favoritos():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    id_variante = int(body.get("id_variante") or body.get("id") or 0)
    id_produto = int(body.get("id_produto") or 0)
    if not id_tenant:
        return jsonify(success=False, message="Dados inválidos."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_variante:
            cur.execute(
                "DELETE FROM tbl_produto_favorito WHERE id_tenant = %s AND id_variante = %s",
                (id_tenant, id_variante),
            )
        elif id_produto:
            cur.execute(
                "DELETE FROM tbl_produto_favorito WHERE id_tenant = %s AND id_produto = %s",
                (id_tenant, id_produto),
            )
        else:
            return jsonify(success=False, message="Dados inválidos."), 400
        conn.commit()
        return jsonify(success=True, message="Produto removido de Meus produtos.")
    finally:
        conn.close()


def _exigir_edicao():
    from global_utils import usuario_tem_permissao

    if session.get("eh_desenvolvedor") or usuario_tem_permissao("produtos.editar"):
        return None
    return jsonify(success=False, message="Sem permissão."), 403


def _id_tenant():
    tid = session.get("id_tenant")
    return int(tid) if tid else None


@vd_meus_produtos_bp.get("/meus-produtos/kits/incluir")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_incluir_pagina():
    return render_template("frm_kit_vendedor_apoio.html")


@vd_meus_produtos_bp.get("/meus-produtos/kits/editar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_editar_pagina():
    return render_template("frm_kit_vendedor_apoio.html")


@vd_meus_produtos_bp.get("/meus-produtos/kits/dados")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def kits_lista():
    id_tenant = _id_tenant()
    busca = (request.args.get("busca") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["k.id_tenant = %s"]
        params: list = [id_tenant]
        if busca:
            where.append("k.nome ILIKE %s")
            params.append(f"%{busca}%")
        cur.execute(
            f"""
            SELECT k.id, k.nome, k.preco_venda, k.usar_preco_sugerido, k.ativo,
                   (SELECT COUNT(*) FROM tbl_kit_vendedor_item i WHERE i.id_kit = k.id)
            FROM tbl_kit_vendedor k
            WHERE {" AND ".join(where)}
            ORDER BY k.atualizado_em DESC
            """,
            params,
        )
        kits = [
            {
                "id": r[0],
                "nome": r[1],
                "preco_venda": float(r[2] or 0),
                "usar_preco_sugerido": bool(r[3]),
                "ativo": bool(r[4]),
                "qtd_itens": int(r[5] or 0),
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, kits=kits)
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/rede-opcoes")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def rede_opcoes():
    """Produtos/variantes da rede para montar kit (favoritos + busca)."""
    id_tenant = _id_tenant()
    busca = (request.args.get("busca") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = [
            "p.id_tenant <> %s",
            "p.publicado = TRUE",
            "p.ativo = TRUE",
            "v.ativo = TRUE",
        ]
        params: list = [id_tenant]
        if busca:
            where.append(
                "(p.nome ILIKE %s OR v.sku ILIKE %s OR v.nome_exibicao ILIKE %s OR t.nome ILIKE %s)"
            )
            like = f"%{busca}%"
            params.extend([like, like, like, like])
        cur.execute(
            f"""
            SELECT v.id, v.sku, v.nome_exibicao, v.preco, v.preco_promocional, v.imagem_url,
                   p.nome AS produto_nome, t.nome AS fornecedor_nome,
                   COALESCE(e.quantidade, 0), p.formato
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE {" AND ".join(where)}
            ORDER BY t.nome, p.nome, v.nome_exibicao
            LIMIT 80
            """,
            params,
        )
        itens = [
            {
                "id_variante": r[0],
                "sku": r[1] or "",
                "nome_exibicao": r[2],
                "preco": float(r[3] or 0),
                "preco_promocional": float(r[4]) if r[4] is not None else None,
                "imagem_url": url_imagem_produto(r[5]),
                "produto_nome": r[6],
                "fornecedor_nome": r[7],
                "estoque": int(r[8] or 0),
                "formato": r[9],
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/kits/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def kit_apoio():
    kid = int((request.get_json(silent=True) or {}).get("id") or 0)
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, descricao, preco_venda, usar_preco_sugerido, ativo FROM tbl_kit_vendedor WHERE id = %s AND id_tenant = %s",
            (kid, id_tenant),
        )
        k = cur.fetchone()
        if not k:
            return jsonify(success=False, message="Kit não encontrado."), 404
        cur.execute(
            """
            SELECT i.id, i.id_variante, i.quantidade, i.ordem,
                   v.sku, v.nome_exibicao, v.preco, v.imagem_url,
                   p.nome, t.nome, COALESCE(e.quantidade, 0)
            FROM tbl_kit_vendedor_item i
            JOIN tbl_produto_variante v ON v.id = i.id_variante
            JOIN tbl_produto p ON p.id = v.id_produto
            JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE i.id_kit = %s
            ORDER BY i.ordem, i.id
            """,
            (kid,),
        )
        itens = [
            {
                "id": r[0],
                "id_variante": r[1],
                "quantidade": r[2],
                "sku": r[4] or "",
                "nome_exibicao": r[5],
                "preco": float(r[6] or 0),
                "imagem_url": url_imagem_produto(r[7]),
                "produto_nome": r[8],
                "fornecedor_nome": r[9],
                "estoque": int(r[10] or 0),
            }
            for r in cur.fetchall()
        ]
        comp = [(x["id_variante"], x["quantidade"]) for x in itens]
        sugerido = float(preco_sugerido_kit(cur, comp))
        estoque_kit = estoque_kit_componentes(cur, comp)
        return jsonify(
            success=True,
            dados={
                "id": k[0],
                "nome": k[1],
                "descricao": k[2] or "",
                "preco_venda": float(k[3] or 0),
                "usar_preco_sugerido": bool(k[4]),
                "ativo": bool(k[5]),
                "preco_sugerido": sugerido,
                "estoque_disponivel": estoque_kit,
                "itens": itens,
            },
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/kits/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_salvar():
    if (resp := _exigir_edicao()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome do kit."), 400
    itens_in = body.get("itens") or []
    if not itens_in:
        return jsonify(success=False, message="Adicione ao menos um item ao kit."), 400

    id_tenant = _id_tenant()
    usar_sug = str(body.get("usar_preco_sugerido", "true")).lower() in ("1", "true", "t", "yes", "sim")
    preco_venda = Decimal(str(body.get("preco_venda") or 0))

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        comp: list[tuple[int, int]] = []
        for raw in itens_in:
            vid = int(raw.get("id_variante") or 0)
            qtd = max(1, int(raw.get("quantidade") or 1))
            if not variante_rede_valida(cur, vid, id_tenant):
                return jsonify(success=False, message=f"Variante {vid} indisponível na rede."), 400
            comp.append((vid, qtd))

        if usar_sug:
            preco_venda = preco_sugerido_kit(cur, comp)

        kid = body.get("id")
        if kid:
            cur.execute(
                """
                UPDATE tbl_kit_vendedor SET nome=%s, descricao=%s, preco_venda=%s,
                    usar_preco_sugerido=%s, ativo=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant=%s RETURNING id
                """,
                (
                    nome,
                    (body.get("descricao") or "").strip(),
                    preco_venda,
                    usar_sug,
                    str(body.get("ativo", "true")).lower() in ("1", "true", "t", "yes", "sim"),
                    agora_utc(),
                    kid,
                    id_tenant,
                ),
            )
            if not cur.fetchone():
                return jsonify(success=False, message="Kit não encontrado."), 404
            kit_id = int(kid)
            cur.execute("DELETE FROM tbl_kit_vendedor_item WHERE id_kit = %s", (kit_id,))
        else:
            cur.execute(
                """
                INSERT INTO tbl_kit_vendedor (id_tenant, nome, descricao, preco_venda, usar_preco_sugerido, ativo, atualizado_em)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    id_tenant,
                    nome,
                    (body.get("descricao") or "").strip(),
                    preco_venda,
                    usar_sug,
                    str(body.get("ativo", "true")).lower() in ("1", "true", "t", "yes", "sim"),
                    agora_utc(),
                ),
            )
            kit_id = cur.fetchone()[0]

        for idx, (vid, qtd) in enumerate(comp):
            cur.execute(
                """
                INSERT INTO tbl_kit_vendedor_item (id_kit, id_variante, quantidade, ordem)
                VALUES (%s, %s, %s, %s)
                """,
                (kit_id, vid, qtd, idx),
            )
        conn.commit()
        return jsonify(success=True, message="Kit salvo.", id=kit_id)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/kits/delete")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_delete():
    if (resp := _exigir_edicao()) is not None:
        return resp
    kid = int((request.get_json(silent=True) or {}).get("id") or 0)
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_kit_vendedor WHERE id = %s AND id_tenant = %s", (kid, id_tenant))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(success=False, message="Kit não encontrado."), 404
        return jsonify(success=True, message="Kit excluído.")
    finally:
        conn.close()
