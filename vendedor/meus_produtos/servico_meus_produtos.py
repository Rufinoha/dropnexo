# vendedor/meus_produtos/servico_meus_produtos.py — serviços de catálogo próprio do vendedor
from __future__ import annotations

# ── servico_categoria_vendedor ────────────────────────

"""Categoria do vendedor em produtos da vitrine (integrados e próprios)."""


from global_utils import agora_utc


def filtro_categoria_sem(id_categoria: str) -> bool:
    return (id_categoria or "").strip().lower() == "sem"


def sql_filtro_categoria_integrado(
    id_categoria: str,
    id_tenant: int,
) -> tuple[str | None, list]:
    """Fragmento SQL + params para filtrar produtos integrados por categoria do vendedor."""
    cat = (id_categoria or "").strip()
    if not cat:
        return None, []
    if filtro_categoria_sem(cat):
        return (
            """NOT EXISTS (
                SELECT 1 FROM tbl_produto_vendedor pv_cat
                WHERE pv_cat.id_produto = p.id AND pv_cat.id_tenant_vendedor = %s
                  AND pv_cat.id_categoria_vendedor IS NOT NULL
            )""",
            [id_tenant],
        )
    try:
        cid = int(cat)
    except (TypeError, ValueError):
        return None, []
    return (
        """EXISTS (
            SELECT 1 FROM tbl_produto_vendedor pv_cat
            WHERE pv_cat.id_produto = p.id AND pv_cat.id_tenant_vendedor = %s
              AND pv_cat.id_categoria_vendedor = %s
        )""",
        [id_tenant, cid],
    )


def sql_filtro_categoria_proprio(id_categoria: str) -> tuple[str | None, list]:
    """Fragmento SQL + params para filtrar produtos próprios por categoria."""
    cat = (id_categoria or "").strip()
    if not cat:
        return None, []
    if filtro_categoria_sem(cat):
        return "p.id_categoria IS NULL", []
    try:
        return "p.id_categoria = %s", [int(cat)]
    except (TypeError, ValueError):
        return None, []


def categoria_pertence_vendedor(cur, id_vendedor: int, id_categoria: int) -> bool:
    cur.execute(
        "SELECT 1 FROM tbl_categoria WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
        (id_categoria, id_vendedor),
    )
    return bool(cur.fetchone())


def associar_categoria_produtos(
    cur,
    id_vendedor: int,
    ids: list[int],
    id_categoria: int | None,
) -> int:
    """Associa categoria do vendedor a produtos próprios ou integrados. Retorna qtd de produtos."""
    if id_categoria is not None and not categoria_pertence_vendedor(cur, id_vendedor, id_categoria):
        raise ValueError("Categoria inválida.")

    atualizados = 0
    agora = agora_utc()
    for pid in ids:
        if pid < 0:
            continue
        cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (pid,))
        row = cur.fetchone()
        if not row:
            continue
        if int(row[0]) == id_vendedor:
            cur.execute(
                """
                UPDATE tbl_produto
                SET id_categoria = %s, atualizado_em = %s
                WHERE id = %s AND id_tenant = %s
                """,
                (id_categoria, agora, pid, id_vendedor),
            )
        else:
            cur.execute(
                """
                UPDATE tbl_produto_vendedor
                SET id_categoria_vendedor = %s, atualizado_em = %s
                WHERE id_tenant_vendedor = %s AND id_produto = %s
                """,
                (id_categoria, agora, id_vendedor, pid),
            )
        if cur.rowcount:
            atualizados += 1
    return atualizados


# ── servico_fornecedor_apoio ──────────────────────────

"""Dados do fornecedor de origem para o apoio de produto integrado (vendedor)."""


from fornecedor.parametros.requisitos import carregar_contato_responsavel_fornecedor, carregar_requisitos


