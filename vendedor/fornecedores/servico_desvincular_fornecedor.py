"""Desconexão de fornecedor pelo vendedor e tratamento dos produtos da vitrine."""

from __future__ import annotations

import json
from typing import Literal

from global_utils import agora_utc
from fornecedor.catalogo.srotas_catalogo import exigir_sku_unico_tenant, resolver_sku_unico_tenant
from fornecedor.catalogo.servico_estoque_deposito import garantir_linhas_estoque_depositos, sincronizar_total_variante

AcaoProdutos = Literal["excluir", "converter"]


def contar_produtos_vitrine(cur, id_vendedor: int, id_fornecedor: int) -> int:
    cur.execute(
        """
        SELECT COUNT(DISTINCT id_produto)::int
        FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _resolver_categoria_vendedor(cur, id_vendedor: int, id_categoria_forn: int | None) -> int | None:
    if not id_categoria_forn:
        return None
    cur.execute(
        "SELECT nome FROM tbl_categoria WHERE id = %s",
        (id_categoria_forn,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    nome = str(row[0]).strip()
    cur.execute(
        """
        INSERT INTO tbl_categoria (id_tenant, nome)
        VALUES (%s, %s)
        ON CONFLICT (id_tenant, nome) DO UPDATE SET ativo = TRUE
        RETURNING id
        """,
        (id_vendedor, nome),
    )
    cat = cur.fetchone()
    return int(cat[0]) if cat else None


def _sku_unico_clone(cur, id_vendedor: int, sku_base: str | None, id_produto_novo: int) -> str | None:
    sku = (sku_base or "").strip()
    if not sku:
        return None
    candidatos = [sku, f"{sku}-DV", f"{sku}-DV{id_produto_novo}"]
    for cand in candidatos:
        try:
            exigir_sku_unico_tenant(cur, id_vendedor, cand, ignorar_id_produto=id_produto_novo)
            return cand
        except ValueError:
            continue
    return f"DV{id_produto_novo}"


def _copiar_imagens_produto(cur, id_produto_origem: int, id_produto_destino: int) -> dict[int, int]:
    """Copia galeria do pai; retorna mapa id_imagem_antiga -> id_imagem_nova."""
    cur.execute(
        """
        SELECT id, caminho, ordem, principal, COALESCE(origem, 'manual_upload')
        FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem, id
        """,
        (id_produto_origem,),
    )
    mapa: dict[int, int] = {}
    for img_id, caminho, ordem, principal, origem in cur.fetchall():
        cur.execute(
            """
            INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal, origem)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (id_produto_destino, caminho, ordem, principal, origem),
        )
        novo_id = cur.fetchone()[0]
        mapa[int(img_id)] = int(novo_id)
    return mapa


def _copiar_atributos_produto(cur, id_produto_origem: int, id_produto_destino: int) -> None:
    cur.execute(
        "SELECT nome, valores, ordem FROM tbl_produto_atributo WHERE id_produto = %s ORDER BY ordem, nome",
        (id_produto_origem,),
    )
    for nome, valores, ordem in cur.fetchall():
        cur.execute(
            """
            INSERT INTO tbl_produto_atributo (id_produto, nome, valores, ordem)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_produto, nome) DO UPDATE SET valores = EXCLUDED.valores, ordem = EXCLUDED.ordem
            """,
            (id_produto_destino, nome, valores, ordem),
        )


