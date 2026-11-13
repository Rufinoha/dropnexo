"""Sincronização produtos/estoque da API do parceiro → catálogo DropNexo."""
from __future__ import annotations

from typing import Any

from api.api_externa import cliente, servico
from fornecedor.importacao.motor_csv import (
    _upsert_produto,
    _upsert_variacao,
    aplicar_imagens_importacao,
    extrair_urls_imagem,
)


def _txt(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _bool_txt(v: Any, default: str = "1") -> str:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return "1" if v else "0"
    s = str(v).strip().lower()
    if s in {"1", "true", "sim", "yes", "s", "publicado"}:
        return "1"
    if s in {"0", "false", "nao", "não", "no", "n"}:
        return "0"
    return default


def _qty_from_item(item: dict) -> str:
    wh = item.get("warehouses") or item.get("depositos") or []
    if isinstance(wh, list) and wh:
        total = 0
        for w in wh:
            if not isinstance(w, dict):
                continue
            try:
                total += int(float(w.get("quantidade") or w.get("qty") or 0))
            except (TypeError, ValueError):
                pass
        return str(max(0, total))
    return _txt(item.get("quantidade") if item.get("quantidade") is not None else item.get("estoque"))


def _imagens(item: dict) -> str:
    imgs = item.get("imagens") or item.get("images") or []
    if isinstance(imgs, str):
        return imgs
    if isinstance(imgs, list):
        urls = []
        for i in imgs:
            if isinstance(i, str) and i.strip():
                urls.append(i.strip())
            elif isinstance(i, dict):
                u = i.get("url") or i.get("src") or ""
                if u:
                    urls.append(str(u).strip())
        return ";".join(urls)
    return ""


def _atributos(item: dict) -> str:
    atr = item.get("atributos") or item.get("attributes") or {}
    if isinstance(atr, str):
        return atr
    if isinstance(atr, dict):
        partes = []
        for k, v in atr.items():
            if k is None or v is None:
                continue
            partes.append(f"{k}={v}")
        return ";".join(partes)
    return ""


def produto_para_valores(item: dict) -> dict[str, str]:
    sku = _txt(item.get("sku"))
    sku_pai = _txt(item.get("sku_pai") or item.get("parent_sku"))
    nome = _txt(item.get("nome") or item.get("name") or sku)
    desc = _txt(item.get("descricao") or item.get("description") or nome)
    valores = {
        "sku": sku,
        "sku_pai": sku_pai,
        "nome": nome,
        "descricao": desc,
        "preco": _txt(item.get("preco") if item.get("preco") is not None else item.get("price")),
        "preco_promocional": _txt(item.get("preco_promocional") or item.get("sale_price")),
        "preco_custo": _txt(item.get("preco_custo") or item.get("cost")),
        "unidade": _txt(item.get("unidade") or item.get("unit") or "UN") or "UN",
        "quantidade": _qty_from_item(item) or "0",
        "gtin": _txt(item.get("gtin") or item.get("ean")),
        "ncm": _txt(item.get("ncm")),
        "origem_fiscal": _txt(item.get("origem_fiscal") or "0") or "0",
        "marca": _txt(item.get("marca") or item.get("brand")),
        "categoria": _txt(item.get("categoria") or item.get("category")),
        "peso_bruto_kg": _txt(item.get("peso_bruto_kg") or item.get("weight_kg") or "0.1") or "0.1",
        "altura_cm": _txt(item.get("altura_cm") or item.get("height_cm") or "1") or "1",
        "largura_cm": _txt(item.get("largura_cm") or item.get("width_cm") or "1") or "1",
        "profundidade_cm": _txt(
            item.get("profundidade_cm") or item.get("length_cm") or item.get("depth_cm") or "1"
        )
        or "1",
        "publicado": _bool_txt(item.get("publicado") if "publicado" in item else True),
        "imagens": _imagens(item),
        "atributos": _atributos(item),
        "nome_variacao": _txt(item.get("nome_variacao") or item.get("variant_name")),
    }
    return valores


def _aplicar_produto(cur, id_tenant: int, item: dict, *, pode_criar: bool, pode_atualizar: bool) -> str:
    valores = produto_para_valores(item)
    sku = valores.get("sku") or ""
    if not sku:
        raise ValueError("Produto sem SKU.")
    cur.execute(
        "SELECT id FROM tbl_produto WHERE id_tenant = %s AND TRIM(sku) = %s LIMIT 1",
        (int(id_tenant), sku),
    )
    existe_pai = cur.fetchone()
    if valores.get("sku_pai"):
        if not pode_criar and not pode_atualizar:
            return "ignorado"
        # variação
        cur.execute(
            "SELECT id FROM tbl_produto WHERE id_tenant = %s AND TRIM(sku) = %s LIMIT 1",
            (int(id_tenant), valores["sku_pai"]),
        )
        if not cur.fetchone():
            raise ValueError(f"SKU pai {valores['sku_pai']} não encontrado para variação {sku}.")
        _pai, _vid, criada = _upsert_variacao(cur, id_tenant=id_tenant, valores=valores)
        return "inserido" if criada else "atualizado"

    if existe_pai and not pode_atualizar:
        return "ignorado"
    if not existe_pai and not pode_criar:
        return "ignorado"
    prod_id, criado = _upsert_produto(
        cur,
        id_tenant=id_tenant,
        valores=valores,
        id_lote=None,
        origem="integracao",
    )
    urls = extrair_urls_imagem(valores, modo_imagens="unico", delimitador=";")
    if urls:
        try:
            aplicar_imagens_importacao(
                cur,
                id_tenant=id_tenant,
                id_produto=int(prod_id),
                sku=sku,
                urls=list(urls),
            )
        except Exception:
            # Produto já gravado; imagens ficam para retry na próxima sync.
            pass
    return "inserido" if criado else "atualizado"


def _atualizar_estoque_sku(cur, id_tenant: int, sku: str, quantidade: int) -> bool:
    sku = (sku or "").strip()
    if not sku:
        return False
    qtd = max(0, int(quantidade))
    cur.execute(
        """
        SELECT v.id
          FROM tbl_produto_variante v
          JOIN tbl_produto p ON p.id = v.id_produto
         WHERE p.id_tenant = %s AND TRIM(v.sku) = %s
         LIMIT 1
        """,
        (int(id_tenant), sku),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            SELECT v.id
              FROM tbl_produto_variante v
              JOIN tbl_produto p ON p.id = v.id_produto
             WHERE p.id_tenant = %s AND TRIM(p.sku) = %s
             ORDER BY v.id
             LIMIT 1
            """,
            (int(id_tenant), sku),
        )
        row = cur.fetchone()
    if not row:
        return False
    vid = int(row[0])
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, %s, NOW())
        ON CONFLICT (id_variante) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (vid, qtd),
    )
    cur.execute(
        """
        UPDATE tbl_produto_estoque pe
           SET quantidade = %s, atualizado_em = NOW()
          FROM tbl_produto_variante v
         WHERE v.id = %s AND pe.id_produto = v.id_produto
        """,
        (qtd, vid),
    )
    return True


def sincronizar_produtos(conn, id_tenant: int, *, max_paginas: int = 20) -> dict:
    cfg = servico.carregar(conn, id_tenant)
    if not cfg.get("liberado") or not cfg.get("ativo"):
        raise PermissionError("Integração inativa ou não liberada.")
    pode_criar = bool(cfg.get("cap_produtos_cadastrar"))
    pode_atualizar = bool(cfg.get("cap_produtos_atualizar"))
    if not pode_criar and not pode_atualizar:
        raise PermissionError("Nenhuma capacidade de produtos habilitada.")

    cur = conn.cursor()
    inseridos = atualizados = ignorados = erros = 0
    detalhes_erro: list[dict] = []
    cursor = None
    for _ in range(max_paginas):
        pagina = cliente.listar_produtos(conn, id_tenant, cursor=cursor)
        itens = pagina.get("data") or []
        if not itens:
            break
        for item in itens:
            if not isinstance(item, dict):
                continue
            sku = _txt(item.get("sku"))
            try:
                acao = _aplicar_produto(
                    cur, id_tenant, item, pode_criar=pode_criar, pode_atualizar=pode_atualizar
                )
                if acao == "inserido":
                    inseridos += 1
                elif acao == "atualizado":
                    atualizados += 1
                else:
                    ignorados += 1
            except Exception as exc:
                erros += 1
                if len(detalhes_erro) < 20:
                    detalhes_erro.append({"sku": sku, "erro": str(exc)[:300]})
        cursor = pagina.get("next_cursor")
        if not cursor:
            break

    msg = (
        f"Produtos: {inseridos} novos, {atualizados} atualizados, "
        f"{ignorados} ignorados, {erros} erros."
    )
    ok = erros == 0
    servico.marcar_sync(conn, id_tenant, ok=ok, mensagem=msg)
    servico.registrar_log(
        conn,
        id_tenant,
        evento="sync.produtos",
        sucesso=ok,
        mensagem=msg,
        direcao="pull",
        detalhe={"inseridos": inseridos, "atualizados": atualizados, "erros": detalhes_erro},
    )
    return {
        "ok": ok,
        "message": msg,
        "inseridos": inseridos,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "erros": erros,
        "detalhes_erro": detalhes_erro,
    }


def sincronizar_estoque(conn, id_tenant: int, *, max_paginas: int = 20) -> dict:
    cfg = servico.carregar(conn, id_tenant)
    if not cfg.get("liberado") or not cfg.get("ativo"):
        raise PermissionError("Integração inativa ou não liberada.")
    if not cfg.get("cap_estoque_atualizar"):
        raise PermissionError("Atualização de estoque desabilitada.")

    cur = conn.cursor()
    atualizados = nao_encontrados = erros = 0
    detalhes_erro: list[dict] = []
    cursor = None
    for _ in range(max_paginas):
        pagina = cliente.listar_estoque(conn, id_tenant, cursor=cursor)
        itens = pagina.get("data") or []
        if not itens:
            break
        for item in itens:
            if not isinstance(item, dict):
                continue
            sku = _txt(item.get("sku"))
            try:
                qtd = int(float(_qty_from_item(item) or 0))
                if _atualizar_estoque_sku(cur, id_tenant, sku, qtd):
                    atualizados += 1
                else:
                    nao_encontrados += 1
            except Exception as exc:
                erros += 1
                if len(detalhes_erro) < 20:
                    detalhes_erro.append({"sku": sku, "erro": str(exc)[:300]})
        cursor = pagina.get("next_cursor")
        if not cursor:
            break

    msg = (
        f"Estoque: {atualizados} atualizados, {nao_encontrados} SKUs não encontrados, "
        f"{erros} erros."
    )
    ok = erros == 0
    servico.marcar_sync(conn, id_tenant, ok=ok, mensagem=msg)
    servico.registrar_log(
        conn,
        id_tenant,
        evento="sync.estoque",
        sucesso=ok,
        mensagem=msg,
        direcao="pull",
        detalhe={"atualizados": atualizados, "nao_encontrados": nao_encontrados, "erros": detalhes_erro},
    )
    return {
        "ok": ok,
        "message": msg,
        "atualizados": atualizados,
        "nao_encontrados": nao_encontrados,
        "erros": erros,
        "detalhes_erro": detalhes_erro,
    }