def _endereco_linha(
    logradouro: str | None,
    numero: str | None,
    complemento: str | None,
    bairro: str | None,
    cidade: str | None,
    uf: str | None,
    cep: str | None,
) -> str:
    partes: list[str] = []
    rua = " ".join(p for p in [(logradouro or "").strip(), (numero or "").strip()] if p)
    if rua:
        partes.append(rua)
    if (complemento or "").strip():
        partes.append(complemento.strip())
    if (bairro or "").strip():
        partes.append(bairro.strip())
    loc = ""
    if (cidade or "").strip():
        loc = cidade.strip()
    if (uf or "").strip():
        loc = f"{loc}/{uf.strip()}" if loc else uf.strip()
    if loc:
        partes.append(loc)
    if (cep or "").strip():
        partes.append(f"CEP {cep.strip()}")
    return " · ".join(partes)


def montar_fornecedor_produto_apoio(cur, id_vendedor: int, id_fornecedor: int) -> dict | None:
    cur.execute(
        """
        SELECT t.id,
               COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), t.nome),
               COALESCE(NULLIF(TRIM(t.razao_social), ''), t.nome),
               t.slug,
               t.documento,
               t.tipo_pessoa,
               t.cidade,
               t.uf,
               t.logradouro,
               t.numero,
               t.complemento,
               t.bairro,
               t.cep,
               t.telefone_comercial,
               t.celular_comercial,
               t.email_comercial,
               t.site,
               COALESCE(v.status, 'nenhum'),
               (SELECT COUNT(*)::int FROM tbl_produto p
                WHERE p.id_tenant = t.id AND p.ativo = TRUE AND p.publicado = TRUE)
        FROM tbl_tenant t
        LEFT JOIN tbl_vinculo_vendedor_fornecedor v
            ON v.id_tenant_fornecedor = t.id AND v.id_tenant_vendedor = %s
        WHERE t.id = %s AND t.ativo = TRUE
        """,
        (id_vendedor, id_fornecedor),
    )
    row = cur.fetchone()
    if not row:
        return None

    cur.execute(
        """
        SELECT s.nome
        FROM tbl_fornecedor_segmento fs
        JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
        WHERE fs.id_tenant = %s
        ORDER BY s.nome
        LIMIT 12
        """,
        (id_fornecedor,),
    )
    segmentos = [r[0] for r in cur.fetchall()]

    req = carregar_requisitos(cur, id_fornecedor)
    contato = None
    if req.get("mostrar_contato_vendedor", True):
        contato = carregar_contato_responsavel_fornecedor(cur, id_fornecedor)

    telefone = (row[13] or "").strip() or (row[14] or "").strip()
    return {
        "id": int(row[0]),
        "nome": row[1] or "",
        "razao_social": row[2] or "",
        "slug": row[3] or "",
        "documento": row[4] or "",
        "tipo_pessoa": row[5] or "J",
        "cidade": row[6] or "",
        "uf": row[7] or "",
        "endereco": _endereco_linha(row[8], row[9], row[10], row[11], row[6], row[7], row[12]),
        "telefone": telefone,
        "celular": (row[14] or "").strip(),
        "email": (row[15] or "").strip(),
        "site": (row[16] or "").strip(),
        "status_vinculo": row[17] or "nenhum",
        "qtd_produtos": int(row[18] or 0),
        "segmentos": segmentos,
        "contato": contato,
        "url_loja": f"/fornecedores/loja?id={int(row[0])}",
    }


# ── servico_deposito_vendedor ─────────────────────────

"""Espelha depósitos do fornecedor na conta do vendedor ao integrar produtos."""


from global_utils import agora_utc

_DEP_COLS = """
    nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
    remetente_nome, remetente_documento, principal
"""


