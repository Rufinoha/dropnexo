"""Motor DropNexo de importação CSV de catálogo (independente de Bling)."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from global_utils import agora_utc

from fornecedor.importacao.campos_catalogo import MAX_IMAGENS_IMPORT, mapa_obrigatoriedade

MAX_LINHAS_CSV = 500


def parse_decimal(valor, padrao: str | None = None) -> Decimal | None:
    if valor is None or str(valor).strip() == "":
        return Decimal(padrao) if padrao is not None else None
    try:
        return Decimal(str(valor).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return Decimal(padrao) if padrao is not None else None


def normalizar_bool(valor, padrao: bool = False) -> bool:
    if valor is None or str(valor).strip() == "":
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "on", "yes", "sim", "s")


def parse_atributos(texto: str) -> dict[str, str]:
    """Aceita Cor=Azul;Tamanho=P ou Cor:Azul;Tamanho:P."""
    out: dict[str, str] = {}
    raw = (texto or "").strip()
    if not raw:
        return out
    for parte in re.split(r"[;|]", raw):
        parte = parte.strip()
        if not parte:
            continue
        if "=" in parte:
            k, v = parte.split("=", 1)
        elif ":" in parte:
            k, v = parte.split(":", 1)
        else:
            continue
        k, v = k.strip(), v.strip()
        if k and v:
            out[k] = v
    return out


def resolver_categoria(cur, id_tenant: int, nome_cat: str | None) -> int | None:
    nome = (nome_cat or "").strip()
    if not nome:
        return None
    cur.execute(
        """
        INSERT INTO tbl_categoria (id_tenant, nome)
        VALUES (%s, %s)
        ON CONFLICT (id_tenant, nome) DO UPDATE SET ativo = TRUE
        RETURNING id
        """,
        (id_tenant, nome),
    )
    return cur.fetchone()[0]


def montar_mapa_colunas(fieldnames: list[str] | None) -> dict[str, str]:
    mapa: dict[str, str] = {}
    for col in fieldnames or []:
        chave = (col or "").strip().lower()
        if chave:
            mapa[chave] = col
    return mapa


def valor_mapeado(row: dict, mapa_arquivo: dict[str, str], coluna_arquivo: str) -> str:
    col = (coluna_arquivo or "").strip()
    if not col:
        return ""
    # tenta nome exato e lower
    if col in row and row.get(col) is not None:
        return str(row.get(col) or "").strip()
    key = col.lower()
    real = mapa_arquivo.get(key)
    if real is not None:
        return str(row.get(real) or "").strip()
    return ""


def extrair_valores_linha(row: dict, mapa_arquivo: dict[str, str], campos_layout: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in campos_layout:
        campo = (c.get("campo_interno") or "").strip()
        if not campo:
            continue
        out[campo] = valor_mapeado(row, mapa_arquivo, c.get("coluna_arquivo") or campo)
    return out


def extrair_urls_imagem(
    valores: dict[str, str],
    *,
    modo_imagens: str,
    delimitador: str = ";",
) -> list[str]:
    urls: list[str] = []
    modo = (modo_imagens or "colunas").strip().lower()
    if modo == "unico":
        bruto = valores.get("imagens") or ""
        sep = delimitador or ";"
        for parte in bruto.split(sep):
            u = parte.strip()
            if u:
                urls.append(u)
    else:
        for i in range(1, MAX_IMAGENS_IMPORT + 1):
            u = (valores.get(f"imagem_{i}") or "").strip()
            if u:
                urls.append(u)
    # dedupe preservando ordem
    vistos: set[str] = set()
    limpos: list[str] = []
    for u in urls:
        if u not in vistos:
            vistos.add(u)
            limpos.append(u)
    return limpos[:MAX_IMAGENS_IMPORT]


def validar_linha_produto(valores: dict[str, str], urls: list[str]) -> list[str]:
    erros: list[str] = []
    regra = mapa_obrigatoriedade()
    campos_produto = [
        "sku",
        "nome",
        "preco",
        "unidade",
        "descricao",
        "categoria",
        "peso_bruto_kg",
        "altura_cm",
        "largura_cm",
        "profundidade_cm",
        "ncm",
        "gtin",
        "origem_fiscal",
    ]
    for campo in campos_produto:
        if regra.get(campo) and not (valores.get(campo) or "").strip():
            erros.append(f"Campo obrigatório ausente: {campo}")
    if parse_decimal(valores.get("preco")) is None:
        erros.append("preco inválido.")
    if not urls:
        erros.append("Informe ao menos 1 imagem (URL).")
    return erros


def validar_linha_variacao(valores: dict[str, str]) -> list[str]:
    erros: list[str] = []
    if not (valores.get("sku") or "").strip():
        erros.append("Campo obrigatório ausente: sku")
    if not (valores.get("sku_pai") or "").strip():
        erros.append("Campo obrigatório ausente: sku_pai")
    if not parse_atributos(valores.get("atributos") or ""):
        erros.append("Campo obrigatório ausente ou inválido: atributos")
    return erros


def _eh_linha_variacao(valores: dict[str, str]) -> bool:
    return bool((valores.get("sku_pai") or "").strip())


def _contar_imagens_produto(cur, id_produto: int) -> int:
    cur.execute(
        "SELECT COUNT(*) FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL",
        (id_produto,),
    )
    return int(cur.fetchone()[0] or 0)


def aplicar_imagens_importacao(
    cur,
    *,
    id_tenant: int,
    id_produto: int,
    sku: str,
    urls: list[str],
) -> None:
    if not urls:
        return
    from pathlib import Path
    from urllib.parse import urlparse

    from api.bling.produtos import baixar_imagem, caminho_db_imagem, pasta_imagens_sku
    from fornecedor.catalogo.catalogo import (
        aplicar_galeria_produto,
        classificar_origem_bling,
        recalcular_bytes_imagens_tenant,
        sincronizar_imagem_principal_produto,
    )

    qtd_atual = _contar_imagens_produto(cur, id_produto)
    qtd_nova = len(urls)

    if qtd_atual > 0 and qtd_nova < qtd_atual:
        cur.execute(
            """
            SELECT COALESCE(MAX(ordem), -1) FROM tbl_produto_imagem
            WHERE id_produto = %s AND id_variante IS NULL
            """,
            (id_produto,),
        )
        ordem = int(cur.fetchone()[0] or -1) + 1
        slots = max(0, MAX_IMAGENS_IMPORT - qtd_atual)
        for url_orig in urls[:slots]:
            ext = Path(urlparse(url_orig).path).suffix.lower() or ".jpg"
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".jpg"
            nome = f"{ordem + 1:02d}-img{ext}"
            pasta = pasta_imagens_sku(id_tenant, sku)
            destino = pasta / nome
            try:
                tamanho = baixar_imagem(url_orig, destino)
            except Exception:
                continue
            caminho_db = caminho_db_imagem(id_tenant, sku, nome)
            cur.execute(
                """
                INSERT INTO tbl_produto_imagem (
                    id_produto, caminho, ordem, principal, origem, tamanho_bytes
                ) VALUES (%s, %s, %s, FALSE, %s, %s)
                """,
                (id_produto, caminho_db, ordem, "manual_upload", tamanho),
            )
            ordem += 1
        sincronizar_imagem_principal_produto(cur, id_produto)
        try:
            recalcular_bytes_imagens_tenant(cur, id_tenant)
        except Exception:
            pass
        return

    aplicar_galeria_produto(
        cur,
        id_tenant=id_tenant,
        id_produto=id_produto,
        sku=sku,
        urls=urls,
        modo_imagem="download",
        origem_fn=classificar_origem_bling,
        baixar_fn=baixar_imagem,
        pasta_sku_fn=pasta_imagens_sku,
        caminho_db_fn=caminho_db_imagem,
    )


def _buscar_produto_por_sku(cur, id_tenant: int, sku: str) -> int | None:
    cur.execute(
        "SELECT id FROM tbl_produto WHERE id_tenant = %s AND TRIM(sku) = %s LIMIT 1",
        (id_tenant, sku.strip()),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _upsert_produto(
    cur,
    *,
    id_tenant: int,
    valores: dict[str, str],
    id_lote: int | None,
    origem: str,
) -> tuple[int, bool]:
    """Retorna (id_produto, criado)."""
    from fornecedor.catalogo.srotas_catalogo import garantir_variante_padrao, sync_pai_de_variante_padrao
    from fornecedor.parametros.precificacao import aplicar_valor_drop_produto_e_variantes
    from sistema.planos.limites import exigir_novo_produto_catalogo

    sku = (valores.get("sku") or "").strip()
    nome = (valores.get("nome") or "").strip()
    preco = parse_decimal(valores.get("preco"), "0") or Decimal("0")
    promo = parse_decimal(valores.get("preco_promocional"))
    custo = parse_decimal(valores.get("preco_custo"))
    unidade = ((valores.get("unidade") or "UN").strip()[:20]) or "UN"
    descricao = valores.get("descricao") or ""
    id_categoria = resolver_categoria(cur, id_tenant, valores.get("categoria"))
    publicado = normalizar_bool(valores.get("publicado"), False)
    marca = (valores.get("marca") or "").strip() or None
    gtin = (valores.get("gtin") or "").strip() or None
    ncm = (valores.get("ncm") or "").strip() or None
    origem_fiscal = (valores.get("origem_fiscal") or "").strip() or None
    cest = (valores.get("cest") or "").strip() or None
    condicao = (valores.get("condicao") or "").strip() or None
    peso_liq = parse_decimal(valores.get("peso_liquido_kg"))
    peso_bruto = parse_decimal(valores.get("peso_bruto_kg"))
    altura = parse_decimal(valores.get("altura_cm"))
    largura = parse_decimal(valores.get("largura_cm"))
    profundidade = parse_decimal(valores.get("profundidade_cm"))
    quantidade = max(0, int(parse_decimal(valores.get("quantidade"), "0") or 0))
    agora = agora_utc()

    prod_id = _buscar_produto_por_sku(cur, id_tenant, sku) if sku else None
    criado = False

    if prod_id:
        cur.execute(
            """
            UPDATE tbl_produto SET
                nome=%s, descricao=%s, preco=%s, preco_promocional=%s, preco_custo=%s,
                unidade=%s, id_categoria=%s, publicado=%s, marca=%s, gtin=%s, ncm=%s,
                origem_fiscal=%s, cest=%s, condicao=%s, referencia=%s,
                peso_liquido_kg=%s, peso_bruto_kg=%s, altura_cm=%s, largura_cm=%s,
                profundidade_cm=%s, valor_atacado=%s, atualizado_em=%s,
                origem = CASE WHEN origem IN ('arquivo', 'integracao') THEN 'editado' ELSE origem END
            WHERE id=%s AND id_tenant=%s
            """,
            (
                nome,
                descricao,
                preco,
                promo,
                custo,
                unidade,
                id_categoria,
                publicado,
                marca,
                gtin,
                ncm,
                origem_fiscal,
                cest,
                condicao,
                condicao,
                peso_liq,
                peso_bruto,
                altura,
                largura,
                profundidade,
                preco,
                agora,
                prod_id,
                id_tenant,
            ),
        )
    else:
        exigir_novo_produto_catalogo(cur, int(id_tenant))
        cur.execute(
            """
            INSERT INTO tbl_produto (
                id_tenant, sku, nome, descricao, preco, preco_promocional, preco_custo,
                unidade, id_categoria, publicado, marca, gtin, ncm, origem_fiscal, cest,
                condicao, referencia, peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm,
                profundidade_cm, valor_atacado, formato, origem, id_importacao_lote, atualizado_em
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'S',%s,%s,%s
            ) RETURNING id
            """,
            (
                id_tenant,
                sku,
                nome,
                descricao,
                preco,
                promo,
                custo,
                unidade,
                id_categoria,
                publicado,
                marca,
                gtin,
                ncm,
                origem_fiscal,
                cest,
                condicao,
                condicao,
                peso_liq,
                peso_bruto,
                altura,
                largura,
                profundidade,
                preco,
                origem,
                id_lote,
                agora,
            ),
        )
        prod_id = int(cur.fetchone()[0])
        criado = True

    vid = garantir_variante_padrao(cur, prod_id, id_tenant)
    cur.execute(
        """
        UPDATE tbl_produto_variante SET
            sku = COALESCE(%s, sku), nome_exibicao = %s, preco = %s,
            preco_promocional = %s, preco_custo = %s, gtin = %s, ncm = %s,
            peso_liquido_kg = %s, peso_bruto_kg = %s, altura_cm = %s, largura_cm = %s,
            profundidade_cm = %s, atualizado_em = %s
        WHERE id = %s
        """,
        (
            sku or None,
            nome,
            preco,
            promo,
            custo,
            gtin,
            ncm,
            peso_liq,
            peso_bruto,
            altura,
            largura,
            profundidade,
            agora,
            vid,
        ),
    )
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_variante) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (vid, quantidade, agora),
    )
    cur.execute(
        """
        INSERT INTO tbl_produto_estoque (id_produto, quantidade, atualizado_em)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_produto) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (prod_id, quantidade, agora),
    )
    sync_pai_de_variante_padrao(cur, prod_id)
    aplicar_valor_drop_produto_e_variantes(cur, id_tenant, prod_id, publicar=False, forcar=True)
    return prod_id, criado


