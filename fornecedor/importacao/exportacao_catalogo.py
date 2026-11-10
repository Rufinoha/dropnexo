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
    so_nao_publicados: bool = False,
) -> list[dict[str, str]]:
    where = ["p.id_tenant = %s"]
    params: list[Any] = [id_tenant]
    if so_nao_publicados:
        where.append("p.publicado = FALSE")
    elif somente_publicados:
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


# Cabeçalho oficial do modelo de produtos Bling (CSV/Excel).
COLUNAS_EXPORT_BLING = [
    "ID",
    "Código",
    "Descrição",
    "Unidade",
    "NCM",
    "Origem",
    "Preço",
    "Valor IPI fixo",
    "Observações",
    "Situação",
    "Estoque",
    "Preço de custo",
    "Cód no fornecedor",
    "Fornecedor",
    "Localização",
    "Estoque maximo",
    "Estoque minimo",
    "Peso líquido (Kg)",
    "Peso bruto (Kg)",
    "GTIN/EAN",
    "GTIN/EAN da embalagem",
    "Largura do Produto",
    "Altura do Produto",
    "Profundidade do produto",
    "Data Validade",
    "Descrição do Produto no Fornecedor",
    "Descrição Complementar",
    "Itens p/ caixa",
    "Produto Variação",
    "Tipo Produção",
    "Classe de enquadramento do IPI",
    "Código da lista de serviços",
    "Tipo do item",
    "Grupo de Tags/Tags",
    "Tributos",
    "Código Pai",
    "Código Integração",
    "Grupo de produtos",
    "Marca",
    "CEST",
    "Volumes",
    "Descrição Curta",
    "Cross-Docking",
    "URL Imagens Externas",
    "Link Externo",
    "Meses Garantia no Fornecedor",
    "Clonar dados do pai",
    "Condição do produto",
    "Frete Grátis",
    "Número FCI",
    "Vídeo",
    "Departamento",
    "Unidade de medida",
    "Preço de compra",
    "Valor base ICMS ST para retenção",
    "Valor ICMS ST para retenção",
    "Valor ICMS próprio do substituto",
    "Categoria do produto",
    "Informações Adicionais",
]


def _fmt_br_num(v: Any) -> str:
    if v is None or v == "":
        return ""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return _fmt(v)
    texto = f"{n:.2f}".rstrip("0").rstrip(".")
    if "." in texto:
        inteiro, dec = texto.split(".", 1)
        return f"{inteiro},{dec}"
    return texto


def _url_imagem_export(caminho: str) -> str:
    c = (caminho or "").strip()
    if not c:
        return ""
    if c.lower().startswith(("http://", "https://")):
        return c
    try:
        from global_utils import obter_base_url

        rel = c.replace("\\", "/").lstrip("/")
        if rel.lower().startswith("static/"):
            rel = rel[7:]
        base = (obter_base_url() or "").rstrip("/")
        if rel.lower().startswith("upload/tenant"):
            # Rota autenticada: Bling não consome; mantém caminho relativo.
            path = f"/api/bling/produto-imagem/{rel}"
        else:
            path = f"/static/{rel}"
        if not base:
            return path
        return f"{base}{path}"
    except Exception:
        return c


def _imagens_produto_urls(cur, id_produto: int, *, id_tenant_vendedor: int | None = None) -> str:
    urls: list[str] = []
    if id_tenant_vendedor:
        try:
            from vendedor.meus_produtos.servico_meus_produtos import listar_imagens_vitrine

            imgs, _ = listar_imagens_vitrine(cur, int(id_tenant_vendedor), int(id_produto))
            for img in imgs[:10]:
                u = _url_imagem_export(img.get("caminho") or "")
                if u:
                    urls.append(u)
        except Exception:
            pass
    if not urls:
        bruto = _imagens_produto(cur, int(id_produto))
        for parte in bruto.split(";"):
            u = _url_imagem_export(parte)
            if u:
                urls.append(u)
    # Bling aceita várias URLs separadas por |
    vistos: set[str] = set()
    limpos: list[str] = []
    for u in urls:
        if u not in vistos:
            vistos.add(u)
            limpos.append(u)
    return "|".join(limpos)


def _condicao_bling(condicao: Any) -> str:
    c = str(condicao or "").strip().lower()
    if c in ("usado", "used", "u"):
        return "USADO"
    return "NOVO"


def _linha_bling_vazia() -> dict[str, str]:
    return {c: "" for c in COLUNAS_EXPORT_BLING}


