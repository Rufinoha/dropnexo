# api/olist/produtos.py — importa catálogo do Olist pelo mesmo cadastro e a mesma foto do Bling
from __future__ import annotations

from typing import Any

from api.bling.produtos import (
    _salvar_produto,
    _salvar_produto_grupo_variacoes,
    aplicar_imagens_produto,
)
from fornecedor.catalogo.catalogo import descartar_arquivos_imagem_locais
from api.olist.cliente import api_request, garantir_tabelas
from global_utils import agora_utc

_LOTE = 5


def _s(val: Any) -> str:
    return str(val or "").strip()


def _num(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _marca(produto: dict) -> str:
    marca = produto.get("marca")
    if isinstance(marca, dict):
        return _s(marca.get("nome") or marca.get("descricao"))
    return _s(marca)


def _dim(produto: dict, *chaves: str) -> float | None:
    dims = produto.get("dimensoes") or produto.get("dimensao") or {}
    if not isinstance(dims, dict):
        dims = {}
    emb = dims.get("embalagem") if isinstance(dims.get("embalagem"), dict) else {}
    for fonte in (dims, emb, produto):
        for chave in chaves:
            n = _num(fonte.get(chave))
            if n is not None:
                return n
    return None


def para_payload_bling(produto: dict, *, nome_pai: str = "") -> dict:
    """Traduz o produto do Olist para o formato que o cadastro do Bling já grava."""
    precos = produto.get("precos") if isinstance(produto.get("precos"), dict) else {}
    nome = _s(produto.get("descricao") or produto.get("nome") or nome_pai)
    comp = _s(produto.get("descricaoComplementar") or produto.get("descricaoCurta"))
    return {
        "id": produto.get("id"),
        "nome": nome,
        "codigo": _s(produto.get("sku") or produto.get("codigo")),
        "gtin": _s(produto.get("gtin")),
        "ncm": _s(produto.get("ncm")),
        "cest": _s(produto.get("cest")),
        "unidade": _s(produto.get("unidade") or "UN"),
        "origem": produto.get("origem"),
        "situacao": produto.get("situacao") or "A",
        "marca": _marca(produto),
        "preco": _num(precos.get("preco") if precos else produto.get("preco")) or 0,
        "precoCusto": _num(precos.get("precoCusto") if precos else produto.get("precoCusto")),
        "descricaoCurta": "",
        "descricaoComplementar": comp,
        "pesoLiquido": _dim(produto, "pesoLiquido", "peso_liquido"),
        "pesoBruto": _dim(produto, "pesoBruto", "peso_bruto"),
        "dimensoes": {
            "altura": _dim(produto, "altura"),
            "largura": _dim(produto, "largura"),
            "profundidade": _dim(produto, "comprimento", "profundidade"),
        },
        "variacao": produto.get("variacao") or {},
    }


def _grade_nome(variacao: dict) -> str:
    grade = variacao.get("grade")
    if isinstance(grade, list) and grade:
        partes = []
        for item in grade:
            if not isinstance(item, dict):
                continue
            chave = _s(item.get("chave"))
            valor = _s(item.get("valor"))
            if chave and valor:
                partes.append(f"{chave}:{valor}")
        if partes:
            return ";".join(partes)
    return _s(variacao.get("descricao"))


def _anexos_midia(id_tenant: int, id_olist: str) -> list[dict]:
    try:
        bruto = api_request(id_tenant, "GET", f"/produtos/{id_olist}/anexos")
    except Exception:
        return []
    if isinstance(bruto, dict):
        bruto = bruto.get("itens") or bruto.get("anexos") or []
    if not isinstance(bruto, list):
        return []
    midia = []
    for item in bruto:
        if not isinstance(item, dict):
            continue
        url = _s(item.get("url"))
        if not url.startswith(("http://", "https://")):
            continue
        midia.append(
            {
                "url": url,
                "tipo": "externa",
                "bling_anexo_id": item.get("id"),
                "ordem": None,
            }
        )
    return midia


def _listar(id_tenant: int, offset: int) -> dict:
    dados = api_request(
        id_tenant,
        "GET",
        "/produtos",
        params={"situacao": "A", "limit": _LOTE, "offset": offset},
    )
    if isinstance(dados, list):
        itens = dados
        pag = {}
    elif isinstance(dados, dict):
        itens = dados.get("itens") if isinstance(dados.get("itens"), list) else []
        pag = dados.get("paginacao") if isinstance(dados.get("paginacao"), dict) else {}
    else:
        return {"itens": [], "total": offset, "total_conhecido": True}
    total = pag.get("total")
    try:
        total_i = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_i = None
    return {
        "itens": itens,
        "total": total_i if total_i is not None else offset + len(itens),
        "total_conhecido": total_i is not None,
    }


def _detalhe(id_tenant: int, id_olist: str) -> dict:
    dados = api_request(id_tenant, "GET", f"/produtos/{id_olist}")
    return dados if isinstance(dados, dict) else {}


def _variacoes_do_produto(produto: dict) -> list[dict]:
    """Variações já vêm em GET /produtos/{id}. Esse caminho não tem GET de lista."""
    bruto = produto.get("variacoes") if isinstance(produto, dict) else None
    if isinstance(bruto, dict):
        bruto = bruto.get("itens") or bruto.get("variacoes") or []
    if not isinstance(bruto, list):
        return []
    saida = []
    for var in bruto:
        if not isinstance(var, dict):
            continue
        payload = para_payload_bling(var)
        nome_grade = _grade_nome(var)
        if not nome_grade and isinstance(var.get("variacao"), dict):
            nome_grade = _grade_nome(var["variacao"])
        if nome_grade:
            payload["variacao"] = {"nome": nome_grade}
            if not _s(payload.get("nome")) or _s(payload.get("nome")) == _s(payload.get("codigo")):
                payload["nome"] = nome_grade.replace(":", " ")
        if payload.get("codigo"):
            saida.append(payload)
    return saida


def _id_existente(cur, id_tenant: int, id_olist: str, sku: str) -> int | None:
    cur.execute(
        """
        SELECT id_produto FROM tbl_integracao_olist_mapa
        WHERE id_tenant = %s AND id_olist = %s AND id_produto IS NOT NULL
        """,
        (id_tenant, id_olist),
    )
    row = cur.fetchone()
    if row and row[0]:
        return int(row[0])
    if not sku:
        return None
    cur.execute(
        "SELECT id FROM tbl_produto WHERE id_tenant = %s AND sku = %s ORDER BY id DESC LIMIT 1",
        (id_tenant, sku),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _gravar_mapa(cur, id_tenant: int, id_olist: str, id_produto: int, sku: str) -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_olist_mapa (id_tenant, id_olist, id_produto, sku, atualizado_em)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, id_olist) DO UPDATE SET
            id_produto = EXCLUDED.id_produto,
            sku = EXCLUDED.sku,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, id_olist, id_produto, sku or None, agora_utc()),
    )


