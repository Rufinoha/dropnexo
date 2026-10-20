# api/olist/painel.py — config, depósitos, categorias e logs no mesmo esquema do Bling
from __future__ import annotations

import json
from typing import Any

from api.olist.cliente import api_request, garantir_tabelas
from global_utils import agora_utc

_MODOS = ("importar", "exportar", "atualizar")


def _modo(valor: Any, padrao: str) -> str:
    v = str(valor or padrao).strip()
    return v if v in _MODOS else padrao


def _itens(dados: Any) -> list[dict]:
    if isinstance(dados, list):
        return [x for x in dados if isinstance(x, dict)]
    if isinstance(dados, dict):
        for chave in ("itens", "categorias", "depositos", "data"):
            bloco = dados.get(chave)
            if isinstance(bloco, list):
                return [x for x in bloco if isinstance(x, dict)]
    return []


def garantir_config(cur, id_tenant: int) -> None:
    garantir_tabelas(cur)
    cur.execute(
        """
        INSERT INTO tbl_integracao_olist_config (
            id_tenant, contexto, fonte_principal, modo_imagem,
            produtos_modo, estoque_modo, pedidos_modo, opcoes, atualizado_em
        ) VALUES (%s, 'fornecedor', 'olist', 'download', 'importar', 'importar', 'exportar', '{}'::jsonb, %s)
        ON CONFLICT (id_tenant, contexto) DO NOTHING
        """,
        (int(id_tenant), agora_utc()),
    )


def ler_config(cur, id_tenant: int) -> dict[str, Any]:
    garantir_config(cur, id_tenant)
    cur.execute(
        """
        SELECT fonte_principal, modo_imagem, produtos_modo, estoque_modo, pedidos_modo,
               opcoes, ultima_sync_produtos, ultima_sync_pedidos, ultima_sync_estoque
        FROM tbl_integracao_olist_config
        WHERE id_tenant = %s AND contexto = 'fornecedor'
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    opcoes = row[5] if row else {}
    if isinstance(opcoes, str):
        try:
            opcoes = json.loads(opcoes)
        except json.JSONDecodeError:
            opcoes = {}
    if not isinstance(opcoes, dict):
        opcoes = {}
    return {
        "contexto": "fornecedor",
        "fonte_principal": (row[0] if row else None) or "olist",
        "modo_imagem": "download",
        "produtos_modo": (row[2] if row else None) or "importar",
        "estoque_modo": (row[3] if row else None) or "importar",
        "pedidos_modo": (row[4] if row else None) or "exportar",
        "opcoes": opcoes,
        "ultima_sync_produtos": row[6].isoformat() if row and row[6] else None,
        "ultima_sync_pedidos": row[7].isoformat() if row and row[7] else None,
        "ultima_sync_estoque": row[8].isoformat() if row and row[8] else None,
    }


def salvar_config(cur, id_tenant: int, body: dict) -> None:
    garantir_config(cur, id_tenant)
    fonte = str(body.get("fonte_principal") or "olist").strip()
    if fonte not in ("olist", "dropnexo"):
        fonte = "olist"
    opcoes = body.get("opcoes") if isinstance(body.get("opcoes"), dict) else None
    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_integracao_olist_config SET
            fonte_principal = %s,
            modo_imagem = 'download',
            produtos_modo = %s,
            estoque_modo = %s,
            pedidos_modo = %s,
            opcoes = CASE WHEN %s::jsonb IS NULL THEN opcoes ELSE COALESCE(opcoes, '{}'::jsonb) || %s::jsonb END,
            atualizado_em = %s
        WHERE id_tenant = %s AND contexto = 'fornecedor'
        """,
        (
            fonte,
            _modo(body.get("produtos_modo"), "importar"),
            _modo(body.get("estoque_modo"), "importar"),
            _modo(body.get("pedidos_modo"), "exportar"),
            json.dumps(opcoes, ensure_ascii=False) if opcoes is not None else None,
            json.dumps(opcoes, ensure_ascii=False) if opcoes is not None else None,
            agora,
            int(id_tenant),
        ),
    )