def _montar_linha_bling(
    *,
    sku: str,
    nome: str,
    descricao: str = "",
    unidade: str = "UN",
    ncm: str = "",
    origem_fiscal: str = "0",
    preco: Any = "",
    estoque: Any = "",
    preco_custo: Any = "",
    fornecedor: str = "",
    peso_liq: Any = "",
    peso_bruto: Any = "",
    gtin: str = "",
    largura: Any = "",
    altura: Any = "",
    profundidade: Any = "",
    marca: str = "",
    cest: str = "",
    categoria: str = "",
    imagens: str = "",
    situacao: str = "Ativo",
    produto_variacao: str = "Produto",
    codigo_pai: str = "",
    clonar_pai: str = "Não",
    condicao: str = "NOVO",
    observacoes: str = "",
) -> dict[str, str]:
    row = _linha_bling_vazia()
    row.update(
        {
            "Código": _fmt(sku),
            "Descrição": _fmt(nome),
            "Unidade": _fmt(unidade) or "UN",
            "NCM": _fmt(ncm),
            "Origem": _fmt(origem_fiscal) if _fmt(origem_fiscal) != "" else "0",
            "Preço": _fmt_br_num(preco),
            "Valor IPI fixo": "0",
            "Observações": _fmt(observacoes),
            "Situação": situacao,
            "Estoque": _fmt(estoque) if estoque is not None and estoque != "" else "0",
            "Preço de custo": _fmt_br_num(preco_custo),
            "Fornecedor": _fmt(fornecedor),
            "Peso líquido (Kg)": _fmt_br_num(peso_liq),
            "Peso bruto (Kg)": _fmt_br_num(peso_bruto),
            "GTIN/EAN": _fmt(gtin),
            "Largura do Produto": _fmt_br_num(largura),
            "Altura do Produto": _fmt_br_num(altura),
            "Profundidade do produto": _fmt_br_num(profundidade),
            "Descrição do Produto no Fornecedor": _fmt(nome),
            "Descrição Complementar": _fmt(descricao),
            "Itens p/ caixa": "1",
            "Produto Variação": produto_variacao,
            "Tipo Produção": "Própria",
            "Código Pai": _fmt(codigo_pai),
            "Código Integração": "0",
            "Marca": _fmt(marca),
            "CEST": _fmt(cest),
            "Volumes": "1",
            "Descrição Curta": _fmt(nome)[:120],
            "URL Imagens Externas": _fmt(imagens),
            "Clonar dados do pai": clonar_pai,
            "Condição do produto": condicao,
            "Frete Grátis": "Não",
            "Unidade de medida": "Centímetro",
            "Categoria do produto": _fmt(categoria),
        }
    )
    return row


