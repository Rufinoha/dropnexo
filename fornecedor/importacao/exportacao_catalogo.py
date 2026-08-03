"""Exportação CSV/Excel do catálogo (FN) e Meus produtos (VD)."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from fornecedor.importacao.campos_catalogo import (
    COLUNAS_EXPORT_FORNECEDOR,
    COLUNAS_EXPORT_VENDEDOR,
)


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "nao"
    return str(v).strip()


def _imagens_produto(cur, id_produto: int, delim: str = ";") -> str:
    cur.execute(
        """
        SELECT caminho FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY principal DESC NULLS LAST, ordem ASC, id ASC
        LIMIT 10
        """,
        (id_produto,),
    )
    urls = []
    for (caminho,) in cur.fetchall():
        c = (caminho or "").strip()
        if c.startswith("http://") or c.startswith("https://"):
            urls.append(c)
        elif c:
            urls.append(c)
    return delim.join(urls)


def _atributos_texto(attrs: Any) -> str:
    if not attrs:
        return ""
    if isinstance(attrs, dict):
        return ";".join(f"{k}={v}" for k, v in attrs.items())
    return str(attrs)


def listar_linhas_export_fornecedor(
    cur,
    id_tenant: int,
    *,
    busca: str = "",
    id_categoria: str = "",
    filtro_tipo: str = "",
    somente_publicados: bool = True,
) -> list[dict[str, str]]:
    where = ["p.id_tenant = %s"]
    params: list[Any] = [id_tenant]
    if somente_publicados:
        where.append("p.publicado = TRUE")
    if busca:
        where.append("(p.nome ILIKE %s OR p.sku ILIKE %s)")
        like = f"%{busca}%"
        params.extend([like, like])
    if id_categoria:
        where.append("p.id_categoria = %s")
        params.append(int(id_categoria))
    if filtro_tipo == "simples":
        where.append("p.formato = 'S'")
    elif filtro_tipo in ("com_variacoes", "somente_variacoes"):
        where.append("p.formato = 'E'")

    cur.execute(
        f"""
        SELECT p.id, p.sku, p.nome, p.descricao, p.preco, p.preco_promocional, p.preco_custo,
               p.unidade, c.nome, p.marca, p.peso_liquido_kg, p.peso_bruto_kg,
               p.altura_cm, p.largura_cm, p.profundidade_cm, p.ncm, p.gtin,
               p.origem_fiscal, p.cest, p.condicao, p.publicado, p.formato,
               COALESCE(ve.quantidade, 0)
        FROM tbl_produto p
        LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = p.id_variante_padrao
        WHERE {" AND ".join(where)}
        ORDER BY p.nome, p.id
        """,
        params,
    )
    produtos = cur.fetchall()
    linhas: list[dict[str, str]] = []

    for p in produtos:
        (
            pid,
            sku,
            nome,
            descricao,
            preco,
            promo,
            custo,
            unidade,
            categoria,
            marca,
            peso_liq,
            peso_bruto,
            altura,
            largura,
            profundidade,
            ncm,
            gtin,
            origem_fiscal,
            cest,
            condicao,
            publicado,
            formato,
            qtd,
        ) = p
        imgs = _imagens_produto(cur, int(pid))
        base = {
            "sku": _fmt(sku),
            "sku_pai": "",
            "atributos": "",
            "nome": _fmt(nome),
            "nome_variacao": "",
            "descricao": _fmt(descricao),
            "preco": _fmt(preco),
            "preco_promocional": _fmt(promo),
            "preco_custo": _fmt(custo),
            "quantidade": _fmt(qtd),
            "categoria": _fmt(categoria),
            "unidade": _fmt(unidade) or "UN",
            "marca": _fmt(marca),
            "peso_liquido_kg": _fmt(peso_liq),
            "peso_bruto_kg": _fmt(peso_bruto),
            "altura_cm": _fmt(altura),
            "largura_cm": _fmt(largura),
            "profundidade_cm": _fmt(profundidade),
            "ncm": _fmt(ncm),
            "gtin": _fmt(gtin),
            "origem_fiscal": _fmt(origem_fiscal),
            "cest": _fmt(cest),
            "condicao": _fmt(condicao),
            "publicado": _fmt(bool(publicado)),
            "imagens": imgs,
        }

        if (formato or "S") != "E" or filtro_tipo == "simples":
            if filtro_tipo != "somente_variacoes":
                linhas.append(base)
            continue

        if filtro_tipo != "somente_variacoes":
            linhas.append(base)

        cur.execute(
            """
            SELECT v.sku, v.nome_exibicao, v.atributos, v.preco, v.preco_promocional,
                   v.preco_custo, COALESCE(e.quantidade, 0), v.gtin, v.ncm,
                   v.peso_liquido_kg, v.peso_bruto_kg, v.altura_cm, v.largura_cm, v.profundidade_cm
            FROM tbl_produto_variante v
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE v.id_produto = %s AND v.ativo = TRUE
            ORDER BY v.ordem, v.id
            """,
            (pid,),
        )
        for v in cur.fetchall():
            linhas.append(
                {
                    "sku": _fmt(v[0]),
                    "sku_pai": _fmt(sku),
                    "atributos": _atributos_texto(v[2]),
                    "nome": _fmt(nome),
                    "nome_variacao": _fmt(v[1]),
                    "descricao": "",
                    "preco": _fmt(v[3]),
                    "preco_promocional": _fmt(v[4]),
                    "preco_custo": _fmt(v[5]),
                    "quantidade": _fmt(v[6]),
                    "categoria": _fmt(categoria),
                    "unidade": _fmt(unidade) or "UN",
                    "marca": _fmt(marca),
                    "peso_liquido_kg": _fmt(v[9]),
                    "peso_bruto_kg": _fmt(v[10]),
                    "altura_cm": _fmt(v[11]),
                    "largura_cm": _fmt(v[12]),
                    "profundidade_cm": _fmt(v[13]),
                    "ncm": _fmt(v[8]),
                    "gtin": _fmt(v[7]),
                    "origem_fiscal": _fmt(origem_fiscal),
                    "cest": _fmt(cest),
                    "condicao": _fmt(condicao),
                    "publicado": _fmt(bool(publicado)),
                    "imagens": "",
                }
            )
    return linhas


def listar_linhas_export_vendedor(
    cur,
    id_tenant: int,
    *,
    busca: str = "",
    id_categoria: str = "",
    filtro_tipo: str = "",
    somente_publicados: bool = True,
) -> list[dict[str, str]]:
    """Exporta somente produtos próprios do vendedor (Meus produtos), nunca catálogo do fornecedor."""
    return listar_linhas_export_fornecedor(
        cur,
        id_tenant,
        busca=busca,
        id_categoria=id_categoria,
        filtro_tipo=filtro_tipo,
        somente_publicados=somente_publicados,
    )


def gerar_csv(linhas: Iterable[dict[str, str]], colunas: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=colunas, delimiter=";", extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for row in linhas:
        w.writerow({c: row.get(c, "") for c in colunas})
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def gerar_xlsx(linhas: list[dict[str, str]], colunas: list[str]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Produtos"
    ws.append(colunas)
    for row in linhas:
        ws.append([row.get(c, "") for c in colunas])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def colunas_para_contexto(contexto: str) -> list[str]:
    if (contexto or "").strip().lower() == "vendedor":
        return list(COLUNAS_EXPORT_VENDEDOR)
    return list(COLUNAS_EXPORT_FORNECEDOR)
