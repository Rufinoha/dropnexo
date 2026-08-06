# api/amazon/produtos.py — export completo DropNexo → Amazon (vendedor)
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any
from urllib.parse import quote

from global_utils import agora_utc

_log = logging.getLogger(__name__)
_MAX_PRODUTOS_POR_SYNC = 20
_MAX_IMAGENS = 9


def _f(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def _kg(peso_liq, peso_bruto) -> float | None:
    for cand in (peso_bruto, peso_liq):
        n = _f(cand)
        if n and n > 0:
            return round(n, 3)
    return None


def _parse_atributos(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if str(k).strip() and str(v).strip()}
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}
        except json.JSONDecodeError:
            pass
    return {}


def _condicao_amazon(condicao: str | None) -> str:
    c = (condicao or "").strip().lower()
    if c in ("novo", "new", "n"):
        return "new_new"
    if "usado" in c or c in ("used", "u"):
        return "used_like_new"
    if "recond" in c or "refurbished" in c:
        return "refurbished_refurbished"
    return "new_new"


def _sql_vitrine(ids_produtos: list[int] | None = None) -> tuple[str, list]:
    extra = ""
    params: list = []
    if ids_produtos:
        extra = " AND p.id = ANY(%s)"
        params.append(ids_produtos)
    sql = f"""
        SELECT pv.id, pv.id_variante, pv.id_produto,
               TRIM(COALESCE(NULLIF(v.sku, ''), p.sku, '')) AS sku,
               COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), NULLIF(TRIM(v.nome_exibicao), ''), p.nome) AS titulo,
               COALESCE(NULLIF(TRIM(p.nome), ''), '') AS nome_pai,
               COALESCE(pv.preco_venda, v.preco, p.preco, 0) AS preco,
               LEFT(COALESCE(
                   NULLIF(TRIM(pv.descricao_vitrine), ''),
                   NULLIF(TRIM(v.descricao), ''),
                   NULLIF(TRIM(p.descricao), ''),
                   ''
               ), 10000) AS descricao,
               COALESCE(NULLIF(TRIM(pv.imagem_url_vitrine), ''), v.imagem_url, p.imagem_url) AS imagem,
               COALESCE(ve.quantidade, 0) AS estoque,
               COALESCE(p.condicao, '') AS condicao,
               COALESCE(NULLIF(TRIM(p.marca), ''), '') AS marca,
               COALESCE(NULLIF(TRIM(v.gtin), ''), NULLIF(TRIM(p.gtin), ''), '') AS gtin,
               pv.id_categoria_vendedor,
               COALESCE(p.formato, 'S') AS formato,
               v.atributos,
               COALESCE(v.peso_liquido_kg, p.peso_liquido_kg) AS peso_liq,
               COALESCE(v.peso_bruto_kg, p.peso_bruto_kg) AS peso_bruto,
               COALESCE(v.altura_cm, p.altura_cm) AS altura_cm,
               COALESCE(v.largura_cm, p.largura_cm) AS largura_cm,
               COALESCE(v.profundidade_cm, p.profundidade_cm) AS profundidade_cm
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
          AND COALESCE(v.ativo, TRUE) = TRUE{extra}
        ORDER BY p.id, v.ordem, pv.id
    """
    return sql, params


def _links_imagens(
    cur,
    id_tenant: int,
    *,
    id_produto: int,
    id_variante: int,
    imagem_fallback: str = "",
) -> list[str]:
    from api.bling.imagens_export import (
        coletar_caminhos_galeria_export,
        preparar_links_export,
    )

    caminhos: list[str] = []
    try:
        from vendedor.meus_produtos.servico_meus_produtos import listar_imagens_vitrine

        imgs, _ = listar_imagens_vitrine(cur, id_tenant, int(id_produto))
        for im in imgs or []:
            c = (im.get("caminho") or "").strip()
            if c:
                caminhos.append(c)
    except Exception:
        pass
    if not caminhos:
        caminhos = coletar_caminhos_galeria_export(
            cur,
            id_produto=int(id_produto),
            id_variante=int(id_variante),
            imagem_fallback=imagem_fallback or "",
        )
    return preparar_links_export(caminhos, max_links=_MAX_IMAGENS).get("links") or []


