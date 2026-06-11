# api/bling/imagens.py — importação de imagens Bling (link ou download)
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

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


def _caminho_eh_url(caminho: str | None) -> bool:
    c = (caminho or "").strip().lower()
    return c.startswith("http://") or c.startswith("https://")


def pasta_imagens_sku(id_tenant: int, sku: str) -> Path:
    pasta = _raiz_projeto() / "upload" / f"tenant{id_tenant}" / "produtos" / sanitizar_sku_pasta(sku)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def caminho_db_imagem(id_tenant: int, sku: str, nome_arquivo: str) -> str:
    return f"upload/tenant{id_tenant}/produtos/{sanitizar_sku_pasta(sku)}/{nome_arquivo}"


def extrair_urls_imagem_bling(produto: dict) -> list[str]:
    urls: list[str] = []

    def add(u: str | None) -> None:
        u = (u or "").strip()
        if u and u.startswith(("http://", "https://")) and u not in urls:
            urls.append(u)

    add(produto.get("imagemURL"))
    add(produto.get("imagemUrl"))

    midia = produto.get("midia") or {}
    if isinstance(midia, dict):
        imagens = midia.get("imagens") or midia.get("imagem") or []
        if isinstance(imagens, dict):
            imagens = imagens.get("externas") or imagens.get("internas") or [imagens]
        if isinstance(imagens, list):
            for item in imagens:
                if isinstance(item, str):
                    add(item)
                elif isinstance(item, dict):
                    add(item.get("link") or item.get("url") or item.get("href"))

    raw = produto.get("urlImagensExternas") or produto.get("imagensExternas")
    if isinstance(raw, str) and "|" in raw:
        for parte in raw.split("|"):
            add(parte)
    elif isinstance(raw, str):
        add(raw)

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


def limpar_galeria_produto(cur, id_produto: int) -> None:
    cur.execute(
        "SELECT caminho FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL",
        (id_produto,),
    )
    for row in cur.fetchall():
        caminho = row[0]
        if caminho and not _caminho_eh_url(caminho):
            rel = caminho.replace("\\", "/").lstrip("/")
            if rel.lower().startswith("upload/") and ".." not in rel:
                p = _raiz_projeto() / rel.replace("/", os.sep)
                if p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass
    cur.execute("DELETE FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL", (id_produto,))


def aplicar_imagens_produto(
    cur,
    *,
    id_tenant: int,
    id_produto: int,
    sku: str,
    urls: list[str],
    modo_imagem: str,
) -> str | None:
    """Retorna caminho/URL da imagem principal ou None."""
    if not urls:
        return None

    limpar_galeria_produto(cur, id_produto)
    principal: str | None = None

    for idx, url in enumerate(urls):
        ordem = idx
        caminho_db = url
        if modo_imagem == "download":
            ext = _extensao_de_url(url)
            nome = f"{idx + 1:02d}-principal{ext}" if idx == 0 else f"{idx + 1:02d}-img{ext}"
            pasta = pasta_imagens_sku(id_tenant, sku)
            destino = pasta / nome
            baixar_imagem(url, destino)
            caminho_db = caminho_db_imagem(id_tenant, sku, nome)

        cur.execute(
            """
            INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal)
            VALUES (%s, %s, %s, %s)
            """,
            (id_produto, caminho_db, ordem, idx == 0),
        )
        if idx == 0:
            principal = caminho_db

    if principal:
        cur.execute(
            "UPDATE tbl_produto SET imagem_url = %s, atualizado_em = %s WHERE id = %s AND id_tenant = %s",
            (principal, agora_utc(), id_produto, id_tenant),
        )
        cur.execute(
            """
            UPDATE tbl_produto_variante SET imagem_url = %s, atualizado_em = %s
            WHERE id = (SELECT id_variante_padrao FROM tbl_produto WHERE id = %s)
            """,
            (principal, agora_utc(), id_produto),
        )
    return principal
