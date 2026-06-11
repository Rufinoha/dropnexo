# api/bling/sync_produtos.py — sincronização de produtos Bling → DropNexo
from __future__ import annotations

import json
from typing import Any

from api.bling.cliente import listar_produtos, obter_produto
from api.bling.imagens import aplicar_imagens_produto, extrair_urls_imagem_bling
from global_utils import agora_utc


def _garantir_config(cur, id_tenant: int, contexto: str) -> dict:
    cur.execute(
        """
        SELECT fonte_principal, modo_imagem, produtos_modo
        FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    if row:
        return {"fonte_principal": row[0], "modo_imagem": row[1], "produtos_modo": row[2]}
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_config (id_tenant, contexto)
        VALUES (%s, %s)
        RETURNING fonte_principal, modo_imagem, produtos_modo
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    return {"fonte_principal": row[0], "modo_imagem": row[1], "produtos_modo": row[2]}


def _registrar_log(cur, id_tenant: int, contexto: str, status: str, resumo: str, detalhe: str = "") -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_log (
            id_tenant, provedor, contexto, entidade, direcao, status, resumo, detalhe
        ) VALUES (%s, 'bling', %s, 'produto', 'importar', %s, %s, %s)
        """,
        (id_tenant, contexto, status, resumo, detalhe[:4000]),
    )


def _buscar_mapa(cur, id_tenant: int, contexto: str, id_bling: str) -> tuple[int | None, str | None]:
    cur.execute(
        """
        SELECT id_dropnexo, sku FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
          AND entidade = 'produto' AND id_bling = %s
        """,
        (id_tenant, contexto, id_bling),
    )
    row = cur.fetchone()
    if not row:
        return None, None
    return (int(row[0]) if row[0] else None), row[1]


def _upsert_mapa(cur, id_tenant: int, contexto: str, id_bling: str, id_dropnexo: int, sku: str, meta: dict) -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'bling', %s, 'produto', %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling) DO UPDATE SET
            id_dropnexo = EXCLUDED.id_dropnexo,
            sku = EXCLUDED.sku,
            meta = EXCLUDED.meta,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, contexto, id_bling, id_dropnexo, sku, json.dumps(meta), agora_utc()),
    )


