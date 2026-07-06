"""Regras de vitrine do vendedor: pausa, estoque efetivo e campos somente leitura."""

from __future__ import annotations

from vendedor.precificacao.servico_precificacao_vendedor import precificar_na_integracao
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
