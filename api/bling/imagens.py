# api/bling/imagens.py — importação de imagens Bling (link ou download)
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from fornecedor.catalogo.servico_imagens import (
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