def _depositos_do_produto(cur, id_fornecedor: int, id_produto: int) -> list[int]:
    """Depósitos do fornecedor usados pelo produto (estoque, expedição ou principal)."""
    ids: set[int] = set()
    cur.execute(
        """
        SELECT DISTINCT ped.id_deposito
        FROM tbl_produto_estoque_deposito ped
        JOIN tbl_produto_variante v ON v.id = ped.id_variante
        WHERE v.id_produto = %s
        """,
        (id_produto,),
    )
    ids.update(int(r[0]) for r in cur.fetchall() if r and r[0])

    cur.execute(
        "SELECT id_deposito_expedicao FROM tbl_produto WHERE id = %s AND id_tenant = %s",
        (id_produto, id_fornecedor),
    )
    row = cur.fetchone()
    if row and row[0]:
        ids.add(int(row[0]))

    if not ids:
        cur.execute(
            """
            SELECT id FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY principal DESC, id
            LIMIT 1
            """,
            (id_fornecedor,),
        )
        principal = cur.fetchone()
        if principal and principal[0]:
            ids.add(int(principal[0]))

    return sorted(ids)


def espelhar_depositos_fornecedor(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    *,
    id_produto: int | None = None,
) -> int:
    """
    Cria depósitos espelho (somente leitura) no vendedor.
    Se id_produto informado, espelha depósitos usados pelo produto
    (estoque por filial, depósito de expedição ou principal do fornecedor).
    """
    if id_produto:
        ids_dep = _depositos_do_produto(cur, id_fornecedor, id_produto)
        if not ids_dep:
            return 0
        cur.execute(
            f"""
            SELECT d.id, {_DEP_COLS}
            FROM tbl_deposito_expedicao d
            WHERE d.id_tenant = %s AND d.ativo = TRUE AND d.id = ANY(%s)
            ORDER BY d.principal DESC, d.nome
            """,
            (id_fornecedor, ids_dep),
        )
        rows = cur.fetchall()
    else:
        cur.execute(
            f"""
            SELECT d.id, {_DEP_COLS}
            FROM tbl_deposito_expedicao d
            WHERE d.id_tenant = %s AND d.ativo = TRUE
            ORDER BY d.principal DESC, d.nome
            """,
            (id_fornecedor,),
        )
        rows = cur.fetchall()
    criados = 0
    for row in rows:
        id_dep_forn = int(row[0])
        cur.execute(
            """
            SELECT id FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND id_deposito_espelho = %s
            LIMIT 1
            """,
            (id_vendedor, id_dep_forn),
        )
        if cur.fetchone():
            continue
        cur.execute(
            f"""
            INSERT INTO tbl_deposito_expedicao (
                id_tenant, nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
                remetente_nome, remetente_documento, principal, ativo,
                id_deposito_espelho, id_tenant_espelho, espelho_somente_leitura, atualizado_em
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE,
                %s, %s, TRUE, %s
            )
            """,
            (
                id_vendedor,
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                bool(row[11]),
                id_dep_forn,
                id_fornecedor,
                agora_utc(),
            ),
        )
        criados += 1
    return criados


def sincronizar_espelhos_integrados(cur, id_vendedor: int) -> int:
    """Garante espelhos para produtos já integrados (idempotente)."""
    cur.execute(
        """
        SELECT DISTINCT pv.id_tenant_fornecedor, pv.id_produto
        FROM tbl_produto_vendedor pv
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
        """,
        (id_vendedor,),
    )
    total = 0
    for id_forn, id_prod in cur.fetchall():
        total += espelhar_depositos_fornecedor(
            cur, id_vendedor, int(id_forn), id_produto=int(id_prod)
        )
    return total


# ── servico_listagem_proprio ──────────────────────────

"""Listagem de produtos próprios do vendedor (id_tenant = vendedor)."""


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
            frag, frag_params = sql_filtro_categoria_proprio(id_categoria)
            if frag:
                where.append(frag)
                params.extend(frag_params)
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
        frag, frag_params = sql_filtro_categoria_proprio(id_categoria)
        if frag:
            where.append(frag)
            params.extend(frag_params)
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


# ── servico_vitrine_vendedor ──────────────────────────

"""Regras de vitrine do vendedor: pausa, estoque efetivo e campos somente leitura."""