def _garantir_atributos_produto(cur, id_produto: int, atributos: dict[str, str]) -> None:
    ordem = 0
    for nome, valor in atributos.items():
        cur.execute(
            """
            SELECT id, valores FROM tbl_produto_atributo
            WHERE id_produto = %s AND LOWER(TRIM(nome)) = LOWER(TRIM(%s))
            LIMIT 1
            """,
            (id_produto, nome),
        )
        row = cur.fetchone()
        if row:
            aid, vals = int(row[0]), row[1]
            lista = list(vals) if isinstance(vals, list) else []
            if valor not in lista:
                lista.append(valor)
                cur.execute(
                    "UPDATE tbl_produto_atributo SET valores = %s::jsonb WHERE id = %s",
                    (json.dumps(lista, ensure_ascii=False), aid),
                )
        else:
            cur.execute(
                """
                INSERT INTO tbl_produto_atributo (id_produto, nome, valores, ordem)
                VALUES (%s, %s, %s::jsonb, %s)
                """,
                (id_produto, nome, json.dumps([valor], ensure_ascii=False), ordem),
            )
        ordem += 1


def _nome_variacao(valores: dict[str, str], atributos: dict[str, str]) -> str:
    nome = (valores.get("nome_variacao") or valores.get("nome") or "").strip()
    if nome:
        return nome[:200]
    if atributos:
        return " / ".join(f"{k} {v}" for k, v in atributos.items())[:200]
    return (valores.get("sku") or "Variação")[:200]


