# api/tiktok/produtos.py — export completo DropNexo → TikTok Shop (vendedor)
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

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


def _kg_de_produto(peso_liq, peso_bruto, peso_gramas) -> float:
    for cand in (peso_bruto, peso_liq):
        n = _f(cand)
        if n and n > 0:
            return round(n, 3)
    g = _f(peso_gramas)
    if g and g > 0:
        return round(g / 1000.0, 3)
    return 0.3  # fallback mínimo aceitável


def _dimensoes_cm(alt, larg, prof) -> dict[str, str] | None:
    a, l, p = _f(alt), _f(larg), _f(prof)
    if not a or not l or not p or a <= 0 or l <= 0 or p <= 0:
        return None
    return {
        "length": str(round(p, 2)),
        "width": str(round(l, 2)),
        "height": str(round(a, 2)),
        "unit": "CENTIMETER",
    }


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


def api_request_multipart(
    cur,
    id_tenant: int,
    path: str,
    *,
    files: dict,
    data: dict | None = None,
) -> Any:
    """POST multipart (upload de imagem). Assina sem body JSON."""
    from api.tiktok.tiktok import (
        _calcular_sign,
        _extrair_data,
        _formatar_erro_tiktok,
        _shop_cipher,
        credenciais_tiktok,
        obter_access_token_valido,
        tiktok_api_base,
        TIKTOK_API_TIMEOUT,
        TIKTOK_API_VERSION,
    )
    import time

    app_key, app_secret = credenciais_tiktok()
    token = obter_access_token_valido(cur, id_tenant)
    api_path = path if path.startswith("/") else f"/{path}"
    url = f"{tiktok_api_base()}{api_path}"

    query: dict[str, Any] = {
        "app_key": app_key,
        "timestamp": str(int(time.time())),
        "version": TIKTOK_API_VERSION,
        "access_token": token,
    }
    shop_cipher = _shop_cipher(cur, id_tenant)
    if shop_cipher:
        query["shop_cipher"] = shop_cipher
    query["sign"] = _calcular_sign(app_secret, api_path, query, body="", method="POST")

    try:
        r = requests.post(
            url,
            params=query,
            files=files,
            data=data or {},
            timeout=TIKTOK_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha upload TikTok Shop: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_tiktok(r.status_code, r.text))
    payload = r.json() if r.content else {}
    if isinstance(payload, dict) and payload.get("code") not in (0, "0", None):
        raise RuntimeError(
            _formatar_erro_tiktok(r.status_code, json.dumps(payload, ensure_ascii=False))
        )
    return _extrair_data(payload)


def upload_imagem_tiktok(cur, id_tenant: int, arquivo: Path, *, use_case: str = "MAIN_IMAGE") -> str:
    with arquivo.open("rb") as fh:
        data = api_request_multipart(
            cur,
            id_tenant,
            "/product/202309/images/upload",
            files={"data": (arquivo.name, fh, "image/jpeg")},
            data={"use_case": use_case},
        )
    if not isinstance(data, dict):
        raise RuntimeError("TikTok Shop não retornou URI da imagem.")
    uri = str(data.get("uri") or data.get("img_uri") or data.get("url") or "").strip()
    if not uri:
        # alguns retornos aninham em img_id / img_url
        uri = str(data.get("img_id") or "").strip()
    if not uri:
        raise RuntimeError("TikTok Shop não retornou URI da imagem.")
    return uri


def _uris_imagens_produto(
    cur,
    id_tenant: int,
    *,
    id_produto: int,
    id_variante: int,
    imagem_fallback: str = "",
) -> list[str]:
    from api.bling.imagens_export import (
        caminho_arquivo_cache,
        coletar_caminhos_galeria_export,
        preparar_imagem_export,
    )

    caminhos: list[str] = []
    # Preferir galeria da vitrine do vendedor
    try:
        from vendedor.meus_produtos.servico_meus_produtos import listar_imagens_vitrine

        imgs, _ = listar_imagens_vitrine(cur, id_tenant, int(id_produto))
        for im in imgs or []:
            c = (im.get("caminho") or im.get("url") or "").strip()
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

    uris: list[str] = []
    vistos: set[str] = set()
    for caminho in caminhos:
        chave = (caminho or "").strip().lower()
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        prep = preparar_imagem_export(caminho)
        if not prep.get("ok"):
            continue
        local = caminho_arquivo_cache(prep.get("cache"))
        try:
            if local is not None and local.is_file():
                uri = upload_imagem_tiktok(cur, id_tenant, local)
            else:
                # fallback: baixar URL pública e reenviar
                url = str(prep.get("url") or "").strip()
                if not url:
                    continue
                r = requests.get(url, timeout=30)
                if r.status_code >= 400 or not r.content:
                    continue
                tmp = Path(caminho_arquivo_cache(prep.get("cache")) or "")
                # write temp beside cache if possible
                from tempfile import NamedTemporaryFile

                with NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                    tf.write(r.content)
                    tmp = Path(tf.name)
                try:
                    uri = upload_imagem_tiktok(cur, id_tenant, tmp)
                finally:
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
            if uri and uri not in uris:
                uris.append(uri)
        except Exception as e:
            _log.warning("Upload imagem TikTok falhou (%s): %s", caminho, e)
        if len(uris) >= _MAX_IMAGENS:
            break
    return uris