from vendedor.precificacao.srotas_precificacao import precificar_na_integracao
from global_utils import agora_utc

MOTIVOS_PAUSA: dict[str, str] = {
    "fornecedor_oculto_rede": "O fornecedor ocultou a empresa na rede de vendedores.",
    "produto_despublicado": "O fornecedor retirou este produto da rede.",
    "produto_inativo": "O produto foi desativado pelo fornecedor.",
    "variante_inativa": "Esta variação foi desativada pelo fornecedor.",
    "vinculo_inativo": "O vínculo com o fornecedor não está ativo.",
}

CAMPOS_READONLY_INTEGRADO = frozenset({
    "sku",
    "formato",
    "valor_drop",
    "unidade",
    "condicao",
    "marca",
    "peso_liquido_kg",
    "peso_bruto_kg",
    "largura_cm",
    "altura_cm",
    "profundidade_cm",
    "itens_por_caixa",
    "gtin",
    "ncm",
    "quantidade",
})


def mensagem_pausa(motivo: str | None) -> str:
    if not motivo:
        return ""
    return MOTIVOS_PAUSA.get(motivo, "Produto pausado na vitrine.")


def produto_integrado(cur, id_tenant_vendedor: int, id_produto: int) -> bool:
    cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    if not row:
        return False
    return int(row[0]) != int(id_tenant_vendedor)


def _motivo_tempo_real(
    *,
    id_tenant_produto: int,
    id_tenant_vendedor: int,
    produto_ativo: bool,
    produto_publicado: bool,
    variante_ativa: bool,
    visivel_rede: bool,
    vinculo_status: str | None,
) -> str | None:
    if id_tenant_produto == id_tenant_vendedor:
        return None
    if (vinculo_status or "").lower() != "ativo":
        return "vinculo_inativo"
    if not visivel_rede:
        return "fornecedor_oculto_rede"
    if not produto_publicado:
        return "produto_despublicado"
    if not produto_ativo:
        return "produto_inativo"
    if not variante_ativa:
        return "variante_inativa"
    return None


def avaliar_pausa_variante(cur, id_tenant_vendedor: int, id_variante: int) -> tuple[bool, str | None, str]:
    """Retorna (pausado, codigo_motivo, mensagem)."""
    cur.execute(
        """
        SELECT pv.pausado_motivo,
               p.id_tenant, p.ativo, p.publicado,
               v.ativo,
               COALESCE(r.visivel_rede_vendedor, FALSE),
               vinc.status
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_fornecedor_requisitos_vendedor r ON r.id_tenant = p.id_tenant
        LEFT JOIN tbl_vinculo_vendedor_fornecedor vinc
            ON vinc.id_tenant_fornecedor = p.id_tenant
           AND vinc.id_tenant_vendedor = pv.id_tenant_vendedor
        WHERE pv.id_tenant_vendedor = %s AND pv.id_variante = %s
        """,
        (id_tenant_vendedor, id_variante),
    )
    row = cur.fetchone()
    if not row:
        return False, None, ""

    pausado_persistido = (row[0] or "").strip() or None
    motivo_rt = _motivo_tempo_real(
        id_tenant_produto=int(row[1]),
        id_tenant_vendedor=id_tenant_vendedor,
        produto_ativo=bool(row[2]),
        produto_publicado=bool(row[3]),
        variante_ativa=bool(row[4]),
        visivel_rede=bool(row[5]),
        vinculo_status=row[6],
    )
    if motivo_rt:
        return True, motivo_rt, mensagem_pausa(motivo_rt)
    if pausado_persistido:
        return True, pausado_persistido, mensagem_pausa(pausado_persistido)
    return False, None, ""


