# api/bling/sync_estoque.py — importação/exportação de estoque por depósito
from __future__ import annotations

import json
import time
from typing import Callable

from api.bling.cliente import api_request, listar_depositos_bling, obter_saldos_estoque
from api.bling.depositos import resolver_deposito_dropnexo, sincronizar_depositos_bling_api
from api.bling.eco_estoque import eco_deve_ignorar_webhook, registrar_eco_pendente
from fornecedor.catalogo.servico_estoque_deposito import (
    garantir_linhas_estoque_depositos,
    sincronizar_total_variante,
)
from global_utils import agora_utc

# Bling: máx. 3 req/s — intervalo conservador entre produtos na sync manual
BLING_INTERVALO_SYNC_SEG = 0.4
BLING_SYNC_MAX_TENTATIVAS = 6


def _obter_saldos_com_retry(id_tenant: int, id_bling: str) -> dict:
    ultimo_erro: Exception | None = None
    for tentativa in range(BLING_SYNC_MAX_TENTATIVAS):
        try:
            return obter_saldos_estoque(id_tenant, id_bling)
        except Exception as exc:
            ultimo_erro = exc
            msg = str(exc).lower()
            if "limite" in msg or "too_many" in msg or "429" in msg:
                time.sleep(min(8.0, 1.5 * (tentativa + 1)))
                continue
            raise
    if ultimo_erro:
        raise ultimo_erro
    return {}


def _estoque_modo_permite_importar(cur, id_tenant: int, contexto: str) -> bool:
    cur.execute(
        """
        SELECT estoque_modo FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s AND ativo = TRUE
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    if not row:
        return True
    return (row[0] or "importar") in ("importar", "atualizar")


def _estoque_recebimento_ativo(cur, id_tenant: int, contexto: str) -> bool:
    cur.execute(
        """
        SELECT opcoes FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s AND ativo = TRUE
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    opcoes = row[0] if row else {}
    if isinstance(opcoes, str):
        try:
            opcoes = json.loads(opcoes) or {}
        except json.JSONDecodeError:
            opcoes = {}
    if not isinstance(opcoes, dict):
        opcoes = {}
    if "estoque_importar_bling" in opcoes:
        return bool(opcoes.get("estoque_importar_bling"))
    return _estoque_modo_permite_importar(cur, id_tenant, contexto)


def marcar_sync_estoque_recebido(cur, id_tenant: int, contexto: str) -> None:
    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET ultima_sync_estoque_recebido = %s,
            ultima_sync_estoque = %s,
            atualizado_em = %s
        WHERE id_tenant = %s AND contexto = %s
        """,
        (agora, agora, agora, id_tenant, contexto),
    )


def marcar_sync_estoque_enviado(cur, id_tenant: int, contexto: str) -> None:
    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET ultima_sync_estoque_enviado = %s,
            ultima_sync_estoque = %s,
            atualizado_em = %s
        WHERE id_tenant = %s AND contexto = %s
        """,
        (agora, agora, agora, id_tenant, contexto),
    )