def _montar_attributes(
    *,
    mp: str,
    titulo: str,
    sku: str,
    preco: float,
    estoque: int,
    descricao: str,
    marca: str,
    gtin: str,
    condicao: str,
    links: list[str],
    peso_kg: float | None,
    altura_cm: float | None,
    largura_cm: float | None,
    profundidade_cm: float | None,
    atributos: dict[str, str],
) -> dict[str, Any]:
    def attr_list(value: Any) -> list[dict]:
        return [{"value": value, "marketplace_id": mp}]

    img_url = links[0] if links else ""
    attributes: dict[str, Any] = {
        "item_name": attr_list((titulo or sku or "Produto")[:200]),
        "brand": attr_list((marca or "Generic")[:100]),
        "condition_type": attr_list(_condicao_amazon(condicao)),
        "purchasable_offer": [
            {
                "currency": "BRL",
                "our_price": [{"schedule": [{"value_with_tax": round(float(preco), 2)}]}],
                "marketplace_id": mp,
            }
        ],
        "fulfillment_availability": [
            {
                "fulfillment_channel_code": "DEFAULT",
                "quantity": max(0, int(estoque or 0)),
            }
        ],
    }
    if img_url:
        attributes["main_product_image_locator"] = [
            {"media_location": img_url, "marketplace_id": mp}
        ]
    # Gallery: other_product_image_locator_1..8
    for i, url in enumerate(links[1:9], start=1):
        attributes[f"other_product_image_locator_{i}"] = [
            {"media_location": url, "marketplace_id": mp}
        ]
    if descricao:
        attributes["product_description"] = attr_list(descricao[:2000])
    gtin_limpo = "".join(c for c in (gtin or "") if c.isdigit())
    if len(gtin_limpo) in (8, 12, 13, 14):
        tipo = "ean" if len(gtin_limpo) == 13 else "gtin"
        attributes["externally_assigned_product_identifier"] = [
            {"type": tipo, "value": gtin_limpo, "marketplace_id": mp}
        ]
    if peso_kg and peso_kg > 0:
        attributes["item_package_weight"] = [
            {"value": float(peso_kg), "unit": "kilograms", "marketplace_id": mp}
        ]
    if altura_cm and largura_cm and profundidade_cm:
        if altura_cm > 0 and largura_cm > 0 and profundidade_cm > 0:
            attributes["item_package_dimensions"] = [
                {
                    "length": {"value": float(profundidade_cm), "unit": "centimeters"},
                    "width": {"value": float(largura_cm), "unit": "centimeters"},
                    "height": {"value": float(altura_cm), "unit": "centimeters"},
                    "marketplace_id": mp,
                }
            ]
    if atributos:
        for k, v in list(atributos.items())[:5]:
            kl = k.strip().lower()
            if "cor" in kl or "color" in kl:
                attributes["color"] = attr_list(v[:100])
            elif "tam" in kl or "size" in kl:
                attributes["size"] = attr_list(v[:100])
    return attributes


def _salvar_map(
    cur,
    id_tenant: int,
    id_variante: int,
    id_produto: int,
    sku: str,
    *,
    asin: str = "",
    product_type: str = "",
) -> None:
    id_bling = f"{asin}:{sku}" if asin and sku else str(sku)
    cur.execute(
        """
        DELETE FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        """,
        (id_tenant, id_variante),
    )
    meta = json.dumps(
        {
            "id_produto": id_produto,
            "seller_sku": sku,
            "asin": asin or None,
            "product_type": product_type or None,
        },
        ensure_ascii=False,
    )
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'amazon', 'vendedor', 'produto', %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling) DO UPDATE SET
            id_dropnexo = EXCLUDED.id_dropnexo,
            sku = EXCLUDED.sku,
            meta = EXCLUDED.meta,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, id_bling, id_variante, sku, meta, agora_utc()),
    )


