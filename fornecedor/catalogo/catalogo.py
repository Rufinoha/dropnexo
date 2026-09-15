# fornecedor/catalogo/catalogo.py — imagens, estoque por depósito e promoção de variantes
from __future__ import annotations

# ── servico_promocao_variante ─────────────────────────

from datetime import date, datetime

from global_utils import agora_utc


def _parse_date(val) -> date | None:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def promocao_variante_ativa(
    *,
    preco_promocional,
    promocao_validade=None,
    promocao_ate_zerar_estoque: bool = False,
    estoque: int = 0,
) -> bool:
    if preco_promocional in (None, ""):
        return False
    try:
        if float(preco_promocional) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    fim = _parse_date(promocao_validade)
    if fim and date.today() > fim:
        return False
    if promocao_ate_zerar_estoque and int(estoque or 0) <= 0:
        return False
    return True


def encerrar_promocao_variante(cur, id_variante: int) -> None:
    cur.execute(
        """
        UPDATE tbl_produto_variante SET
            preco_promocional = NULL,
            promocao_validade = NULL,
            promocao_ate_zerar_estoque = FALSE,
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_variante),
    )


def reagir_estoque_promocao(cur, id_variante: int, total_antes: int, total_depois: int) -> bool:
    """Encerra promo 'até zerar estoque' ao esgotar ou ao repor estoque."""
    cur.execute(
        """
        SELECT promocao_ate_zerar_estoque, preco_promocional
        FROM tbl_produto_variante WHERE id = %s
        """,
        (id_variante,),
    )
    row = cur.fetchone()
    if not row or not row[0] or row[1] is None:
        return False
    if total_depois <= 0 or (total_antes <= 0 and total_depois > 0):
        encerrar_promocao_variante(cur, id_variante)
        return True
    return False


# ── servico_imagens ───────────────────────────────────

import ipaddress
import io
import os
import re
import socket
import time
from datetime import timezone
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from global_utils import agora_utc, url_imagem_produto

MAX_IMAGENS_PRODUTO = 10
HOSTS_BLING = ("bling.com.br", "orgbling.com.br", "orgbling.s3.amazonaws.com")
MODOS_IMAGEM_BLING = frozenset({"link", "hibrido", "download"})
_QUERY_ASSINADA = frozenset(
    {
        "expires",
        "signature",
        "awsaccesskeyid",
        "x-amz-signature",
        "x-amz-expires",
        "x-amz-credential",
        "x-amz-security-token",
    }
)

ATRIBUTOS_VISUAIS = ("cor", "color", "colour", "estampa", "modelo", "sabor")


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]


def caminho_eh_url(caminho: str | None) -> bool:
    c = (caminho or "").strip().lower()
    return c.startswith("http://") or c.startswith("https://")


def tipo_de_caminho(caminho: str | None) -> str:
    return "link" if caminho_eh_url(caminho) else "upload"


def normalizar_modo_imagem_bling(modo: str | None) -> str:
    m = (modo or "").strip().lower()
    if m in MODOS_IMAGEM_BLING:
        return m
    return "download"


_COLS_VINCULO_OK = False


def garantir_colunas_vinculo_imagem(cur) -> None:
    """Garante colunas de vínculo Bling (idempotente). Uma vez por processo após OK."""
    global _COLS_VINCULO_OK
    if _COLS_VINCULO_OK:
        return
    try:
        cur.execute("SAVEPOINT sp_img_vinculo")
        cur.execute(
            """
            ALTER TABLE tbl_produto_imagem
                ADD COLUMN IF NOT EXISTS bling_anexo_id BIGINT NULL
            """
        )
        cur.execute(
            """
            ALTER TABLE tbl_produto_imagem
                ADD COLUMN IF NOT EXISTS url_origem TEXT NULL
            """
        )
        cur.execute("RELEASE SAVEPOINT sp_img_vinculo")
        _COLS_VINCULO_OK = True
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sp_img_vinculo")
        except Exception:
            conn = getattr(cur, "connection", None)
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass


def url_imagem_temporaria(url: str | None) -> bool:
    """Detecta URL assinada / hospedagem Bling que expira."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return False
    parsed = urlparse(u)
    host = (parsed.hostname or "").lower()
    if "orgbling" in host:
        return True
    qs_keys = {
        parte.split("=", 1)[0].lower()
        for parte in (parsed.query or "").split("&")
        if parte
    }
    return bool(qs_keys & _QUERY_ASSINADA)


def expira_em_de_url(url: str | None) -> datetime | None:
    """Extrai validade de URL assinada AWS (Expires unix ou X-Amz-Date + X-Amz-Expires)."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return None
    qs = parse_qs(urlparse(u).query)
    for key in ("Expires", "expires"):
        vals = qs.get(key) or []
        if not vals:
            continue
        try:
            ts = int(str(vals[0]).strip())
            if ts > 1_000_000_000:
                return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    amz_exp = (qs.get("X-Amz-Expires") or qs.get("x-amz-expires") or [None])[0]
    amz_date = (qs.get("X-Amz-Date") or qs.get("x-amz-date") or [None])[0]
    if amz_exp and amz_date:
        try:
            segundos = int(str(amz_exp).strip())
            raw = str(amz_date).strip()
            if raw.endswith("Z") and "T" in raw:
                inicio = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                return datetime.fromtimestamp(inicio.timestamp() + segundos, tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    return None


def classificar_origem_bling(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "orgbling" in host or any(h in host for h in HOSTS_BLING):
        return "bling_interna"
    if url_imagem_temporaria(url):
        return "bling_interna"
    return "bling_externa"


def recalcular_bytes_imagens_tenant(cur, id_tenant: int) -> int:
    """Soma bytes de arquivos locais do tenant e persiste em tbl_tenant_armazenamento."""
    total = 0
    cur.execute(
        """
        SELECT i.caminho, i.tamanho_bytes
        FROM tbl_produto_imagem i
        JOIN tbl_produto p ON p.id = i.id_produto
        WHERE p.id_tenant = %s
        """,
        (id_tenant,),
    )
    for caminho, tamanho in cur.fetchall():
        if caminho_eh_url(caminho):
            continue
        if tamanho is not None and int(tamanho) > 0:
            total += int(tamanho)
            continue
        rel = (caminho or "").replace("\\", "/").lstrip("/")
        if ".." in rel:
            continue
        if rel.lower().startswith("upload/"):
            p = _raiz_projeto() / rel.replace("/", os.sep)
        elif rel.lower().startswith("imge/produtos/"):
            p = _raiz_projeto() / "static" / rel.replace("/", os.sep)
        else:
            continue
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass

    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_tenant_armazenamento (id_tenant, bytes_imagens, atualizado_em)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            bytes_imagens = EXCLUDED.bytes_imagens,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, total, agora),
    )
    return total


def obter_bytes_imagens_tenant(cur, id_tenant: int) -> int:
    cur.execute(
        "SELECT bytes_imagens FROM tbl_tenant_armazenamento WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    if row and row[0] is not None:
        return int(row[0])
    return recalcular_bytes_imagens_tenant(cur, id_tenant)


def classificar_origem_manual(caminho: str) -> str:
    return "manual_url" if caminho_eh_url(caminho) else "manual_upload"


_UA_IMG_LINK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_RE_OG_IMAGE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_RE_OG_IMAGE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.I,
)
_RE_IPOSTIMG = re.compile(r"https://i\.postimg\.cc/[^\s\"'<>]+", re.I)
_HOSTS_PAGINA_IMAGEM = (
    "postimg.cc",
    "postimages.org",
    "postimg.org",
    "ibb.co",
    "imgbb.com",
)
_HOSTS_CDN_IMAGEM = (
    "i.postimg.cc",
    "i.ibb.co",
)
_EXT_ARQUIVO_IMAGEM = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
_PROXY_MEM_CACHE: dict[str, tuple[float, bytes, str]] = {}
_PROXY_MEM_CACHE_TTL_S = 30 * 60
_PROXY_MEM_CACHE_MAX = 80


def _referer_para_cdn(url: str) -> str | None:
    """Alguns CDNs (Postimages, ImgBB) exigem Referer do site da página."""
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        return None
    if host == "i.postimg.cc" or host.endswith(".postimg.cc"):
        return "https://postimg.cc/"
    if host in ("postimg.cc", "postimages.org", "postimg.org"):
        return "https://postimg.cc/"
    if host == "i.ibb.co" or host.endswith(".ibb.co"):
        return "https://ibb.co/"
    if host in ("ibb.co", "imgbb.com"):
        return "https://ibb.co/"
    return None


def _headers_fetch_imagem(url: str) -> dict[str, str]:
    headers = {
        "User-Agent": _UA_IMG_LINK,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    ref = _referer_para_cdn(url)
    if ref:
        headers["Referer"] = ref
    return headers


def _host_url_seguro(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL inválida. Use http:// ou https://.")
    host = (parsed.hostname or "").strip().lower()
    if not host or host in ("localhost",) or host.endswith(".local"):
        raise ValueError("URL de host local não é permitida.")
    # CDNs conhecidos: não bloqueia por classificação rara de IP (anycast/CGNAT).
    if any(host == h or host.endswith("." + h) for h in _HOSTS_CDN_IMAGEM + _HOSTS_PAGINA_IMAGEM):
        return host
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError("Não foi possível resolver o host da URL.") from e
    for info in infos:
        ip_txt = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_txt)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise ValueError("URL de rede privada não é permitida.")
    return host


def _content_type_eh_imagem(ct: str | None) -> bool:
    if not ct:
        return False
    return ct.lower().split(";", 1)[0].strip().startswith("image/")


def _url_parece_arquivo_imagem(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return Path(path.split("?")[0]).suffix in _EXT_ARQUIVO_IMAGEM


def _host_cdn_imagem(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _HOSTS_CDN_IMAGEM)


def _extrair_url_imagem_de_html(html: str, base_url: str) -> str | None:
    texto = unescape(html or "")
    for rx in (_RE_OG_IMAGE, _RE_OG_IMAGE_ALT):
        m = rx.search(texto)
        if m:
            cand = (m.group(1) or "").strip()
            if cand:
                return urljoin(base_url, cand)
    m = _RE_IPOSTIMG.search(texto)
    if m:
        return m.group(0).rstrip("\\").split("&amp;")[0]
    return None


def _inspecionar_url_remota(url: str, *, timeout: float) -> tuple[str, str | None, bytes]:
    """Retorna (url_final, content_type, amostra_ou_html)."""
    headers = _headers_fetch_imagem(url)
    with requests.get(
        url,
        headers=headers,
        timeout=timeout,
        stream=True,
        allow_redirects=True,
    ) as resp:
        resp.raise_for_status()
        final = str(resp.url or url)
        ct = resp.headers.get("Content-Type")
        chunks: list[bytes] = []
        total = 0
        limite = 250_000 if (ct or "").lower().startswith("text/html") else 4096
        for parte in resp.iter_content(chunk_size=8192):
            if not parte:
                continue
            chunks.append(parte)
            total += len(parte)
            if total >= limite:
                break
        return final, ct, b"".join(chunks)


def _bytes_parecem_imagem(bruto: bytes) -> bool:
    if not bruto or len(bruto) < 3:
        return False
    if bruto.startswith(b"\xff\xd8\xff"):
        return True
    if bruto.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if bruto.startswith((b"GIF87a", b"GIF89a")):
        return True
    if len(bruto) >= 12 and bruto[:4] == b"RIFF" and bruto[8:12] == b"WEBP":
        return True
    inicio = bruto.lstrip()[:64].lower()
    if inicio.startswith((b"<!doctype", b"<html", b"<?xml", b"<head")):
        return False
    return False


def _bytes_parecem_html(bruto: bytes) -> bool:
    inicio = (bruto or b"").lstrip()[:64].lower()
    return inicio.startswith((b"<!doctype", b"<html", b"<?xml"))


def resolver_url_imagem_link(url: str, *, timeout: float = 12.0) -> dict:
    """
    Valida/normaliza URL para modo link (não baixa nem grava arquivo).

    Retorna {"url", "convertida", "aviso"}.
    Levanta ValueError se não for possível obter um link direto de imagem.
    """
    bruto = (url or "").strip()
    if not bruto.lower().startswith(("http://", "https://")):
        raise ValueError("URL inválida. Use http:// ou https://.")
    _host_url_seguro(bruto)

    # Direct link óbvio em CDN conhecido — aceita sem depender de fetch (evita timeout).
    if _url_parece_arquivo_imagem(bruto) and _host_cdn_imagem(bruto):
        return {"url": bruto, "convertida": False, "aviso": None}

    final = bruto
    ct = None
    sample = b""
    try:
        final, ct, sample = _inspecionar_url_remota(bruto, timeout=timeout)
        _host_url_seguro(final)
    except requests.RequestException as e:
        if _url_parece_arquivo_imagem(bruto):
            return {"url": bruto, "convertida": False, "aviso": None}
        raise ValueError(
            "Não foi possível acessar a URL. Confira o link ou tente o Direct link."
        ) from e

    if _content_type_eh_imagem(ct) or _bytes_parecem_imagem(sample):
        return {
            "url": final,
            "convertida": final.rstrip("/") != bruto.rstrip("/"),
            "aviso": None,
        }

    eh_html = (ct or "").lower().startswith("text/html") or _bytes_parecem_html(sample)
    if not eh_html:
        raise ValueError(
            "Este link não aponta para uma imagem. "
            "Use o Direct link (arquivo .jpg/.png), não o link da página."
        )

    html = sample.decode("utf-8", errors="ignore")
    if len(sample) < 2000:
        # Amostra curta — busca HTML completo
        try:
            html_resp = requests.get(
                final,
                headers={"User-Agent": _UA_IMG_LINK, "Accept": "text/html,*/*"},
                timeout=timeout,
                allow_redirects=True,
            )
            html_resp.raise_for_status()
            html = html_resp.text[:250_000]
            final = str(html_resp.url or final)
        except requests.RequestException as e:
            raise ValueError(
                "Este parece ser o link de uma página, não da imagem. "
                "No Postimages use o campo Direct link."
            ) from e

    extraida = _extrair_url_imagem_de_html(html, final)
    if not extraida:
        raise ValueError(
            "Não encontrei a imagem nesse link de página. "
            "Cole o Direct link (ex.: i.postimg.cc/...jpg)."
        )
    if not extraida.lower().startswith(("http://", "https://")):
        raise ValueError("Link de imagem inválido na página.")
    _host_url_seguro(extraida)

    if _url_parece_arquivo_imagem(extraida):
        return {
            "url": extraida,
            "convertida": True,
            "aviso": "Link da página convertido para o link direto da imagem.",
        }

    try:
        final2, ct2, sample2 = _inspecionar_url_remota(extraida, timeout=timeout)
    except requests.RequestException as e:
        if _url_parece_arquivo_imagem(extraida):
            return {
                "url": extraida,
                "convertida": True,
                "aviso": "Link da página convertido para o link direto da imagem.",
            }
        raise ValueError("Achei um candidato a imagem, mas ele não abriu.") from e

    if not (_content_type_eh_imagem(ct2) or _bytes_parecem_imagem(sample2)):
        raise ValueError(
            "Este link é de página, não de imagem direta. "
            "Use o Direct link do hospedeiro (Postimages, ImgBB, etc.)."
        )

    return {
        "url": final2,
        "convertida": True,
        "aviso": "Link da página convertido para o link direto da imagem.",
    }


def proxy_bytes_imagem_remota(url: str, *, timeout: float = 20.0, max_bytes: int = 8_000_000) -> tuple[bytes, str]:
    """
    Busca bytes de imagem remota para exibição (não grava em disco).
    Usa cache em memória curto para acelerar reabertura da galeria.
    Retorna (conteudo, content_type). Levanta ValueError se inválido.
    """
    bruto = (url or "").strip()
    if not bruto.lower().startswith(("http://", "https://")):
        raise ValueError("URL inválida.")

    # Página Postimages/ImgBB → tenta Direct link antes do fetch de bytes.
    host = (urlparse(bruto).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in _HOSTS_PAGINA_IMAGEM) and not _url_parece_arquivo_imagem(bruto):
        try:
            resolvida = resolver_url_imagem_link(bruto, timeout=min(timeout, 15.0))
            if resolvida.get("url"):
                bruto = resolvida["url"]
        except ValueError:
            pass

    agora = time.time()
    hit = _PROXY_MEM_CACHE.get(bruto)
    if hit and hit[0] > agora:
        return hit[1], hit[2]

    _host_url_seguro(bruto)
    headers = _headers_fetch_imagem(bruto)
    try:
        with requests.get(
            bruto,
            headers=headers,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            final = str(resp.url or bruto)
            _host_url_seguro(final)
            ct = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip() or "application/octet-stream"
            chunks: list[bytes] = []
            total = 0
            for parte in resp.iter_content(chunk_size=16384):
                if not parte:
                    continue
                total += len(parte)
                if total > max_bytes:
                    raise ValueError("Imagem remota muito grande.")
                chunks.append(parte)
            data = b"".join(chunks)
    except requests.RequestException as e:
        raise ValueError("Não foi possível carregar a imagem remota.") from e
    if not data:
        raise ValueError("Imagem remota vazia.")
    if not (_content_type_eh_imagem(ct) or _bytes_parecem_imagem(data)):
        # Última chance: HTML de página de hospedagem → extrai Direct link.
        if (ct or "").lower().startswith("text/html") or _bytes_parecem_html(data[:2000]):
            try:
                resolvida = resolver_url_imagem_link(bruto, timeout=min(timeout, 15.0))
                alt = (resolvida.get("url") or "").strip()
                if alt and alt != bruto:
                    return proxy_bytes_imagem_remota(alt, timeout=timeout, max_bytes=max_bytes)
            except ValueError:
                pass
        raise ValueError("A URL remota não devolveu uma imagem.")
    if not _content_type_eh_imagem(ct):
        if data.startswith(b"\xff\xd8\xff"):
            ct = "image/jpeg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            ct = "image/png"
        elif data.startswith((b"GIF87a", b"GIF89a")):
            ct = "image/gif"
        elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ct = "image/webp"
        else:
            ct = "application/octet-stream"

    # Evict entradas velhas / excesso (só memória, sem disco).
    vencidos = [k for k, v in _PROXY_MEM_CACHE.items() if v[0] <= agora]
    for k in vencidos:
        _PROXY_MEM_CACHE.pop(k, None)
    if len(_PROXY_MEM_CACHE) >= _PROXY_MEM_CACHE_MAX:
        mais_antiga = min(_PROXY_MEM_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _PROXY_MEM_CACHE.pop(mais_antiga, None)
    _PROXY_MEM_CACHE[bruto] = (agora + _PROXY_MEM_CACHE_TTL_S, data, ct)
    return data, ct


def obter_imagem_modo(cur, id_produto: int) -> str | None:
    cur.execute("SELECT imagem_modo FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    if row and row[0]:
        return str(row[0])
    cur.execute(
        """
        SELECT caminho FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem ASC, id ASC
        LIMIT 1
        """,
        (id_produto,),
    )
    row = cur.fetchone()
    if row and row[0]:
        return tipo_de_caminho(row[0])
    cur.execute("SELECT imagem_url FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    if row and row[0]:
        return tipo_de_caminho(row[0])
    return None


def definir_imagem_modo(cur, id_produto: int, modo: str | None) -> None:
    cur.execute(
        "UPDATE tbl_produto SET imagem_modo = %s, atualizado_em = %s WHERE id = %s",
        (modo, agora_utc(), id_produto),
    )


def exigir_modo_compativel(cur, id_produto: int, modo: str) -> None:
    atual = obter_imagem_modo(cur, id_produto)
    if atual and atual != modo:
        raise ValueError(
            "Não é possível misturar link e upload. Exclua todas as imagens para trocar o modo."
        )


def _limpar_arquivo_upload(caminho: str | None) -> None:
    if not caminho or caminho_eh_url(caminho):
        return
    rel = caminho.replace("\\", "/").lstrip("/")
    if rel.lower().startswith("upload/") and ".." not in rel:
        p = _raiz_projeto() / rel.replace("/", os.sep)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
        return
    if rel.lower().startswith("imge/produtos/") and ".." not in rel:
        p = _raiz_projeto() / "static" / rel.replace("/", os.sep)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass


def descartar_arquivos_imagem_locais(caminhos: list[str] | None) -> None:
    """Remove arquivos locais criados no disco (não desfaz rollback de SQL)."""
    for c in caminhos or []:
        _limpar_arquivo_upload(c)


def pasta_imagens_tenant(id_tenant: int) -> Path:
    """Pasta pública por tenant: static/imge/produtos/{id_tenant}/."""
    pasta = _raiz_projeto() / "static" / "imge" / "produtos" / str(int(id_tenant))
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def caminho_db_imagem_tenant(id_tenant: int, nome_arquivo: str) -> str:
    return f"imge/produtos/{int(id_tenant)}/{nome_arquivo}"


def _ext_de_bytes_ou_url(data: bytes, url: str, content_type: str | None) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in ("image/jpeg", "image/jpg"):
        return ".jpg"
    if ct == "image/png":
        return ".png"
    if ct == "image/webp":
        return ".webp"
    if ct == "image/gif":
        return ".gif"
    path = urlparse(url).path or ""
    ext = Path(path.split("?")[0]).suffix.lower()
    if ext in _EXT_ARQUIVO_IMAGEM:
        return ext if ext != ".jpeg" else ".jpg"
    return ".jpg"


def baixar_e_gravar_imagem_tenant(
    *,
    id_tenant: int,
    id_produto: int,
    id_imagem: int,
    url: str,
    max_bytes: int = 2 * 1024 * 1024,
    leve: bool = False,
) -> tuple[str, int]:
    """
    Resolve link (página→direct se preciso), baixa bytes e grava em
    static/imge/produtos/{tenant}/. Retorna (caminho_db, tamanho_bytes).

    leve=True (fila/import): baixa e grava; só re-encode se não for JPG ok.
    """
    bruto = (url or "").strip()
    # Direct link (.jpg/.png/…) → 1 HTTP. Página (Postimages etc.) → resolve depois baixa.
    if _url_parece_arquivo_imagem(bruto):
        _host_url_seguro(bruto)
        final_url = bruto
    else:
        resolvida = resolver_url_imagem_link(bruto)
        final_url = resolvida["url"]
    data, ct = proxy_bytes_imagem_remota(final_url)
    if not data:
        raise ValueError("Imagem remota vazia.")
    if len(data) > max_bytes:
        raise ValueError("Imagem deve ter no máximo 2 MB.")

    try:
        from api.bling.imagens_export import (
            MAX_LADO_PX,
            MIN_LADO_BLOQUEIO,
            validar_imagem_upload_bytes,
        )
        from PIL import Image, ImageOps

        gravar = None
        if data.startswith(b"\xff\xd8\xff"):
            im = Image.open(io.BytesIO(data))
            try:
                im2 = ImageOps.exif_transpose(im)
                w, h = (im2 or im).size
            finally:
                im.close()
            if min(w, h) < MIN_LADO_BLOQUEIO:
                raise ValueError(
                    f"Imagem muito pequena ({w}×{h}). Mínimo: {MIN_LADO_BLOQUEIO}px no menor lado."
                )
            if max(w, h) <= MAX_LADO_PX:
                gravar = data

        if gravar is None:
            if leve and data.startswith(b"\xff\xd8\xff"):
                # Import: aceita JPG grande sem re-encode caro; só bloqueia se minúscula.
                gravar = data
            else:
                valid = validar_imagem_upload_bytes(data)
                gravar = valid.get("jpg") if isinstance(valid, dict) else None
                if not gravar:
                    gravar = data
    except ValueError:
        raise
    except Exception:
        gravar = data

    ext = ".jpg" if gravar.startswith(b"\xff\xd8\xff") else _ext_de_bytes_ou_url(gravar, final_url, ct)

    nome = f"{int(id_produto)}_{int(id_imagem)}{ext}"
    destino = pasta_imagens_tenant(id_tenant) / nome
    destino.write_bytes(gravar)
    caminho_db = caminho_db_imagem_tenant(id_tenant, nome)
    return caminho_db, len(gravar)


def materializar_imagens_remotas_produto(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    max_bytes: int = 2 * 1024 * 1024,
) -> int:
    """Converte caminhos http(s) da galeria em arquivos locais. Retorna qtd convertida."""
    cur.execute(
        """
        SELECT id, caminho FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem ASC, id ASC
        """,
        (id_produto,),
    )
    convertidas = 0
    for id_img, caminho in cur.fetchall():
        if not caminho_eh_url(caminho):
            continue
        novo, tam = baixar_e_gravar_imagem_tenant(
            id_tenant=id_tenant,
            id_produto=id_produto,
            id_imagem=int(id_img),
            url=str(caminho),
            max_bytes=max_bytes,
        )
        cur.execute(
            """
            UPDATE tbl_produto_imagem
            SET caminho = %s, tamanho_bytes = %s, origem = COALESCE(origem, 'manual_url')
            WHERE id = %s
            """,
            (novo, tam, int(id_img)),
        )
        convertidas += 1
    if convertidas:
        definir_imagem_modo(cur, id_produto, "upload")
        sincronizar_imagem_principal_produto(cur, id_produto)
        recalcular_bytes_imagens_tenant(cur, id_tenant)
    return convertidas


def limpar_galeria_produto(cur, id_produto: int) -> None:
    cur.execute(
        "SELECT caminho FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL",
        (id_produto,),
    )
    for row in cur.fetchall():
        _limpar_arquivo_upload(row[0])
    cur.execute(
        "UPDATE tbl_produto_variante SET id_imagem_principal = NULL WHERE id_produto = %s",
        (id_produto,),
    )
    cur.execute("DELETE FROM tbl_produto_atributo_imagem WHERE id_produto = %s", (id_produto,))
    cur.execute(
        "DELETE FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL",
        (id_produto,),
    )


def sincronizar_imagem_principal_produto(cur, id_produto: int) -> str | None:
    cur.execute(
        """
        SELECT caminho FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem ASC, id ASC
        LIMIT 1
        """,
        (id_produto,),
    )
    row = cur.fetchone()
    caminho = row[0] if row else None
    modo = tipo_de_caminho(caminho) if caminho else None
    cur.execute(
        "UPDATE tbl_produto SET imagem_url = %s, imagem_modo = %s, atualizado_em = %s WHERE id = %s",
        (caminho, modo, agora_utc(), id_produto),
    )
    if not caminho:
        definir_imagem_modo(cur, id_produto, None)
    return caminho


def sincronizar_cache_variante(cur, id_variante: int) -> None:
    cur.execute(
        """
        SELECT v.herda_pai, v.id_produto, v.id_imagem_principal, i.caminho, p.imagem_url
        FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        LEFT JOIN tbl_produto_imagem i ON i.id = v.id_imagem_principal
        WHERE v.id = %s
        """,
        (id_variante,),
    )
    row = cur.fetchone()
    if not row:
        return
    herda_pai, id_produto, id_img, caminho_img, pai_url = row
    caminho: str | None
    if herda_pai:
        caminho = obter_caminho_imagem_principal_produto(cur, id_produto)
    elif id_img and caminho_img:
        caminho = caminho_img
    else:
        caminho = None
    cur.execute(
        "UPDATE tbl_produto_variante SET imagem_url = %s, atualizado_em = %s WHERE id = %s",
        (caminho, agora_utc(), id_variante),
    )


def obter_caminho_imagem_principal_produto(cur, id_produto: int) -> str | None:
    cur.execute(
        """
        SELECT caminho FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem ASC, id ASC
        LIMIT 1
        """,
        (id_produto,),
    )
    row = cur.fetchone()
    if row and row[0]:
        return row[0]
    cur.execute("SELECT imagem_url FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def resolver_caminho_variante(
    cur,
    *,
    id_variante: int | None = None,
    herda_pai: bool = True,
    id_imagem_principal: int | None = None,
    id_produto: int | None = None,
    imagem_url_legado: str | None = None,
) -> str | None:
    if id_variante and id_produto is None:
        cur.execute(
            """
            SELECT v.herda_pai, v.id_produto, v.id_imagem_principal, i.caminho, v.imagem_url
            FROM tbl_produto_variante v
            LEFT JOIN tbl_produto_imagem i ON i.id = v.id_imagem_principal
            WHERE v.id = %s
            """,
            (id_variante,),
        )
        row = cur.fetchone()
        if not row:
            return None
        herda_pai, id_produto, id_imagem_principal, caminho_img, imagem_url_legado = row
        if herda_pai:
            return obter_caminho_imagem_principal_produto(cur, int(id_produto))
        if id_imagem_principal and caminho_img:
            return caminho_img
        return imagem_url_legado

    if herda_pai and id_produto:
        return obter_caminho_imagem_principal_produto(cur, id_produto)
    if id_imagem_principal:
        cur.execute("SELECT caminho FROM tbl_produto_imagem WHERE id = %s", (id_imagem_principal,))
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    return imagem_url_legado


def url_exibicao(caminho: str | None) -> str:
    if not caminho:
        return ""
    return caminho if caminho_eh_url(caminho) else url_imagem_produto(caminho)


def buscar_mapa_url_imagem(cur, id_produto: int) -> dict[str, int]:
    cur.execute(
        """
        SELECT id, caminho FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        """,
        (id_produto,),
    )
    return {str(row[1]): int(row[0]) for row in cur.fetchall() if row[1]}


def _resolver_id_imagem_por_url(mapa: dict[str, int], url: str | None) -> int | None:
    u = (url or "").strip()
    if not u:
        return None
    if u in mapa:
        return mapa[u]
    sem_query = u.split("?")[0]
    for caminho, id_img in mapa.items():
        if caminho.split("?")[0] == sem_query:
            return id_img
    return None


def aplicar_galeria_produto(
    cur,
    *,
    id_tenant: int,
    id_produto: int,
    sku: str,
    urls: list[str] | None = None,
    modo_imagem: str | None = None,
    origem_fn=None,
    baixar_fn=None,
    pasta_sku_fn=None,
    caminho_db_fn=None,
    midia_itens: list[dict] | None = None,
    adiar_download: bool = False,
    id_importacao_lote: int | None = None,
) -> tuple[str | None, dict[str, int], list[str]]:
    """Sincroniza galeria do produto com origem Bling/manual.

    Ordem padrão: registro no banco → download → atualiza caminho.
    Com ``adiar_download=True`` (import Bling): só registra + enfileira download.

    Arquivos novos gravados nesta chamada são devolvidos em ``arquivos_novos``;
    se a transação/savepoint for desfeita depois, o caller deve chamar
    ``descartar_arquivos_imagem_locais``.

    Retorna (caminho principal, mapa url/caminho → id_imagem, arquivos_novos).
    """
    _ = (modo_imagem, baixar_fn, pasta_sku_fn, caminho_db_fn, sku)  # legado da API Bling
    garantir_colunas_vinculo_imagem(cur)

    itens: list[dict] = []
    if midia_itens:
        for it in midia_itens:
            if not isinstance(it, dict):
                continue
            u = (it.get("url") or "").strip()
            if not u.startswith(("http://", "https://")):
                continue
            itens.append(
                {
                    "url": u,
                    "tipo": (it.get("tipo") or "externa").strip().lower(),
                    "bling_anexo_id": it.get("bling_anexo_id"),
                    "ordem": it.get("ordem"),
                }
            )
    else:
        origem_fn = origem_fn or classificar_origem_bling
        for u in urls or []:
            u = (u or "").strip()
            if not u.startswith(("http://", "https://")):
                continue
            origem = origem_fn(u)
            itens.append(
                {
                    "url": u,
                    "tipo": "interna" if origem == "bling_interna" else "externa",
                    "bling_anexo_id": None,
                    "ordem": None,
                }
            )

    itens = itens[:MAX_IMAGENS_PRODUTO]
    if not itens:
        limpar_galeria_produto(cur, id_produto)
        sincronizar_imagem_principal_produto(cur, id_produto)
        if not adiar_download:
            try:
                recalcular_bytes_imagens_tenant(cur, id_tenant)
            except Exception:
                pass
        return None, {}, []

    cur.execute(
        """
        SELECT id, caminho, bling_anexo_id, url_origem
        FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem ASC, id ASC
        """,
        (id_produto,),
    )
    existentes = cur.fetchall()
    por_anexo: dict[int, dict] = {}
    por_url: dict[str, dict] = {}
    for row in existentes:
        rec = {
            "id": int(row[0]),
            "caminho": row[1] or "",
            "bling_anexo_id": int(row[2]) if row[2] is not None else None,
            "url_origem": (row[3] or "").strip() or None,
        }
        if rec["bling_anexo_id"]:
            por_anexo[rec["bling_anexo_id"]] = rec
        if rec["url_origem"]:
            por_url[rec["url_origem"]] = rec
        if caminho_eh_url(rec["caminho"]):
            por_url.setdefault(rec["caminho"].strip(), rec)

    mapa: dict[str, int] = {}
    manter_ids: set[int] = set()
    principal: str | None = None
    ordem = 0
    arquivos_novos: list[str] = []

    def _enfileirar(id_img: int, url: str) -> None:
        if not adiar_download:
            return
        try:
            from api.bling.imagens_fila import enfileirar_download_imagem

            enfileirar_download_imagem(
                cur,
                id_tenant=id_tenant,
                id_produto=id_produto,
                id_imagem=id_img,
                url=url,
                id_importacao_lote=id_importacao_lote,
            )
        except Exception:
            pass

    def _materializar(id_img: int, url: str) -> tuple[str, int]:
        caminho_db, tam = baixar_e_gravar_imagem_tenant(
            id_tenant=id_tenant,
            id_produto=id_produto,
            id_imagem=id_img,
            url=url,
        )
        arquivos_novos.append(caminho_db)
        return caminho_db, tam

    try:
        for it in itens:
            url = it["url"]
            anexo_id = it.get("bling_anexo_id")
            try:
                anexo_id = int(anexo_id) if anexo_id is not None else None
            except (TypeError, ValueError):
                anexo_id = None
            tipo = it.get("tipo") or ("interna" if anexo_id else "externa")
            if tipo == "interna" and not anexo_id:
                tipo = "externa"

            existente = None
            if tipo == "interna" and anexo_id and anexo_id in por_anexo:
                existente = por_anexo[anexo_id]
            elif tipo == "externa" and url in por_url:
                existente = por_url[url]

            if existente and existente["id"] in manter_ids:
                continue

            if existente:
                id_img = existente["id"]
                caminho_db = existente["caminho"]
                if caminho_eh_url(caminho_db):
                    if adiar_download:
                        _enfileirar(id_img, url)
                        cur.execute(
                            """
                            UPDATE tbl_produto_imagem
                            SET ordem = %s, principal = %s,
                                bling_anexo_id = COALESCE(%s, bling_anexo_id),
                                url_origem = COALESCE(%s, url_origem),
                                origem = %s
                            WHERE id = %s
                            """,
                            (
                                ordem,
                                ordem == 0,
                                anexo_id,
                                None if tipo == "interna" else url,
                                "bling_interna" if tipo == "interna" else "bling_externa",
                                id_img,
                            ),
                        )
                    else:
                        try:
                            caminho_db, tam = _materializar(id_img, url)
                            cur.execute(
                                """
                                UPDATE tbl_produto_imagem
                                SET caminho = %s, tamanho_bytes = %s, link_expira_em = NULL,
                                    origem = %s, bling_anexo_id = %s, url_origem = %s,
                                    ordem = %s, principal = %s
                                WHERE id = %s
                                """,
                                (
                                    caminho_db,
                                    tam,
                                    "bling_interna" if tipo == "interna" else "bling_externa",
                                    anexo_id,
                                    None if tipo == "interna" else url,
                                    ordem,
                                    ordem == 0,
                                    id_img,
                                ),
                            )
                        except Exception:
                            cur.execute(
                                """
                                UPDATE tbl_produto_imagem
                                SET ordem = %s, principal = %s,
                                    bling_anexo_id = COALESCE(%s, bling_anexo_id),
                                    url_origem = COALESCE(%s, url_origem)
                                WHERE id = %s
                                """,
                                (
                                    ordem,
                                    ordem == 0,
                                    anexo_id,
                                    None if tipo == "interna" else url,
                                    id_img,
                                ),
                            )
                else:
                    cur.execute(
                        """
                        UPDATE tbl_produto_imagem
                        SET ordem = %s, principal = %s,
                            bling_anexo_id = COALESCE(%s, bling_anexo_id),
                            url_origem = CASE
                                WHEN %s IS NOT NULL THEN %s
                                ELSE url_origem
                            END,
                            link_expira_em = NULL,
                            origem = %s
                        WHERE id = %s
                        """,
                        (
                            ordem,
                            ordem == 0,
                            anexo_id,
                            None if tipo == "interna" else url,
                            None if tipo == "interna" else url,
                            "bling_interna" if tipo == "interna" else "bling_externa",
                            id_img,
                        ),
                    )
                manter_ids.add(id_img)
            else:
                origem = "bling_interna" if tipo == "interna" else "bling_externa"
                url_origem = None if tipo == "interna" else url
                if adiar_download:
                    cur.execute(
                        """
                        INSERT INTO tbl_produto_imagem (
                            id_produto, caminho, ordem, principal, origem,
                            link_expira_em, tamanho_bytes, bling_anexo_id, url_origem
                        )
                        VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s, %s)
                        RETURNING id
                        """,
                        (id_produto, url, ordem, ordem == 0, origem, anexo_id, url_origem),
                    )
                    id_img = int(cur.fetchone()[0])
                    caminho_db = url
                    _enfileirar(id_img, url)
                else:
                    cur.execute(
                        """
                        INSERT INTO tbl_produto_imagem (
                            id_produto, caminho, ordem, principal, origem,
                            link_expira_em, tamanho_bytes, bling_anexo_id, url_origem
                        )
                        VALUES (%s, '', %s, %s, %s, NULL, NULL, %s, %s)
                        RETURNING id
                        """,
                        (id_produto, ordem, ordem == 0, origem, anexo_id, url_origem),
                    )
                    id_img = int(cur.fetchone()[0])
                    try:
                        caminho_db, tam = _materializar(id_img, url)
                        cur.execute(
                            """
                            UPDATE tbl_produto_imagem
                            SET caminho = %s, tamanho_bytes = %s, link_expira_em = NULL
                            WHERE id = %s
                            """,
                            (caminho_db, tam, id_img),
                        )
                    except Exception:
                        caminho_db = url
                        cur.execute(
                            """
                            UPDATE tbl_produto_imagem
                            SET caminho = %s, tamanho_bytes = NULL, link_expira_em = NULL
                            WHERE id = %s
                            """,
                            (caminho_db, id_img),
                        )
                manter_ids.add(id_img)

            mapa[url] = id_img
            mapa[caminho_db] = id_img
            if principal is None:
                principal = caminho_db
            ordem += 1

        for row in existentes:
            id_old = int(row[0])
            if id_old in manter_ids:
                continue
            _limpar_arquivo_upload(row[1])
            cur.execute(
                "UPDATE tbl_produto_variante SET id_imagem_principal = NULL WHERE id_imagem_principal = %s",
                (id_old,),
            )
            cur.execute("DELETE FROM tbl_produto_atributo_imagem WHERE id_imagem = %s", (id_old,))
            cur.execute("DELETE FROM tbl_produto_imagem WHERE id = %s", (id_old,))

        definir_imagem_modo(cur, id_produto, "upload")
        sincronizar_imagem_principal_produto(cur, id_produto)
        if not adiar_download:
            try:
                recalcular_bytes_imagens_tenant(cur, id_tenant)
            except Exception:
                pass
        return principal, mapa, arquivos_novos
    except Exception:
        descartar_arquivos_imagem_locais(arquivos_novos)
        raise


def vincular_imagens_variantes_bling(
    cur,
    *,
    id_produto: int,
    mapa_url_id: dict[str, int],
    variacoes_bling: list[dict],
    extrair_urls_fn,
) -> None:
    if not mapa_url_id:
        return
    cur.execute(
        "SELECT id, sku FROM tbl_produto_variante WHERE id_produto = %s",
        (id_produto,),
    )
    por_sku = {(row[1] or "").strip(): int(row[0]) for row in cur.fetchall()}

    for var in variacoes_bling:
        if not isinstance(var, dict):
            continue
        sku = (var.get("codigo") or "").strip()
        vid = por_sku.get(sku)
        if not vid:
            continue
        urls = extrair_urls_fn(var)
        if not urls:
            continue
        ids_img: list[int] = []
        for url in urls:
            id_img = _resolver_id_imagem_por_url(mapa_url_id, url)
            if id_img and id_img not in ids_img:
                ids_img.append(id_img)
        if not ids_img:
            continue
        salvar_imagens_variante(
            cur,
            id_variante=vid,
            id_produto=id_produto,
            ids_imagens=ids_img,
            herda_pai=False,
        )
        cur.execute(
            "UPDATE tbl_produto_variante SET herda_pai = FALSE, atualizado_em = %s WHERE id = %s",
            (agora_utc(), vid),
        )

    aplicar_regras_atributo_imagem(cur, id_produto)


def vincular_variante_padrao_galeria(cur, id_produto: int) -> None:
    cur.execute("SELECT id_variante_padrao FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    if not row or not row[0]:
        return
    vid = int(row[0])
    cur.execute(
        """
        SELECT id FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem ASC, id ASC
        LIMIT 1
        """,
        (id_produto,),
    )
    img = cur.fetchone()
    if not img:
        return
    cur.execute(
        """
        UPDATE tbl_produto_variante
        SET id_imagem_principal = %s, atualizado_em = %s
        WHERE id = %s AND id_imagem_principal IS NULL
        """,
        (int(img[0]), agora_utc(), vid),
    )
    sincronizar_cache_variante(cur, vid)


def _chave_atributo_visual(atributos: dict) -> tuple[str, str] | None:
    if not isinstance(atributos, dict):
        return None
    for nome, valor in atributos.items():
        if str(nome).strip().lower() in ATRIBUTOS_VISUAIS and str(valor).strip():
            return str(nome).strip(), str(valor).strip()
    for nome, valor in atributos.items():
        if str(valor).strip():
            return str(nome).strip(), str(valor).strip()
    return None


def aplicar_regras_atributo_imagem(cur, id_produto: int) -> None:
    cur.execute(
        """
        SELECT nome_atributo, valor, id_imagem
        FROM tbl_produto_atributo_imagem
        WHERE id_produto = %s
        """,
        (id_produto,),
    )
    regras = cur.fetchall()
    if not regras:
        return

    cur.execute(
        "SELECT id, atributos, herda_pai FROM tbl_produto_variante WHERE id_produto = %s",
        (id_produto,),
    )
    for vid, atributos_raw, herda_pai in cur.fetchall():
        if herda_pai:
            continue
        atributos = (
            atributos_raw
            if isinstance(atributos_raw, dict)
            else (__import__("json").loads(atributos_raw) if atributos_raw else {})
        )
        for nome_attr, valor_attr, id_imagem in regras:
            val = atributos.get(nome_attr)
            if val is None:
                for k, v in atributos.items():
                    if str(k).strip().lower() == str(nome_attr).strip().lower():
                        val = v
                        break
            if str(val or "").strip().lower() != str(valor_attr).strip().lower():
                continue
            cur.execute(
                """
                UPDATE tbl_produto_variante
                SET id_imagem_principal = %s, herda_pai = FALSE, atualizado_em = %s
                WHERE id = %s
                """,
                (int(id_imagem), agora_utc(), int(vid)),
            )
            sincronizar_cache_variante(cur, int(vid))
            break


def salvar_regra_atributo_imagem(
    cur,
    *,
    id_produto: int,
    nome_atributo: str,
    valor: str,
    id_imagem: int,
) -> None:
    nome = (nome_atributo or "").strip()
    val = (valor or "").strip()
    if not nome or not val:
        raise ValueError("Informe atributo e valor.")
    cur.execute(
        "SELECT id FROM tbl_produto_imagem WHERE id = %s AND id_produto = %s",
        (id_imagem, id_produto),
    )
    if not cur.fetchone():
        raise ValueError("Imagem não pertence a este produto.")
    cur.execute(
        """
        INSERT INTO tbl_produto_atributo_imagem (id_produto, nome_atributo, valor, id_imagem)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_produto, nome_atributo, valor)
        DO UPDATE SET id_imagem = EXCLUDED.id_imagem
        """,
        (id_produto, nome, val, id_imagem),
    )
    aplicar_regras_atributo_imagem(cur, id_produto)


def listar_regras_atributo_imagem(cur, id_produto: int) -> list[dict]:
    cur.execute(
        """
        SELECT r.id, r.nome_atributo, r.valor, r.id_imagem, i.caminho
        FROM tbl_produto_atributo_imagem r
        JOIN tbl_produto_imagem i ON i.id = r.id_imagem
        WHERE r.id_produto = %s
        ORDER BY r.nome_atributo, r.valor
        """,
        (id_produto,),
    )
    out = []
    for row in cur.fetchall():
        caminho = row[4] or ""
        out.append(
            {
                "id": row[0],
                "nome_atributo": row[1],
                "valor": row[2],
                "id_imagem": row[3],
                "caminho": caminho,
                "url": url_exibicao(caminho),
            }
        )
    return out


def listar_ids_imagens_variante(cur, id_variante: int) -> list[int]:
    cur.execute(
        """
        SELECT id_imagem FROM tbl_produto_variante_imagem
        WHERE id_variante = %s
        ORDER BY ordem ASC, id_imagem ASC
        """,
        (id_variante,),
    )
    ids = [int(r[0]) for r in cur.fetchall()]
    if ids:
        return ids
    cur.execute(
        "SELECT id_imagem_principal FROM tbl_produto_variante WHERE id = %s",
        (id_variante,),
    )
    row = cur.fetchone()
    if row and row[0]:
        return [int(row[0])]
    return []


def _imagem_galeria_dict(cur, row) -> dict:
    caminho = row[1] or ""
    return {
        "id": int(row[0]),
        "caminho": caminho,
        "url": url_exibicao(caminho),
        "ordem": int(row[2] or 0),
        "principal": bool(row[3]),
        "origem": row[4] if len(row) > 4 else "manual_upload",
    }


def listar_imagens_galeria_pai(cur, id_produto: int) -> list[dict]:
    cur.execute(
        """
        SELECT id, caminho, ordem, principal, origem
        FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem ASC, id ASC
        """,
        (id_produto,),
    )
    return [_imagem_galeria_dict(cur, r) for r in cur.fetchall()]


def listar_imagens_variante_selecionadas(cur, id_variante: int, id_produto: int) -> list[dict]:
    ids = listar_ids_imagens_variante(cur, id_variante)
    if not ids:
        return []
    cur.execute(
        """
        SELECT id, caminho, ordem, principal, origem
        FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL AND id = ANY(%s)
        """,
        (id_produto, ids),
    )
    por_id = {int(r[0]): _imagem_galeria_dict(cur, r) for r in cur.fetchall()}
    return [por_id[i] for i in ids if i in por_id]


def salvar_imagens_variante(
    cur,
    *,
    id_variante: int,
    id_produto: int,
    ids_imagens: list[int] | None,
    herda_pai: bool,
) -> None:
    cur.execute("DELETE FROM tbl_produto_variante_imagem WHERE id_variante = %s", (id_variante,))
    if herda_pai:
        cur.execute(
            """
            UPDATE tbl_produto_variante
            SET id_imagem_principal = NULL, imagem_url = NULL, atualizado_em = %s
            WHERE id = %s
            """,
            (agora_utc(), id_variante),
        )
        sincronizar_cache_variante(cur, id_variante)
        return

    vistos: set[int] = set()
    limpos: list[int] = []
    for raw in ids_imagens or []:
        try:
            id_img = int(raw)
        except (TypeError, ValueError):
            continue
        if id_img in vistos:
            continue
        if not validar_id_imagem_produto(cur, id_img, id_produto):
            continue
        vistos.add(id_img)
        limpos.append(id_img)

    for ordem, id_img in enumerate(limpos):
        cur.execute(
            """
            INSERT INTO tbl_produto_variante_imagem (id_variante, id_imagem, ordem)
            VALUES (%s, %s, %s)
            """,
            (id_variante, id_img, ordem),
        )

    id_principal = limpos[0] if limpos else None
    cur.execute(
        """
        UPDATE tbl_produto_variante
        SET id_imagem_principal = %s, imagem_url = NULL, atualizado_em = %s
        WHERE id = %s
        """,
        (id_principal, agora_utc(), id_variante),
    )
    sincronizar_cache_variante(cur, id_variante)


def validar_id_imagem_produto(cur, id_imagem: int, id_produto: int) -> bool:
    cur.execute(
        """
        SELECT id FROM tbl_produto_imagem
        WHERE id = %s AND id_produto = %s AND id_variante IS NULL
        """,
        (id_imagem, id_produto),
    )
    return cur.fetchone() is not None


def sugerir_regras_por_url_variantes(cur, id_produto: int) -> int:
    """Agrupa variantes com mesma imagem vinculada em regras por atributo visual."""
    cur.execute(
        """
        SELECT v.id_imagem_principal, v.atributos
        FROM tbl_produto_variante v
        WHERE v.id_produto = %s AND v.id_imagem_principal IS NOT NULL
        """,
        (id_produto,),
    )
    grupos: dict[int, list[dict]] = {}
    for id_img, atributos_raw in cur.fetchall():
        atributos = (
            atributos_raw
            if isinstance(atributos_raw, dict)
            else (__import__("json").loads(atributos_raw) if atributos_raw else {})
        )
        grupos.setdefault(int(id_img), []).append(atributos)

    criadas = 0
    for id_img, lista in grupos.items():
        if len(lista) < 2:
            continue
        chaves = [_chave_atributo_visual(a) for a in lista]
        chaves = [c for c in chaves if c]
        if not chaves:
            continue
        nome_attr, _ = chaves[0]
        valores = {v for n, v in chaves if n.lower() == nome_attr.lower()}
        if len(valores) != 1:
            continue
        valor = next(iter(valores))
        try:
            salvar_regra_atributo_imagem(
                cur,
                id_produto=id_produto,
                nome_atributo=nome_attr,
                valor=valor,
                id_imagem=id_img,
            )
            criadas += 1
        except ValueError:
            pass
    return criadas


# ── servico_estoque_deposito ──────────────────────────

from global_utils import agora_utc


def produto_integrado_bling(cur, id_tenant: int, id_produto: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND entidade = 'produto'
          AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_produto),
    )
    if cur.fetchone():
        return True
    cur.execute(
        """
        SELECT 1 FROM tbl_produto
        WHERE id = %s AND id_tenant = %s AND origem IN ('integracao', 'arquivo')
        """,
        (id_produto, id_tenant),
    )
    return bool(cur.fetchone())


def id_bling_produto(cur, id_tenant: int, id_produto: int, *, contexto: str = "fornecedor") -> str | None:
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
          AND entidade = 'produto' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, contexto, id_produto),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def garantir_linhas_estoque_depositos(cur, id_tenant: int, id_variante: int) -> None:
    cur.execute(
        """
        INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
        SELECT %s, d.id, 0, %s
        FROM tbl_deposito_expedicao d
        WHERE d.id_tenant = %s AND d.ativo = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM tbl_produto_estoque_deposito ped
              WHERE ped.id_variante = %s AND ped.id_deposito = d.id
          )
        """,
        (id_variante, agora_utc(), id_tenant, id_variante),
    )


def sincronizar_total_variante(cur, id_variante: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantidade), 0) FROM tbl_produto_estoque_deposito
        WHERE id_variante = %s
        """,
        (id_variante,),
    )
    total = int(cur.fetchone()[0] or 0)
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_variante) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_variante, total, agora),
    )
    try:
        from api.mercado_livre.eco_estoque import ml_sync_suprimido
        from api.mercado_livre.sync_runtime import propagar_estoque_variante_ml

        if not ml_sync_suprimido():
            propagar_estoque_variante_ml(cur, int(id_variante), quantidade=total)
    except Exception:
        pass
    try:
        from api.amazon.eco_estoque import amazon_sync_suprimido
        from api.amazon.sync_runtime import propagar_estoque_variante_amazon

        if not amazon_sync_suprimido():
            propagar_estoque_variante_amazon(cur, int(id_variante), quantidade=total)
    except Exception:
        pass
    return total