def _garantir_variante_padrao(cur, id_produto: int, id_tenant: int, nome: str) -> int:
    cur.execute(
        "SELECT id_variante_padrao FROM tbl_produto WHERE id = %s AND id_tenant = %s",
        (id_produto, id_tenant),
    )
    row = cur.fetchone()
    if row and row[0]:
        return int(row[0])
    cur.execute(
        """
        INSERT INTO tbl_produto_variante (id_produto, nome_exibicao, preco, ativo, ordem, atualizado_em)
        VALUES (%s, %s, 0, TRUE, 0, %s) RETURNING id
        """,
        (id_produto, nome or "Padrão", agora_utc()),
    )
    vid = cur.fetchone()[0]
    cur.execute(
        "UPDATE tbl_produto SET id_variante_padrao = %s, formato = COALESCE(formato, 'S') WHERE id = %s",
        (vid, id_produto),
    )
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, 0, %s) ON CONFLICT (id_variante) DO NOTHING
        """,
        (vid, agora_utc()),
    )
    return int(vid)


def _montar_descricao(produto: dict) -> str:
    partes = [
        (produto.get("descricaoCurta") or "").strip(),
        (produto.get("descricaoComplementar") or "").strip(),
    ]
    return "\n\n".join(p for p in partes if p)


def _produto_ativo(produto: dict) -> bool:
    sit = str(produto.get("situacao") or "A").upper()
    return sit in ("A", "ATIVO", "1", "TRUE")


def _salvar_produto(
    cur,
    *,
    id_tenant: int,
    produto: dict,
    id_produto_existente: int | None,
) -> int:
    sku = (produto.get("codigo") or "").strip()
    nome = (produto.get("nome") or sku or "Produto Bling").strip()
    preco = float(produto.get("preco") or 0)
    preco_custo = produto.get("precoCusto")
    preco_custo = float(preco_custo) if preco_custo not in (None, "") else None
    descricao = _montar_descricao(produto)
    unidade = (produto.get("unidade") or "UN").strip()[:10] or "UN"
    gtin = (produto.get("gtin") or produto.get("ean") or "")[:20] or None
    ncm = (produto.get("ncm") or "")[:10] or None
    ativo = _produto_ativo(produto)
    agora = agora_utc()

    if id_produto_existente:
        cur.execute(
            """
            UPDATE tbl_produto SET
                nome = %s, descricao = %s, sku = %s, preco = %s, preco_custo = %s,
                unidade = %s, gtin = %s, ncm = %s, ativo = %s, atualizado_em = %s
            WHERE id = %s AND id_tenant = %s
            RETURNING id
            """,
            (
                nome,
                descricao or None,
                sku,
                preco,
                preco_custo,
                unidade,
                gtin,
                ncm,
                ativo,
                agora,
                id_produto_existente,
                id_tenant,
            ),
        )
        prod_id = cur.fetchone()[0]
    else:
        cur.execute(
            """
            INSERT INTO tbl_produto (
                id_tenant, nome, descricao, sku, preco, preco_custo, unidade,
                gtin, ncm, ativo, publicado, formato, tipo, atualizado_em
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, 'S', 'P', %s
            ) RETURNING id
            """,
            (
                id_tenant,
                nome,
                descricao or None,
                sku,
                preco,
                preco_custo,
                unidade,
                gtin,
                ncm,
                ativo,
                agora,
            ),
        )
        prod_id = cur.fetchone()[0]

    vid = _garantir_variante_padrao(cur, prod_id, id_tenant, nome)
    cur.execute(
        """
        UPDATE tbl_produto_variante SET
            sku = %s, nome_exibicao = %s, preco = %s, preco_custo = %s, ativo = %s, atualizado_em = %s
        WHERE id = %s
        """,
        (sku, nome, preco, preco_custo, ativo, agora, vid),
    )
    return int(prod_id)


def importar_produtos(
    cur,
    id_tenant: int,
    contexto: str,
) -> dict[str, Any]:
    cfg = _garantir_config(cur, id_tenant, contexto)
    modo = cfg["produtos_modo"]
    if modo not in ("importar", "atualizar"):
        raise ValueError(f"Modo de produtos '{modo}' não permite importação. Altere para Importar ou Atualizar.")

    importados = 0
    atualizados = 0
    ignorados = 0
    erros: list[str] = []

    pagina = 1
    while True:
        lista = listar_produtos(id_tenant, pagina=pagina, limite=100)
        if not lista:
            break

        for item in lista:
            id_bling = str(item.get("id") or "")
            sku_lista = (item.get("codigo") or "").strip()
            try:
                if not sku_lista:
                    ignorados += 1
                    erros.append(f"Bling #{id_bling}: SKU obrigatório.")
                    continue

                detalhe = obter_produto(id_tenant, id_bling) if id_bling else item
                sku = (detalhe.get("codigo") or sku_lista).strip()
                if not sku:
                    ignorados += 1
                    erros.append(f"Bling #{id_bling}: SKU obrigatório.")
                    continue

                id_existente, _ = _buscar_mapa(cur, id_tenant, contexto, id_bling)
                if not id_existente:
                    cur.execute(
                        "SELECT id FROM tbl_produto WHERE id_tenant = %s AND sku = %s",
                        (id_tenant, sku),
                    )
                    row = cur.fetchone()
                    if row:
                        id_existente = int(row[0])

                criando = id_existente is None
                prod_id = _salvar_produto(
                    cur,
                    id_tenant=id_tenant,
                    produto=detalhe,
                    id_produto_existente=id_existente,
                )

                urls = extrair_urls_imagem_bling(detalhe)
                if urls:
                    aplicar_imagens_produto(
                        cur,
                        id_tenant=id_tenant,
                        id_produto=prod_id,
                        sku=sku,
                        urls=urls,
                        modo_imagem=cfg["modo_imagem"],
                    )

                _upsert_mapa(
                    cur,
                    id_tenant,
                    contexto,
                    id_bling,
                    prod_id,
                    sku,
                    {"nome": detalhe.get("nome"), "urls_imagem": urls},
                )

                if criando:
                    importados += 1
                else:
                    atualizados += 1
            except Exception as e:
                ignorados += 1
                erros.append(f"Bling #{id_bling or '?'}: {e}")

        if len(lista) < 100:
            break
        pagina += 1

    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET ultima_sync_produtos = %s, atualizado_em = %s
        WHERE id_tenant = %s AND contexto = %s
        """,
        (agora_utc(), agora_utc(), id_tenant, contexto),
    )

    resumo = f"Importados: {importados}, atualizados: {atualizados}, ignorados: {ignorados}"
    status = "erro" if erros and importados + atualizados == 0 else ("aviso" if erros else "ok")
    _registrar_log(cur, id_tenant, contexto, status, resumo, "\n".join(erros[:50]))

    return {
        "importados": importados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "erros": erros[:20],
        "resumo": resumo,
    }
