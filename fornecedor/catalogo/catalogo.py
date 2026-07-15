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

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from global_utils import agora_utc, url_imagem_produto

MAX_IMAGENS_PRODUTO = 10
HOSTS_BLING = ("bling.com.br", "orgbling.com.br")

ATRIBUTOS_VISUAIS = ("cor", "color", "colour", "estampa", "modelo", "sabor")


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]


def caminho_eh_url(caminho: str | None) -> bool:
    c = (caminho or "").strip().lower()
    return c.startswith("http://") or c.startswith("https://")


def tipo_de_caminho(caminho: str | None) -> str:
    return "link" if caminho_eh_url(caminho) else "upload"


def classificar_origem_bling(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if any(h in host for h in HOSTS_BLING):
        return "bling_interna"
    return "bling_externa"


def classificar_origem_manual(caminho: str) -> str:
    return "manual_url" if caminho_eh_url(caminho) else "manual_upload"


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
    urls: list[str],
    modo_imagem: str,
    origem_fn=None,
    baixar_fn=None,
    pasta_sku_fn=None,
    caminho_db_fn=None,
) -> tuple[str | None, dict[str, int]]:
    """Importa URLs na galeria do pai. Retorna (caminho principal, mapa url→id)."""
    if not urls:
        return None, {}

    modo = "link" if modo_imagem != "download" else "upload"
    exigir_modo_compativel(cur, id_produto, modo)
    limpar_galeria_produto(cur, id_produto)

    mapa: dict[str, int] = {}
    principal: str | None = None
    origem_fn = origem_fn or classificar_origem_bling

    for idx, url in enumerate(urls[:MAX_IMAGENS_PRODUTO]):
        caminho_db = url.strip()
        origem = origem_fn(caminho_db) if modo == "link" else "manual_upload"

        if modo == "download" and baixar_fn and pasta_sku_fn and caminho_db_fn:
            ext = Path(urlparse(url).path).suffix.lower() or ".jpg"
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".jpg"
            nome = f"{idx + 1:02d}-principal{ext}" if idx == 0 else f"{idx + 1:02d}-img{ext}"
            pasta = pasta_sku_fn(id_tenant, sku)
            destino = pasta / nome
            baixar_fn(url, destino)
            caminho_db = caminho_db_fn(id_tenant, sku, nome)
            origem = "manual_upload"

        cur.execute(
            """
            INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal, origem)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (id_produto, caminho_db, idx, idx == 0, origem),
        )
        id_img = int(cur.fetchone()[0])
        mapa[caminho_db] = id_img
        if idx == 0:
            principal = caminho_db

    definir_imagem_modo(cur, id_produto, modo)
    sincronizar_imagem_principal_produto(cur, id_produto)
    return principal, mapa


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
