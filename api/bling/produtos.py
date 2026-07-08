# api/bling/produtos.py — importação, exportação e imagens de produtos Bling
from __future__ import annotations

# ── imagens ───────────────────────────────────────────

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from fornecedor.catalogo.catalogo import (
    aplicar_galeria_produto,
    classificar_origem_bling,
    limpar_galeria_produto,
    sincronizar_cache_variante,
    vincular_imagens_variantes_bling,
    vincular_variante_padrao_galeria,
)
from global_utils import agora_utc

MAX_BYTES_IMAGEM = 3 * 1024 * 1024
EXT_PERMITIDAS = {".png", ".jpg", ".jpeg", ".webp"}
PLACEHOLDER_STATIC = "imge/icone_dropnexo.png"


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]


def sanitizar_sku_pasta(sku: str) -> str:
    s = (sku or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s or "sem-sku"


def pasta_imagens_sku(id_tenant: int, sku: str) -> Path:
    pasta = _raiz_projeto() / "upload" / f"tenant{id_tenant}" / "produtos" / sanitizar_sku_pasta(sku)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def caminho_db_imagem(id_tenant: int, sku: str, nome_arquivo: str) -> str:
    return f"upload/tenant{id_tenant}/produtos/{sanitizar_sku_pasta(sku)}/{nome_arquivo}"


def _url_de_item_imagem(item) -> str | None:
    if isinstance(item, str):
        u = item.strip()
        return u if u.startswith(("http://", "https://")) else None
    if not isinstance(item, dict):
        return None
    for key in ("link", "url", "href", "imagemURL", "imagemUrl"):
        u = (item.get(key) or "").strip()
        if u.startswith(("http://", "https://")):
            return u
    u = (item.get("linkMiniatura") or "").strip()
    if u.startswith(("http://", "https://")):
        return u
    return None


def _adicionar_itens_imagem(urls: list[str], items, *, ordenar_por: str | None = None) -> None:
    if not items:
        return
    lista = items if isinstance(items, list) else [items]
    if ordenar_por:
        lista = sorted(
            lista,
            key=lambda x: (x.get(ordenar_por) if isinstance(x, dict) else 0) or 0,
        )
    for item in lista:
        u = _url_de_item_imagem(item)
        if u and u not in urls:
            urls.append(u)


def _extrair_urls_midia_dict(midia: dict, urls: list[str]) -> None:
    imagens = midia.get("imagens")
    if isinstance(imagens, dict):
        _adicionar_itens_imagem(urls, imagens.get("internas"), ordenar_por="ordem")
        _adicionar_itens_imagem(urls, imagens.get("externas"))
        for chave in ("imagens", "all"):
            parte = imagens.get(chave)
            if isinstance(parte, list):
                _adicionar_itens_imagem(urls, parte)
    elif isinstance(imagens, list):
        _adicionar_itens_imagem(urls, imagens)

    imagem = midia.get("imagem")
    if isinstance(imagem, list):
        _adicionar_itens_imagem(urls, imagem)
    elif isinstance(imagem, dict):
        u = _url_de_item_imagem(imagem)
        if u and u not in urls:
            urls.append(u)


def extrair_urls_imagem_bling(
    produto: dict,
    *,
    variacoes: list[dict] | None = None,
) -> list[str]:
    urls: list[str] = []

    def add(u: str | None) -> None:
        u = (u or "").strip()
        if u and u.startswith(("http://", "https://")) and u not in urls:
            urls.append(u)

    add(produto.get("imagemURL"))
    add(produto.get("imagemUrl"))

    midia = produto.get("midia") or {}
    if isinstance(midia, dict):
        _extrair_urls_midia_dict(midia, urls)

    for key in ("urlImagensExternas", "imagensExternas", "url_imagens_externas"):
        raw = produto.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        for parte in raw.split("|"):
            add(parte.strip())

    for var in variacoes or []:
        if not isinstance(var, dict):
            continue
        add(var.get("imagemURL"))
        add(var.get("imagemUrl"))
        var_midia = var.get("midia") or {}
        if isinstance(var_midia, dict):
            _extrair_urls_midia_dict(var_midia, urls)

    return urls[:10]


def _extensao_de_url(url: str) -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    return ext if ext in EXT_PERMITIDAS else ".jpg"


def baixar_imagem(url: str, destino: Path) -> int:
    r = requests.get(url, timeout=30, stream=True)
    r.raise_for_status()
    total = 0
    chunks: list[bytes] = []
    for chunk in r.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES_IMAGEM:
            raise ValueError("Imagem excede 3 MB.")
        chunks.append(chunk)
    if total <= 0:
        raise ValueError("Imagem vazia.")
    destino.write_bytes(b"".join(chunks))
    return total


def aplicar_imagens_produto(
    cur,
    *,
    id_tenant: int,
    id_produto: int,
    sku: str,
    urls: list[str],
    modo_imagem: str,
    variacoes_bling: list[dict] | None = None,
) -> str | None:
    """Popula galeria do pai e vincula imagem padrão às variantes. Retorna caminho principal."""
    if not urls:
        return None

    principal, mapa = aplicar_galeria_produto(
        cur,
        id_tenant=id_tenant,
        id_produto=id_produto,
        sku=sku,
        urls=urls,
        modo_imagem=modo_imagem,
        origem_fn=classificar_origem_bling,
        baixar_fn=baixar_imagem if modo_imagem == "download" else None,
        pasta_sku_fn=pasta_imagens_sku,
        caminho_db_fn=caminho_db_imagem,
    )

    if variacoes_bling:
        vincular_imagens_variantes_bling(
            cur,
            id_produto=id_produto,
            mapa_url_id=mapa,
            variacoes_bling=variacoes_bling,
            extrair_urls_fn=lambda p: extrair_urls_imagem_bling(p),
        )
    else:
        vincular_variante_padrao_galeria(cur, id_produto)

    cur.execute(
        """
        UPDATE tbl_produto_variante SET imagem_url = %s, atualizado_em = %s
        WHERE id = (SELECT id_variante_padrao FROM tbl_produto WHERE id = %s)
          AND herda_pai = TRUE
        """,
        (principal, agora_utc(), id_produto),
    )
    if principal:
        cur.execute(
            "SELECT id FROM tbl_produto_variante WHERE id_produto = %s AND herda_pai = TRUE",
            (id_produto,),
        )
        for row in cur.fetchall():
            sincronizar_cache_variante(cur, int(row[0]))

    return principal


# Compatibilidade com imports antigos
__all__ = [
    "aplicar_imagens_produto",
    "extrair_urls_imagem_bling",
    "limpar_galeria_produto",
    "baixar_imagem",
]


# ── sync_produtos ─────────────────────────────────────

import json
import traceback
from collections.abc import Callable
from typing import Any

from api.bling.campos import (
    extrair_campos_produto_bling,
    preco_referencia_grupo,
    tupla_campos_produto_sql,
)
from api.bling.produtos import aplicar_imagens_produto, extrair_urls_imagem_bling
from api.bling.categorias_bling import (
    extrair_id_categoria_produto,
    garantir_categoria_bling,
    ids_categoria_bling_com_descendentes,
    resolver_id_segmento_import,
    sincronizar_arvore_categorias_bling,
)
from api.bling.estoque import resumo_depositos_bling
from fornecedor.importacao.servico_importacao import montar_payload_erro
from fornecedor.importacao.servico_importacao import (
    MODULO_CATALOGO,
    ORIGEM_INTEGRACAO,
    STATUS_CONCLUIDO,
    STATUS_ERRO,
    finalizar_lote,
    registrar_erro_lote,
)
from fornecedor.parametros.precificacao import aplicar_valor_drop_produto_e_variantes
from global_utils import agora_utc
from api.bling.cliente import listar_produtos, obter_produto, obter_variacoes_produto

_SAVEPOINT_PRODUTO = "bling_sync_produto"


def _savepoint(cur, nome: str) -> None:
    cur.execute(f"SAVEPOINT {nome}")


def _rollback_savepoint(cur, nome: str) -> None:
    cur.execute(f"ROLLBACK TO SAVEPOINT {nome}")


def _release_savepoint(cur, nome: str) -> None:
    cur.execute(f"RELEASE SAVEPOINT {nome}")


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


def _fetch_returning_id(cur, *, contexto: str) -> int:
    row = cur.fetchone()
    if not row or row[0] is None:
        raise ValueError(contexto)
    return int(row[0])


def _produto_local_existe(cur, id_tenant: int, id_produto: int | None) -> int | None:
    """Retorna o id se o produto ainda existe no tenant; None se foi excluído ou inválido."""
    if not id_produto:
        return None
    cur.execute(
        "SELECT id FROM tbl_produto WHERE id = %s AND id_tenant = %s",
        (id_produto, id_tenant),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _resolver_produto_existente(
    cur,
    id_tenant: int,
    *,
    id_mapa: int | None,
    sku: str,
) -> int | None:
    """
    Define qual produto local atualizar.
    Se o vínculo Bling apontar para produto excluído, ignora o mapa e tenta pelo SKU;
    se não achar nada, retorna None (será criado um produto novo).
    """
    id_produto = _produto_local_existe(cur, id_tenant, id_mapa)
    if id_produto:
        return id_produto
    sku = (sku or "").strip()
    if not sku:
        return None
    cur.execute(
        "SELECT id FROM tbl_produto WHERE id_tenant = %s AND sku = %s",
        (id_tenant, sku),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _registrar_log(cur, id_tenant: int, contexto: str, status: str, resumo: str, detalhe: str = "") -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_log (
            id_tenant, provedor, contexto, entidade, direcao, status, resumo, detalhe
        ) VALUES (%s, 'bling', %s, 'produto', 'importar', %s, %s, %s)
        """,
        (id_tenant, contexto, status, resumo, detalhe[:4000]),
    )


def _registrar_falha(
    falhas: list[dict[str, str]],
    *,
    id_bling: str,
    nome: str,
    sku: str,
    motivo: str,
    tipo: str = "produto",
) -> None:
    falhas.append(
        {
            "id_bling": id_bling or "?",
            "nome": (nome or "").strip() or "—",
            "sku": (sku or "").strip(),
            "motivo": motivo.strip(),
            "tipo": tipo,
        }
    )


def _formato_bling(produto: dict) -> str:
    fmt = produto.get("formato")
    if fmt is not None and str(fmt).strip():
        return str(fmt).strip().upper()[:1]
    if _id_pai_bling(produto):
        return "V"
    return "S"


def _id_pai_bling(produto: dict) -> str | None:
    pai = produto.get("produtoPai") or produto.get("produto_pai")
    if isinstance(pai, dict):
        pid = str(pai.get("id") or "").strip()
        if pid and pid != "0":
            return pid
    for key in ("idProdutoPai", "id_produto_pai", "idPai", "id_pai"):
        val = produto.get(key)
        if val not in (None, "", 0, "0"):
            pid = str(val).strip()
            if pid:
                return pid
    return None


def _eh_variacao_filha(produto: dict) -> bool:
    """Produto filho (variação) — identificado pelo vínculo com o pai."""
    return bool(_id_pai_bling(produto))


def _eh_produto_pai_variacoes(produto: dict) -> bool:
    """Produto pai com grade (campos confiáveis na listagem)."""
    if _id_pai_bling(produto):
        return False
    fmt = str(produto.get("formato") or "").strip().upper()
    if fmt in ("E", "C"):
        return True
    variacoes = produto.get("variacoes")
    return isinstance(variacoes, list) and len(variacoes) > 0


def _detalhe_eh_pai_variavel(id_tenant: int, detalhe: dict) -> bool:
    """Confirma produto formato V (variável) consultando variações na API."""
    fmt = str(detalhe.get("formato") or "").strip().upper()
    if fmt != "V" or _id_pai_bling(detalhe):
        return False
    id_p = str(detalhe.get("id") or "")
    if not id_p:
        return False
    try:
        vars_resp = obter_variacoes_produto(id_tenant, id_p)
        return len(_extrair_lista_variacoes(vars_resp)) > 0
    except Exception:
        return False


def _preparar_jobs_importacao(itens: list[dict]) -> list[dict]:
    """Agrupa produtos pai (E/V pai) e evita importar variações (filhas) isoladamente."""
    jobs_grupo: dict[str, dict] = {}
    ids_filhas: set[str] = set()

    for item in itens:
        id_bling = str(item.get("id") or "")
        if not id_bling:
            continue

        pai_id = _id_pai_bling(item)
        if pai_id:
            ids_filhas.add(id_bling)
            if pai_id not in jobs_grupo:
                jobs_grupo[pai_id] = {"tipo": "grupo", "id_bling": pai_id, "item": None}
            continue

        if _eh_produto_pai_variacoes(item):
            jobs_grupo[id_bling] = {"tipo": "grupo", "id_bling": id_bling, "item": item}

    jobs_simples: list[dict] = []
    for item in itens:
        id_bling = str(item.get("id") or "")
        if not id_bling or id_bling in ids_filhas or id_bling in jobs_grupo:
            continue
        if _eh_variacao_filha(item) or _eh_produto_pai_variacoes(item):
            continue
        jobs_simples.append({"tipo": "simples", "id_bling": id_bling, "item": item})

    return list(jobs_grupo.values()) + jobs_simples


def _extrair_lista_variacoes(dados: dict | list | None) -> list[dict]:
    if not dados:
        return []
    if isinstance(dados, list):
        return [v for v in dados if isinstance(v, dict)]
    if isinstance(dados.get("variacoes"), list):
        return [v for v in dados["variacoes"] if isinstance(v, dict)]
    inner = dados.get("data")
    if isinstance(inner, dict) and isinstance(inner.get("variacoes"), list):
        return [v for v in inner["variacoes"] if isinstance(v, dict)]
    return []


def _validar_grupo_variacoes(variacoes: list[dict]) -> list[str]:
    problemas: list[str] = []
    if not variacoes:
        problemas.append("Nenhuma variação encontrada na API Bling.")
        return problemas
    for var in variacoes:
        vid = str(var.get("id") or "?")
        nome = (var.get("nome") or var.get("descricao") or "").strip()
        sku = (var.get("codigo") or "").strip()
        if not sku:
            rotulo = nome or f"ID {vid}"
            problemas.append(f"variação «{rotulo}» (#{vid}) sem SKU")
    return problemas


def _sku_pai_de_variacoes(pai: dict, variacoes: list[dict]) -> str:
    sku_pai = (pai.get("codigo") or "").strip()
    if sku_pai:
        return sku_pai
    for var in variacoes:
        sku = (var.get("codigo") or "").strip()
        if sku:
            return sku
    return ""


def _limpar_variantes(cur, id_produto: int) -> None:
    cur.execute("UPDATE tbl_produto SET id_variante_padrao = NULL WHERE id = %s", (id_produto,))
    cur.execute("DELETE FROM tbl_produto_variante WHERE id_produto = %s", (id_produto,))


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
    vid = _fetch_returning_id(
        cur,
        contexto="Falha ao criar variante padrão do produto.",
    )
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
    id_categoria: int | None = None,
    id_importacao_lote: int | None = None,
) -> int:
    campos = extrair_campos_produto_bling(produto)
    sku = campos.get("sku") or ""
    nome = campos.get("nome") or sku or "Produto Bling"
    campos["nome"] = nome
    campos["sku"] = sku or None
    vals = tupla_campos_produto_sql(campos)
    agora = agora_utc()

    if id_produto_existente:
        cur.execute(
            """
            UPDATE tbl_produto SET
                nome = %s, descricao = %s, sku = %s, preco = %s, preco_custo = %s,
                unidade = %s, gtin = %s, ncm = %s, marca = %s, referencia = %s, condicao = %s,
                peso_liquido_kg = %s, peso_bruto_kg = %s, altura_cm = %s, largura_cm = %s,
                profundidade_cm = %s, moq = %s, volumes = %s, frete_gratis = %s,
                origem_fiscal = %s, cest = %s, producao = %s, ativo = %s,
                id_categoria = COALESCE(%s, id_categoria), atualizado_em = %s
            WHERE id = %s AND id_tenant = %s
            RETURNING id
            """,
            vals + (id_categoria, agora, id_produto_existente, id_tenant),
        )
        row = cur.fetchone()
        if row and row[0]:
            prod_id = int(row[0])
        else:
            id_produto_existente = None

    if not id_produto_existente:
        cur.execute(
            """
            INSERT INTO tbl_produto (
                id_tenant, id_categoria, nome, descricao, sku, preco, preco_custo, unidade,
                gtin, ncm, marca, referencia, condicao, peso_liquido_kg, peso_bruto_kg,
                altura_cm, largura_cm, profundidade_cm, moq, volumes, frete_gratis,
                origem_fiscal, cest, producao, ativo, publicado, formato, tipo, origem,
                id_importacao_lote, atualizado_em
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, FALSE, 'S', 'P', %s, %s, %s
            ) RETURNING id
            """,
            (
                id_tenant,
                id_categoria,
                *vals,
                ORIGEM_INTEGRACAO if id_importacao_lote else "manual",
                id_importacao_lote,
                agora,
            ),
        )
        prod_id = _fetch_returning_id(cur, contexto="Falha ao inserir produto.")

    vid = _garantir_variante_padrao(cur, prod_id, id_tenant, nome)
    cur.execute(
        """
        UPDATE tbl_produto_variante SET
            sku = %s, nome_exibicao = %s, preco = %s, preco_custo = %s,
            gtin = %s, ncm = %s, peso_liquido_kg = %s, peso_bruto_kg = %s,
            altura_cm = %s, largura_cm = %s, profundidade_cm = %s, ativo = %s, atualizado_em = %s
        WHERE id = %s
        """,
        (
            sku or None,
            nome,
            campos.get("preco"),
            campos.get("preco_custo"),
            campos.get("gtin"),
            campos.get("ncm"),
            campos.get("peso_liquido_kg"),
            campos.get("peso_bruto_kg"),
            campos.get("altura_cm"),
            campos.get("largura_cm"),
            campos.get("profundidade_cm"),
            campos.get("ativo"),
            agora,
            vid,
        ),
    )
    aplicar_valor_drop_produto_e_variantes(cur, id_tenant, prod_id, publicar=False, forcar=True)
    return int(prod_id)


def _atributos_de_variacao_bling(var: dict) -> dict:
    bloco = var.get("variacao") if isinstance(var.get("variacao"), dict) else {}
    nome = (bloco.get("nome") or "").strip()
    out: dict[str, str] = {}
    if not nome:
        return out
    for parte in nome.split(";"):
        parte = parte.strip()
        if ":" in parte:
            k, v = parte.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                out[k] = v
    return out


def _valores_atributos_texto(atributos: dict) -> str:
    if not isinstance(atributos, dict):
        return ""
    return " ".join(str(v).strip() for v in atributos.values() if str(v or "").strip())


def _descricao_composta_pai(pai_desc: str, atributos: dict) -> str:
    base = (pai_desc or "").strip()
    sufixo = _valores_atributos_texto(atributos)
    if not sufixo:
        return base
    if not base:
        return sufixo
    return f"{base} {sufixo}"


def _descricao_variante_bling(cur, id_produto: int, var: dict, atributos: dict) -> tuple[str, bool]:
    """Retorna (descricao, herda_pai) — nunca vazio na exibição; usa Bling, senão pai + atributos."""
    campos = extrair_campos_produto_bling(var)
    importada = (campos.get("descricao") or "").strip()
    cur.execute("SELECT descricao FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    pai_desc = (row[0] or "").strip() if row else ""
    if importada:
        return importada, False
    composta = _descricao_composta_pai(pai_desc, atributos) or pai_desc
    return composta, True


def _inserir_variante_bling(cur, id_produto: int, var: dict, ordem: int) -> int:
    campos = extrair_campos_produto_bling(var)
    sku = campos.get("sku") or ""
    nome = campos.get("nome") or sku or "Variação"
    preco = campos.get("preco") or 0
    preco_custo = campos.get("preco_custo")
    ativo = campos.get("ativo", True)
    atributos = _atributos_de_variacao_bling(var)
    descricao, herda_pai = _descricao_variante_bling(cur, id_produto, var, atributos)
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_produto_variante (
            id_produto, sku, nome_exibicao, preco, preco_custo, ativo, ordem,
            atributos, descricao, herda_pai, gtin, ncm, peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm, profundidade_cm,
            atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (
            id_produto,
            sku or None,
            nome,
            preco,
            preco_custo,
            ativo,
            ordem,
            json.dumps(atributos, ensure_ascii=False),
            descricao if not herda_pai else None,
            herda_pai,
            campos.get("gtin"),
            campos.get("ncm"),
            campos.get("peso_liquido_kg"),
            campos.get("peso_bruto_kg"),
            campos.get("altura_cm"),
            campos.get("largura_cm"),
            campos.get("profundidade_cm"),
            agora,
        ),
    )
    vid = _fetch_returning_id(cur, contexto="Falha ao inserir variação do produto.")
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, 0, %s) ON CONFLICT (id_variante) DO NOTHING
        """,
        (vid, agora),
    )
    return vid


def _salvar_produto_grupo_variacoes(
    cur,
    *,
    id_tenant: int,
    pai: dict,
    variacoes: list[dict],
    id_produto_existente: int | None,
    id_categoria: int | None = None,
    id_importacao_lote: int | None = None,
) -> int:
    campos = extrair_campos_produto_bling(pai)
    sku_raiz = _sku_pai_de_variacoes(pai, variacoes) or campos.get("sku")
    nome = campos.get("nome") or sku_raiz or "Produto Bling"
    campos["nome"] = nome
    campos["sku"] = sku_raiz or None
    campos["preco"] = preco_referencia_grupo(pai, variacoes)
    vals = tupla_campos_produto_sql(campos)
    agora = agora_utc()

    if id_produto_existente:
        cur.execute(
            """
            UPDATE tbl_produto SET
                nome = %s, descricao = %s, sku = %s, preco = %s, preco_custo = %s,
                unidade = %s, gtin = %s, ncm = %s, marca = %s, referencia = %s, condicao = %s,
                peso_liquido_kg = %s, peso_bruto_kg = %s, altura_cm = %s, largura_cm = %s,
                profundidade_cm = %s, moq = %s, volumes = %s, frete_gratis = %s,
                origem_fiscal = %s, cest = %s, producao = %s, ativo = %s, formato = 'E',
                id_categoria = COALESCE(%s, id_categoria), atualizado_em = %s
            WHERE id = %s AND id_tenant = %s
            RETURNING id
            """,
            vals + (id_categoria, agora, id_produto_existente, id_tenant),
        )
        row = cur.fetchone()
        if row and row[0]:
            prod_id = int(row[0])
            _limpar_variantes(cur, prod_id)
        else:
            id_produto_existente = None

    if not id_produto_existente:
        cur.execute(
            """
            INSERT INTO tbl_produto (
                id_tenant, id_categoria, nome, descricao, sku, preco, preco_custo, unidade,
                gtin, ncm, marca, referencia, condicao, peso_liquido_kg, peso_bruto_kg,
                altura_cm, largura_cm, profundidade_cm, moq, volumes, frete_gratis,
                origem_fiscal, cest, producao, ativo, publicado, formato, tipo, origem,
                id_importacao_lote, atualizado_em
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, FALSE, 'E', 'P', %s, %s, %s
            ) RETURNING id
            """,
            (
                id_tenant,
                id_categoria,
                *vals,
                ORIGEM_INTEGRACAO if id_importacao_lote else "manual",
                id_importacao_lote,
                agora,
            ),
        )
        prod_id = _fetch_returning_id(cur, contexto="Falha ao inserir produto com variações.")

    primeira_vid: int | None = None
    for ordem, var in enumerate(variacoes):
        vid = _inserir_variante_bling(cur, prod_id, var, ordem)
        if primeira_vid is None:
            primeira_vid = vid

    if primeira_vid:
        cur.execute(
            "UPDATE tbl_produto SET id_variante_padrao = %s, formato = 'E' WHERE id = %s",
            (primeira_vid, prod_id),
        )
    aplicar_valor_drop_produto_e_variantes(cur, id_tenant, prod_id, publicar=False, forcar=True)
    return prod_id


def _processar_item_produto(
    cur,
    *,
    id_tenant: int,
    contexto: str,
    cfg: dict,
    item: dict,
    cache_categorias: dict[str, dict],
    categorias_sincronizadas: set[str],
    ids_categoria_filtro: set[str] | None,
    id_segmento: int | None = None,
    id_importacao_lote: int | None = None,
    grupos_concluidos: set[str] | None = None,
    somente_mapa: bool = False,
) -> tuple[str, int | None]:
    id_bling = str(item.get("id") or "")
    sku_lista = (item.get("codigo") or "").strip()
    if not sku_lista:
        raise ValueError("SKU obrigatório.")

    detalhe = obter_produto(id_tenant, id_bling) if id_bling else item
    concluidos = grupos_concluidos if grupos_concluidos is not None else set()

    pai_id = _id_pai_bling(detalhe) or _id_pai_bling(item)
    if pai_id:
        if pai_id in concluidos:
            return "ignorado_filtro", None
        resultado, prod_id = _processar_grupo_variacoes(
            cur,
            id_tenant=id_tenant,
            contexto=contexto,
            cfg=cfg,
            job={"tipo": "grupo", "id_bling": pai_id, "item": None},
            cache_categorias=cache_categorias,
            categorias_sincronizadas=categorias_sincronizadas,
            ids_categoria_filtro=ids_categoria_filtro,
            id_segmento=id_segmento,
            id_importacao_lote=id_importacao_lote,
            grupos_concluidos=concluidos,
            somente_mapa=somente_mapa,
        )
        return resultado, prod_id

    if _eh_produto_pai_variacoes(detalhe) or _detalhe_eh_pai_variavel(id_tenant, detalhe):
        if id_bling in concluidos:
            return "ignorado_filtro", None
        resultado, prod_id = _processar_grupo_variacoes(
            cur,
            id_tenant=id_tenant,
            contexto=contexto,
            cfg=cfg,
            job={"tipo": "grupo", "id_bling": id_bling, "item": detalhe},
            cache_categorias=cache_categorias,
            categorias_sincronizadas=categorias_sincronizadas,
            ids_categoria_filtro=ids_categoria_filtro,
            id_segmento=id_segmento,
            id_importacao_lote=id_importacao_lote,
            grupos_concluidos=concluidos,
            somente_mapa=somente_mapa,
        )
        return resultado, prod_id

    sku = (detalhe.get("codigo") or sku_lista).strip()
    if not sku:
        raise ValueError("SKU obrigatório.")

    id_cat_bling = extrair_id_categoria_produto(detalhe)
    if ids_categoria_filtro is not None:
        if not id_cat_bling or id_cat_bling not in ids_categoria_filtro:
            return "ignorado_filtro", None

    if id_cat_bling:
        from api.bling.categorias_bling import categoria_bling_ignorada

        if categoria_bling_ignorada(cur, id_tenant, contexto, id_cat_bling):
            return "ignorado_categoria", None

    id_categoria_drop = None
    if id_cat_bling:
        id_categoria_drop = garantir_categoria_bling(
            cur,
            id_tenant,
            contexto,
            id_cat_bling,
            id_segmento=id_segmento,
            cache_api=cache_categorias,
            somente_mapa=somente_mapa,
        )
        categorias_sincronizadas.add(id_cat_bling)

    id_mapa, _ = _buscar_mapa(cur, id_tenant, contexto, id_bling)
    id_existente = _resolver_produto_existente(cur, id_tenant, id_mapa=id_mapa, sku=sku)

    criando = id_existente is None
    prod_id = _salvar_produto(
        cur,
        id_tenant=id_tenant,
        produto=detalhe,
        id_produto_existente=id_existente,
        id_categoria=id_categoria_drop,
        id_importacao_lote=id_importacao_lote if criando else None,
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
        {"nome": detalhe.get("nome"), "urls_imagem": urls, "id_categoria_bling": id_cat_bling},
    )
    return ("importado" if criando else "atualizado"), prod_id


def _processar_grupo_variacoes(
    cur,
    *,
    id_tenant: int,
    contexto: str,
    cfg: dict,
    job: dict,
    cache_categorias: dict[str, dict],
    categorias_sincronizadas: set[str],
    ids_categoria_filtro: set[str] | None,
    id_segmento: int | None = None,
    id_importacao_lote: int | None = None,
    grupos_concluidos: set[str] | None = None,
    somente_mapa: bool = False,
) -> tuple[str, int | None]:
    """Importa produto pai + todas as variações em uma única unidade (tudo ou nada)."""
    id_bling_pai = str(job.get("id_bling") or "")
    concluidos = grupos_concluidos if grupos_concluidos is not None else set()
    if id_bling_pai and id_bling_pai in concluidos:
        return "ignorado_filtro", None

    item_lista = job.get("item") or {}
    detalhe_pai = obter_produto(id_tenant, id_bling_pai) if id_bling_pai else item_lista
    if not detalhe_pai:
        raise ValueError("Produto pai não encontrado na API Bling.")

    vars_resp = obter_variacoes_produto(id_tenant, id_bling_pai)
    variacoes = _extrair_lista_variacoes(vars_resp)
    if not variacoes:
        variacoes = _extrair_lista_variacoes(detalhe_pai)

    problemas = _validar_grupo_variacoes(variacoes)
    if problemas:
        raise ValueError(
            "Nenhuma variação importada (regra tudo ou nada): " + "; ".join(problemas)
        )

    id_cat_bling = extrair_id_categoria_produto(detalhe_pai)
    if ids_categoria_filtro is not None:
        if not id_cat_bling or id_cat_bling not in ids_categoria_filtro:
            return "ignorado_filtro", None

    if id_cat_bling:
        from api.bling.categorias_bling import categoria_bling_ignorada

        if categoria_bling_ignorada(cur, id_tenant, contexto, id_cat_bling):
            return "ignorado_categoria", None

    id_categoria_drop = None
    if id_cat_bling:
        id_categoria_drop = garantir_categoria_bling(
            cur,
            id_tenant,
            contexto,
            id_cat_bling,
            id_segmento=id_segmento,
            cache_api=cache_categorias,
            somente_mapa=somente_mapa,
        )
        categorias_sincronizadas.add(id_cat_bling)

    id_mapa, _ = _buscar_mapa(cur, id_tenant, contexto, id_bling_pai)
    sku_raiz = _sku_pai_de_variacoes(detalhe_pai, variacoes)
    id_existente = _resolver_produto_existente(cur, id_tenant, id_mapa=id_mapa, sku=sku_raiz)

    criando = id_existente is None
    prod_id = _salvar_produto_grupo_variacoes(
        cur,
        id_tenant=id_tenant,
        pai=detalhe_pai,
        variacoes=variacoes,
        id_produto_existente=id_existente,
        id_categoria=id_categoria_drop,
        id_importacao_lote=id_importacao_lote if criando else None,
    )

    urls = extrair_urls_imagem_bling(detalhe_pai, variacoes=variacoes)
    sku_mapa = _sku_pai_de_variacoes(detalhe_pai, variacoes)
    if urls:
        aplicar_imagens_produto(
            cur,
            id_tenant=id_tenant,
            id_produto=prod_id,
            sku=sku_mapa or f"bling-{id_bling_pai}",
            urls=urls,
            modo_imagem=cfg["modo_imagem"],
            variacoes_bling=variacoes,
        )

    _upsert_mapa(
        cur,
        id_tenant,
        contexto,
        id_bling_pai,
        prod_id,
        sku_mapa,
        {
            "nome": detalhe_pai.get("nome"),
            "formato": "E",
            "qtd_variacoes": len(variacoes),
            "urls_imagem": urls,
            "id_categoria_bling": id_cat_bling,
        },
    )
    for var in variacoes:
        var_id = str(var.get("id") or "")
        if not var_id:
            continue
        var_sku = (var.get("codigo") or "").strip()
        _upsert_mapa(
            cur,
            id_tenant,
            contexto,
            var_id,
            prod_id,
            var_sku,
            {
                "nome": var.get("nome"),
                "formato": "V",
                "id_pai_bling": id_bling_pai,
            },
        )
        cur.execute(
            """
            SELECT id FROM tbl_produto_variante
            WHERE id_produto = %s AND sku IS NOT DISTINCT FROM %s
            ORDER BY id DESC LIMIT 1
            """,
            (prod_id, var_sku or None),
        )
        vrow = cur.fetchone()
        if vrow:
            pass

    if id_bling_pai:
        concluidos.add(id_bling_pai)
    return ("importado" if criando else "atualizado"), prod_id


def _iterar_listas_produtos(
    id_tenant: int,
    *,
    ids_categoria_api: list[str | None],
) -> list[dict]:
    """Busca produtos paginados; uma ou várias consultas por categoria Bling."""
    vistos: set[str] = set()
    acumulado: list[dict] = []
    for id_cat in ids_categoria_api:
        pagina = 1
        while True:
            lista = listar_produtos(
                id_tenant,
                pagina=pagina,
                limite=100,
                id_categoria=id_cat,
            )
            if not lista:
                break
            for item in lista:
                bid = str(item.get("id") or "")
                if bid and bid not in vistos:
                    vistos.add(bid)
                    acumulado.append(item)
            if len(lista) < 100:
                break
            pagina += 1
    return acumulado


def importar_produtos(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    id_categoria_bling: str | None = None,
    ids_categorias_bling: list[str] | None = None,
    incluir_subcategorias: bool = True,
    id_segmento: int | None = None,
    id_importacao_lote: int | None = None,
    id_usuario: int | None = None,
    modo_categorias: str = "mapeamento",
    on_progresso: Callable[[dict[str, int]], None] | None = None,
    intervalo_progresso: int = 3,
) -> dict[str, Any]:
    cfg = _garantir_config(cur, id_tenant, contexto)
    modo = cfg["produtos_modo"]
    if modo not in ("importar", "atualizar"):
        raise ValueError(f"Modo de produtos '{modo}' não permite importação. Altere para Importar ou Atualizar.")

    id_segmento_resolvido = resolver_id_segmento_import(cur, id_tenant, id_segmento)
    resumo_deps = resumo_depositos_bling(cur, id_tenant)
    somente_mapa = modo_categorias == "mapeamento"
    if modo_categorias == "legado":
        n_cats_arvore = sincronizar_arvore_categorias_bling(
            cur,
            id_tenant,
            contexto,
            id_segmento=id_segmento_resolvido,
        )
    else:
        n_cats_arvore = 0

    importados = 0
    atualizados = 0
    ignorados = 0
    falhas: list[dict[str, str]] = []
    categorias_sincronizadas: set[str] = set()
    cache_categorias: dict[str, dict] = {}

    ids_filtro: set[str] | None = None
    ids_categoria_api: list[str | None] = [None]

    raizes: list[str] = []
    if ids_categorias_bling:
        raizes = [str(c).strip() for c in ids_categorias_bling if str(c or "").strip()]
    elif id_categoria_bling:
        raizes = [str(id_categoria_bling).strip()]

    if raizes and not somente_mapa:
        ids_filtro = set()
        ids_categoria_api = []
        for cat_id in raizes:
            _savepoint(cur, _SAVEPOINT_PRODUTO)
            try:
                garantir_categoria_bling(
                    cur,
                    id_tenant,
                    contexto,
                    cat_id,
                    id_segmento=id_segmento_resolvido,
                    cache_api=cache_categorias,
                )
                _release_savepoint(cur, _SAVEPOINT_PRODUTO)
            except Exception as e:
                _rollback_savepoint(cur, _SAVEPOINT_PRODUTO)
                raise ValueError(f"Categoria Bling #{cat_id}: {e}") from e
            categorias_sincronizadas.add(cat_id)
            if incluir_subcategorias:
                ids_cat = ids_categoria_bling_com_descendentes(
                    id_tenant,
                    cat_id,
                    incluir_subcategorias=True,
                )
            else:
                ids_cat = {cat_id}
            ids_filtro |= ids_cat
            ids_categoria_api.extend(ids_cat)
        ids_categoria_api = sorted(set(ids_categoria_api))
    elif raizes:
        ids_filtro = set()
        ids_categoria_api = []
        for cat_id in raizes:
            if incluir_subcategorias:
                ids_cat = ids_categoria_bling_com_descendentes(
                    id_tenant,
                    cat_id,
                    incluir_subcategorias=True,
                )
            else:
                ids_cat = {cat_id}
            ids_filtro |= ids_cat
            ids_categoria_api.extend(ids_cat)
        ids_categoria_api = sorted(set(ids_categoria_api))

    itens = _iterar_listas_produtos(id_tenant, ids_categoria_api=ids_categoria_api)
    jobs = _preparar_jobs_importacao(itens)
    grupos_concluidos: set[str] = set()
    total_jobs = len(jobs)

    def _emitir_progresso(processados: int) -> None:
        if not on_progresso:
            return
        on_progresso(
            {
                "total": total_jobs,
                "processados": processados,
                "importados": importados,
                "atualizados": atualizados,
                "ignorados": ignorados,
                "rejeitadas": len(falhas),
            }
        )

    if on_progresso:
        _emitir_progresso(0)

    for idx, job in enumerate(jobs, start=1):
        id_bling = str(job.get("id_bling") or "")
        item = job.get("item") or {}
        nome_ref = (item.get("nome") or "").strip()
        sku_ref = (item.get("codigo") or "").strip()
        tipo_job = job.get("tipo") or "simples"
        _savepoint(cur, _SAVEPOINT_PRODUTO)
        try:
            if tipo_job == "grupo":
                resultado, _ = _processar_grupo_variacoes(
                    cur,
                    id_tenant=id_tenant,
                    contexto=contexto,
                    cfg=cfg,
                    job=job,
                    cache_categorias=cache_categorias,
                    categorias_sincronizadas=categorias_sincronizadas,
                    ids_categoria_filtro=ids_filtro,
                    id_segmento=id_segmento_resolvido,
                    id_importacao_lote=id_importacao_lote,
                    grupos_concluidos=grupos_concluidos,
                    somente_mapa=somente_mapa,
                )
            else:
                resultado, _ = _processar_item_produto(
                    cur,
                    id_tenant=id_tenant,
                    contexto=contexto,
                    cfg=cfg,
                    item=item,
                    cache_categorias=cache_categorias,
                    categorias_sincronizadas=categorias_sincronizadas,
                    ids_categoria_filtro=ids_filtro,
                    id_segmento=id_segmento_resolvido,
                    id_importacao_lote=id_importacao_lote,
                    grupos_concluidos=grupos_concluidos,
                    somente_mapa=somente_mapa,
                )
            _release_savepoint(cur, _SAVEPOINT_PRODUTO)
            if resultado == "importado":
                importados += 1
            elif resultado == "atualizado":
                atualizados += 1
            elif resultado in ("ignorado_filtro", "ignorado_categoria"):
                ignorados += 1
        except Exception as e:
            _rollback_savepoint(cur, _SAVEPOINT_PRODUTO)
            if tipo_job == "grupo" and not nome_ref:
                try:
                    pai = obter_produto(id_tenant, id_bling)
                    nome_ref = (pai.get("nome") or "").strip()
                    sku_ref = (pai.get("codigo") or "").strip()
                except Exception:
                    pass
            motivo_tecnico = str(e)
            extra: dict[str, Any] = {
                "tipo_job": tipo_job,
                "id_bling": id_bling,
                "contexto_integracao": contexto,
            }
            if tipo_job == "grupo":
                extra["job"] = {
                    k: job.get(k)
                    for k in ("id_bling", "tipo")
                    if job.get(k) is not None
                }
            elif item:
                extra["bling_resumo"] = {
                    k: item.get(k)
                    for k in ("id", "codigo", "nome", "formato", "situacao", "preco")
                    if item.get(k) is not None
                }
            payload_erro = montar_payload_erro(
                mensagem_tecnica=motivo_tecnico,
                origem="bling",
                extra=extra,
                traceback_txt=traceback.format_exc(),
            )
            _registrar_falha(
                falhas,
                id_bling=id_bling,
                nome=nome_ref,
                sku=sku_ref,
                motivo=motivo_tecnico,
                tipo="grupo_variacoes" if tipo_job == "grupo" else "produto",
            )
            if id_importacao_lote:
                registrar_erro_lote(
                    cur,
                    id_tenant=id_tenant,
                    id_lote=id_importacao_lote,
                    modulo=MODULO_CATALOGO,
                    ref_externa=id_bling,
                    nome_registro=nome_ref,
                    sku_registro=sku_ref,
                    mensagem=motivo_tecnico,
                    payload=payload_erro,
                    origem="bling",
                )

        if on_progresso and (idx % intervalo_progresso == 0 or idx == total_jobs):
            _emitir_progresso(idx)

    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET ultima_sync_produtos = %s, atualizado_em = %s
        WHERE id_tenant = %s AND contexto = %s
        """,
        (agora_utc(), agora_utc(), id_tenant, contexto),
    )

    cat_n = len(categorias_sincronizadas)
    if raizes:
        escopo = f"categorias ({len(raizes)} selecionada(s))"
    else:
        escopo = "todos"
    resumo = (
        f"Importados: {importados}, atualizados: {atualizados}, ignorados: {ignorados}"
        f", falhas: {len(falhas)} · categorias: {cat_n} (árvore: {n_cats_arvore})"
        f" · depósitos vinculados: {resumo_deps.get('vinculados', 0)}"
        f" · escopo: {escopo}"
    )
    if falhas:
        status = "erro" if importados + atualizados == 0 else "aviso"
    else:
        status = "ok"
    detalhe_log = json.dumps({"falhas": falhas[:80]}, ensure_ascii=False)
    _registrar_log(cur, id_tenant, contexto, status, resumo, detalhe_log)

    if id_importacao_lote and not on_progresso:
        lote_status = STATUS_ERRO if importados + atualizados == 0 else STATUS_CONCLUIDO
        finalizar_lote(
            cur,
            id_importacao_lote,
            status=lote_status,
            total_linhas=total_jobs,
            total_importadas=importados,
            total_atualizadas=atualizados,
            total_rejeitadas=len(falhas),
            meta={"contexto": contexto, "escopo": escopo, "id_usuario": id_usuario},
        )

    erros_txt = [f"Bling #{f['id_bling']}: {f['motivo']}" for f in falhas]
    return {
        "importados": importados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "falhas": falhas,
        "total_falhas": len(falhas),
        "total_jobs": total_jobs,
        "categorias": cat_n,
        "categorias_arvore": n_cats_arvore,
        "depositos": resumo_deps,
        "id_segmento": id_segmento_resolvido,
        "erros": erros_txt[:50],
        "status": status,
        "resumo": resumo,
        "id_importacao_lote": id_importacao_lote,
    }


# ── export_produtos ───────────────────────────────────

import json
from typing import Any

from api.bling.cliente import api_request, listar_depositos_bling
from global_utils import agora_utc


def _registrar_log(
    cur,
    id_tenant: int,
    contexto: str,
    status: str,
    resumo: str,
    detalhe: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_log (
            id_tenant, provedor, contexto, entidade, direcao, status, resumo, detalhe
        ) VALUES (%s, 'bling', %s, 'produto', 'exportar', %s, %s, %s)
        """,
        (id_tenant, contexto, status, resumo, detalhe),
    )


def _garantir_config(cur, id_tenant: int, contexto: str) -> dict:
    cur.execute(
        """
        SELECT produtos_modo, estoque_modo, opcoes
        FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s AND ativo = TRUE
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Configure a integração Bling antes de exportar produtos.")
    opcoes = row[2] or {}
    if isinstance(opcoes, str) and opcoes.strip():
        try:
            opcoes = json.loads(opcoes) or {}
        except json.JSONDecodeError:
            opcoes = {}
    return {
        "produtos_modo": row[0] or "exportar",
        "estoque_modo": row[1] or "exportar",
        "opcoes": opcoes if isinstance(opcoes, dict) else {},
    }


def _buscar_id_bling_mapa(
    cur, id_tenant: int, contexto: str, *, id_variante: int | None = None, sku: str | None = None
) -> str | None:
    if id_variante:
        cur.execute(
            """
            SELECT id_bling FROM tbl_integracao_map
            WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
              AND entidade = 'produto' AND id_dropnexo = %s
            LIMIT 1
            """,
            (id_tenant, contexto, id_variante),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0])
    sku = (sku or "").strip()
    if sku:
        cur.execute(
            """
            SELECT id_bling FROM tbl_integracao_map
            WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
              AND entidade = 'produto' AND TRIM(sku) = %s
            LIMIT 1
            """,
            (id_tenant, contexto, sku),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0])
    return None


def _upsert_mapa(
    cur, id_tenant: int, contexto: str, id_bling: str, id_variante: int, sku: str, meta: dict
) -> None:
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
        (id_tenant, contexto, id_bling, id_variante, sku, json.dumps(meta, ensure_ascii=False), agora_utc()),
    )


def _deposito_bling_padrao(id_tenant: int) -> str | None:
    deps = listar_depositos_bling(id_tenant)
    for dep in deps:
        did = dep.get("id")
        if did not in (None, ""):
            return str(did)
    return None


def _montar_payload_produto(row: tuple) -> dict[str, Any]:
    (
        _pv_id,
        id_variante,
        sku,
        nome,
        preco,
        _estoque,
        descricao,
        unidade,
        imagem_url,
        ncm,
        gtin,
    ) = row
    payload: dict[str, Any] = {
        "nome": (nome or sku or f"Variante {id_variante}")[:120],
        "codigo": sku,
        "preco": float(preco or 0),
        "tipo": "P",
        "situacao": "A",
        "formato": "S",
        "unidade": (unidade or "UN")[:20],
    }
    if descricao:
        payload["descricaoCurta"] = str(descricao)[:5000]
    if ncm:
        payload["ncm"] = str(ncm)[:10]
    if gtin:
        payload["gtin"] = str(gtin)[:20]
    url = (imagem_url or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        payload["midia"] = {"imagens": {"externas": [{"link": url}]}}
    return payload


def _exportar_estoque_variante(
    cur,
    id_tenant: int,
    *,
    id_bling: str,
    quantidade: int,
    id_deposito_bling: str,
) -> tuple[bool, str | None]:
    qtd = max(0, int(quantidade))
    try:
        api_request(
            id_tenant,
            "POST",
            "/estoques",
            json_body={
                "produto": {"id": int(id_bling)},
                "deposito": {"id": int(id_deposito_bling)},
                "operacao": "B",
                "quantidade": qtd,
                "observacoes": "Sincronizado via DropNexo (Meus produtos)",
            },
        )
        agora = agora_utc()
        cur.execute(
            """
            UPDATE tbl_integracao_bling_config
            SET ultima_sync_estoque_enviado = %s, atualizado_em = %s
            WHERE id_tenant = %s AND contexto = 'vendedor'
            """,
            (agora, agora, id_tenant),
        )
        return True, None
    except Exception as e:
        return False, str(e)


def exportar_produtos_vendedor(
    cur,
    id_tenant: int,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    if id_usuario is not None:
        pass  # reservado para auditoria futura

    cfg = _garantir_config(cur, id_tenant, "vendedor")
    modo_prod = (cfg["produtos_modo"] or "exportar").strip()
    if modo_prod not in ("exportar", "atualizar"):
        raise ValueError("Modo de produtos não permite exportar ao Bling. Ative em Integrações → Bling → Produtos.")

    modo_est = (cfg["estoque_modo"] or "exportar").strip()
    exportar_estoque = modo_est in ("exportar", "atualizar")
    opcoes = cfg.get("opcoes") or {}
    if opcoes.get("produtos_exportar") is False:
        raise ValueError("Exportação de produtos está desativada. Ative na aba Produtos.")

    id_dep_bling = _deposito_bling_padrao(id_tenant) if exportar_estoque else None
    if exportar_estoque and not id_dep_bling:
        raise ValueError("Nenhum depósito encontrado no Bling para sincronizar estoque.")

    cur.execute(
        """
        SELECT pv.id, v.id, TRIM(v.sku),
               COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), v.nome_exibicao, p.nome),
               pv.preco_venda, COALESCE(e.quantidade, 0),
               p.descricao, COALESCE(p.unidade, 'UN'),
               COALESCE(NULLIF(TRIM(pv.imagem_url_vitrine), ''), v.imagem_url, p.imagem_url),
               p.ncm, p.gtin
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
          AND v.ativo = TRUE AND p.ativo = TRUE
        ORDER BY p.nome, v.ordem, v.id
        """,
        (id_tenant,),
    )
    linhas = cur.fetchall()

    exportados = 0
    atualizados = 0
    ignorados = 0
    estoque_ok = 0
    falhas: list[dict[str, str]] = []

    for row in linhas:
        sku = (row[2] or "").strip()
        id_variante = int(row[1])
        if not sku:
            ignorados += 1
            falhas.append({"sku": "", "motivo": f"Variante #{id_variante} sem SKU"})
            continue

        payload = _montar_payload_produto(row)
        id_bling = _buscar_id_bling_mapa(cur, id_tenant, "vendedor", id_variante=id_variante, sku=sku)
        try:
            if id_bling:
                api_request(id_tenant, "PUT", f"/produtos/{id_bling}", json_body=payload)
                atualizados += 1
                acao = "atualizado"
            else:
                resp = api_request(id_tenant, "POST", "/produtos", json_body=payload)
                criado = resp.get("data") if isinstance(resp.get("data"), dict) else {}
                novo_id = criado.get("id")
                if not novo_id:
                    raise RuntimeError("Bling não retornou ID do produto criado.")
                id_bling = str(novo_id)
                exportados += 1
                acao = "exportado"

            _upsert_mapa(
                cur,
                id_tenant,
                "vendedor",
                id_bling,
                id_variante,
                sku,
                {"nome": payload.get("nome"), "acao": acao},
            )

            if exportar_estoque and id_dep_bling and opcoes.get("estoque_exportar", True) is not False:
                ok_est, err_est = _exportar_estoque_variante(
                    cur,
                    id_tenant,
                    id_bling=id_bling,
                    quantidade=int(row[5] or 0),
                    id_deposito_bling=id_dep_bling,
                )
                if ok_est:
                    estoque_ok += 1
                elif err_est:
                    falhas.append({"sku": sku, "motivo": f"Estoque: {err_est}"})
        except Exception as e:
            falhas.append({"sku": sku, "motivo": str(e)[:300]})

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET ultima_sync_produtos = %s, atualizado_em = %s
        WHERE id_tenant = %s AND contexto = 'vendedor'
        """,
        (agora, agora, id_tenant),
    )

    total_ok = exportados + atualizados
    resumo = (
        f"{exportados} exportado(s), {atualizados} atualizado(s), {ignorados} ignorado(s), "
        f"{estoque_ok} estoque(s), {len(falhas)} falha(s)."
    )
    status_log = "ok" if not falhas else ("aviso" if total_ok else "erro")
    _registrar_log(cur, id_tenant, "vendedor", status_log, resumo)

    return {
        "exportados": exportados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "estoque_sincronizado": estoque_ok,
        "falhas": falhas,
        "total_falhas": len(falhas),
        "message": resumo,
    }
