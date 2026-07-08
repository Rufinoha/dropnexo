# api/bling/pedidos.py — importação, exportação e status de pedidos Bling
from __future__ import annotations

# ── sync_pedidos ──────────────────────────────────────

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from api.bling.campos import (
    descricao_situacao_pedido,
    parse_pedido_bling,
    pedido_bling_importavel,
)
from api.bling.cliente import api_request
from global_utils import agora_utc
from core.pedidos.servico import importar_pedido_bling


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


# ── sync_pedido_status ────────────────────────────────

import json
import logging
import re
from typing import Any

from api.bling.cliente import api_request

_log = logging.getLogger(__name__)

_EVENTO_SITUACAO_NOMES: dict[str, tuple[str, ...]] = {
    "pago": ("pago", "aprovado", "confirmado", "em aberto"),
    "expedido": ("enviado", "em transporte", "despachado", "expedido", "postado"),
    "entregue": ("entregue", "atendido", "concluído", "concluido", "finalizado"),
    "cancelado": ("cancelado", "cancelada"),
}

_MODULO_PEDIDOS_ID: int | None = None
_SITUACOES_CACHE: dict[int, list[dict[str, Any]]] = {}


def _normalizar(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "").strip().lower())


def _carregar_config_vendedor(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT pedidos_modo, opcoes
        FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = 'vendedor'
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {"pedidos_modo": "importar", "opcoes": {}}
    opcoes = row[1]
    if isinstance(opcoes, str) and opcoes.strip():
        try:
            opcoes = json.loads(opcoes)
        except json.JSONDecodeError:
            opcoes = {}
    if not isinstance(opcoes, dict):
        opcoes = {}
    return {"pedidos_modo": row[0] or "importar", "opcoes": opcoes}


def _bling_conectado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return bool(row and row[0] == "conectado")


def _id_modulo_pedidos_venda(id_tenant: int) -> int | None:
    global _MODULO_PEDIDOS_ID
    if _MODULO_PEDIDOS_ID:
        return _MODULO_PEDIDOS_ID
    try:
        body = api_request(id_tenant, "GET", "/situacoes/modulos")
        modulos = body.get("data") if isinstance(body, dict) else body
        if not isinstance(modulos, list):
            return None
        for mod in modulos:
            nome = _normalizar(str(mod.get("nome") or mod.get("descricao") or ""))
            if "pedido" in nome and "venda" in nome:
                _MODULO_PEDIDOS_ID = int(mod["id"])
                return _MODULO_PEDIDOS_ID
        for mod in modulos:
            nome = _normalizar(str(mod.get("nome") or ""))
            if nome == "vendas" or "pedidos de venda" in nome:
                _MODULO_PEDIDOS_ID = int(mod["id"])
                return _MODULO_PEDIDOS_ID
    except Exception as e:
        _log.warning("Bling módulo situações pedidos: %s", e)
    return None


def _listar_situacoes_venda(id_tenant: int) -> list[dict[str, Any]]:
    id_mod = _id_modulo_pedidos_venda(id_tenant)
    if not id_mod:
        return []
    if id_mod in _SITUACOES_CACHE:
        return _SITUACOES_CACHE[id_mod]
    try:
        body = api_request(id_tenant, "GET", f"/situacoes/modulos/{id_mod}")
        dados = body.get("data") if isinstance(body, dict) else body
        if not isinstance(dados, list):
            return []
        _SITUACOES_CACHE[id_mod] = dados
        return dados
    except Exception as e:
        _log.warning("Bling listar situações: %s", e)
        return []


def _resolver_situacao_id(id_tenant: int, evento: str, opcoes: dict) -> int | None:
    chave = f"bling_situacao_{evento}"
    manual = opcoes.get(chave)
    if manual not in (None, ""):
        try:
            return int(manual)
        except (TypeError, ValueError):
            pass
    nomes = _EVENTO_SITUACAO_NOMES.get(evento, ())
    for sit in _listar_situacoes_venda(id_tenant):
        sid = sit.get("id")
        nome = _normalizar(str(sit.get("nome") or sit.get("descricao") or ""))
        if sid is None:
            continue
        if any(n in nome for n in nomes):
            return int(sid)
    return None


def exportar_status_pedido_bling(
    cur,
    id_pedido: int,
    *,
    evento: str,
) -> bool:
    """
    Atualiza situação no Bling para pedidos importados (origem bling).
    Retorna True se enviou com sucesso.
    """
    cur.execute(
        """
        SELECT p.id, p.id_tenant_vendedor, p.origem, p.id_bling_pedido
        FROM tbl_pedido p WHERE p.id = %s
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        return False
    _, id_vendedor, origem, id_bling = row
    if (origem or "") != "bling" or not id_bling:
        return False
    id_vendedor = int(id_vendedor)
    if not _bling_conectado(cur, id_vendedor):
        return False

    cfg = _carregar_config_vendedor(cur, id_vendedor)
    opcoes = cfg.get("opcoes") or {}
    if opcoes.get("pedidos_exportar_status") is False:
        return False
    modo = (cfg.get("pedidos_modo") or "importar").strip()
    if modo not in ("exportar", "atualizar"):
        return False

    id_situacao = _resolver_situacao_id(id_vendedor, evento, opcoes)
    if not id_situacao:
        _log.info("Bling: situação não mapeada para evento %s (pedido %s)", evento, id_pedido)
        return False

    try:
        api_request(
            id_vendedor,
            "PATCH",
            f"/pedidos/vendas/{id_bling}/situacoes/{id_situacao}",
        )
        return True
    except Exception as e:
        _log.warning("Bling PATCH situação pedido %s: %s", id_bling, e)
        return False


# ── export_pedidos ────────────────────────────────────

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from api.bling.cliente import api_request
from fornecedor.catalogo.catalogo import id_bling_produto
from global_utils import agora_utc
from core.pedidos.servico import STATUS_PAGO, listar_itens_pedido, obter_pedido, status_vendedor_pedido


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
        ) VALUES (%s, 'bling', %s, 'pedido', 'exportar', %s, %s, %s)
        """,
        (id_tenant, contexto, status, resumo, detalhe),
    )


def _carregar_config_fornecedor(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT pedidos_modo, opcoes FROM tbl_integracao_bling_config
        WHERE id_tenant = %s AND contexto = 'fornecedor' AND ativo = TRUE
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {"pedidos_modo": "exportar", "opcoes": {}}
    opcoes = row[1] or {}
    if isinstance(opcoes, str) and opcoes.strip():
        try:
            opcoes = json.loads(opcoes) or {}
        except json.JSONDecodeError:
            opcoes = {}
    return {"pedidos_modo": row[0] or "exportar", "opcoes": opcoes if isinstance(opcoes, dict) else {}}


def _bling_conectado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return bool(row and row[0] == "conectado")


def _pedido_ja_exportado(cur, id_tenant: int, id_pedido: int) -> str | None:
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = 'fornecedor'
          AND entidade = 'pedido' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_pedido),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _upsert_mapa_pedido(cur, id_tenant: int, id_pedido: int, id_bling: str, numero: str) -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'bling', 'fornecedor', 'pedido', %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling) DO UPDATE SET
            id_dropnexo = EXCLUDED.id_dropnexo,
            sku = EXCLUDED.sku,
            meta = EXCLUDED.meta,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            id_bling,
            id_pedido,
            numero,
            json.dumps({"numero_dropnexo": numero}, ensure_ascii=False),
            agora_utc(),
        ),
    )


