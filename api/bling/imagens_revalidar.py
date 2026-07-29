# api/bling/imagens_revalidar.py — renova links temporários (modo_imagem=link)
from __future__ import annotations

import time
from datetime import timedelta

from api.bling.cliente import obter_produto, obter_variacoes_produto
from api.bling.produtos import aplicar_imagens_produto, extrair_urls_imagem_bling
from fornecedor.catalogo.catalogo import (
    id_bling_produto,
    recalcular_bytes_imagens_tenant,
    url_imagem_temporaria,
)
from global_utils import agora_utc

DIAS_ANTECEDENCIA = 3
PAUSA_ENTRE_PRODUTOS_S = 0.4


def listar_tenants_modo_link(cur) -> list[int]:
    cur.execute(
        """
        SELECT DISTINCT id_tenant
        FROM tbl_integracao_bling_config
        WHERE contexto = 'fornecedor' AND modo_imagem = 'link'
        ORDER BY id_tenant
        """
    )
    return [int(r[0]) for r in cur.fetchall()]


def listar_produtos_para_revalidar(
    cur,
    id_tenant: int,
    *,
    dias_antecedencia: int = DIAS_ANTECEDENCIA,
    limite: int | None = None,
) -> list[int]:
    """Produtos com link temporário vencendo / vencido (ou sem data mas URL assinada)."""
    limite_dt = agora_utc() + timedelta(days=max(0, dias_antecedencia))
    sql = """
        SELECT DISTINCT p.id
        FROM tbl_produto p
        JOIN tbl_produto_imagem i ON i.id_produto = p.id AND i.id_variante IS NULL
        WHERE p.id_tenant = %s
          AND (
                (i.link_expira_em IS NOT NULL AND i.link_expira_em <= %s)
             OR (
                    i.link_expira_em IS NULL
                    AND (i.caminho ILIKE 'http%%')
                    AND (
                        i.caminho ILIKE '%%orgbling%%'
                        OR i.caminho ILIKE '%%Expires=%%'
                        OR i.caminho ILIKE '%%X-Amz-Expires=%%'
                    )
                )
          )
        ORDER BY p.id
    """
    params: list = [id_tenant, limite_dt]
    if limite:
        sql += " LIMIT %s"
        params.append(int(limite))
    cur.execute(sql, params)
    return [int(r[0]) for r in cur.fetchall()]


def revalidar_produto_imagens(
    cur,
    *,
    id_tenant: int,
    id_produto: int,
    contexto: str = "fornecedor",
) -> dict:
    id_bling = id_bling_produto(cur, id_tenant, id_produto, contexto=contexto)
    if not id_bling:
        return {"ok": False, "id_produto": id_produto, "erro": "sem_mapa_bling"}

    cur.execute(
        "SELECT sku FROM tbl_produto WHERE id = %s AND id_tenant = %s",
        (id_produto, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "id_produto": id_produto, "erro": "produto_nao_encontrado"}
    sku = (row[0] or "").strip() or "sem-sku"

    detalhe = obter_produto(id_tenant, id_bling)
    if not detalhe:
        return {"ok": False, "id_produto": id_produto, "erro": "bling_vazio"}

    variacoes: list[dict] = []
    try:
        pai = obter_variacoes_produto(id_tenant, id_bling)
        raw = pai.get("variacoes") if isinstance(pai, dict) else None
        if isinstance(raw, list):
            variacoes = [v for v in raw if isinstance(v, dict)]
    except Exception:
        variacoes = []

    urls = extrair_urls_imagem_bling(detalhe, variacoes=variacoes or None)
    if not urls:
        return {"ok": False, "id_produto": id_produto, "erro": "sem_urls"}

    # Em modo link: só persiste URLs (com expires); não baixa.
    aplicar_imagens_produto(
        cur,
        id_tenant=id_tenant,
        id_produto=id_produto,
        sku=sku,
        urls=urls,
        modo_imagem="link",
        variacoes_bling=variacoes or None,
    )
    temporarias = sum(1 for u in urls if url_imagem_temporaria(u))
    return {
        "ok": True,
        "id_produto": id_produto,
        "id_bling": id_bling,
        "urls": len(urls),
        "temporarias": temporarias,
    }


def revalidar_tenant(
    cur,
    id_tenant: int,
    *,
    dias_antecedencia: int = DIAS_ANTECEDENCIA,
    limite: int | None = None,
    pausa_s: float = PAUSA_ENTRE_PRODUTOS_S,
) -> dict:
    ids = listar_produtos_para_revalidar(
        cur, id_tenant, dias_antecedencia=dias_antecedencia, limite=limite
    )
    ok = 0
    erros: list[dict] = []
    for i, id_produto in enumerate(ids):
        try:
            r = revalidar_produto_imagens(cur, id_tenant=id_tenant, id_produto=id_produto)
            if r.get("ok"):
                ok += 1
            else:
                erros.append(r)
        except Exception as e:
            erros.append({"ok": False, "id_produto": id_produto, "erro": str(e)})
        if i + 1 < len(ids) and pausa_s > 0:
            time.sleep(pausa_s)
    try:
        bytes_img = recalcular_bytes_imagens_tenant(cur, id_tenant)
    except Exception:
        bytes_img = None
    return {
        "id_tenant": id_tenant,
        "candidatos": len(ids),
        "ok": ok,
        "erros": len(erros),
        "detalhe_erros": erros[:20],
        "bytes_imagens": bytes_img,
    }


def revalidar_todos(
    cur,
    *,
    id_tenant: int | None = None,
    dias_antecedencia: int = DIAS_ANTECEDENCIA,
    limite_por_tenant: int | None = None,
    pausa_s: float = PAUSA_ENTRE_PRODUTOS_S,
) -> list[dict]:
    tenants = [id_tenant] if id_tenant else listar_tenants_modo_link(cur)
    return [
        revalidar_tenant(
            cur,
            tid,
            dias_antecedencia=dias_antecedencia,
            limite=limite_por_tenant,
            pausa_s=pausa_s,
        )
        for tid in tenants
        if tid
    ]