def listar_estoque_por_deposito(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    id_variante: int | None = None,
) -> tuple[int | None, list[dict], bool]:
    if id_variante:
        return _listar_estoque_variante(cur, id_tenant, id_variante)

    cur.execute(
        """
        SELECT id_variante_padrao, formato FROM tbl_produto
        WHERE id = %s AND id_tenant = %s
        """,
        (id_produto, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        return None, [], False
    id_variante, formato = row[0], row[1] or "S"
    if formato == "E":
        return id_variante, [], produto_integrado_bling(cur, id_tenant, id_produto)

    if not id_variante:
        from fornecedor.catalogo.srotas_catalogo import garantir_variante_padrao as _gvp

        id_variante = _gvp(cur, id_produto, id_tenant)

    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    cur.execute(
        """
        SELECT ped.id_deposito, d.nome, d.cidade, d.uf, d.principal,
               ped.quantidade, ped.atualizado_em,
               dm.id_bling_deposito, dm.nome_bling
        FROM tbl_produto_estoque_deposito ped
        JOIN tbl_deposito_expedicao d ON d.id = ped.id_deposito
        LEFT JOIN tbl_integracao_deposito_map dm
            ON dm.id_tenant = %s AND dm.id_deposito_dropnexo = d.id
        WHERE ped.id_variante = %s AND d.id_tenant = %s AND d.ativo = TRUE
        ORDER BY d.principal DESC, d.nome
        """,
        (id_tenant, id_variante, id_tenant),
    )
    itens = []
    for r in cur.fetchall():
        itens.append(
            {
                "id_deposito": r[0],
                "nome": r[1],
                "cidade": r[2] or "",
                "uf": r[3] or "",
                "principal": bool(r[4]),
                "quantidade": int(r[5] or 0),
                "atualizado_em": r[6].isoformat() if r[6] else None,
                "id_bling_deposito": r[7],
                "nome_bling": r[8],
                "vinculado_bling": bool(r[7]),
            }
        )
    integrado = produto_integrado_bling(cur, id_tenant, id_produto)
    return id_variante, itens, integrado


def _listar_estoque_variante(
    cur,
    id_tenant: int,
    id_variante: int,
) -> tuple[int | None, list[dict], bool]:
    cur.execute(
        """
        SELECT v.id_produto, p.id_tenant
        FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        WHERE v.id = %s AND p.id_tenant = %s
        """,
        (id_variante, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        return None, [], False
    id_produto = int(row[0])
    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    cur.execute(
        """
        SELECT ped.id_deposito, d.nome, d.cidade, d.uf, d.principal,
               ped.quantidade, ped.atualizado_em,
               dm.id_bling_deposito, dm.nome_bling
        FROM tbl_produto_estoque_deposito ped
        JOIN tbl_deposito_expedicao d ON d.id = ped.id_deposito
        LEFT JOIN tbl_integracao_deposito_map dm
            ON dm.id_tenant = %s AND dm.id_deposito_dropnexo = d.id
        WHERE ped.id_variante = %s AND d.id_tenant = %s AND d.ativo = TRUE
        ORDER BY d.principal DESC, d.nome
        """,
        (id_tenant, id_variante, id_tenant),
    )
    itens = []
    for r in cur.fetchall():
        itens.append(
            {
                "id_deposito": r[0],
                "nome": r[1],
                "cidade": r[2] or "",
                "uf": r[3] or "",
                "principal": bool(r[4]),
                "quantidade": int(r[5] or 0),
                "atualizado_em": r[6].isoformat() if r[6] else None,
                "id_bling_deposito": r[7],
                "nome_bling": r[8],
                "vinculado_bling": bool(r[7]),
            }
        )
    integrado = produto_integrado_bling(cur, id_tenant, id_produto)
    return id_variante, itens, integrado


def id_bling_variante(cur, id_tenant: int, id_variante: int, *, contexto: str = "fornecedor") -> str | None:
    cur.execute(
        """
        SELECT v.id_produto, v.sku FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto AND p.id_tenant = %s
        WHERE v.id = %s
        """,
        (id_tenant, id_variante),
    )
    row = cur.fetchone()
    if not row:
        return None
    id_produto, sku = int(row[0]), (row[1] or "").strip()
    if sku:
        cur.execute(
            """
            SELECT id_bling FROM tbl_integracao_map
            WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
              AND entidade = 'produto' AND id_dropnexo = %s AND sku = %s
            ORDER BY atualizado_em DESC NULLS LAST
            LIMIT 1
            """,
            (id_tenant, contexto, id_produto, sku),
        )
        r2 = cur.fetchone()
        if r2 and r2[0]:
            return str(r2[0])
    return id_bling_produto(cur, id_tenant, id_produto, contexto=contexto)


def atualizar_saldo_deposito(
    cur,
    id_tenant: int,
    *,
    id_produto: int,
    id_deposito: int,
    quantidade: int,
    sincronizar_bling: bool = False,
    contexto: str = "fornecedor",
    id_variante: int | None = None,
) -> dict:
    quantidade = max(0, int(quantidade))
    if id_variante:
        cur.execute(
            """
            SELECT v.id_produto, p.formato FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto AND p.id_tenant = %s
            WHERE v.id = %s
            """,
            (id_tenant, id_variante),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Variante não encontrada.")
        id_produto = int(row[0])
    else:
        cur.execute(
            """
            SELECT p.id_variante_padrao, p.formato FROM tbl_produto p
            WHERE p.id = %s AND p.id_tenant = %s
            """,
            (id_produto, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Produto não encontrado.")
        id_variante, formato = row[0], row[1] or "S"
        if formato == "E":
            raise ValueError("Produto com variações: edite o estoque em cada variação.")
        if not id_variante:
            from fornecedor.catalogo.srotas_catalogo import garantir_variante_padrao as _gvp

            id_variante = _gvp(cur, id_produto, id_tenant)

    cur.execute(
        """
        SELECT 1 FROM tbl_deposito_expedicao
        WHERE id = %s AND id_tenant = %s AND ativo = TRUE
        """,
        (id_deposito, id_tenant),
    )
    if not cur.fetchone():
        raise ValueError("Depósito inválido.")

    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    cur.execute(
        "SELECT COALESCE(quantidade, 0) FROM tbl_produto_variante_estoque WHERE id_variante = %s",
        (id_variante,),
    )
    row_est = cur.fetchone()
    total_antes = int(row_est[0] or 0) if row_est else 0
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_variante, id_deposito) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_variante, id_deposito, quantidade, agora),
    )
    total = sincronizar_total_variante(cur, id_variante)


    promo_encerrada = reagir_estoque_promocao(cur, id_variante, total_antes, total)

    bling_ok = False
    bling_msg = None
    integrado = produto_integrado_bling(cur, id_tenant, id_produto)
    if sincronizar_bling and integrado:
        from api.bling.estoque import exportar_saldo_deposito_bling

        id_bling_var = id_bling_variante(cur, id_tenant, int(id_variante), contexto=contexto)
        bling_ok, bling_msg = exportar_saldo_deposito_bling(
            cur,
            id_tenant,
            contexto=contexto,
            id_produto=id_produto,
            id_deposito=id_deposito,
            quantidade=quantidade,
            id_bling_override=id_bling_var,
        )

    return {
        "quantidade": quantidade,
        "total_variante": total,
        "promocao_encerrada": promo_encerrada,
        "integrado_bling": integrado,
        "bling_sincronizado": bling_ok,
        "bling_mensagem": bling_msg,
    }


def sincronizar_estoque_produto_bling(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    contexto: str = "fornecedor",
    id_bling_deposito_filtro: str | None = None,
) -> tuple[bool, str | None, int]:
    """Importa saldos do Bling para o produto (simples ou variações)."""
    import json

    from api.bling.estoque import resumo_depositos_bling
    from api.bling.estoque import importar_estoque_produto_bling

    resumo_deps = resumo_depositos_bling(cur, id_tenant)
    if resumo_deps.get("vinculados", 0) <= 0:
        return False, "Nenhum depósito Bling vinculado.", 0

    cur.execute(
        """
        SELECT id_bling, sku, meta FROM tbl_integracao_map
        WHERE id_tenant = %s AND id_dropnexo = %s AND provedor = 'bling'
          AND entidade = 'produto'
        """,
        (id_tenant, id_produto),
    )
    maps = cur.fetchall()
    if not maps:
        return False, "Produto sem vínculo no Bling.", 0

    total = 0
    for id_bling, sku, meta in maps:
        meta_obj = meta if isinstance(meta, dict) else {}
        if isinstance(meta, str):
            try:
                meta_obj = json.loads(meta) or {}
            except json.JSONDecodeError:
                meta_obj = {}
        fmt = str(meta_obj.get("formato") or "").upper()
        id_variante = None
        if fmt == "V":
            cur.execute(
                """
                SELECT id FROM tbl_produto_variante
                WHERE id_produto = %s AND sku IS NOT DISTINCT FROM %s
                LIMIT 1
                """,
                (id_produto, sku),
            )
            vrow = cur.fetchone()
            if not vrow:
                continue
            id_variante = int(vrow[0])
        else:
            cur.execute(
                "SELECT id_variante_padrao FROM tbl_produto WHERE id = %s AND id_tenant = %s",
                (id_produto, id_tenant),
            )
            vrow = cur.fetchone()
            id_variante = int(vrow[0]) if vrow and vrow[0] else None
        if not id_variante:
            continue
        total += importar_estoque_produto_bling(
            cur,
            id_tenant,
            contexto,
            id_produto=id_produto,
            id_variante=id_variante,
            id_bling_override=str(id_bling),
            id_bling_deposito_filtro=id_bling_deposito_filtro,
        )
    if total <= 0:
        msg = "Nenhum saldo importado (verifique vínculo de depósitos)."
        if resumo_deps.get("pendentes"):
            msg += f" {resumo_deps['pendentes']} depósito(s) Bling sem vínculo."
        return False, msg, 0
    return True, None, total


def sincronizar_estoque_produtos_bling(
    cur,
    id_tenant: int,
    ids_produto: list[int],
    *,
    contexto: str = "fornecedor",
) -> dict:
    ok = 0
    falhas: list[str] = []
    for pid in ids_produto:
        sucesso, msg, _ = sincronizar_estoque_produto_bling(
            cur, id_tenant, int(pid), contexto=contexto
        )
        if sucesso:
            ok += 1
        else:
            falhas.append(f"#{pid}: {msg or 'falha'}")
    return {"sincronizados": ok, "falhas": falhas, "total": len(ids_produto)}
