# api/bling/sync_pedidos.py — importação de pedidos pagos Bling → DropNexo (vendedor)
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.bling.campos_pedido import parse_pedido_bling, pedido_bling_importavel
from api.bling.cliente import api_request
from global_utils import agora_utc
from servico_pedido import importar_pedido_bling


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
        ) VALUES (%s, 'bling', %s, 'pedido', 'importar', %s, %s, %s)
        """,
        (id_tenant, contexto, status, resumo, detalhe),
    )


def _modo_permite_importar(cur, id_tenant: int, contexto: str) -> bool:
    cur.execute(
        """
        SELECT pedidos_modo FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = %s AND ativo = TRUE
        """,
        (id_tenant, contexto),
    )
    row = cur.fetchone()
    if not row:
        return False
    return row[0] in ("importar", "atualizar")


def listar_pedidos_bling(
    id_tenant: int,
    *,
    data_inicial: str,
    data_final: str,
    pagina: int = 1,
) -> list[dict]:
    body = api_request(
        id_tenant,
        "GET",
        "/pedidos/vendas",
        params={
            "pagina": pagina,
            "limite": 100,
            "dataInicial": data_inicial,
            "dataFinal": data_final,
        },
    )
    data = body.get("data")
    if isinstance(data, list):
        return data
    return []


def obter_pedido_bling(id_tenant: int, id_bling_pedido: str) -> dict:
    body = api_request(id_tenant, "GET", f"/pedidos/vendas/{id_bling_pedido}")
    return body.get("data") or {}


def importar_pedidos_bling(
    cur,
    id_tenant: int,
    *,
    contexto: str = "vendedor",
    dias: int = 30,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    if contexto != "vendedor":
        raise ValueError("Importação de pedidos Bling disponível apenas para o perfil vendedor.")
    if not _modo_permite_importar(cur, id_tenant, contexto):
        raise ValueError("Modo de pedidos não permite importação. Ajuste em Integrações → Bling → Pedidos.")

    fim = datetime.now(timezone.utc).date()
    ini = fim - timedelta(days=max(1, min(int(dias or 30), 90)))

    importados = 0
    ignorados = 0
    erros = 0
    ids_criados: list[int] = []
    pagina = 1

    while True:
        lista = listar_pedidos_bling(
            id_tenant,
            data_inicial=ini.isoformat(),
            data_final=fim.isoformat(),
            pagina=pagina,
        )
        if not lista:
            break

        for stub in lista:
            id_bling = str(stub.get("id") or "").strip()
            if not id_bling:
                ignorados += 1
                continue
            try:
                det = obter_pedido_bling(id_tenant, id_bling)
                if not pedido_bling_importavel(det):
                    ignorados += 1
                    continue
                parsed = parse_pedido_bling(det)
                if not parsed["itens"]:
                    ignorados += 1
                    continue
                novos = importar_pedido_bling(
                    cur,
                    id_tenant,
                    id_bling,
                    parsed,
                    id_usuario=id_usuario,
                )
                if novos:
                    importados += len(novos)
                    ids_criados.extend(novos)
                else:
                    ignorados += 1
            except ValueError as e:
                ignorados += 1
                _registrar_log(cur, id_tenant, contexto, "aviso", f"Pedido Bling #{id_bling}", str(e))
            except Exception as e:
                erros += 1
                _registrar_log(cur, id_tenant, contexto, "erro", f"Pedido Bling #{id_bling}", str(e)[:500])

        if len(lista) < 100:
            break
        pagina += 1

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET ultima_sync_pedidos = %s, atualizado_em = %s
        WHERE id_tenant = %s AND contexto = %s
        """,
        (agora, agora, id_tenant, contexto),
    )

    resumo = f"{importados} pedido(s) importado(s), {ignorados} ignorado(s), {erros} erro(s)."
    _registrar_log(cur, id_tenant, contexto, "ok" if erros == 0 else "aviso", resumo)

    return {
        "importados": importados,
        "ignorados": ignorados,
        "erros": erros,
        "pedidos_ids": ids_criados,
        "message": resumo,
    }
