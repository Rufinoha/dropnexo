# api/bling/estoque.py — depósitos Bling e sincronização de estoque
from __future__ import annotations

# ── depositos ─────────────────────────────────────────

from global_utils import agora_utc


def listar_mapa_depositos(cur, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        SELECT dm.id, dm.id_bling_deposito, dm.nome_bling, dm.id_deposito_dropnexo, d.nome,
               dm.estoque_sync_pendente, dm.estoque_sync_concluido_em
        FROM tbl_integracao_deposito_map dm
        LEFT JOIN tbl_deposito_expedicao d ON d.id = dm.id_deposito_dropnexo
        WHERE dm.id_tenant = %s
        ORDER BY dm.nome_bling NULLS LAST, dm.id_bling_deposito
        """,
        (id_tenant,),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": r[0],
                "id_bling_deposito": r[1],
                "nome_bling": r[2] or "",
                "id_deposito_dropnexo": r[3],
                "nome_dropnexo": r[4] or "",
                "estoque_sync_pendente": bool(r[5]) if len(r) > 5 else False,
                "estoque_sync_concluido_em": r[6].isoformat() if len(r) > 6 and r[6] else None,
            }
        )
    return out


def resolver_deposito_dropnexo(cur, id_tenant: int, id_bling_deposito: str) -> int | None:
    cur.execute(
        """
        SELECT id_deposito_dropnexo FROM tbl_integracao_deposito_map
        WHERE id_tenant = %s AND id_bling_deposito = %s AND id_deposito_dropnexo IS NOT NULL
        LIMIT 1
        """,
        (id_tenant, str(id_bling_deposito)),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] else None


def salvar_vinculo_deposito(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    nome_bling: str | None,
    id_deposito_dropnexo: int | None,
) -> tuple[int, bool]:
    id_bling = str(id_bling_deposito).strip()
    if not id_bling:
        raise ValueError("Depósito Bling inválido.")
    if id_deposito_dropnexo:
        cur.execute(
            """
            SELECT 1 FROM tbl_deposito_expedicao
            WHERE id = %s AND id_tenant = %s AND ativo = TRUE
            """,
            (id_deposito_dropnexo, id_tenant),
        )
        if not cur.fetchone():
            raise ValueError("Depósito DropNexo inválido.")

    cur.execute(
        """
        SELECT id_deposito_dropnexo FROM tbl_integracao_deposito_map
        WHERE id_tenant = %s AND id_bling_deposito = %s
        """,
        (id_tenant, id_bling),
    )
    row_ant = cur.fetchone()
    id_ant = int(row_ant[0]) if row_ant and row_ant[0] is not None else None
    id_novo = int(id_deposito_dropnexo) if id_deposito_dropnexo else None
    alterado = id_ant != id_novo

    sync_pendente = False
    sync_concluido = None
    if id_novo and alterado:
        sync_pendente = True
    elif id_novo and not alterado:
        cur.execute(
            """
            SELECT estoque_sync_pendente, estoque_sync_concluido_em
            FROM tbl_integracao_deposito_map
            WHERE id_tenant = %s AND id_bling_deposito = %s
            """,
            (id_tenant, id_bling),
        )
        st = cur.fetchone()
        if st:
            sync_pendente = bool(st[0])
            sync_concluido = st[1]

    cur.execute(
        """
        INSERT INTO tbl_integracao_deposito_map (
            id_tenant, id_bling_deposito, nome_bling, id_deposito_dropnexo,
            estoque_sync_pendente, estoque_sync_concluido_em, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, id_bling_deposito) DO UPDATE SET
            nome_bling = EXCLUDED.nome_bling,
            id_deposito_dropnexo = EXCLUDED.id_deposito_dropnexo,
            estoque_sync_pendente = CASE
                WHEN EXCLUDED.id_deposito_dropnexo IS NULL THEN FALSE
                WHEN tbl_integracao_deposito_map.id_deposito_dropnexo IS DISTINCT FROM EXCLUDED.id_deposito_dropnexo
                    THEN TRUE
                ELSE tbl_integracao_deposito_map.estoque_sync_pendente
            END,
            estoque_sync_concluido_em = CASE
                WHEN EXCLUDED.id_deposito_dropnexo IS NULL THEN NULL
                WHEN tbl_integracao_deposito_map.id_deposito_dropnexo IS DISTINCT FROM EXCLUDED.id_deposito_dropnexo
                    THEN NULL
                ELSE tbl_integracao_deposito_map.estoque_sync_concluido_em
            END,
            atualizado_em = EXCLUDED.atualizado_em
        RETURNING id
        """,
        (
            id_tenant,
            id_bling,
            (nome_bling or "").strip() or None,
            id_deposito_dropnexo,
            sync_pendente,
            sync_concluido,
            agora_utc(),
        ),
    )
    return int(cur.fetchone()[0]), alterado


def sincronizar_depositos_bling_api(cur, id_tenant: int, depositos_bling: list[dict]) -> int:
    """Garante registros no mapa para cada depósito retornado pela API (sem vínculo)."""
    n = 0
    for dep in depositos_bling:
        id_b = str(dep.get("id") or "")
        if not id_b:
            continue
        nome = (dep.get("descricao") or dep.get("nome") or "").strip()
        cur.execute(
            """
            INSERT INTO tbl_integracao_deposito_map (id_tenant, id_bling_deposito, nome_bling, atualizado_em)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_tenant, id_bling_deposito) DO UPDATE SET
                nome_bling = COALESCE(EXCLUDED.nome_bling, tbl_integracao_deposito_map.nome_bling),
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, id_b, nome or None, agora_utc()),
        )
        n += 1
    return n


