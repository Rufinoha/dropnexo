# sistema/tarefas_secundarias/cache_amazon.py — cache de Product Types Amazon
from __future__ import annotations

import logging
import time
from typing import Any

from global_utils import agora_utc

_log = logging.getLogger(__name__)

CODIGO_AMAZON_PRODUCT_TYPES = "amazon_product_types_cache"


def garantir_tabela_amazon_product_type_cache(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_amazon_product_type_cache (
            id SERIAL PRIMARY KEY,
            marketplace_id VARCHAR(32) NOT NULL,
            product_type VARCHAR(128) NOT NULL,
            display_name VARCHAR(255) NOT NULL DEFAULT '',
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (marketplace_id, product_type)
        )
        """
    )


def tenant_amazon_conectado(cur) -> int:
    cur.execute(
        """
        SELECT id_tenant
        FROM tbl_integracao_amazon
        WHERE status = 'conectado'
        ORDER BY atualizado_em DESC NULLS LAST
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            "Nenhuma conta Amazon conectada. Conecte uma conta e tente de novo."
        )
    return int(row[0])


def marketplace_amazon_para_cache(cur, id_tenant: int) -> str:
    from api.amazon.amazon import carregar_config_amazon, marketplace_id_padrao

    cfg = carregar_config_amazon(cur, id_tenant)
    return str(cfg.get("marketplace_id") or marketplace_id_padrao()).strip()


def _parse_product_types(data: Any) -> tuple[list[dict], str | None]:
    tipos: list[dict] = []
    next_token = None
    payload = data
    if isinstance(data, dict):
        next_token = data.get("nextToken") or data.get("NextToken")
        payload = data.get("productTypes")
        if payload is None and isinstance(data.get("payload"), dict):
            payload = data["payload"].get("productTypes")
            next_token = next_token or data["payload"].get("nextToken")
    if not isinstance(payload, list):
        payload = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("productType") or "").strip()
        display = (item.get("displayName") or name).strip()
        if name:
            tipos.append({"product_type": name, "display_name": display or name})
    return tipos, (str(next_token).strip() if next_token else None)


def _buscar_tipos(
    cur, id_tenant: int, mp: str, *, keywords: str | None = None, next_token: str | None = None
) -> tuple[list[dict], str | None]:
    from api.amazon.amazon import api_request

    params: dict[str, Any] = {"marketplaceIds": mp}
    if next_token:
        params = {"marketplaceIds": mp, "keywords": keywords} if keywords else {"marketplaceIds": mp}
        # SP-API usa pageToken / nextToken conforme versão — tentar ambos via keywords page
        params["pageToken"] = next_token
    if keywords:
        params["keywords"] = keywords
    data = api_request(
        cur,
        id_tenant,
        "GET",
        "/definitions/2020-09-01/productTypes",
        params=params,
    )
    return _parse_product_types(data)