def put_listing_amazon(
    cur,
    id_tenant: int,
    *,
    linha: dict,
) -> dict[str, Any]:
    """Cria ou atualiza listing completo (PUT) para um SKU/variante."""
    from api.amazon.amazon import (
        _mapa_product_type_amazon,
        _marketplace_id,
        _seller_id,
        api_request,
    )

    sku = (linha.get("sku") or "").strip()
    titulo = (linha.get("titulo") or linha.get("nome_pai") or sku or "Produto")[:200]
    if not sku:
        raise RuntimeError(f"«{titulo}»: SKU obrigatório.")
    preco = float(linha.get("preco") or 0)
    if preco <= 0:
        raise RuntimeError(f"Preço inválido para «{titulo}».")

    id_cat = linha.get("id_categoria_vendedor")
    product_type = _mapa_product_type_amazon(
        cur, id_tenant, int(id_cat) if id_cat else None
    )
    if not product_type:
        raise RuntimeError(
            f"«{titulo}»: mapeie o Product Type Amazon em Integrações → Amazon → Mapear categorias."
        )

    links = _links_imagens(
        cur,
        id_tenant,
        id_produto=int(linha["id_produto"]),
        id_variante=int(linha["id_variante"]),
        imagem_fallback=linha.get("imagem") or "",
    )
    if not links:
        raise RuntimeError(f"«{titulo}»: foto pública obrigatória para a Amazon.")

    seller_id = _seller_id(cur, id_tenant)
    if not seller_id:
        raise RuntimeError("Seller ID Amazon ausente. Reconecte a conta.")
    mp = _marketplace_id(cur, id_tenant)

    attrs = _montar_attributes(
        mp=mp,
        titulo=titulo,
        sku=sku,
        preco=preco,
        estoque=int(linha.get("estoque") or 0),
        descricao=linha.get("descricao") or "",
        marca=linha.get("marca") or "",
        gtin=linha.get("gtin") or "",
        condicao=linha.get("condicao") or "",
        links=links,
        peso_kg=_kg(linha.get("peso_liq"), linha.get("peso_bruto")),
        altura_cm=_f(linha.get("altura_cm")),
        largura_cm=_f(linha.get("largura_cm")),
        profundidade_cm=_f(linha.get("profundidade_cm")),
        atributos=_parse_atributos(linha.get("atributos")),
    )

    body = {
        "productType": product_type,
        "requirements": "LISTING",
        "attributes": attrs,
    }
    sku_enc = quote(sku, safe="")
    try:
        data = api_request(
            cur,
            id_tenant,
            "PUT",
            f"/listings/2021-08-01/items/{seller_id}/{sku_enc}",
            params={"marketplaceIds": mp},
            json_body=body,
        )
    except RuntimeError as e:
        msg = str(e)
        if any(x in msg.lower() for x in ("attribute", "required", "missing", "validation")):
            raise RuntimeError(
                f"«{titulo}»: Amazon rejeitou atributos do Product Type «{product_type}». "
                "Complete no Seller Central ou revise o mapeamento."
            ) from e
        raise

    asin = ""
    acao = "atualizado"
    if isinstance(data, dict):
        status = str(data.get("status") or "").upper()
        issues = data.get("issues") or []
        if issues and status in ("INVALID", "INVALIDATED"):
            first = issues[0] if isinstance(issues[0], dict) else {}
            detail = (first.get("message") or first.get("code") or str(first))[:200]
            raise RuntimeError(f"«{titulo}»: Amazon rejeitou ({detail}).")
        summaries = data.get("summaries") or []
        if summaries and isinstance(summaries[0], dict):
            asin = str(summaries[0].get("asin") or "").strip()
        # ACCEPTED sem ASIN ainda = criação em processamento
        if status in ("ACCEPTED", "VALID") and not asin:
            acao = "criado"

    # Se não havia mapa, tratar como criado
    from api.amazon.amazon import _item_ja_vinculado_amazon

    if not _item_ja_vinculado_amazon(cur, id_tenant, int(linha["id_variante"])):
        acao = "criado"

    _salvar_map(
        cur,
        id_tenant,
        int(linha["id_variante"]),
        int(linha["id_produto"]),
        sku,
        asin=asin,
        product_type=product_type,
    )
    return {
        "id_produto": int(linha["id_produto"]),
        "id_variante": int(linha["id_variante"]),
        "sku": sku,
        "titulo": titulo,
        "asin": asin,
        "acao": acao,
        "product_type": product_type,
    }