def _upsert_variacao(
    cur,
    *,
    id_tenant: int,
    valores: dict[str, str],
) -> tuple[int, int, bool]:
    """Retorna (id_produto_pai, id_variante, criada)."""
    from fornecedor.parametros.precificacao import aplicar_valor_drop_variante

    sku = (valores.get("sku") or "").strip()
    sku_pai = (valores.get("sku_pai") or "").strip()
    atributos = parse_atributos(valores.get("atributos") or "")
    id_pai = _buscar_produto_por_sku(cur, id_tenant, sku_pai)
    if not id_pai:
        raise ValueError(f"Produto pai não encontrado (sku_pai={sku_pai}).")

    cur.execute(
        "UPDATE tbl_produto SET formato = 'E', atualizado_em = %s WHERE id = %s AND id_tenant = %s",
        (agora_utc(), id_pai, id_tenant),
    )
    _garantir_atributos_produto(cur, id_pai, atributos)

    preco = parse_decimal(valores.get("preco"))
    promo = parse_decimal(valores.get("preco_promocional"))
    custo = parse_decimal(valores.get("preco_custo"))
    gtin = (valores.get("gtin") or "").strip() or None
    ncm = (valores.get("ncm") or "").strip() or None
    peso_liq = parse_decimal(valores.get("peso_liquido_kg"))
    peso_bruto = parse_decimal(valores.get("peso_bruto_kg"))
    altura = parse_decimal(valores.get("altura_cm"))
    largura = parse_decimal(valores.get("largura_cm"))
    profundidade = parse_decimal(valores.get("profundidade_cm"))
    quantidade = max(0, int(parse_decimal(valores.get("quantidade"), "0") or 0))
    nome_exibicao = _nome_variacao(valores, atributos)
    agora = agora_utc()

    cur.execute(
        """
        SELECT id FROM tbl_produto_variante
        WHERE id_produto = %s AND TRIM(sku) = %s
        LIMIT 1
        """,
        (id_pai, sku),
    )
    row = cur.fetchone()
    criada = False
    if row:
        vid = int(row[0])
        cur.execute(
            """
            UPDATE tbl_produto_variante SET
                nome_exibicao=%s, preco=COALESCE(%s, preco), preco_promocional=%s,
                preco_custo=%s, atributos=%s::jsonb, gtin=%s, ncm=%s,
                peso_liquido_kg=%s, peso_bruto_kg=%s, altura_cm=%s, largura_cm=%s,
                profundidade_cm=%s, herda_pai=FALSE, atualizado_em=%s
            WHERE id=%s
            """,
            (
                nome_exibicao,
                preco,
                promo,
                custo,
                json.dumps(atributos, ensure_ascii=False),
                gtin,
                ncm,
                peso_liq,
                peso_bruto,
                altura,
                largura,
                profundidade,
                agora,
                vid,
            ),
        )
    else:
        cur.execute(
            "SELECT COALESCE(MAX(ordem), 0) + 1 FROM tbl_produto_variante WHERE id_produto = %s",
            (id_pai,),
        )
        ordem = int(cur.fetchone()[0] or 1)
        if preco is None:
            cur.execute("SELECT preco FROM tbl_produto WHERE id = %s", (id_pai,))
            preco = cur.fetchone()[0] or Decimal("0")
        cur.execute(
            """
            INSERT INTO tbl_produto_variante (
                id_produto, sku, nome_exibicao, preco, preco_promocional, preco_custo,
                atributos, gtin, ncm, peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm,
                profundidade_cm, ativo, ordem, herda_pai, atualizado_em
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,FALSE,%s
            ) RETURNING id
            """,
            (
                id_pai,
                sku,
                nome_exibicao,
                preco,
                promo,
                custo,
                json.dumps(atributos, ensure_ascii=False),
                gtin,
                ncm,
                peso_liq,
                peso_bruto,
                altura,
                largura,
                profundidade,
                ordem,
                agora,
            ),
        )
        vid = int(cur.fetchone()[0])
        criada = True

    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_variante) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (vid, quantidade, agora),
    )
    try:
        aplicar_valor_drop_variante(cur, id_tenant, vid, forcar=True)
    except Exception:
        pass
    return id_pai, vid, criada