def _listar_linhas_bling_proprios(
    cur,
    id_tenant: int,
    *,
    busca: str = "",
    id_categoria: str = "",
    filtro_tipo: str = "",
    somente_publicados: bool = True,
    ids_produto: list[int] | None = None,
) -> list[dict[str, str]]:
    where = ["p.id_tenant = %s"]
    params: list[Any] = [id_tenant]
    if ids_produto is not None:
        if not ids_produto:
            return []
        where.append("p.id = ANY(%s)")
        params.append(ids_produto)
    if somente_publicados and ids_produto is None:
        where.append("p.publicado = TRUE")
    if busca and ids_produto is None:
        where.append("(p.nome ILIKE %s OR p.sku ILIKE %s)")
        like = f"%{busca}%"
        params.extend([like, like])
    if id_categoria and ids_produto is None:
        from vendedor.meus_produtos.servico_meus_produtos import sql_filtro_categoria_proprio

        frag, frag_params = sql_filtro_categoria_proprio(id_categoria)
        if frag:
            where.append(frag)
            params.extend(frag_params)
    if ids_produto is None:
        if filtro_tipo == "simples":
            where.append("p.formato = 'S'")
        elif filtro_tipo in ("com_variacoes", "somente_variacoes"):
            where.append("p.formato = 'E'")

    cur.execute(
        f"""
        SELECT p.id, p.sku, p.nome, p.descricao, p.preco, p.preco_custo,
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
    # Seleção explícita: sempre exporta a família completa (pai + todas as variações).
    tipo_efetivo = "" if ids_produto is not None else filtro_tipo

    for p in produtos:
        (
            pid,
            sku,
            nome,
            descricao,
            preco,
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
        imgs = _imagens_produto_urls(cur, int(pid), id_tenant_vendedor=int(id_tenant))
        situacao = "Ativo" if publicado else "Inativo"
        cond = _condicao_bling(condicao)
        eh_variacao = (formato or "S") == "E"

        if tipo_efetivo == "simples" or not eh_variacao:
            if tipo_efetivo != "somente_variacoes":
                linhas.append(
                    _montar_linha_bling(
                        sku=sku,
                        nome=nome,
                        descricao=descricao or "",
                        unidade=unidade or "UN",
                        ncm=ncm or "",
                        origem_fiscal=origem_fiscal if origem_fiscal is not None else "0",
                        preco=preco,
                        estoque=qtd,
                        preco_custo=custo,
                        peso_liq=peso_liq,
                        peso_bruto=peso_bruto,
                        gtin=gtin or "",
                        largura=largura,
                        altura=altura,
                        profundidade=profundidade,
                        marca=marca or "",
                        cest=cest or "",
                        categoria=categoria or "",
                        imagens=imgs,
                        situacao=situacao,
                        produto_variacao="Produto",
                        condicao=cond,
                        observacoes="Cadastro próprio",
                    )
                )
            continue

        if tipo_efetivo != "somente_variacoes":
            linhas.append(
                _montar_linha_bling(
                    sku=sku,
                    nome=nome,
                    descricao=descricao or "",
                    unidade=unidade or "UN",
                    ncm=ncm or "",
                    origem_fiscal=origem_fiscal if origem_fiscal is not None else "0",
                    preco=preco,
                    estoque=0,
                    preco_custo=custo,
                    peso_liq=peso_liq,
                    peso_bruto=peso_bruto,
                    gtin=gtin or "",
                    largura=largura,
                    altura=altura,
                    profundidade=profundidade,
                    marca=marca or "",
                    cest=cest or "",
                    categoria=categoria or "",
                    imagens=imgs,
                    situacao=situacao,
                    produto_variacao="Produto",
                    condicao=cond,
                    observacoes="Produto pai com variações",
                )
            )

        cur.execute(
            """
            SELECT v.sku, v.nome_exibicao, v.atributos, v.preco, v.preco_custo,
                   COALESCE(e.quantidade, 0), v.gtin, v.ncm,
                   v.peso_liquido_kg, v.peso_bruto_kg, v.altura_cm, v.largura_cm, v.profundidade_cm,
                   v.ativo
            FROM tbl_produto_variante v
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE v.id_produto = %s AND v.ativo = TRUE
            ORDER BY v.ordem, v.id
            """,
            (pid,),
        )
        for v in cur.fetchall():
            attrs = _atributos_texto(v[2])
            desc_var = attrs or _fmt(v[1]) or _fmt(nome)
            linhas.append(
                _montar_linha_bling(
                    sku=v[0],
                    nome=desc_var,
                    descricao="",
                    unidade=unidade or "UN",
                    ncm=v[7] or ncm or "",
                    origem_fiscal=origem_fiscal if origem_fiscal is not None else "0",
                    preco=v[3],
                    estoque=v[5],
                    preco_custo=v[4],
                    peso_liq=v[8],
                    peso_bruto=v[9],
                    gtin=v[6] or "",
                    largura=v[11],
                    altura=v[10],
                    profundidade=v[12],
                    marca=marca or "",
                    cest=cest or "",
                    categoria=categoria or "",
                    imagens="",
                    situacao="Ativo" if v[13] else "Inativo",
                    produto_variacao="Variação",
                    codigo_pai=sku,
                    clonar_pai="Sim",
                    condicao=cond,
                    observacoes=_fmt(v[1]),
                )
            )
    return linhas


def _listar_linhas_bling_rede(
    cur,
    id_tenant: int,
    *,
    busca: str = "",
    id_categoria: str = "",
    filtro_tipo: str = "",
    somente_ativos: bool = True,
    ids_produto: list[int] | None = None,
) -> list[dict[str, str]]:
    where = ["pv.id_tenant_vendedor = %s", "p.id_tenant <> %s"]
    params: list[Any] = [id_tenant, id_tenant]
    if ids_produto is not None:
        if not ids_produto:
            return []
        where.append("p.id = ANY(%s)")
        params.append(ids_produto)
    if somente_ativos and ids_produto is None:
        where.append("pv.ativo = TRUE")
    if busca and ids_produto is None:
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
    if id_categoria and ids_produto is None:
        from vendedor.meus_produtos.servico_meus_produtos import sql_filtro_categoria_integrado

        frag, frag_params = sql_filtro_categoria_integrado(id_categoria, id_tenant)
        if frag:
            where.append(frag)
            params.extend(frag_params)
    if ids_produto is None:
        if filtro_tipo == "simples":
            where.append("p.formato = 'S'")
        elif filtro_tipo in ("com_variacoes", "somente_variacoes"):
            where.append("p.formato = 'E'")

    where_sql = " AND ".join(where)
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
               p.descricao, p.unidade,
               COALESCE(
                   (SELECT cv.nome
                    FROM tbl_categoria cv
                    INNER JOIN tbl_produto_vendedor pvc ON pvc.id_categoria_vendedor = cv.id
                    WHERE pvc.id_produto = p.id AND pvc.id_tenant_vendedor = %s
                    LIMIT 1),
                   c.nome
               ),
               p.marca, p.peso_liquido_kg, p.peso_bruto_kg,
               p.altura_cm, p.largura_cm, p.profundidade_cm, p.ncm, p.gtin,
               p.origem_fiscal, p.cest, p.condicao, p.formato,
               COALESCE(tf.nome, ''),
               BOOL_OR(pv.ativo),
               COALESCE(
                   (SELECT pv_p.preco_venda
                    FROM tbl_produto_vendedor pv_p
                    WHERE pv_p.id_produto = p.id AND pv_p.id_tenant_vendedor = %s
                    ORDER BY CASE WHEN pv_p.id_variante = p.id_variante_padrao THEN 0 ELSE 1 END, pv_p.id
                    LIMIT 1),
                   p.preco, 0
               ),
               COALESCE(
                   (SELECT SUM(e.quantidade)
                    FROM tbl_produto_vendedor pv_e
                    JOIN tbl_produto_variante_estoque e ON e.id_variante = pv_e.id_variante
                    WHERE pv_e.id_produto = p.id AND pv_e.id_tenant_vendedor = %s
                      AND (%s OR pv_e.ativo = TRUE)),
                   0
               )
        FROM tbl_produto p
        INNER JOIN tbl_produto_vendedor pv ON pv.id_produto = p.id AND pv.id_tenant_vendedor = %s
        LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
        LEFT JOIN tbl_tenant tf ON tf.id = p.id_tenant
        WHERE {where_sql}
        GROUP BY p.id, p.sku, p.nome, p.descricao, p.unidade, c.nome, p.marca,
                 p.peso_liquido_kg, p.peso_bruto_kg, p.altura_cm, p.largura_cm, p.profundidade_cm,
                 p.ncm, p.gtin, p.origem_fiscal, p.cest, p.condicao, p.formato, tf.nome, p.preco,
                 p.id_variante_padrao
        ORDER BY p.nome, p.id
        """,
        [id_tenant, id_tenant, id_tenant, id_tenant, (not somente_ativos), id_tenant] + params,
    )

    produtos = cur.fetchall()
    linhas: list[dict[str, str]] = []

    for p in produtos:
        (
            pid,
            sku,
            nome,
            descricao,
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
            formato,
            fornecedor,
            ativo,
            preco,
            estoque,
        ) = p
        imgs = _imagens_produto_urls(cur, int(pid), id_tenant_vendedor=int(id_tenant))
        situacao = "Ativo" if ativo else "Inativo"
        cond = _condicao_bling(condicao)
        eh_variacao = (formato or "S") == "E"
        tipo_efetivo = "" if ids_produto is not None else filtro_tipo

        if tipo_efetivo == "simples" or not eh_variacao:
            if tipo_efetivo != "somente_variacoes":
                linhas.append(
                    _montar_linha_bling(
                        sku=sku,
                        nome=nome,
                        descricao=descricao or "",
                        unidade=unidade or "UN",
                        ncm=ncm or "",
                        origem_fiscal=origem_fiscal if origem_fiscal is not None else "0",
                        preco=preco,
                        estoque=estoque,
                        fornecedor=fornecedor,
                        peso_liq=peso_liq,
                        peso_bruto=peso_bruto,
                        gtin=gtin or "",
                        largura=largura,
                        altura=altura,
                        profundidade=profundidade,
                        marca=marca or "",
                        cest=cest or "",
                        categoria=categoria or "",
                        imagens=imgs,
                        situacao=situacao,
                        produto_variacao="Produto",
                        condicao=cond,
                        observacoes="Produto da rede",
                    )
                )
            continue

        if tipo_efetivo != "somente_variacoes":
            linhas.append(
                _montar_linha_bling(
                    sku=sku,
                    nome=nome,
                    descricao=descricao or "",
                    unidade=unidade or "UN",
                    ncm=ncm or "",
                    origem_fiscal=origem_fiscal if origem_fiscal is not None else "0",
                    preco=preco,
                    estoque=0,
                    fornecedor=fornecedor,
                    peso_liq=peso_liq,
                    peso_bruto=peso_bruto,
                    gtin=gtin or "",
                    largura=largura,
                    altura=altura,
                    profundidade=profundidade,
                    marca=marca or "",
                    cest=cest or "",
                    categoria=categoria or "",
                    imagens=imgs,
                    situacao=situacao,
                    produto_variacao="Produto",
                    condicao=cond,
                    observacoes="Produto pai com variações",
                )
            )

        var_where = ["pv.id_produto = %s", "pv.id_tenant_vendedor = %s"]
        var_params: list[Any] = [pid, id_tenant]
        if somente_ativos and ids_produto is None:
            var_where.append("pv.ativo = TRUE")
        cur.execute(
            f"""
            SELECT v.sku,
                   COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), v.nome_exibicao),
                   v.atributos, pv.preco_venda, COALESCE(e.quantidade, 0),
                   v.gtin, COALESCE(NULLIF(v.ncm, ''), %s),
                   v.peso_liquido_kg, v.peso_bruto_kg, v.altura_cm, v.largura_cm, v.profundidade_cm,
                   pv.ativo
            FROM tbl_produto_vendedor pv
            JOIN tbl_produto_variante v ON v.id = pv.id_variante
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE {" AND ".join(var_where)}
            ORDER BY v.ordem, v.id
            """,
            [ncm or ""] + var_params,
        )
        for v in cur.fetchall():
            attrs = _atributos_texto(v[2])
            desc_var = attrs or _fmt(v[1]) or _fmt(nome)
            linhas.append(
                _montar_linha_bling(
                    sku=v[0],
                    nome=desc_var,
                    descricao="",
                    unidade=unidade or "UN",
                    ncm=v[6] or ncm or "",
                    origem_fiscal=origem_fiscal if origem_fiscal is not None else "0",
                    preco=v[3],
                    estoque=v[4],
                    fornecedor=fornecedor,
                    peso_liq=v[7],
                    peso_bruto=v[8],
                    gtin=v[5] or "",
                    largura=v[10],
                    altura=v[9],
                    profundidade=v[11],
                    marca=marca or "",
                    cest=cest or "",
                    categoria=categoria or "",
                    imagens="",
                    situacao="Ativo" if v[12] else "Inativo",
                    produto_variacao="Variação",
                    codigo_pai=sku,
                    clonar_pai="Sim",
                    condicao=cond,
                    observacoes=_fmt(v[1]),
                )
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
    filtro_origem: str = "",
    ids_produto: list[int] | None = None,
) -> list[dict[str, str]]:
    """Exporta Meus produtos no padrão Bling: rede (vitrine) + cadastro próprio.

    Com ids_produto, exporta só esses produtos e a família completa
    (pai + todas as variações), mesmo que a seleção tenha partido de um filho.
    """
    origem = (filtro_origem or "").strip().lower()
    ids = None
    if ids_produto is not None:
        ids = sorted({int(x) for x in ids_produto if int(x) > 0})
    linhas: list[dict[str, str]] = []
    if origem in ("", "integrado", "rede"):
        if filtro_tipo != "kit":
            linhas.extend(
                _listar_linhas_bling_rede(
                    cur,
                    int(id_tenant),
                    busca=busca,
                    id_categoria=id_categoria,
                    filtro_tipo=filtro_tipo,
                    somente_ativos=somente_publicados,
                    ids_produto=ids,
                )
            )
    if origem in ("", "proprio"):
        if filtro_tipo != "kit":
            linhas.extend(
                _listar_linhas_bling_proprios(
                    cur,
                    int(id_tenant),
                    busca=busca,
                    id_categoria=id_categoria,
                    filtro_tipo=filtro_tipo,
                    somente_publicados=somente_publicados,
                    ids_produto=ids,
                )
            )
    return linhas


def gerar_csv(linhas: Iterable[dict[str, str]], colunas: list[str]) -> bytes:
    delim = "," if colunas and colunas[0] == "ID" and "Código" in colunas else ";"
    buf = io.StringIO()
    w = csv.DictWriter(
        buf,
        fieldnames=colunas,
        delimiter=delim,
        extrasaction="ignore",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
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
    ctx = (contexto or "").strip().lower()
    if ctx in ("vendedor", "bling", "meus_produtos"):
        return list(COLUNAS_EXPORT_BLING)
    return list(COLUNAS_EXPORT_FORNECEDOR)