def estoque_real_variante(cur, id_variante: int) -> int:
    cur.execute(
        "SELECT COALESCE(quantidade, 0) FROM tbl_produto_variante_estoque WHERE id_variante = %s",
        (id_variante,),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def estoque_efetivo(cur, id_tenant_vendedor: int, id_variante: int) -> int:
    pausado, _, _ = avaliar_pausa_variante(cur, id_tenant_vendedor, id_variante)
    if pausado:
        return 0
    return estoque_real_variante(cur, id_variante)


def pausar_vitrine_fornecedor(cur, id_fornecedor: int, motivo: str = "fornecedor_oculto_rede") -> int:
    cur.execute(
        """
        UPDATE tbl_produto_vendedor
        SET pausado_motivo = %s,
            pausado_em = %s,
            estoque_vitrine = 0,
            atualizado_em = %s
        WHERE id_tenant_fornecedor = %s
          AND (pausado_motivo IS DISTINCT FROM %s OR pausado_motivo IS NULL)
        """,
        (motivo, agora_utc(), agora_utc(), id_fornecedor, motivo),
    )
    return int(cur.rowcount or 0)


def despausar_vitrine_fornecedor(cur, id_fornecedor: int) -> int:
    cur.execute(
        """
        UPDATE tbl_produto_vendedor
        SET pausado_motivo = NULL,
            pausado_em = NULL,
            atualizado_em = %s
        WHERE id_tenant_fornecedor = %s
          AND pausado_motivo = 'fornecedor_oculto_rede'
        """,
        (agora_utc(), id_fornecedor),
    )
    return int(cur.rowcount or 0)


def restaurar_vitrine_produto(cur, id_tenant_vendedor: int, id_produto: int) -> int:
    if not produto_integrado(cur, id_tenant_vendedor, id_produto):
        return 0

    cur.execute(
        """
        SELECT pv.id, pv.id_variante, p.id_tenant, p.id_categoria,
               COALESCE(NULLIF(v.valor_drop, 0), NULLIF(p.valor_drop, 0), v.preco) AS preco_drop
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        WHERE pv.id_tenant_vendedor = %s AND pv.id_produto = %s
        """,
        (id_tenant_vendedor, id_produto),
    )
    rows = cur.fetchall()
    n = 0
    for pv_id, _vid, id_forn, id_cat, preco_drop in rows:
        preco_venda = precificar_na_integracao(
            cur, id_tenant_vendedor, int(id_forn), id_cat, float(preco_drop or 0)
        )
        cur.execute(
            """
            UPDATE tbl_produto_vendedor SET
                nome_vitrine = NULL,
                descricao_vitrine = NULL,
                imagem_url_vitrine = NULL,
                preco_manual = FALSE,
                preco_venda = %s,
                pausado_motivo = NULL,
                pausado_em = NULL,
                atualizado_em = %s
            WHERE id = %s
            """,
            (preco_venda, agora_utc(), pv_id),
        )
        n += 1
    return n


def restaurar_vitrine_variante(cur, id_tenant_vendedor: int, id_variante: int) -> bool:
    cur.execute(
        """
        SELECT pv.id, p.id, p.id_tenant, p.id_categoria,
               COALESCE(NULLIF(v.valor_drop, 0), NULLIF(p.valor_drop, 0), v.preco) AS preco_drop
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        WHERE pv.id_tenant_vendedor = %s AND pv.id_variante = %s
        """,
        (id_tenant_vendedor, id_variante),
    )
    row = cur.fetchone()
    if not row:
        return False
    if not produto_integrado(cur, id_tenant_vendedor, int(row[1])):
        return False

    preco_venda = precificar_na_integracao(
        cur, id_tenant_vendedor, int(row[2]), row[3], float(row[4] or 0)
    )
    cur.execute(
        """
        UPDATE tbl_produto_vendedor SET
            nome_vitrine = NULL,
            descricao_vitrine = NULL,
            imagem_url_vitrine = NULL,
            preco_manual = FALSE,
            preco_venda = %s,
            pausado_motivo = NULL,
            pausado_em = NULL,
            atualizado_em = %s
        WHERE id = %s
        """,
        (preco_venda, agora_utc(), row[0]),
    )
    return True