def processar_linhas_csv(
    cur,
    *,
    id_tenant: int,
    rows: list[tuple[int, dict]],
    campos_layout: list[dict],
    mapa_arquivo: dict[str, str],
    modo_imagens: str = "colunas",
    delimitador_imagens: str = ";",
    id_lote: int | None = None,
    origem: str = "arquivo",
) -> dict[str, Any]:
    """
    rows: lista de (numero_linha, dict_csv).
    Processa pais/simples primeiro e variações depois.
    """
    inseridos = 0
    atualizados = 0
    rejeitadas = 0
    erros: list[dict] = []

    preparadas: list[dict] = []
    for num, row in rows:
        valores = extrair_valores_linha(row, mapa_arquivo, campos_layout)
        # ignora linha totalmente vazia
        if not any(str(v).strip() for v in valores.values()):
            continue
        preparadas.append({"num": num, "valores": valores, "variacao": _eh_linha_variacao(valores)})

    # pais/simples primeiro
    ordem = sorted(preparadas, key=lambda x: (1 if x["variacao"] else 0, x["num"]))

    for item in ordem:
        num = item["num"]
        valores = item["valores"]
        try:
            if item["variacao"]:
                errs = validar_linha_variacao(valores)
                if errs:
                    rejeitadas += 1
                    erros.append({"linha": num, "erro": "; ".join(errs), "sku": valores.get("sku")})
                    continue
                _pai, _vid, criada = _upsert_variacao(cur, id_tenant=id_tenant, valores=valores)
                if criada:
                    inseridos += 1
                else:
                    atualizados += 1
                # imagens de variação: se vierem URLs, aplicam no pai (galeria compartilhada)
                urls = extrair_urls_imagem(
                    valores, modo_imagens=modo_imagens, delimitador=delimitador_imagens
                )
                if urls:
                    aplicar_imagens_importacao(
                        cur,
                        id_tenant=id_tenant,
                        id_produto=_pai,
                        sku=(valores.get("sku_pai") or "").strip(),
                        urls=urls,
                    )
            else:
                urls = extrair_urls_imagem(
                    valores, modo_imagens=modo_imagens, delimitador=delimitador_imagens
                )
                errs = validar_linha_produto(valores, urls)
                if errs:
                    rejeitadas += 1
                    erros.append({"linha": num, "erro": "; ".join(errs), "sku": valores.get("sku")})
                    continue
                prod_id, criado = _upsert_produto(
                    cur,
                    id_tenant=id_tenant,
                    valores=valores,
                    id_lote=id_lote,
                    origem=origem,
                )
                aplicar_imagens_importacao(
                    cur,
                    id_tenant=id_tenant,
                    id_produto=prod_id,
                    sku=(valores.get("sku") or "").strip() or f"P{prod_id}",
                    urls=urls,
                )
                if criado:
                    inseridos += 1
                else:
                    atualizados += 1
        except Exception as ex:
            rejeitadas += 1
            erros.append({"linha": num, "erro": str(ex), "sku": valores.get("sku")})

    return {
        "inseridos": inseridos,
        "atualizados": atualizados,
        "rejeitadas": rejeitadas,
        "erros": erros,
        "total_linhas": len(preparadas),
    }