def _clonar_produto_para_vendedor(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    id_produto_origem: int,
) -> dict[int, int]:
    """Clona produto integrado para o tenant do vendedor. Retorna mapa variante_antiga -> variante_nova."""
    cur.execute(
        """
        SELECT nome_vitrine, descricao_vitrine, imagem_url_vitrine
        FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_produto = %s
        ORDER BY id
        LIMIT 1
        """,
        (id_vendedor, id_produto_origem),
    )
    vit = cur.fetchone()
    nome_vit = (vit[0] or "").strip() if vit and vit[0] else None
    desc_vit = (vit[1] or "").strip() if vit and vit[1] else None
    img_vit = (vit[2] or "").strip() if vit and vit[2] else None

    cur.execute(
        """
        SELECT nome, descricao, sku, preco, preco_promocional, unidade, id_categoria, imagem_url,
               ativo, publicado, formato, tipo, preco_custo, gtin, ncm, referencia, condicao,
               peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm, profundidade_cm,
               prazo_envio_dias, moq, marca, grupo, valor_atacado, valor_dropshipping,
               reposicao_estoque, dimensao_caixa_cm, peso_gramas, id_deposito_expedicao,
               cest, origem_fiscal, frete_gratis, volumes, producao, valor_drop, valor_drop_manual
        FROM tbl_produto
        WHERE id = %s AND id_tenant = %s
        """,
        (id_produto_origem, id_fornecedor),
    )
    p = cur.fetchone()
    if not p:
        return {}

    id_categoria = _resolver_categoria_vendedor(cur, id_vendedor, p[6])
    nome = nome_vit or p[0]
    descricao = desc_vit if desc_vit is not None else (p[1] or "")
    imagem_url = img_vit or p[7]

    cur.execute(
        """
        INSERT INTO tbl_produto (
            id_tenant, nome, descricao, sku, preco, preco_promocional, unidade, id_categoria,
            imagem_url, ativo, publicado, formato, tipo, preco_custo, gtin, ncm, referencia,
            condicao, peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm, profundidade_cm,
            prazo_envio_dias, moq, marca, grupo, valor_atacado, valor_dropshipping,
            reposicao_estoque, dimensao_caixa_cm, peso_gramas, id_deposito_expedicao,
            cest, origem_fiscal, frete_gratis, volumes, producao, valor_drop, valor_drop_manual,
            origem, atualizado_em
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual',%s
        )
        RETURNING id
        """,
        (
            id_vendedor,
            nome,
            descricao,
            p[2],
            p[3],
            p[4],
            p[5] or "UN",
            id_categoria,
            imagem_url,
            True,
            False,
            p[10] or "S",
            p[11] or "P",
            p[12],
            p[13],
            p[14],
            p[15],
            p[16],
            p[17],
            p[18],
            p[19],
            p[20],
            p[21],
            p[22],
            p[23] or 1,
            p[24],
            p[25],
            p[26],
            p[27],
            bool(p[28]),
            p[29],
            p[30],
            None,
            p[32],
            p[33],
            bool(p[34]),
            p[35],
            p[36],
            p[37],
            bool(p[38]),
            agora_utc(),
        ),
    )
    id_produto_novo = int(cur.fetchone()[0])
    sku_novo = _sku_unico_clone(cur, id_vendedor, p[2], id_produto_novo)
    if sku_novo:
        cur.execute("UPDATE tbl_produto SET sku = %s WHERE id = %s", (sku_novo, id_produto_novo))

    mapa_imagens = _copiar_imagens_produto(cur, id_produto_origem, id_produto_novo)
    _copiar_atributos_produto(cur, id_produto_origem, id_produto_novo)

    cur.execute(
        """
        SELECT pv.id_variante, pv.preco_venda, pv.preco_fornecedor, pv.ativo, pv.estoque_vitrine,
               pv.nome_vitrine, pv.descricao_vitrine, pv.imagem_url_vitrine
        FROM tbl_produto_vendedor pv
        WHERE pv.id_tenant_vendedor = %s AND pv.id_produto = %s AND pv.id_tenant_fornecedor = %s
        ORDER BY pv.id
        """,
        (id_vendedor, id_produto_origem, id_fornecedor),
    )
    pv_rows = cur.fetchall()
    if not pv_rows:
        return {}

    cur.execute(
        "SELECT nome FROM tbl_produto_atributo WHERE id_produto = %s ORDER BY ordem, nome",
        (id_produto_origem,),
    )
    nomes_attr = [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
    skus_reservados: set[str] = set()

    mapa_variantes: dict[int, int] = {}
    primeiro_vid: int | None = None
    ordem = 0

    for pv_row in pv_rows:
        id_var_origem = int(pv_row[0])
        cur.execute(
            """
            SELECT v.sku, v.nome_exibicao, v.preco, v.preco_promocional, v.preco_custo, v.atributos,
                   v.imagem_url, v.ativo, v.herda_pai, v.peso_liquido_kg, v.peso_bruto_kg,
                   v.altura_cm, v.largura_cm, v.profundidade_cm, v.gtin, v.ncm, v.descricao,
                   v.valor_drop, COALESCE(v.valor_drop_manual, FALSE), v.id_imagem_principal, v.ordem
            FROM tbl_produto_variante v
            WHERE v.id = %s AND v.id_produto = %s
            """,
            (id_var_origem, id_produto_origem),
        )
        v = cur.fetchone()
        if not v:
            continue

        preco_venda = float(pv_row[1] or v[2] or 0)
        preco_custo = float(pv_row[2] or v[4] or 0) if pv_row[2] or v[4] else None
        ativo = bool(pv_row[3])
        estoque = int(pv_row[4] or 0)
        nome_var = (pv_row[5] or "").strip() or v[1]
        desc_var = (pv_row[6] or "").strip() if pv_row[6] else (v[16] or "")
        img_var = (pv_row[7] or "").strip() or v[6]

        atributos = v[5] if isinstance(v[5], dict) else (json.loads(v[5]) if v[5] else {})
        sku_var = (v[0] or "").strip()
        if sku_var:
            try:
                sku_var = resolver_sku_unico_tenant(
                    cur,
                    id_vendedor,
                    sku_novo or sku_var,
                    nomes_attr,
                    atributos,
                    id_produto_novo,
                    skus_reservados,
                )
            except ValueError:
                sku_var = f"DV{id_produto_novo}-{id_var_origem}"
            skus_reservados.add(sku_var)

        id_img_principal = None
        if v[19] and int(v[19]) in mapa_imagens:
            id_img_principal = mapa_imagens[int(v[19])]

        ordem += 1
        cur.execute(
            """
            INSERT INTO tbl_produto_variante (
                id_produto, sku, nome_exibicao, preco, preco_promocional, preco_custo,
                atributos, imagem_url, ativo, ordem, herda_pai, peso_liquido_kg, peso_bruto_kg,
                altura_cm, largura_cm, profundidade_cm, gtin, ncm, descricao,
                valor_drop, valor_drop_manual, id_imagem_principal, atualizado_em
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            RETURNING id
            """,
            (
                id_produto_novo,
                sku_var or None,
                nome_var,
                preco_venda,
                v[3],
                preco_custo,
                json.dumps(atributos, ensure_ascii=False),
                img_var,
                ativo,
                ordem,
                bool(v[8]),
                v[9],
                v[10],
                v[11],
                v[12],
                v[13],
                v[14],
                v[15],
                desc_var,
                v[17],
                bool(v[18]),
                id_img_principal,
                agora_utc(),
            ),
        )
        id_var_nova = int(cur.fetchone()[0])
        mapa_variantes[id_var_origem] = id_var_nova
        if primeiro_vid is None:
            primeiro_vid = id_var_nova

        cur.execute(
            """
            INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
            VALUES (%s, %s, %s)
            ON CONFLICT (id_variante) DO UPDATE SET quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_var_nova, max(0, estoque), agora_utc()),
        )
        garantir_linhas_estoque_depositos(cur, id_vendedor, id_var_nova)
        sincronizar_total_variante(cur, id_var_nova)

    formato = "E" if len(mapa_variantes) > 1 else "S"
    cur.execute(
        """
        UPDATE tbl_produto
        SET formato = %s, id_variante_padrao = %s, atualizado_em = %s
        WHERE id = %s
        """,
        (formato, primeiro_vid, agora_utc(), id_produto_novo),
    )

    if formato == "S" and primeiro_vid:
        cur.execute(
            "SELECT preco, imagem_url FROM tbl_produto_variante WHERE id = %s",
            (primeiro_vid,),
        )
        var_pai = cur.fetchone()
        if var_pai:
            cur.execute(
                """
                UPDATE tbl_produto
                SET preco = %s, imagem_url = COALESCE(NULLIF(imagem_url, ''), %s), atualizado_em = %s
                WHERE id = %s
                """,
                (var_pai[0], var_pai[1], agora_utc(), id_produto_novo),
            )

    return mapa_variantes


def _remover_referencias_variantes(cur, id_vendedor: int, ids_variantes: list[int]) -> None:
    if not ids_variantes:
        return
    cur.execute(
        """
        DELETE FROM tbl_kit_vendedor_item i
        USING tbl_kit_vendedor k
        WHERE i.id_kit = k.id AND k.id_tenant = %s AND i.id_variante = ANY(%s)
        """,
        (id_vendedor, ids_variantes),
    )
    cur.execute(
        "DELETE FROM tbl_produto_favorito WHERE id_tenant = %s AND id_variante = ANY(%s)",
        (id_vendedor, ids_variantes),
    )


def _atualizar_referencias_variantes(cur, id_vendedor: int, mapa: dict[int, int]) -> None:
    if not mapa:
        return
    for id_antigo, id_novo in mapa.items():
        cur.execute(
            """
            UPDATE tbl_kit_vendedor_item i
            SET id_variante = %s
            FROM tbl_kit_vendedor k
            WHERE i.id_kit = k.id AND k.id_tenant = %s AND i.id_variante = %s
            """,
            (id_novo, id_vendedor, id_antigo),
        )
        cur.execute(
            """
            UPDATE tbl_produto_favorito
            SET id_variante = %s, id_produto = (
                SELECT id_produto FROM tbl_produto_variante WHERE id = %s
            )
            WHERE id_tenant = %s AND id_variante = %s
            """,
            (id_novo, id_novo, id_vendedor, id_antigo),
        )


def _excluir_produtos_vitrine(cur, id_vendedor: int, id_fornecedor: int) -> int:
    cur.execute(
        """
        SELECT id_variante FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    ids_variantes = [int(r[0]) for r in cur.fetchall()]
    _remover_referencias_variantes(cur, id_vendedor, ids_variantes)
    cur.execute(
        """
        DELETE FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    return cur.rowcount


def _converter_produtos_vitrine(cur, id_vendedor: int, id_fornecedor: int) -> tuple[int, int]:
    cur.execute(
        """
        SELECT DISTINCT id_produto
        FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        ORDER BY id_produto
        """,
        (id_vendedor, id_fornecedor),
    )
    produtos = [int(r[0]) for r in cur.fetchall()]
    mapa_global: dict[int, int] = {}
    convertidos = 0
    for id_produto in produtos:
        mapa = _clonar_produto_para_vendedor(cur, id_vendedor, id_fornecedor, id_produto)
        if mapa:
            mapa_global.update(mapa)
            convertidos += 1

    _atualizar_referencias_variantes(cur, id_vendedor, mapa_global)
    cur.execute(
        """
        DELETE FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    return convertidos, len(mapa_global)


def desconectar_fornecedor(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    acao_produtos: AcaoProdutos = "excluir",
) -> dict:
    if id_vendedor == id_fornecedor:
        raise ValueError("Operação inválida.")

    cur.execute(
        """
        SELECT id, status FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    vinc = cur.fetchone()
    if not vinc or vinc[1] != "ativo":
        raise ValueError("Vínculo com este fornecedor não está ativo.")

    qtd_vitrine = contar_produtos_vitrine(cur, id_vendedor, id_fornecedor)
    produtos_removidos = 0
    produtos_convertidos = 0
    variantes_convertidas = 0

    if qtd_vitrine > 0:
        if acao_produtos == "converter":
            produtos_convertidos, variantes_convertidas = _converter_produtos_vitrine(
                cur, id_vendedor, id_fornecedor
            )
        else:
            produtos_removidos = _excluir_produtos_vitrine(cur, id_vendedor, id_fornecedor)
    else:
        cur.execute(
            """
            DELETE FROM tbl_produto_vendedor
            WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
            """,
            (id_vendedor, id_fornecedor),
        )

    cur.execute(
        """
        UPDATE tbl_vinculo_vendedor_fornecedor
        SET status = 'inativo', inativado_em = NOW()
        WHERE id = %s AND id_tenant_fornecedor = %s
        """,
        (vinc[0], id_fornecedor),
    )

    return {
        "qtd_produtos_vitrine": qtd_vitrine,
        "produtos_removidos": produtos_removidos,
        "produtos_convertidos": produtos_convertidos,
        "variantes_convertidas": variantes_convertidas,
    }