def listar_logs(cur, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        SELECT status, resumo, detalhe, criado_em
        FROM tbl_integracao_log
        WHERE id_tenant = %s AND provedor = 'olist'
        ORDER BY id DESC
        LIMIT 20
        """,
        (int(id_tenant),),
    )
    saida = []
    for row in cur.fetchall():
        saida.append(
            {
                "status": row[0],
                "resumo": row[1] or "",
                "detalhe": row[2] or "",
                "criado_em": row[3].isoformat() if row[3] else None,
            }
        )
    return saida


def _buscar_lista(id_tenant: int, caminhos: list[str]) -> list[dict]:
    ultimo = ""
    for caminho in caminhos:
        try:
            return _itens(api_request(id_tenant, "GET", caminho))
        except Exception as e:
            ultimo = str(e)
    if ultimo:
        raise RuntimeError(ultimo)
    return []


def listar_depositos(cur, id_tenant: int) -> dict[str, Any]:
    garantir_tabelas(cur)
    try:
        remotos = _buscar_lista(id_tenant, ["/depositos"])
    except RuntimeError as e:
        texto = str(e)
        if "respondeu 401" in texto:
            raise RuntimeError(
                "A conta no Olist não tem o módulo Depósitos ativado. "
                "Ative Depósitos para o usuário que conectou o DropNexo e conecte de novo."
            ) from e
        if "respondeu 403" in texto:
            raise RuntimeError(
                "O Olist recusou a lista de depósitos. "
                "Deixe Depósitos em Leitura no aplicativo Dropnexo e conecte de novo."
            ) from e
        raise
    cur.execute(
        """
        SELECT id_olist, id_deposito FROM tbl_integracao_olist_deposito
        WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    mapa = {str(r[0]): r[1] for r in cur.fetchall()}
    cur.execute(
        """
        SELECT id, nome FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE
        ORDER BY principal DESC, nome
        """,
        (int(id_tenant),),
    )
    locais = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
    itens = []
    for dep in remotos:
        id_olist = str(dep.get("id") or "").strip()
        if not id_olist:
            continue
        itens.append(
            {
                "id": id_olist,
                "nome": str(dep.get("nome") or dep.get("descricao") or id_olist).strip(),
                "id_deposito": mapa.get(id_olist),
            }
        )
    vinculados = sum(1 for item in itens if item["id_deposito"])
    return {"olist": itens, "dropnexo": locais, "vinculados": vinculados}


def vincular_deposito(cur, id_tenant: int, id_olist: str, nome: str, id_deposito: int | None) -> None:
    garantir_tabelas(cur)
    cur.execute(
        """
        INSERT INTO tbl_integracao_olist_deposito (id_tenant, id_olist, nome, id_deposito, atualizado_em)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, id_olist) DO UPDATE SET
            nome = EXCLUDED.nome,
            id_deposito = EXCLUDED.id_deposito,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (int(id_tenant), id_olist, (nome or "")[:180], id_deposito, agora_utc()),
    )


def _achatar_arvore(nos: Any, pai: str = "", id_pai: str = "") -> list[dict]:
    if isinstance(nos, dict):
        if nos.get("id") or nos.get("descricao") or nos.get("nome"):
            nos = [nos]
        else:
            nos = nos.get("filhas") or nos.get("itens") or nos.get("categorias") or []
    saida: list[dict] = []
    for no in nos or []:
        if not isinstance(no, dict):
            continue
        nome = str(no.get("descricao") or no.get("nome") or "").strip()
        id_olist = str(no.get("id") or "").strip()
        caminho = f"{pai} > {nome}" if pai and nome else nome
        if id_olist:
            saida.append(
                {
                    "id": id_olist,
                    "descricao": nome or id_olist,
                    "caminho": caminho or nome or id_olist,
                    "id_pai": id_pai,
                }
            )
        filhas = no.get("filhas") if isinstance(no.get("filhas"), list) else no.get("nodes")
        if isinstance(filhas, list) and filhas:
            saida.extend(_achatar_arvore(filhas, caminho or pai, id_olist or id_pai))
    return saida


def listar_categorias(cur, id_tenant: int) -> dict[str, Any]:
    garantir_tabelas(cur)
    try:
        bruto = api_request(id_tenant, "GET", "/categorias/todas")
    except RuntimeError as e:
        texto = str(e)
        if "respondeu 401" in texto:
            raise RuntimeError(
                "A conta no Olist não tem o módulo Categorias ativado. "
                "Ative Categorias para o usuário que conectou o DropNexo e conecte de novo."
            ) from e
        if "respondeu 403" in texto:
            raise RuntimeError(
                "O Olist recusou a lista de categorias. Pode ser que ainda não exista nenhuma categoria no Olist. "
                "Se já existir, deixe Categorias em Leitura no aplicativo Dropnexo e conecte de novo."
            ) from e
        raise
    remotos = _achatar_arvore(bruto)
    cur.execute(
        """
        SELECT id_olist, acao, id_segmento, id_categoria
        FROM tbl_integracao_olist_categoria
        WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    mapa = {str(r[0]): {"acao": r[1], "id_segmento": r[2], "id_categoria": r[3]} for r in cur.fetchall()}
    cur.execute(
        """
        SELECT s.id, s.nome
        FROM tbl_fornecedor_segmento fs
        JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
        WHERE fs.id_tenant = %s
        ORDER BY s.nome
        """,
        (int(id_tenant),),
    )
    segmentos = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
    cur.execute(
        """
        SELECT id, nome, id_segmento FROM tbl_categoria
        WHERE id_tenant = %s AND ativo = TRUE
        ORDER BY nome
        """,
        (int(id_tenant),),
    )
    locais = [{"id": r[0], "nome": r[1], "id_segmento": r[2]} for r in cur.fetchall()]
    nomes = {str(c.get("id")): str(c.get("descricao") or c.get("nome") or "").strip() for c in remotos}
    itens = []
    for cat in remotos:
        id_olist = str(cat.get("id") or "").strip()
        if not id_olist:
            continue
        nome = nomes.get(id_olist) or str(cat.get("caminho") or id_olist)
        caminho = str(cat.get("caminho") or nome)
        salvo = mapa.get(id_olist) or {}
        itens.append(
            {
                "id": id_olist,
                "nome": nome,
                "caminho": caminho,
                "acao": salvo.get("acao") or "",
                "id_segmento": salvo.get("id_segmento"),
                "id_categoria": salvo.get("id_categoria"),
                "id_pai": str(cat.get("id_pai") or ""),
            }
        )
    return {"olist": itens, "segmentos": segmentos, "dropnexo": locais}


def salvar_categoria(cur, id_tenant: int, body: dict) -> None:
    garantir_tabelas(cur)
    id_olist = str(body.get("id_olist") or "").strip()
    if not id_olist:
        raise ValueError("Categoria do Olist inválida.")
    acao = str(body.get("acao") or "ignorar").strip()
    if acao not in ("vincular", "criar", "ignorar"):
        acao = "ignorar"
    id_segmento = body.get("id_segmento")
    id_categoria = body.get("id_categoria")
    try:
        id_segmento = int(id_segmento) if id_segmento not in (None, "") else None
    except (TypeError, ValueError):
        id_segmento = None
    try:
        id_categoria = int(id_categoria) if id_categoria not in (None, "") else None
    except (TypeError, ValueError):
        id_categoria = None
    if acao == "criar" and id_segmento:
        cur.execute(
            """
            SELECT id FROM tbl_categoria
            WHERE id_tenant = %s AND id_segmento = %s AND lower(nome) = lower(%s)
            LIMIT 1
            """,
            (int(id_tenant), id_segmento, str(body.get("nome") or "").strip()),
        )
        achou = cur.fetchone()
        if achou:
            id_categoria = int(achou[0])
        else:
            cur.execute(
                """
                INSERT INTO tbl_categoria (id_tenant, id_segmento, parent_id, nome, ordem, nivel, ativo)
                VALUES (%s, %s, NULL, %s, 0, 1, TRUE)
                RETURNING id
                """,
                (int(id_tenant), id_segmento, str(body.get("nome") or "Categoria")[:120]),
            )
            id_categoria = int(cur.fetchone()[0])
        acao = "vincular"
    cur.execute(
        """
        INSERT INTO tbl_integracao_olist_categoria (
            id_tenant, id_olist, nome, acao, id_segmento, id_categoria, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, id_olist) DO UPDATE SET
            nome = EXCLUDED.nome,
            acao = EXCLUDED.acao,
            id_segmento = EXCLUDED.id_segmento,
            id_categoria = EXCLUDED.id_categoria,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            int(id_tenant),
            id_olist,
            str(body.get("nome") or "")[:180],
            acao,
            id_segmento,
            id_categoria if acao == "vincular" else None,
            agora_utc(),
        ),
    )