def _endereco_tenant(cur, id_tenant: int) -> dict | None:
    cur.execute(
        """
        SELECT nome, cep, logradouro, numero, complemento, bairro, cidade, uf
        FROM tbl_tenant WHERE id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return None
    cep = "".join(ch for ch in str(row[1] or "") if ch.isdigit())
    if len(cep) != 8:
        return None
    log = (row[2] or "").strip()
    bairro = (row[5] or "").strip()
    cidade = (row[6] or "").strip()
    uf = (row[7] or "").strip()[:2].upper()
    if not log or not bairro or not cidade or len(uf) != 2:
        return None
    return {
        "nome_tenant": (row[0] or "").strip(),
        "cep": cep,
        "logradouro": log,
        "numero": (row[3] or "S/N").strip() or "S/N",
        "complemento": (row[4] or "").strip() or None,
        "bairro": bairro,
        "cidade": cidade,
        "uf": uf,
    }


def _criar_deposito_dropnexo(
    cur,
    id_tenant: int,
    *,
    nome: str,
    endereco: dict,
    principal: bool = False,
) -> int:
    if principal:
        cur.execute(
            "UPDATE tbl_deposito_expedicao SET principal = FALSE WHERE id_tenant = %s",
            (id_tenant,),
        )
    cur.execute(
        """
        INSERT INTO tbl_deposito_expedicao (
            id_tenant, nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
            remetente_nome, principal, ativo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
        RETURNING id
        """,
        (
            id_tenant,
            (nome or "Depósito").strip()[:120],
            endereco["cep"],
            endereco["logradouro"],
            endereco["numero"],
            endereco.get("complemento"),
            endereco["bairro"],
            endereco["cidade"],
            endereco["uf"],
            endereco.get("nome_tenant"),
            principal,
            agora_utc(),
        ),
    )
    return int(cur.fetchone()[0])


def _normalizar_nome_dep(nome: str) -> str:
    return " ".join((nome or "").strip().lower().split())


def criar_deposito_igual_bling(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    nome_bling: str | None = None,
    padrao_bling: bool = False,
) -> int:
    """
    Cria depósito DropNexo espelhando o depósito Bling (nome e flag principal)
    e usa o endereço cadastrado da empresa.
    """
    endereco = _endereco_tenant(cur, id_tenant)
    if not endereco:
        raise ValueError(
            "Complete o endereço da empresa (Minha Empresa) antes de criar depósitos automaticamente."
        )

    nome = (nome_bling or "").strip()
    if not nome:
        cur.execute(
            """
            SELECT nome_bling FROM tbl_integracao_deposito_map
            WHERE id_tenant = %s AND id_bling_deposito = %s
            LIMIT 1
            """,
            (id_tenant, str(id_bling_deposito)),
        )
        row = cur.fetchone()
        nome = (row[0] if row else "") or "Depósito Bling"

    cur.execute(
        """
        SELECT id FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE
          AND LOWER(TRIM(nome)) = LOWER(TRIM(%s))
        LIMIT 1
        """,
        (id_tenant, nome),
    )
    existente = cur.fetchone()
    if existente:
        return int(existente[0])

    cur.execute(
        "SELECT COUNT(*) FROM tbl_deposito_expedicao WHERE id_tenant = %s AND ativo = TRUE",
        (id_tenant,),
    )
    sem_depositos = int(cur.fetchone()[0] or 0) == 0
    principal = padrao_bling or sem_depositos

    try:
        return _criar_deposito_dropnexo(
            cur,
            id_tenant,
            nome=nome,
            endereco=endereco,
            principal=principal,
        )
    except Exception as exc:
        err = str(exc).lower()
        if "unique" in err and "cep" in err:
            raise ValueError(
                "Já existe um depósito com o CEP da empresa. "
                "Cadastre outro endereço em Expedição ou vincule a um depósito existente."
            ) from exc
        raise


def vincular_ou_criar_deposito_bling(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    nome_bling: str | None,
    id_deposito_dropnexo: int | None,
    criar_igual: bool = False,
    padrao_bling: bool = False,
) -> tuple[int, int | None, bool, bool]:
    """
    Salva vínculo Bling ↔ DropNexo. Se criar_igual, cria depósito antes de vincular.
    Retorna (id_mapa, id_deposito_dropnexo, criou_deposito, alterado).
    """
    id_drop = id_deposito_dropnexo
    criou = False
    if criar_igual:
        id_drop = criar_deposito_igual_bling(
            cur,
            id_tenant,
            id_bling_deposito=id_bling_deposito,
            nome_bling=nome_bling,
            padrao_bling=padrao_bling,
        )
        criou = True

    rid = salvar_vinculo_deposito(
        cur,
        id_tenant,
        id_bling_deposito=id_bling_deposito,
        nome_bling=nome_bling,
        id_deposito_dropnexo=id_drop,
    )
    return rid[0], id_drop, criou, rid[1]


def resumo_depositos_bling(cur, id_tenant: int) -> dict:
    """
    Sincroniza lista de depósitos Bling no mapa (sem autovínculo).
    Retorna contagem de vinculados e pendentes.
    """

    try:
        sincronizar_depositos_tenant(cur, id_tenant)
    except Exception:
        pass
    mapa = listar_mapa_depositos(cur, id_tenant)
    vinculados = sum(1 for m in mapa if m.get("id_deposito_dropnexo"))
    pendentes = len(mapa) - vinculados
    return {
        "mapa": len(mapa),
        "vinculados": vinculados,
        "criados": 0,
        "pendentes": pendentes,
    }


def _depositos_ui_from_mapa(mapa: list[dict]) -> list[dict]:
    """Fallback quando a API Bling está indisponível — usa nomes já salvos no mapa local."""
    out: list[dict] = []
    vistos: set[str] = set()
    for m in mapa:
        bid = str(m.get("id_bling_deposito") or "").strip()
        if not bid or bid in vistos:
            continue
        vistos.add(bid)
        nome = (m.get("nome_bling") or bid).strip()
        out.append({"id": bid, "descricao": nome, "nome": nome})
    return out


def carregar_depositos_bling_ui(cur, id_tenant: int) -> tuple[list[dict], list[dict], str | None]:
    """
    Lista depósitos para a tela de pareamento.
    Retorna (mapa_enriquecido, depositos_bling, aviso_api ou None).
    """
    from api.bling.cliente import listar_depositos_bling

    mapa = listar_mapa_depositos(cur, id_tenant)
    aviso: str | None = None
    bling_deps: list[dict] = []
    try:
        bling_deps = listar_depositos_bling(id_tenant)
        sincronizar_depositos_bling_api(cur, id_tenant, bling_deps)
        mapa = listar_mapa_depositos(cur, id_tenant)
    except Exception as exc:
        aviso = str(exc)[:240]
        bling_deps = _depositos_ui_from_mapa(mapa)
        if not bling_deps:
            raise

    mapa_enriquecido: list[dict] = []
    for m in mapa:
        item = dict(m)
        job = obter_job_sync_ativo_deposito(cur, id_tenant, str(m.get("id_bling_deposito") or ""))
        if job:
            item["sync_job"] = job
        mapa_enriquecido.append(item)
    return mapa_enriquecido, bling_deps, aviso


def garantir_depositos_bling_vinculados(cur, id_tenant: int) -> dict:
    """Alias legado — apenas lista depósitos; vínculo é sempre manual."""
    return resumo_depositos_bling(cur, id_tenant)


def marcar_sync_estoque_deposito_concluido(cur, id_tenant: int, id_bling_deposito: str) -> None:
    cur.execute(
        """
        UPDATE tbl_integracao_deposito_map
        SET estoque_sync_pendente = FALSE,
            estoque_sync_concluido_em = %s,
            atualizado_em = %s
        WHERE id_tenant = %s AND id_bling_deposito = %s
        """,
        (agora_utc(), agora_utc(), id_tenant, str(id_bling_deposito)),
    )


def obter_job_sync_ativo_deposito(cur, id_tenant: int, id_bling_deposito: str) -> dict | None:
    try:
        cur.execute(
            """
            SELECT job_id::text, status, total, processados, sincronizados, falhas, mensagem
            FROM tbl_integracao_bling_sync_job
            WHERE id_tenant = %s
              AND id_bling_deposito = %s
              AND status = 'processando'
            ORDER BY criado_em DESC
            LIMIT 1
            """,
            (id_tenant, str(id_bling_deposito)),
        )
    except Exception:
        return None
    row = cur.fetchone()
    if not row:
        return None
    return {
        "job_id": row[0],
        "status": row[1],
        "total": row[2] or 0,
        "processados": row[3] or 0,
        "sincronizados": row[4] or 0,
        "falhas": row[5] or 0,
        "mensagem": row[6] or "",
    }


# ── sync_estoque ──────────────────────────────────────

import json
import time
from typing import Callable

from api.bling.cliente import api_request, listar_depositos_bling, obter_saldos_estoque
from api.bling.config import eco_deve_ignorar_webhook, registrar_eco_pendente
from fornecedor.catalogo.catalogo import (
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
        from fornecedor.catalogo.catalogo import id_bling_produto as buscar_id_bling

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
    from fornecedor.catalogo.catalogo import sincronizar_estoque_produto_bling

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

    from fornecedor.catalogo.catalogo import id_bling_produto as buscar_id_bling

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