def publicar_produtos_amazon_completo(cur, id_tenant: int, ids_produtos: list[int]) -> dict:
    """Exporta/atualiza cada SKU com payload completo (imagens numeradas, peso, dims, GTIN…)."""
    from api.amazon.amazon import (
        _buscar_listing_amazon_por_sku,
        carregar_config_amazon,
    )

    ids: list[int] = []
    for x in ids_produtos or []:
        try:
            pid = int(x)
            if pid > 0:
                ids.append(pid)
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise RuntimeError("Selecione ao menos um produto.")

    cfg = carregar_config_amazon(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Conecte a Amazon em Integrações.")
    if not cfg.get("produtos_exportar_auto"):
        raise RuntimeError(
            "Ative a exportação de produtos em Integrações → Amazon → Produtos."
        )

    modo = cfg.get("produtos_modo") or "vincular_sku"
    sql, extra = _sql_vitrine(ids)
    cur.execute(sql, [id_tenant, *extra])
    cols = [
        "pv_id",
        "id_variante",
        "id_produto",
        "sku",
        "titulo",
        "nome_pai",
        "preco",
        "descricao",
        "imagem",
        "estoque",
        "condicao",
        "marca",
        "gtin",
        "id_categoria_vendedor",
        "formato",
        "atributos",
        "peso_liq",
        "peso_bruto",
        "altura_cm",
        "largura_cm",
        "profundidade_cm",
    ]
    linhas = [dict(zip(cols, row)) for row in cur.fetchall()]
    if not linhas:
        raise RuntimeError("Nenhuma variação ativa encontrada nos produtos selecionados.")

    por_produto: dict[int, list[dict]] = defaultdict(list)
    for lin in linhas:
        por_produto[int(lin["id_produto"])].append(lin)

    exportados = 0
    atualizados = 0
    vinculados = 0
    erros: list[str] = []
    resultados: list[dict] = []
    processados = 0
    skus_processados = 0

    for id_produto, variantes in por_produto.items():
        if processados >= _MAX_PRODUTOS_POR_SYNC:
            break
        processados += 1
        titulo_pai = (variantes[0].get("nome_pai") or variantes[0].get("titulo") or f"#{id_produto}")[
            :80
        ]

        for lin in variantes:
            if skus_processados >= _MAX_PRODUTOS_POR_SYNC * 5:
                break
            skus_processados += 1
            sku = (lin.get("sku") or "").strip()
            titulo = (lin.get("titulo") or titulo_pai)[:80]
            from api.amazon.amazon import _item_ja_vinculado_amazon

            map_id = _item_ja_vinculado_amazon(cur, id_tenant, int(lin["id_variante"]))

            try:
                if modo == "vincular_sku" and not map_id:
                    if not sku:
                        raise RuntimeError("SKU obrigatório para vincular.")
                    found = _buscar_listing_amazon_por_sku(cur, id_tenant, sku)
                    if not found:
                        resultados.append(
                            {
                                "id_produto": id_produto,
                                "titulo": titulo,
                                "sku": sku,
                                "status": "erro",
                                "mensagem": "Nenhum listing Amazon com este SKU.",
                            }
                        )
                        continue
                    seller_sku, asin = found
                    _salvar_map(
                        cur,
                        id_tenant,
                        int(lin["id_variante"]),
                        id_produto,
                        seller_sku,
                        asin=asin,
                    )
                    vinculados += 1
                    map_id = f"{asin}:{seller_sku}" if asin else seller_sku

                # Sempre PUT completo (cria ou atualiza todos os campos)
                res = put_listing_amazon(cur, id_tenant, linha=lin)
                if res["acao"] == "criado":
                    exportados += 1
                else:
                    atualizados += 1
                resultados.append(
                    {
                        "id_produto": id_produto,
                        "titulo": titulo,
                        "sku": sku,
                        "status": "ok",
                        "acao": res["acao"],
                        "mensagem": (
                            f"Listing {res['acao']} na Amazon "
                            f"(imagens, preço, estoque, peso/dims, GTIN)."
                        ),
                        "asin": res.get("asin") or "",
                    }
                )
            except Exception as e:
                msg = str(e)[:300]
                if msg not in erros:
                    erros.append(msg)
                resultados.append(
                    {
                        "id_produto": id_produto,
                        "titulo": titulo,
                        "sku": sku,
                        "status": "erro",
                        "mensagem": msg,
                    }
                )

    partes = []
    if exportados:
        partes.append(f"{exportados} criado(s)")
    if atualizados:
        partes.append(f"{atualizados} atualizado(s)")
    if vinculados:
        partes.append(f"{vinculados} vinculado(s)")
    n_err = len([r for r in resultados if r.get("status") == "erro"])
    if n_err:
        partes.append(f"{n_err} com erro")
    msg = " · ".join(partes) + " na Amazon." if partes else "Nenhum produto processado."

    out = {
        "message": msg,
        "total_produtos": len(por_produto),
        "modo": modo,
        "exportados": exportados,
        "atualizados": atualizados,
        "vinculados": vinculados,
        "erros": n_err,
        "resultados": resultados,
    }
    if erros:
        out["detalhes_erros"] = erros[:8]
    return out