def _registrar_log_estoque(cur, id_tenant: int, contexto: str, status: str, resumo: str) -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_log (
            id_tenant, provedor, contexto, entidade, direcao, status, resumo, criado_em
        ) VALUES (%s, 'bling', %s, 'estoque', 'importar', %s, %s, %s)
        """,
        (id_tenant, contexto, status, resumo, agora_utc()),
    )


def _aplicar_quantidade_deposito(
    cur,
    *,
    id_variante: int,
    id_deposito: int,
    quantidade: int,
) -> bool:
    cur.execute(
        """
        SELECT quantidade FROM tbl_produto_estoque_deposito
        WHERE id_variante = %s AND id_deposito = %s
        """,
        (id_variante, id_deposito),
    )
    row = cur.fetchone()
    atual = int(row[0] or 0) if row else None
    if atual is not None and atual == quantidade:
        return False
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
    sincronizar_total_variante(cur, id_variante)
    return True


def _resolver_variante_por_bling(
    cur,
    id_tenant: int,
    id_bling_produto: str,
) -> tuple[int | None, int | None]:
    cur.execute(
        """
        SELECT id_dropnexo, sku, meta FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND entidade = 'produto'
          AND id_bling = %s
        LIMIT 1
        """,
        (id_tenant, str(id_bling_produto)),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None, None
    id_produto = int(row[0])
    sku = row[1]
    meta = row[2] if isinstance(row[2], dict) else {}
    if isinstance(row[2], str):
        try:
            meta = json.loads(row[2]) or {}
        except json.JSONDecodeError:
            meta = {}
    fmt = str((meta or {}).get("formato") or "").upper()
    if fmt == "V" and sku:
        cur.execute(
            """
            SELECT id FROM tbl_produto_variante
            WHERE id_produto = %s AND sku IS NOT DISTINCT FROM %s
            LIMIT 1
            """,
            (id_produto, sku),
        )
        vrow = cur.fetchone()
        return id_produto, int(vrow[0]) if vrow else None
    cur.execute(
        "SELECT id_variante_padrao FROM tbl_produto WHERE id = %s AND id_tenant = %s",
        (id_produto, id_tenant),
    )
    vrow = cur.fetchone()
    return id_produto, int(vrow[0]) if vrow and vrow[0] else None


def importar_estoque_produto_bling(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    id_produto: int,
    id_variante: int,
    id_bling_override: str | None = None,
    id_bling_deposito_filtro: str | None = None,
) -> int:
    if not _estoque_modo_permite_importar(cur, id_tenant, contexto):
        return 0
    id_bling = (id_bling_override or "").strip() or None
    if not id_bling:
        from fornecedor.catalogo.servico_estoque_deposito import id_bling_produto as buscar_id_bling

        id_bling = buscar_id_bling(cur, id_tenant, id_produto, contexto=contexto)
    if not id_bling:
        return 0

    try:
        saldos = _obter_saldos_com_retry(id_tenant, id_bling)
    except Exception:
        return 0

    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    atualizados = 0
    depositos = saldos.get("depositos") or []
    if not isinstance(depositos, list):
        depositos = []

    for dep in depositos:
        if not isinstance(dep, dict):
            continue
        id_bling_dep = str(dep.get("id") or (dep.get("deposito") or {}).get("id") or "")
        if not id_bling_dep:
            continue
        if id_bling_deposito_filtro and id_bling_dep != str(id_bling_deposito_filtro):
            continue
        id_dep_drop = resolver_deposito_dropnexo(cur, id_tenant, id_bling_dep)
        if not id_dep_drop:
            continue
        qtd = dep.get("saldoFisico")
        if qtd is None:
            qtd = dep.get("saldoVirtual")
        if qtd is None:
            qtd = dep.get("quantidade")
        try:
            quantidade = max(0, int(float(qtd or 0)))
        except (TypeError, ValueError):
            quantidade = 0
        if _aplicar_quantidade_deposito(
            cur,
            id_variante=id_variante,
            id_deposito=id_dep_drop,
            quantidade=quantidade,
        ):
            atualizados += 1

    return atualizados


def processar_webhook_estoque_bling(
    cur,
    id_tenant: int,
    payload: dict,
    *,
    contexto: str = "fornecedor",
) -> dict:
    if not _estoque_recebimento_ativo(cur, id_tenant, contexto):
        return {"ok": True, "ignorado": True, "motivo": "recebimento_desativado"}

    produto = payload.get("produto") or {}
    deposito = payload.get("deposito") or {}
    id_bling_prod = str(produto.get("id") or payload.get("produtoId") or "").strip()
    id_bling_dep = str(deposito.get("id") or payload.get("depositoId") or "").strip()
    if not id_bling_prod or not id_bling_dep:
        return {"ok": False, "motivo": "payload_incompleto"}

    qtd = deposito.get("saldoFisico")
    if qtd is None:
        qtd = deposito.get("saldoVirtual")
    if qtd is None:
        qtd = payload.get("saldoFisicoTotal")
    try:
        quantidade = max(0, int(float(qtd or 0)))
    except (TypeError, ValueError):
        quantidade = 0

    if eco_deve_ignorar_webhook(
        cur,
        id_tenant,
        id_bling_produto=id_bling_prod,
        id_bling_deposito=id_bling_dep,
        quantidade=quantidade,
    ):
        return {"ok": True, "ignorado": True, "motivo": "eco_suprimido"}

    id_dep_drop = resolver_deposito_dropnexo(cur, id_tenant, id_bling_dep)
    if not id_dep_drop:
        return {"ok": True, "ignorado": True, "motivo": "deposito_nao_vinculado"}

    _, id_variante = _resolver_variante_por_bling(cur, id_tenant, id_bling_prod)
    if not id_variante:
        return {"ok": True, "ignorado": True, "motivo": "produto_nao_mapeado"}

    garantir_linhas_estoque_depositos(cur, id_tenant, id_variante)
    alterou = _aplicar_quantidade_deposito(
        cur,
        id_variante=id_variante,
        id_deposito=id_dep_drop,
        quantidade=quantidade,
    )
    if alterou:
        marcar_sync_estoque_recebido(cur, id_tenant, contexto)
        _registrar_log_estoque(
            cur,
            id_tenant,
            contexto,
            "ok",
            f"Webhook estoque produto Bling #{id_bling_prod} dep #{id_bling_dep} → {quantidade}",
        )
    return {"ok": True, "alterou": alterou, "quantidade": quantidade}


def sincronizar_estoque_inicial_tenant(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    contexto: str = "fornecedor",
    on_progresso: Callable[[dict[str, int]], None] | None = None,
) -> dict:
    from fornecedor.catalogo.servico_estoque_deposito import sincronizar_estoque_produto_bling

    cur.execute(
        """
        SELECT DISTINCT id_dropnexo FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND entidade = 'produto'
          AND id_dropnexo IS NOT NULL
        ORDER BY id_dropnexo
        """,
        (id_tenant,),
    )
    ids = [int(r[0]) for r in cur.fetchall()]
    total = len(ids)
    ok = 0
    falhas = 0
    if on_progresso:
        on_progresso(
            {
                "total": total,
                "processados": 0,
                "sincronizados": 0,
                "falhas": 0,
                "mensagem": f"Sincronizando estoque ({total} produtos)…",
            }
        )

    for idx, pid in enumerate(ids, start=1):
        sucesso, msg, n = sincronizar_estoque_produto_bling(
            cur,
            id_tenant,
            pid,
            contexto=contexto,
            id_bling_deposito_filtro=id_bling_deposito,
        )
        if sucesso and n > 0:
            ok += 1
        elif not sucesso:
            falhas += 1
        if on_progresso and (idx % 2 == 0 or idx == total):
            on_progresso(
                {
                    "total": total,
                    "processados": idx,
                    "sincronizados": ok,
                    "falhas": falhas,
                    "mensagem": f"Processados {idx}/{total}",
                }
            )
        if idx < total:
            time.sleep(BLING_INTERVALO_SYNC_SEG)

    if ok > 0:
        marcar_sync_estoque_recebido(cur, id_tenant, contexto)
    resumo = f"Sync inicial depósito Bling #{id_bling_deposito}: {ok} produto(s) com saldo, {falhas} falha(s)"
    _registrar_log_estoque(cur, id_tenant, contexto, "ok" if ok else "aviso", resumo)
    return {
        "total": total,
        "processados": total,
        "sincronizados": ok,
        "falhas": falhas,
        "resumo": resumo,
    }


def exportar_saldo_deposito_bling(
    cur,
    id_tenant: int,
    *,
    contexto: str,
    id_produto: int,
    id_deposito: int,
    quantidade: int,
    id_bling_override: str | None = None,
    origem_eco: str = "export_manual",
) -> tuple[bool, str | None]:
    cur.execute(
        """
        SELECT estoque_modo FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s AND ativo = TRUE
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    modo = (row[0] or "importar") if row else "importar"
    if modo not in ("exportar", "atualizar"):
        return False, "Modo de estoque não permite exportar ao Bling."

    from fornecedor.catalogo.servico_estoque_deposito import id_bling_produto as buscar_id_bling

    id_bling = id_bling_override or buscar_id_bling(cur, id_tenant, id_produto, contexto=contexto)
    if not id_bling:
        return False, "Produto sem vínculo no Bling."

    cur.execute(
        """
        SELECT id_bling_deposito FROM tbl_integracao_deposito_map
        WHERE id_tenant = %s AND id_deposito_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_deposito),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return False, "Depósito não vinculado ao Bling."

    id_bling_dep = str(row[0])
    qtd = max(0, int(quantidade))
    registrar_eco_pendente(
        cur,
        id_tenant,
        id_bling_produto=str(id_bling),
        id_bling_deposito=id_bling_dep,
        quantidade_esperada=qtd,
        origem=origem_eco,
    )
    try:
        api_request(
            id_tenant,
            "POST",
            "/estoques",
            json_body={
                "produto": {"id": int(id_bling)},
                "deposito": {"id": int(id_bling_dep)},
                "operacao": "B",
                "quantidade": qtd,
                "observacoes": "Ajuste via DropNexo",
            },
        )
        marcar_sync_estoque_enviado(cur, id_tenant, contexto)
        return True, None
    except Exception as e:
        return False, str(e)


def sincronizar_depositos_tenant(cur, id_tenant: int) -> int:
    depositos = listar_depositos_bling(id_tenant)
    return sincronizar_depositos_bling_api(cur, id_tenant, depositos)