def _log(cur, id_tenant: int, status: str, resumo: str, detalhe: str = "") -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_log (
            id_tenant, provedor, contexto, entidade, direcao, status, resumo, detalhe
        ) VALUES (%s, 'olist', 'fornecedor', 'produto', 'importar', %s, %s, %s)
        """,
        (id_tenant, status, resumo[:240], (detalhe or "")[:2000]),
    )


def _id_categoria_olist(produto: dict) -> str:
    cat = produto.get("categoria")
    if isinstance(cat, dict):
        return _s(cat.get("id"))
    if cat not in (None, "", [], {}):
        return _s(cat)
    return _s(produto.get("idCategoria") or produto.get("categoriaId"))


def _mapa_categorias(cur, id_tenant: int) -> dict[str, tuple[str, int | None]]:
    cur.execute(
        """
        SELECT id_olist, acao, id_categoria
        FROM tbl_integracao_olist_categoria
        WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    mapa: dict[str, tuple[str, int | None]] = {}
    for id_olist, acao, id_categoria in cur.fetchall():
        mapa[str(id_olist)] = (str(acao or ""), int(id_categoria) if id_categoria else None)
    return mapa


def importar_lote(
    cur,
    id_tenant: int,
    offset: int = 0,
    *,
    ids_categorias: set[str] | None = None,
    id_importacao_lote: int | None = None,
    respeitar_ignorar: bool = False,
) -> dict[str, Any]:
    """Importa um lote curto. A foto segue aplicar_imagens_produto (download local)."""
    garantir_tabelas(cur)
    mapa_cat = _mapa_categorias(cur, id_tenant)
    pagina = _listar(id_tenant, max(0, int(offset)))
    importados = 0
    atualizados = 0
    ignorados = 0
    erros: list[str] = []

    for item in pagina["itens"]:
        id_olist = _s(item.get("id"))
        if not id_olist:
            ignorados += 1
            continue
        cur.execute("SAVEPOINT sp_olist_prod")
        arquivos: list[str] = []
        try:
            detalhe = _detalhe(id_tenant, id_olist)
            tipo_var = _s(detalhe.get("tipoVariacao") or item.get("tipoVariacao")).upper()
            variacoes = _variacoes_do_produto(detalhe) or _variacoes_do_produto(item)
            if tipo_var == "V" and not variacoes:
                cur.execute("RELEASE SAVEPOINT sp_olist_prod")
                ignorados += 1
                continue
            base = dict(item) if isinstance(item, dict) else {}
            if detalhe:
                for chave, valor in detalhe.items():
                    if valor not in (None, "", [], {}):
                        base[chave] = valor
            pai = para_payload_bling(base)
            id_cat_olist = _id_categoria_olist(base)
            if ids_categorias is not None and id_cat_olist not in ids_categorias:
                cur.execute("RELEASE SAVEPOINT sp_olist_prod")
                ignorados += 1
                continue
            acao_cat, id_cat_drop = mapa_cat.get(id_cat_olist, ("", None))
            if respeitar_ignorar and acao_cat == "ignorar":
                cur.execute("RELEASE SAVEPOINT sp_olist_prod")
                ignorados += 1
                continue
            if acao_cat != "vincular":
                id_cat_drop = None
            sku = _s(pai.get("codigo"))
            if not sku and variacoes:
                sku = _s(variacoes[0].get("codigo"))
                pai["codigo"] = sku
            if not sku:
                raise ValueError("Produto sem SKU no Olist.")
            existente = _id_existente(cur, id_tenant, id_olist, sku)
            criando = existente is None
            midia = _anexos_midia(id_tenant, id_olist)
            vistos = {m["url"] for m in midia}
            for var in variacoes:
                var_id = _s(var.get("id"))
                if not var_id:
                    continue
                for extra in _anexos_midia(id_tenant, var_id):
                    if extra["url"] not in vistos:
                        vistos.add(extra["url"])
                        midia.append(extra)
            if variacoes:
                prod_id = _salvar_produto_grupo_variacoes(
                    cur,
                    id_tenant=id_tenant,
                    pai=pai,
                    variacoes=variacoes,
                    id_produto_existente=existente,
                    id_categoria=id_cat_drop,
                    id_importacao_lote=id_importacao_lote,
                )
            else:
                prod_id = _salvar_produto(
                    cur,
                    id_tenant=id_tenant,
                    produto=pai,
                    id_produto_existente=existente,
                    id_categoria=id_cat_drop,
                    id_importacao_lote=id_importacao_lote,
                )
            if midia:
                _, arquivos = aplicar_imagens_produto(
                    cur,
                    id_tenant=id_tenant,
                    id_produto=prod_id,
                    sku=sku,
                    midia_itens=midia,
                    modo_imagem="download",
                    adiar_download=False,
                )
                arquivos = arquivos or []
            _gravar_mapa(cur, id_tenant, id_olist, prod_id, sku)
            cur.execute("RELEASE SAVEPOINT sp_olist_prod")
            if criando:
                importados += 1
            else:
                atualizados += 1
        except Exception as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_olist_prod")
            except Exception:
                raise
            descartar_arquivos_imagem_locais(arquivos)
            if isinstance(e, ValueError) and "limite" in str(e).lower():
                raise
            erros.append(f"{id_olist}: {e}")
            if id_importacao_lote:
                from fornecedor.importacao.servico_importacao import MODULO_CATALOGO, registrar_erro_lote

                registrar_erro_lote(
                    cur,
                    id_tenant=id_tenant,
                    id_lote=int(id_importacao_lote),
                    modulo=MODULO_CATALOGO,
                    mensagem=str(e),
                    ref_externa=id_olist,
                    nome_registro=_s(item.get("descricao") or item.get("nome")),
                    sku_registro=_s(item.get("sku") or item.get("codigo")),
                    payload={"mensagem_tecnica": str(e)},
                    origem="olist",
                )

    proximo = int(offset) + len(pagina["itens"])
    if pagina.get("total_conhecido"):
        fim = proximo >= int(pagina["total"]) or not pagina["itens"]
    else:
        fim = len(pagina["itens"]) < _LOTE
    resumo = f"{importados} novo(s), {atualizados} atualizado(s), {len(erros)} erro(s)."
    try:
        cur.execute("SAVEPOINT sp_olist_log")
        _log(cur, id_tenant, "ok" if not erros else "erro", resumo, "\n".join(erros[:12]))
        cur.execute("RELEASE SAVEPOINT sp_olist_log")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sp_olist_log")
        except Exception:
            pass
    return {
        "importados": importados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "erros": erros[:12],
        "offset": int(offset),
        "proximo_offset": proximo,
        "total": int(pagina["total"]),
        "fim": fim,
    }