def obter_warehouse_id(cur, id_tenant: int) -> str:
    """Busca warehouse padrão e persiste em shop_info."""
    from api.tiktok.tiktok import api_request

    cur.execute(
        "SELECT shop_info FROM tbl_integracao_tiktok WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    loja: dict = {}
    if row and row[0]:
        raw = row[0]
        if isinstance(raw, dict):
            loja = dict(raw)
        elif isinstance(raw, str) and raw.strip():
            try:
                loja = json.loads(raw) or {}
            except json.JSONDecodeError:
                loja = {}
    wid = str(loja.get("warehouse_id") or "").strip()
    if wid:
        return wid

    data = api_request(cur, id_tenant, "GET", "/logistics/202309/warehouses")
    warehouses = []
    if isinstance(data, dict):
        warehouses = data.get("warehouses") or data.get("warehouse_list") or []
    elif isinstance(data, list):
        warehouses = data
    escolhido = ""
    for w in warehouses:
        if not isinstance(w, dict):
            continue
        cand = str(w.get("id") or w.get("warehouse_id") or "").strip()
        if not cand:
            continue
        tipo = str(w.get("type") or w.get("warehouse_type") or "").lower()
        if w.get("is_default") or "sales" in tipo or "default" in tipo:
            escolhido = cand
            break
        if not escolhido:
            escolhido = cand
    if not escolhido:
        raise RuntimeError(
            "Nenhum depósito (warehouse) encontrado no TikTok Shop. "
            "Cadastre um warehouse na loja e tente de novo."
        )
    loja["warehouse_id"] = escolhido
    cur.execute(
        """
        UPDATE tbl_integracao_tiktok
        SET shop_info = %s::jsonb, atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (json.dumps(loja, ensure_ascii=False), agora_utc(), id_tenant),
    )
    return escolhido


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
               NULL::numeric AS peso_gramas,
               COALESCE(v.altura_cm, p.altura_cm) AS altura_cm,
               COALESCE(v.largura_cm, p.largura_cm) AS largura_cm,
               COALESCE(v.profundidade_cm, p.profundidade_cm) AS profundidade_cm,
               COALESCE(v.ativo, TRUE) AS variante_ativa
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
          AND COALESCE(v.ativo, TRUE) = TRUE{extra}
        ORDER BY p.id, v.ordem, pv.id
    """
    return sql, params


def _sales_attributes(atributos: dict[str, str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for nome, valor in atributos.items():
        out.append({"name": str(nome)[:100], "value_name": str(valor)[:100]})
    return out


def _montar_sku_payload(
    *,
    sku: str,
    preco: float,
    estoque: int,
    warehouse_id: str,
    gtin: str,
    atributos: dict[str, str],
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "seller_sku": (sku or "")[:100],
        "original_price": str(round(float(preco), 2)),
        "inventory": [
            {
                "warehouse_id": warehouse_id,
                "quantity": max(0, int(estoque or 0)),
            }
        ],
    }
    # formato legado também aceito em algumas regiões
    item["available_stock"] = max(0, int(estoque or 0))
    if atributos:
        item["sales_attributes"] = _sales_attributes(atributos)
    gtin_limpo = "".join(c for c in (gtin or "") if c.isdigit())
    if len(gtin_limpo) in (8, 12, 13, 14):
        item["identifier_code"] = {"code": gtin_limpo, "type": "GTIN"}
    return item


def _product_id_por_variantes(cur, id_tenant: int, ids_variante: list[int]) -> str | None:
    if not ids_variante:
        return None
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'tiktok' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = ANY(%s)
        """,
        (id_tenant, ids_variante),
    )
    for (raw,) in cur.fetchall():
        s = str(raw or "")
        if s:
            return s.split(":", 1)[0]
    return None


def _salvar_maps_produto(
    cur,
    id_tenant: int,
    id_produto: int,
    product_id: str,
    skus_resp: list[dict],
    variantes: list[dict],
) -> None:
    from api.tiktok.tiktok import _salvar_map_produto_tiktok

    # index por seller_sku
    by_sku: dict[str, str] = {}
    for s in skus_resp:
        if not isinstance(s, dict):
            continue
        seller = (s.get("seller_sku") or s.get("sku") or "").strip()
        sid = str(s.get("id") or s.get("sku_id") or "").strip()
        if seller:
            by_sku[seller] = sid

    for v in variantes:
        sku = (v.get("sku") or "").strip()
        sku_id = by_sku.get(sku, "")
        if not sku_id and len(variantes) == 1 and skus_resp:
            sku_id = str(
                (skus_resp[0] or {}).get("id") or (skus_resp[0] or {}).get("sku_id") or ""
            )
        _salvar_map_produto_tiktok(
            cur,
            id_tenant,
            int(v["id_variante"]),
            int(id_produto),
            sku,
            product_id,
            sku_id,
        )


def _criar_ou_atualizar_produto(
    cur,
    id_tenant: int,
    *,
    linhas: list[dict],
    warehouse_id: str,
    atualizar: bool,
) -> dict[str, Any]:
    from api.tiktok.tiktok import _mapa_categoria_tiktok, api_request

    if not linhas:
        raise RuntimeError("Produto sem variações ativas.")

    primeira = linhas[0]
    id_produto = int(primeira["id_produto"])
    titulo = (primeira.get("titulo") or primeira.get("nome_pai") or "Produto")[:255]
    descricao = (primeira.get("descricao") or titulo)[:10000]
    id_cat = primeira.get("id_categoria_vendedor")
    categoria = _mapa_categoria_tiktok(cur, id_tenant, int(id_cat) if id_cat else None)
    if not categoria:
        raise RuntimeError(
            f"«{titulo}»: mapeie a categoria em Integrações → TikTok Shop → Mapear categorias."
        )

    uris = _uris_imagens_produto(
        cur,
        id_tenant,
        id_produto=id_produto,
        id_variante=int(primeira["id_variante"]),
        imagem_fallback=primeira.get("imagem") or "",
    )
    if not uris:
        raise RuntimeError(f"«{titulo}»: envie ao menos 1 imagem (upload TikTok obrigatório).")

    peso = _kg_de_produto(
        primeira.get("peso_liq"), primeira.get("peso_bruto"), primeira.get("peso_gramas")
    )
    dims = _dimensoes_cm(
        primeira.get("altura_cm"), primeira.get("largura_cm"), primeira.get("profundidade_cm")
    )

    skus_payload: list[dict] = []
    for lin in linhas:
        preco = float(lin.get("preco") or 0)
        if preco <= 0:
            raise RuntimeError(f"Preço inválido no SKU «{lin.get('sku') or '?'}».")
        sku = (lin.get("sku") or "").strip()
        if not sku:
            raise RuntimeError(f"«{titulo}»: variação sem SKU.")
        skus_payload.append(
            _montar_sku_payload(
                sku=sku,
                preco=preco,
                estoque=int(lin.get("estoque") or 0),
                warehouse_id=warehouse_id,
                gtin=lin.get("gtin") or "",
                atributos=_parse_atributos(lin.get("atributos")),
            )
        )

    # multi-SKU exige sales_attributes em todos
    if len(skus_payload) > 1:
        for i, lin in enumerate(linhas):
            attrs = _parse_atributos(lin.get("atributos"))
            if not attrs:
                # fallback: Nome da variação
                nome_var = (lin.get("titulo") or lin.get("sku") or f"Opção {i+1}")[:100]
                skus_payload[i]["sales_attributes"] = [
                    {"name": "Variação", "value_name": nome_var}
                ]

    payload: dict[str, Any] = {
        "title": titulo,
        "description": descricao,
        "category_id": str(categoria),
        "main_images": [{"uri": u} for u in uris],
        "skus": skus_payload,
        "package_weight": {"value": str(peso), "unit": "KILOGRAM"},
    }
    if dims:
        payload["package_dimensions"] = dims
    marca = (primeira.get("marca") or "").strip()
    if marca:
        # brand_id exigiria Brands API; envia brand name quando aceito
        payload["brand_name"] = marca[:100]

    ids_var = [int(x["id_variante"]) for x in linhas]
    product_id_existente = _product_id_por_variantes(cur, id_tenant, ids_var)

    if atualizar and product_id_existente:
        data = api_request(
            cur,
            id_tenant,
            "PUT",
            f"/product/202309/products/{product_id_existente}",
            json_body=payload,
        )
        product_id = product_id_existente
        acao = "atualizado"
    else:
        data = api_request(
            cur, id_tenant, "POST", "/product/202309/products", json_body=payload
        )
        product_id = ""
        if isinstance(data, dict):
            product_id = str(data.get("product_id") or data.get("id") or "").strip()
        if not product_id:
            raise RuntimeError(f"«{titulo}»: TikTok Shop não retornou product_id.")
        acao = "criado"

    skus_resp = []
    if isinstance(data, dict):
        skus_resp = data.get("skus") or data.get("sku_list") or []
    if not skus_resp:
        # recarrega detalhe
        try:
            det = api_request(cur, id_tenant, "GET", f"/product/202309/products/{product_id}")
            if isinstance(det, dict):
                skus_resp = det.get("skus") or det.get("sku_list") or []
        except Exception:
            pass

    _salvar_maps_produto(cur, id_tenant, id_produto, product_id, skus_resp, linhas)
    return {
        "id_produto": id_produto,
        "titulo": titulo,
        "product_id": product_id,
        "acao": acao,
        "skus": len(skus_payload),
    }


def publicar_produtos_tiktok_completo(cur, id_tenant: int, ids_produtos: list[int]) -> dict:
    """Exporta/atualiza produtos com campos completos + imagens + variações agrupadas."""
    from api.tiktok.tiktok import (
        _buscar_produto_tiktok_por_sku,
        _salvar_map_produto_tiktok,
        carregar_config_tiktok,
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

    cfg = carregar_config_tiktok(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Conecte o TikTok Shop em Integrações.")
    if not cfg.get("produtos_exportar_auto"):
        raise RuntimeError(
            "Ative a exportação de produtos em Integrações → TikTok Shop → Produtos."
        )

    modo = cfg.get("produtos_modo") or "vincular_sku"
    warehouse_id = obter_warehouse_id(cur, id_tenant)

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
        "peso_gramas",
        "altura_cm",
        "largura_cm",
        "profundidade_cm",
        "variante_ativa",
    ]
    linhas_raw = [dict(zip(cols, row)) for row in cur.fetchall()]
    if not linhas_raw:
        raise RuntimeError("Nenhuma variação ativa encontrada nos produtos selecionados.")

    por_produto: dict[int, list[dict]] = defaultdict(list)
    for lin in linhas_raw:
        por_produto[int(lin["id_produto"])].append(lin)

    exportados = 0
    atualizados = 0
    vinculados = 0
    erros: list[str] = []
    resultados: list[dict] = []
    processados = 0

    for id_produto, variantes in por_produto.items():
        if processados >= _MAX_PRODUTOS_POR_SYNC:
            break
        processados += 1
        titulo = (variantes[0].get("titulo") or variantes[0].get("nome_pai") or f"#{id_produto}")[
            :80
        ]
        ids_var = [int(v["id_variante"]) for v in variantes]
        ja_tem = _product_id_por_variantes(cur, id_tenant, ids_var)

        try:
            if modo == "vincular_sku" and not ja_tem:
                # tenta vincular pelo SKU da primeira variação
                for v in variantes:
                    sku = (v.get("sku") or "").strip()
                    if not sku:
                        continue
                    found = _buscar_produto_tiktok_por_sku(cur, id_tenant, sku)
                    if not found:
                        continue
                    product_id, sku_id = found
                    _salvar_map_produto_tiktok(
                        cur,
                        id_tenant,
                        int(v["id_variante"]),
                        id_produto,
                        sku,
                        product_id,
                        sku_id,
                    )
                    ja_tem = product_id
                    vinculados += 1
                    break
                if not ja_tem:
                    resultados.append(
                        {
                            "id_produto": id_produto,
                            "titulo": titulo,
                            "status": "erro",
                            "mensagem": "Nenhum SKU correspondente no TikTok Shop para vincular.",
                        }
                    )
                    continue

            # Sempre atualiza conteúdo completo se já existe vínculo; senão cria.
            res = _criar_ou_atualizar_produto(
                cur,
                id_tenant,
                linhas=variantes,
                warehouse_id=warehouse_id,
                atualizar=bool(ja_tem),
            )
            if res["acao"] == "criado":
                exportados += 1
            else:
                atualizados += 1
            resultados.append(
                {
                    "id_produto": id_produto,
                    "titulo": titulo,
                    "status": "ok",
                    "acao": res["acao"],
                    "mensagem": (
                        f"Produto {res['acao']} no TikTok Shop "
                        f"({res['skus']} SKU(s), imagens e dados completos)."
                    ),
                    "product_id": res["product_id"],
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
    msg = " · ".join(partes) + " no TikTok Shop." if partes else "Nenhum produto processado."
    if len(por_produto) > _MAX_PRODUTOS_POR_SYNC and processados >= _MAX_PRODUTOS_POR_SYNC:
        msg += f" Limite de {_MAX_PRODUTOS_POR_SYNC} produtos por sync — execute novamente."

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
