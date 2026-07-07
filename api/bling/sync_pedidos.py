# api/bling/sync_pedidos.py — importação de pedidos pagos Bling → DropNexo (vendedor)
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from api.bling.campos_pedido import (
    descricao_situacao_pedido,
    parse_pedido_bling,
    pedido_bling_importavel,
)
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


def _opcoes_vendedor(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT opcoes FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = 'vendedor' AND ativo = TRUE
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return {}
    raw = row[0]
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw) or {}
        except json.JSONDecodeError:
            return {}
    return {}


def pedidos_importacao_auto_ativa(cur, id_tenant: int) -> bool:
    if not _modo_permite_importar(cur, id_tenant, "vendedor"):
        return False
    opcoes = _opcoes_vendedor(cur, id_tenant)
    return opcoes.get("pedidos_importar_auto") is True


def _importar_um_pedido(
    cur,
    id_tenant: int,
    id_bling: str,
    *,
    contexto: str,
    id_usuario: int | None,
) -> tuple[list[int], str | None, str | None]:
    """Retorna (ids_pedidos_criados, motivo_ignorado, detalhe_extra)."""
    det = obter_pedido_bling(id_tenant, id_bling)
    if not pedido_bling_importavel(det, id_tenant=id_tenant):
        return [], "situacao_invalida", descricao_situacao_pedido(det, id_tenant=id_tenant)
    parsed = parse_pedido_bling(det)
    if not parsed["itens"]:
        return [], "sem_itens", None
    novos = importar_pedido_bling(
        cur,
        id_tenant,
        id_bling,
        parsed,
        id_usuario=id_usuario,
    )
    if novos:
        return novos, None, None
    return [], "ja_importado_ou_sem_match", None


def importar_pedido_bling_por_id(
    cur,
    id_tenant: int,
    id_bling_pedido: str,
    *,
    contexto: str = "vendedor",
    id_usuario: int | None = None,
) -> dict[str, Any]:
    if contexto != "vendedor":
        raise ValueError("Importação de pedidos Bling disponível apenas para o perfil vendedor.")
    if not _modo_permite_importar(cur, id_tenant, contexto):
        raise ValueError("Modo de pedidos não permite importação.")

    id_bling = str(id_bling_pedido or "").strip()
    if not id_bling:
        raise ValueError("ID do pedido Bling inválido.")

    try:
        novos, motivo, detalhe_extra = _importar_um_pedido(
            cur, id_tenant, id_bling, contexto=contexto, id_usuario=id_usuario
        )
    except ValueError as e:
        _registrar_log(cur, id_tenant, contexto, "aviso", f"Pedido Bling #{id_bling}", str(e))
        return {"importados": 0, "ignorado": True, "message": str(e)}
    except Exception as e:
        _registrar_log(cur, id_tenant, contexto, "erro", f"Pedido Bling #{id_bling}", str(e)[:500])
        raise

    if novos:
        agora = agora_utc()
        cur.execute(
            """
            UPDATE tbl_integracao_bling_config
            SET ultima_sync_pedidos = %s, atualizado_em = %s
            WHERE id_tenant = %s AND contexto = %s
            """,
            (agora, agora, id_tenant, contexto),
        )
        msg = f"Pedido Bling #{id_bling} importado."
        _registrar_log(cur, id_tenant, contexto, "ok", msg)
        return {"importados": len(novos), "ignorado": False, "message": msg, "pedidos_ids": novos}

    msg = {
        "situacao_invalida": "Situação do pedido no Bling não permite importação.",
        "sem_itens": "Pedido sem itens.",
        "ja_importado_ou_sem_match": "Pedido já importado ou SKU não encontrado em Meus produtos.",
    }.get(motivo or "", "Pedido ignorado.")
    detalhe_log = (
        f"{msg} · Situação: {detalhe_extra}"
        if motivo == "situacao_invalida" and detalhe_extra
        else msg
    )
    _registrar_log(cur, id_tenant, contexto, "aviso", f"Pedido Bling #{id_bling}", detalhe_log)
    return {"importados": 0, "ignorado": True, "message": msg}


def importar_pedidos_bling(
    cur,
    id_tenant: int,
    *,
    contexto: str = "vendedor",
    dias: int = 30,
    data_inicial: str | None = None,
    data_final: str | None = None,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    if contexto != "vendedor":
        raise ValueError("Importação de pedidos Bling disponível apenas para o perfil vendedor.")
    if not _modo_permite_importar(cur, id_tenant, contexto):
        raise ValueError("Modo de pedidos não permite importação. Ajuste em Integrações → Bling → Pedidos.")

    hoje = datetime.now(timezone.utc).date()
    if data_inicial:
        try:
            ini = datetime.strptime(str(data_inicial)[:10], "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Data do pedido inválida. Use o formato AAAA-MM-DD.")
        if data_final:
            try:
                fim = datetime.strptime(str(data_final)[:10], "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Data final inválida.")
        else:
            fim = hoje
    else:
        fim = hoje
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
                novos, motivo, detalhe_extra = _importar_um_pedido(
                    cur, id_tenant, id_bling, contexto=contexto, id_usuario=id_usuario
                )
                if novos:
                    importados += len(novos)
                    ids_criados.extend(novos)
                else:
                    ignorados += 1
                    if motivo == "situacao_invalida" and detalhe_extra:
                        _registrar_log(
                            cur,
                            id_tenant,
                            contexto,
                            "aviso",
                            f"Pedido Bling #{id_bling}",
                            f"Situação no Bling: {detalhe_extra}",
                        )
                    elif motivo and motivo not in ("ja_importado_ou_sem_match", "situacao_invalida"):
                        _registrar_log(cur, id_tenant, contexto, "aviso", f"Pedido Bling #{id_bling}", motivo)
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