def sincronizar_cache_product_types_amazon(
    cur,
    *,
    conn=None,
    id_exec: int | None = None,
    atualizar_progresso=None,
) -> dict:
    garantir_tabela_amazon_product_type_cache(cur)
    id_tenant = tenant_amazon_conectado(cur)
    mp = marketplace_amazon_para_cache(cur, id_tenant)
    if conn is not None:
        conn.commit()

    log: list[str] = [f"=== Amazon marketplace {mp} (tenant #{id_tenant}) ==="]

    def prog(meta: dict, mensagem: str) -> None:
        if atualizar_progresso:
            atualizar_progresso(cur, conn, id_exec, mensagem, meta)

    prog({"fase": "inicio", "pct": 5, "marketplace_id": mp}, "Baixando Product Types Amazon…")

    coletados: dict[str, str] = {}
    try:
        tipos, token = _buscar_tipos(cur, id_tenant, mp)
        for t in tipos:
            coletados[t["product_type"]] = t["display_name"]
        log.append(f"Lista inicial: {len(tipos)} tipo(s).")
        # Paginação best-effort
        pages = 1
        while token and pages < 20:
            pages += 1
            mais, token = _buscar_tipos(cur, id_tenant, mp, next_token=token)
            for t in mais:
                coletados[t["product_type"]] = t["display_name"]
            time.sleep(0.15)
            prog(
                {"fase": "baixando", "pct": min(70, 10 + pages * 3), "folhas": len(coletados)},
                f"Amazon: página {pages} · {len(coletados)} product types",
            )
    except Exception as e:
        log.append(f"Lista completa falhou ({e}); tentando por palavras-chave…")
        coletados.clear()

    # Complementa com buscas por letra se a lista veio curta
    if len(coletados) < 50:
        letras = list("abcdefghijklmnopqrstuvwxyz0123456789") + [
            "shirt",
            "shoe",
            "bag",
            "phone",
            "book",
            "toy",
            "home",
            "beauty",
            "pet",
            "kitchen",
            "sport",
            "eletronic",
            "produto",
            "roupa",
        ]
        for i, kw in enumerate(letras):
            try:
                mais, _ = _buscar_tipos(cur, id_tenant, mp, keywords=kw)
                for t in mais:
                    coletados[t["product_type"]] = t["display_name"]
            except Exception as e:
                log.append(f"KW «{kw}»: {e}")
            if i % 5 == 0:
                prog(
                    {
                        "fase": "baixando",
                        "pct": min(85, 20 + int(i / max(len(letras), 1) * 60)),
                        "folhas": len(coletados),
                    },
                    f"Amazon: buscando «{kw}» · {len(coletados)} tipos",
                )
            time.sleep(0.12)

    prog(
        {"fase": "gravando", "pct": 92, "folhas": len(coletados), "marketplace_id": mp},
        f"Gravando {len(coletados)} product types…",
    )
    cur.execute(
        "DELETE FROM tbl_amazon_product_type_cache WHERE marketplace_id = %s", (mp,)
    )
    agora = agora_utc()
    for pt, display in sorted(coletados.items()):
        cur.execute(
            """
            INSERT INTO tbl_amazon_product_type_cache (
                marketplace_id, product_type, display_name, atualizado_em
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (marketplace_id, product_type) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (mp, pt[:128], (display or pt)[:255], agora),
        )
    if conn is not None:
        conn.commit()

    msg = f"{len(coletados)} product types Amazon em cache ({mp})."
    log.append(msg)
    log_texto = "\n".join(log)
    if len(coletados) <= 0:
        from sistema.tarefas_secundarias.servico import TarefaSecundariaErro

        raise TarefaSecundariaErro(
            "Cache de Product Types Amazon ficou vazio. Confira a conta conectada.",
            log_texto=log_texto,
        )
    prog({"fase": "ok", "pct": 100, "folhas": len(coletados)}, msg)
    return {
        "folhas": len(coletados),
        "ignoradas_sem_nome": 0,
        "erros_site": 0,
        "sites": [mp],
        "mensagem": msg,
        "log_texto": log_texto,
    }


def buscar_product_types_cache_amazon(
    cur, marketplace_id: str, termo: str, limit: int = 40
) -> list[dict]:
    garantir_tabela_amazon_product_type_cache(cur)
    mp = (marketplace_id or "").strip()
    termo = (termo or "").strip()
    lim = max(1, min(int(limit or 40), 80))
    if len(termo) < 2:
        cur.execute(
            """
            SELECT product_type, display_name
            FROM tbl_amazon_product_type_cache
            WHERE marketplace_id = %s
            ORDER BY display_name, product_type
            LIMIT %s
            """,
            (mp, lim),
        )
    else:
        like = f"%{termo}%"
        cur.execute(
            """
            SELECT product_type, display_name
            FROM tbl_amazon_product_type_cache
            WHERE marketplace_id = %s
              AND (
                product_type ILIKE %s
                OR display_name ILIKE %s
              )
            ORDER BY
              CASE WHEN lower(product_type) = lower(%s) THEN 0
                   WHEN lower(product_type) LIKE lower(%s) THEN 1
                   ELSE 2 END,
              product_type
            LIMIT %s
            """,
            (mp, like, like, termo, f"{termo}%", lim),
        )
    return [
        {
            "category_id": str(r[0]),  # alias p/ picker ML-compat
            "product_type": str(r[0]),
            "nome": (r[1] or r[0]),
            "display_name": (r[1] or r[0]),
            "path_nomes": str(r[0]),
        }
        for r in cur.fetchall()
        if r[0]
    ]
