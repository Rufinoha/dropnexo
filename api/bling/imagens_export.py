# api/bling/imagens_export.py — URL pública estável + JPG normalizado para export Bling
from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from global_utils import obter_base_url

logger = logging.getLogger(__name__)

_IMG_PUBLICA_VALIDADE_S = 7 * 24 * 3600
MAX_LADO_PX = 1800
JPG_QUALITY = 85
MIN_LADO_OK = 800
MIN_LADO_BLOQUEIO = 400
MAX_BYTES_DOWNLOAD = 8 * 1024 * 1024
CACHE_PREFIX = "upload/bling_export_cache"


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]


def assinatura_imagem_publica(caminho: str, exp: int) -> str:
    secret = (os.getenv("SECRET_KEY") or "dev-inseguro").encode("utf-8")
    raw = f"{caminho}|{exp}".encode("utf-8")
    return hmac.new(secret, raw, hashlib.sha256).hexdigest()[:40]


def validar_assinatura_imagem_publica(caminho: str, exp: int, sig: str) -> bool:
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < int(time.time()):
        return False
    esperado = assinatura_imagem_publica(caminho, exp_i)
    return hmac.compare_digest(esperado, (sig or "").strip())


def caminho_publico_permitido(caminho: str) -> bool:
    rel = (caminho or "").replace("\\", "/").lstrip("/").lower()
    if ".." in rel.split("/"):
        return False
    if rel.startswith(f"{CACHE_PREFIX}/") and rel.endswith(".jpg"):
        return True
    if rel.startswith("upload/tenant") and "/produtos/" in rel:
        return True
    return False


def url_assinada_publica(rel_caminho: str) -> str:
    rel = rel_caminho.replace("\\", "/").lstrip("/")
    exp = int(time.time()) + _IMG_PUBLICA_VALIDADE_S
    sig = assinatura_imagem_publica(rel, exp)
    base = obter_base_url().rstrip("/")
    qs = urlencode({"c": rel, "e": exp, "s": sig})
    return f"{base}/api/produto-imagem/publico?{qs}"


def resolver_arquivo_local(caminho: str | None) -> Path | None:
    s = (caminho or "").strip().replace("\\", "/").lstrip("/")
    if not s or ".." in s.split("/"):
        return None
    if s.lower().startswith("static/"):
        s = s[7:]
    root = _raiz_projeto()
    if s.lower().startswith("upload/"):
        p = root / s.replace("/", os.sep)
    elif s.lower().startswith("imge/produtos/"):
        p = root / "static" / s.replace("/", os.sep)
    else:
        return None
    return p if p.is_file() else None


def _hash_cache(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8", errors="ignore"))
        h.update(b"\0")
    return h.hexdigest()[:20]


def _pasta_cache() -> Path:
    pasta = _raiz_projeto() / "upload" / "bling_export_cache"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _abrir_rgb(conteudo: bytes):
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(conteudo))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        fundo.paste(rgba, mask=rgba.split()[-1])
        return fundo
    return img.convert("RGB")


def normalizar_para_jpg(
    conteudo: bytes,
    *,
    bloquear_pequena: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    """Retorna JPEG otimizado + meta (largura, altura, fraca)."""
    from PIL import Image

    img = _abrir_rgb(conteudo)
    w, h = img.size
    lado = min(w, h)
    meta = {
        "largura": w,
        "altura": h,
        "fraca": lado < MIN_LADO_OK,
        "bloqueada": lado < MIN_LADO_BLOQUEIO,
    }
    if bloquear_pequena and meta["bloqueada"]:
        raise ValueError(
            f"Imagem muito pequena ({w}×{h}). Mínimo: {MIN_LADO_BLOQUEIO}px no menor lado."
        )

    if max(w, h) > MAX_LADO_PX:
        img.thumbnail((MAX_LADO_PX, MAX_LADO_PX), Image.Resampling.LANCZOS)
        meta["largura"], meta["altura"] = img.size

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), meta