def _limpar_doc(doc: str | None) -> str:
    return "".join(c for c in str(doc or "") if c.isdigit())


def _buscar_contato_bling(id_tenant: int, documento: str, nome: str) -> int | None:
    doc = _limpar_doc(documento)
    if doc:
        try:
            resp = api_request(
                id_tenant,
                "GET",
                "/contatos",
                params={"pagina": 1, "limite": 5, "numeroDocumento": doc},
            )
            data = resp.get("data") or []
            if isinstance(data, list) and data:
                cid = data[0].get("id")
                if cid:
                    return int(cid)
        except Exception:
            pass

    if nome:
        try:
            resp = api_request(
                id_tenant,
                "GET",
                "/contatos",
                params={"pagina": 1, "limite": 5, "pesquisa": nome[:60]},
            )
            data = resp.get("data") or []
            if isinstance(data, list):
                for c in data:
                    if doc and _limpar_doc(c.get("numeroDocumento")) == doc:
                        return int(c["id"])
                if data and data[0].get("id"):
                    return int(data[0]["id"])
        except Exception:
            pass
    return None


def _criar_contato_bling(id_tenant: int, ped: dict) -> int:
    doc = _limpar_doc(ped.get("cliente_documento"))
    payload: dict[str, Any] = {
        "nome": (ped.get("cliente_nome") or "Cliente DropNexo")[:120],
        "tipo": "J" if doc and len(doc) > 11 else "F",
        "situacao": "A",
    }
    if doc:
        payload["numeroDocumento"] = doc
    if ped.get("cliente_email"):
        payload["email"] = str(ped["cliente_email"])[:120]
    if ped.get("cliente_telefone"):
        payload["telefone"] = str(ped["cliente_telefone"])[:30]

    endereco = {
        "endereco": (ped.get("entrega_logradouro") or "")[:120] or None,
        "numero": (ped.get("entrega_numero") or "")[:20] or None,
        "complemento": (ped.get("entrega_complemento") or "")[:60] or None,
        "bairro": (ped.get("entrega_bairro") or "")[:60] or None,
        "municipio": (ped.get("entrega_cidade") or "")[:60] or None,
        "uf": (ped.get("entrega_uf") or "")[:2] or None,
        "cep": _limpar_doc(ped.get("entrega_cep")) or None,
    }
    if any(endereco.values()):
        payload["endereco"] = {"geral": {k: v for k, v in endereco.items() if v}}

    resp = api_request(id_tenant, "POST", "/contatos", json_body=payload)
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    cid = data.get("id")
    if not cid:
        raise RuntimeError("Bling não retornou ID do contato criado.")
    return int(cid)


