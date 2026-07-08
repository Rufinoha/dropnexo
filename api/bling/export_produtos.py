# api/bling/export_produtos.py — exportação Meus produtos (vendedor) → Bling
from __future__ import annotations

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