def _baixar_remoto(url: str) -> bytes:
    resp = requests.get(
        url,
        timeout=25,
        stream=True,
        headers={"User-Agent": "DropNexo-BlingExport/1.0"},
    )
    if resp.status_code >= 400:
        raise ValueError(f"HTTP {resp.status_code} ao baixar imagem remota.")
    total = 0
    chunks: list[bytes] = []
    for chunk in resp.iter_content(64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES_DOWNLOAD:
            raise ValueError("Imagem remota excede o tamanho máximo permitido.")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise ValueError("Imagem remota vazia.")
    return data


def _gravar_cache(chave: str, jpg: bytes) -> str:
    nome = f"{chave}.jpg"
    pasta = _pasta_cache()
    full = pasta / nome
    if not full.is_file() or full.stat().st_size != len(jpg):
        tmp = pasta / f".{nome}.tmp"
        tmp.write_bytes(jpg)
        tmp.replace(full)
    return f"{CACHE_PREFIX}/{nome}"


def preparar_imagem_export(caminho: str | None) -> dict[str, Any]:
    """
    Prepara uma imagem para o Bling.
    Retorno: {ok, url, motivo, fraca, fonte, cache}
    """
    s = (caminho or "").strip()
    if not s:
        return {"ok": False, "url": None, "motivo": "caminho_vazio", "fraca": False}

    try:
        if s.lower().startswith(("http://", "https://")):
            try:
                bruto = _baixar_remoto(s)
                chave = _hash_cache("url", s, str(len(bruto)))
                jpg, meta = normalizar_para_jpg(bruto)
                rel = _gravar_cache(chave, jpg)
                return {
                    "ok": True,
                    "url": url_assinada_publica(rel),
                    "motivo": None,
                    "fraca": bool(meta.get("fraca")),
                    "fonte": "remota_cache",
                    "cache": rel,
                    "largura": meta.get("largura"),
                    "altura": meta.get("altura"),
                }
            except Exception as e:
                # Fallback: manda a URL original (comportamento antigo) se ainda for https
                logger.warning("Falha ao normalizar URL remota %s: %s", s[:120], e)
                if s.lower().startswith("https://"):
                    return {
                        "ok": True,
                        "url": s,
                        "motivo": f"fallback_url: {e}",
                        "fraca": False,
                        "fonte": "remota_passthrough",
                        "cache": None,
                    }
                return {"ok": False, "url": None, "motivo": str(e)[:200], "fraca": False}

        local = resolver_arquivo_local(s)
        if not local:
            return {
                "ok": False,
                "url": None,
                "motivo": "arquivo_local_nao_encontrado",
                "fraca": False,
            }

        st = local.stat()
        chave = _hash_cache("local", str(local), str(int(st.st_mtime)), str(st.st_size))
        cache_rel = f"{CACHE_PREFIX}/{chave}.jpg"
        cache_full = _raiz_projeto() / cache_rel.replace("/", os.sep)
        if cache_full.is_file() and cache_full.stat().st_size > 0:
            return {
                "ok": True,
                "url": url_assinada_publica(cache_rel),
                "motivo": None,
                "fraca": False,
                "fonte": "local_cache",
                "cache": cache_rel,
            }

        jpg, meta = normalizar_para_jpg(local.read_bytes())
        rel = _gravar_cache(chave, jpg)
        return {
            "ok": True,
            "url": url_assinada_publica(rel),
            "motivo": None,
            "fraca": bool(meta.get("fraca")),
            "fonte": "local_novo",
            "cache": rel,
            "largura": meta.get("largura"),
            "altura": meta.get("altura"),
        }
    except Exception as e:
        logger.exception("preparar_imagem_export falhou")
        return {"ok": False, "url": None, "motivo": str(e)[:220], "fraca": False}


def caminho_arquivo_cache(cache_rel: str | None) -> Path | None:
    """Resolve Path absoluto do JPG em cache (se existir)."""
    rel = (cache_rel or "").replace("\\", "/").lstrip("/")
    if not rel or not caminho_publico_permitido(rel):
        return None
    p = _raiz_projeto() / rel.replace("/", os.sep)
    return p if p.is_file() else None


def coletar_caminhos_galeria_export(
    cur,
    *,
    id_produto: int,
    id_variante: int | None = None,
    imagem_fallback: str = "",
) -> list[str]:
    """Galeria da variação → galeria do pai → fallback (vitrine)."""
    from fornecedor.catalogo.catalogo import listar_imagens_galeria_pai

    caminhos: list[str] = []
    if id_variante:
        cur.execute(
            """
            SELECT i.caminho
            FROM tbl_produto_variante_imagem vi
            JOIN tbl_produto_imagem i ON i.id = vi.id_imagem
            WHERE vi.id_variante = %s
            ORDER BY vi.ordem ASC, vi.id_imagem ASC
            """,
            (int(id_variante),),
        )
        for row in cur.fetchall():
            c = (row[0] or "").strip()
            if c:
                caminhos.append(c)

    if not caminhos and id_produto:
        try:
            for img in listar_imagens_galeria_pai(cur, int(id_produto)):
                c = (img.get("caminho") or "").strip()
                if c:
                    caminhos.append(c)
        except Exception:
            pass

    fb = (imagem_fallback or "").strip()
    if fb and fb not in caminhos:
        caminhos.insert(0, fb)
    return caminhos


def preparar_links_export(
    caminhos: list[str] | None,
    *,
    max_links: int = 6,
) -> dict[str, Any]:
    """Prepara URLs públicas JPG para qualquer integração (Bling, ML, Amazon, TikTok…)."""
    links: list[str] = []
    seen: set[str] = set()
    ignoradas: list[dict[str, str]] = []
    fracas = 0
    detalhes: list[dict[str, Any]] = []

    for cand in caminhos or []:
        if len(links) >= max_links:
            break
        prep = preparar_imagem_export(cand)
        detalhes.append({"caminho": (cand or "")[:240], **prep})
        if not prep.get("ok") or not prep.get("url"):
            ignoradas.append(
                {
                    "caminho": (cand or "")[:180],
                    "motivo": str(prep.get("motivo") or "falha"),
                }
            )
            continue
        url = prep["url"]
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
        if prep.get("fraca"):
            fracas += 1

    return {
        "links": links,
        "ignoradas": ignoradas,
        "fracas": fracas,
        "detalhes": detalhes,
    }


# Alias legado (Bling)
preparar_links_export_bling = preparar_links_export


def validar_imagem_upload_bytes(conteudo: bytes) -> dict[str, Any]:
    """Validação na entrada (fornecedor). Lança ValueError se bloqueada."""
    if not conteudo:
        raise ValueError("Arquivo de imagem vazio.")
    jpg, meta = normalizar_para_jpg(conteudo, bloquear_pequena=True)
    return {
        "ok": True,
        "jpg": jpg,
        "largura": meta["largura"],
        "altura": meta["altura"],
        "fraca": meta["fraca"],
        "aviso": (
            f"Imagem abaixo de {MIN_LADO_OK}px no menor lado — pode ficar ruim no Bling/marketplaces."
            if meta["fraca"]
            else None
        ),
    }