def _garantir_contato_bling(id_tenant: int, ped: dict) -> int:
    existente = _buscar_contato_bling(
        id_tenant,
        ped.get("cliente_documento"),
        ped.get("cliente_nome") or "",
    )
    if existente:
        return existente
    return _criar_contato_bling(id_tenant, ped)


def _montar_itens_bling(cur, id_fornecedor: int, itens: list[dict]) -> list[dict]:
    resultado: list[dict] = []
    for item in itens:
        sku = (item.get("sku") or "").strip()
        id_prod = item.get("id_produto")
        id_bling = None
        if id_prod:
            id_bling = id_bling_produto(cur, id_fornecedor, int(id_prod), contexto="fornecedor")
        if not id_bling:
            raise ValueError(f"SKU «{sku or '?'}» sem vínculo no Bling. Importe o produto antes de exportar pedidos.")
        valor = float(item.get("preco_venda") or item.get("valor_drop") or 0)
        resultado.append(
            {
                "produto": {"id": int(id_bling)},
                "codigo": sku or None,
                "quantidade": int(item.get("quantidade") or 0),
                "valor": valor,
            }
        )
    if not resultado:
        raise ValueError("Pedido sem itens exportáveis.")
    return resultado


def exportar_pedido_fornecedor_bling(
    cur,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    if id_usuario is not None:
        pass

    ped = obter_pedido(cur, id_pedido)
    if not ped:
        raise ValueError("Pedido não encontrado.")

    id_forn = int(ped["id_tenant_fornecedor"])
    if not _bling_conectado(cur, id_forn):
        raise ValueError("Fornecedor não está conectado ao Bling.")

    cfg = _carregar_config_fornecedor(cur, id_forn)
    modo = (cfg.get("pedidos_modo") or "exportar").strip()
    if modo not in ("exportar", "atualizar"):
        raise ValueError("Modo de pedidos não permite exportar ao Bling.")

    opcoes = cfg.get("opcoes") or {}
    if opcoes.get("pedidos_exportar") is False:
        raise ValueError("Exportação de pedidos está desativada.")

    if (ped.get("origem") or "") == "bling":
        raise ValueError("Pedidos importados do Bling (vendedor) não são reexportados.")

    if status_vendedor_pedido(ped) != STATUS_PAGO:
        raise ValueError("Somente pedidos pagos podem ser exportados ao Bling.")

    if _pedido_ja_exportado(cur, id_forn, id_pedido):
        return {"exportados": 0, "ignorado": True, "message": "Pedido já exportado ao Bling."}

    itens = listar_itens_pedido(cur, id_pedido)
    itens_bling = _montar_itens_bling(cur, id_forn, itens)
    contato_id = _garantir_contato_bling(id_forn, ped)

    data_ped = ped.get("pago_em") or ped.get("confirmado_em") or ped.get("criado_em")
    if data_ped:
        data_str = str(data_ped)[:10]
    else:
        data_str = datetime.now(timezone.utc).date().isoformat()

    obs_partes = [f"DropNexo #{ped.get('numero') or id_pedido}"]
    if ped.get("observacoes"):
        obs_partes.append(str(ped["observacoes"])[:500])

    payload: dict[str, Any] = {
        "contato": {"id": contato_id},
        "data": data_str,
        "observacoes": " — ".join(obs_partes)[:1000],
        "itens": itens_bling,
    }

    transporte: dict[str, Any] = {}
    if ped.get("entrega_cep") or ped.get("entrega_logradouro"):
        transporte["etiqueta"] = {
            "nome": (ped.get("cliente_nome") or "")[:120] or None,
            "endereco": (ped.get("entrega_logradouro") or "")[:120] or None,
            "numero": (ped.get("entrega_numero") or "")[:20] or None,
            "complemento": (ped.get("entrega_complemento") or "")[:60] or None,
            "bairro": (ped.get("entrega_bairro") or "")[:60] or None,
            "municipio": (ped.get("entrega_cidade") or "")[:60] or None,
            "uf": (ped.get("entrega_uf") or "")[:2] or None,
            "cep": _limpar_doc(ped.get("entrega_cep")) or None,
        }
        transporte["etiqueta"] = {k: v for k, v in transporte["etiqueta"].items() if v}
    if transporte:
        payload["transporte"] = transporte

    resp = api_request(id_forn, "POST", "/pedidos/vendas", json_body=payload)
    criado = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    id_bling_ped = criado.get("id")
    if not id_bling_ped:
        raise RuntimeError("Bling não retornou ID do pedido criado.")

    numero = str(ped.get("numero") or id_pedido)
    _upsert_mapa_pedido(cur, id_forn, id_pedido, str(id_bling_ped), numero)

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_bling_config
        SET ultima_sync_pedidos = %s, atualizado_em = %s
        WHERE id_tenant = %s AND contexto = 'fornecedor'
        """,
        (agora, agora, id_forn),
    )

    msg = f"Pedido DropNexo #{numero} exportado ao Bling (#{id_bling_ped})."
    _registrar_log(cur, id_forn, "fornecedor", "ok", msg)
    return {"exportados": 1, "ignorado": False, "message": msg, "id_bling_pedido": str(id_bling_ped)}


def pedidos_exportacao_auto_ativa(cur, id_tenant: int) -> bool:
    cfg = _carregar_config_fornecedor(cur, id_tenant)
    modo = (cfg.get("pedidos_modo") or "exportar").strip()
    if modo not in ("exportar", "atualizar"):
        return False
    opcoes = cfg.get("opcoes") or {}
    return opcoes.get("pedidos_exportar_auto") is True and opcoes.get("pedidos_exportar") is not False


def tentar_exportar_pedido_fornecedor_apos_pagamento(cur, id_pedido: int) -> bool:
    ped = obter_pedido(cur, id_pedido)
    if not ped:
        return False
    id_forn = int(ped["id_tenant_fornecedor"])
    if not _bling_conectado(cur, id_forn):
        return False
    if not pedidos_exportacao_auto_ativa(cur, id_forn):
        return False
    try:
        res = exportar_pedido_fornecedor_bling(cur, id_pedido)
        return bool(res.get("exportados"))
    except Exception as e:
        _registrar_log(cur, id_forn, "fornecedor", "aviso", f"Pedido #{id_pedido}", str(e)[:500])
        return False


def exportar_pedidos_pendentes_fornecedor(
    cur,
    id_tenant: int,
    *,
    dias: int = 30,
    id_usuario: int | None = None,
) -> dict[str, Any]:
    if id_usuario is not None:
        pass

    cfg = _carregar_config_fornecedor(cur, id_tenant)
    modo = (cfg.get("pedidos_modo") or "exportar").strip()
    if modo not in ("exportar", "atualizar"):
        raise ValueError("Modo de pedidos não permite exportar ao Bling.")

    if not _bling_conectado(cur, id_tenant):
        raise ValueError("Conecte o Bling antes de exportar pedidos.")

    limite = datetime.now(timezone.utc) - timedelta(days=max(1, min(int(dias or 30), 90)))
    cv = "status_vendedor"
    try:
        from core.pedidos.servico import col_status_vendedor

        cv = col_status_vendedor(cur)
    except Exception:
        pass

    cur.execute(
        f"""
        SELECT p.id
        FROM tbl_pedido p
        WHERE p.id_tenant_fornecedor = %s
          AND p.{cv} = %s
          AND COALESCE(p.origem, '') <> 'bling'
          AND COALESCE(p.pago_em, p.confirmado_em, p.criado_em) >= %s
          AND NOT EXISTS (
              SELECT 1 FROM tbl_integracao_map m
              WHERE m.id_tenant = %s AND m.provedor = 'bling' AND m.contexto = 'fornecedor'
                AND m.entidade = 'pedido' AND m.id_dropnexo = p.id
          )
        ORDER BY p.id
        """,
        (id_tenant, STATUS_PAGO, limite, id_tenant),
    )
    ids = [int(r[0]) for r in cur.fetchall()]

    exportados = 0
    ignorados = 0
    erros = 0
    for pid in ids:
        try:
            res = exportar_pedido_fornecedor_bling(cur, pid)
            if res.get("exportados"):
                exportados += 1
            else:
                ignorados += 1
        except ValueError:
            ignorados += 1
        except Exception as e:
            erros += 1
            _registrar_log(cur, id_tenant, "fornecedor", "erro", f"Pedido #{pid}", str(e)[:500])

    resumo = f"{exportados} pedido(s) exportado(s), {ignorados} ignorado(s), {erros} erro(s)."
    _registrar_log(cur, id_tenant, "fornecedor", "ok" if erros == 0 else "aviso", resumo)
    return {
        "exportados": exportados,
        "ignorados": ignorados,
        "erros": erros,
        "message": resumo,
    }
