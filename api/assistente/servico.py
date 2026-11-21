# api/assistente/servico.py — auth, consultas e escritas (fase/contato)
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sistema.planos.fornecedor_acompanhamento import (
    FASE_ROTULO,
    definir_fase,
    listar_contatos,
    registrar_contato,
    triagem_rotulo,
)
from sistema.planos.fornecedor_fundador import prazo_ativacao_fundador

RATE_LIMIT_POR_MIN = 60
_rate: dict[str, list[float]] = {}


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _hint(token: str) -> str:
    t = token or ""
    if len(t) < 10:
        return t[:4] + "…"
    return f"{t[:8]}…{t[-4:]}"


def erro_generico(msg: str = "Não foi possível concluir a solicitação.") -> dict:
    return {"success": False, "message": msg}


def autenticar(conn, authorization: str | None) -> tuple[dict | None, str | None]:
    """Retorna (token_row, erro). token_row tem id, hint."""
    raw = (authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        return None, "Token ausente ou inválido."
    token = raw[7:].strip()
    if not token.startswith("dn_assist_") or len(token) < 20:
        return None, "Token ausente ou inválido."
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, token_hint, ativo, revogado_em
          FROM tbl_assistente_token
         WHERE token_hash = %s
         LIMIT 1
        """,
        (_hash_token(token),),
    )
    row = cur.fetchone()
    if not row or not row[2] or row[3]:
        return None, "Token ausente ou inválido."
    hint = row[1] or _hint(token)
    if not _rate_ok(hint):
        return None, "Limite de requisições excedido. Tente em instantes."
    return {"id": int(row[0]), "hint": hint}, None


def _rate_ok(hint: str) -> bool:
    agora = time.time()
    janela = int(agora // 60)
    chave = f"{hint}:{janela}"
    # limpa chaves antigas ocasionalmente
    if len(_rate) > 500:
        _rate.clear()
    bucket = _rate.setdefault(chave, [])
    bucket[:] = [t for t in bucket if agora - t < 60]
    if len(bucket) >= RATE_LIMIT_POR_MIN:
        return False
    bucket.append(agora)
    return True


def auditar(
    conn,
    *,
    rota: str,
    metodo: str,
    ip: str | None,
    token_hint: str | None,
    http_status: int,
    id_tenant_alvo: int | None = None,
) -> None:
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tbl_assistente_auditoria
              (rota, metodo, ip, token_hint, http_status, id_tenant_alvo)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (rota[:300], (metodo or "GET")[:12], (ip or "")[:80], (token_hint or "")[:40], http_status, id_tenant_alvo),
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def status_token(conn) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, token_hint, nome, ativo, criado_em, revogado_em
          FROM tbl_assistente_token
         ORDER BY criado_em DESC
         LIMIT 5
        """
    )
    itens = []
    for r in cur.fetchall():
        itens.append(
            {
                "id": int(r[0]),
                "token_hint": r[1],
                "nome": r[2],
                "ativo": bool(r[3]),
                "criado_em": r[4].isoformat() if r[4] else None,
                "revogado_em": r[5].isoformat() if r[5] else None,
            }
        )
    ativo = next((i for i in itens if i["ativo"]), None)
    return {"ativo": ativo, "itens": itens}


def gerar_token(conn, *, id_usuario: int | None, nome: str = "Assistente") -> tuple[dict, str]:
    token = "dn_assist_" + secrets.token_urlsafe(32)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_assistente_token
           SET ativo = FALSE, revogado_em = NOW(), revogado_por = %s
         WHERE ativo = TRUE
        """,
        (id_usuario,),
    )
    cur.execute(
        """
        INSERT INTO tbl_assistente_token (token_hash, token_hint, nome, criado_por)
        VALUES (%s, %s, %s, %s)
        RETURNING id, token_hint, nome, criado_em
        """,
        (_hash_token(token), _hint(token), (nome or "Assistente")[:80], id_usuario),
    )
    r = cur.fetchone()
    cfg = {
        "id": int(r[0]),
        "token_hint": r[1],
        "nome": r[2],
        "ativo": True,
        "criado_em": r[3].isoformat() if r[3] else None,
    }
    return cfg, token


def revogar_token(conn, *, id_usuario: int | None) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tbl_assistente_token
           SET ativo = FALSE, revogado_em = NOW(), revogado_por = %s
         WHERE ativo = TRUE
        """,
        (id_usuario,),
    )
    return status_token(conn)


def _eh_fornecedor(cur, id_tenant: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_tenant
         WHERE id = %s AND tipo_negocio IN ('fornecedor', 'hibrido')
        """,
        (int(id_tenant),),
    )
    return bool(cur.fetchone())


def eh_indicado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT 1 FROM tbl_comissao_indicacao WHERE id_tenant_indicado = %s LIMIT 1",
        (int(id_tenant),),
    )
    return bool(cur.fetchone())


def _indicado_por_nome(cur, id_tenant: int) -> str:
    cur.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(tp.nome_fantasia), ''), NULLIF(TRIM(tp.nome), ''), '')
          FROM tbl_comissao_indicacao i
          JOIN tbl_tenant tp ON tp.id = i.id_tenant_pai
         WHERE i.id_tenant_indicado = %s
         LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return (row[0] or "").strip() if row else ""


def _ultimo_acesso_dono(cur, id_tenant: int):
    cur.execute(
        """
        SELECT ut.ultimo_acesso_em
          FROM tbl_usuario_tenant ut
          JOIN tbl_perfil pf ON pf.id = ut.id_perfil
         WHERE ut.id_tenant = %s AND LOWER(COALESCE(pf.codigo, '')) = 'dono'
         ORDER BY ut.ativo DESC NULLS LAST, ut.ultimo_acesso_em DESC NULLS LAST
         LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return row[0].isoformat() if row and row[0] else None


def _contato_dono(cur, id_tenant: int) -> dict[str, str]:
    from sistema.planos.fornecedor_fundador import contato_whatsapp_dono

    cur.execute(
        """
        SELECT u.email
          FROM tbl_usuario_tenant ut
          JOIN tbl_usuario u ON u.id = ut.id_usuario
          JOIN tbl_perfil pf ON pf.id = ut.id_perfil
         WHERE ut.id_tenant = %s AND LOWER(COALESCE(pf.codigo, '')) = 'dono'
         ORDER BY ut.ativo DESC NULLS LAST, ut.id
         LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return {
        "email": (row[0] or "").strip() if row else "",
        "whatsapp": contato_whatsapp_dono(cur, id_tenant),
    }


def _resumo_numeros(cur, id_tenant: int) -> dict[str, Any]:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT
          (SELECT COUNT(*)::int FROM tbl_produto p WHERE p.id_tenant = %s AND COALESCE(p.publicado, FALSE) = TRUE),
          (SELECT COUNT(*)::int FROM tbl_produto p WHERE p.id_tenant = %s),
          (SELECT COUNT(*)::int FROM tbl_pedido ped
            WHERE ped.id_tenant_fornecedor = %s
              AND ped.criado_em >= NOW() - INTERVAL '30 days'
              AND COALESCE(ped.{st}, '') NOT IN ('rascunho', 'cancelado')),
          (SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor v
            WHERE v.id_tenant_fornecedor = %s AND v.status = 'ativo'),
          (SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor v
            WHERE v.id_tenant_fornecedor = %s AND v.status = 'aguardando')
        """.format(st=col_st),
        (tid, tid, tid, tid, tid),
    )
    r = cur.fetchone() or (0, 0, 0, 0, 0)
    atrasados = _contar_atrasados(cur, tid)
    return {
        "produtos_publicados": int(r[0] or 0),
        "produtos_total": int(r[1] or 0),
        "pedidos_30d": int(r[2] or 0),
        "pedidos_atrasados": atrasados,
        "vendedores_conectados": int(r[3] or 0),
        "vendedores_aguardando": int(r[4] or 0),
    }


def _contar_atrasados(cur, id_tenant: int) -> int:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    cur.execute(
        f"""
        SELECT COUNT(*)::int
          FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND COALESCE(ped.{col_st}, '') IN ('pago', 'em_expedicao', 'aguardando_confirmacao')
           AND ped.criado_em < NOW() - INTERVAL '48 hours'
           AND COALESCE(ped.{col_st}, '') NOT IN ('expedido', 'enviado', 'entregue', 'cancelado')
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def listar_fornecedores(
    cur,
    *,
    page: int = 1,
    per_page: int = 50,
    fundador: int | None = None,
    fase: str | None = None,
    indicado: int | None = None,
    desde: str | None = None,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 100))
    where = ["t.tipo_negocio IN ('fornecedor', 'hibrido')"]
    params: list[Any] = []
    if fundador == 1:
        where.append("COALESCE(t.eh_fornecedor_fundador, FALSE) = TRUE")
    elif fundador == 0:
        where.append("COALESCE(t.eh_fornecedor_fundador, FALSE) = FALSE")
    if fase:
        where.append("t.fornecedor_fase = %s")
        params.append(fase)
    if indicado == 1:
        where.append("EXISTS (SELECT 1 FROM tbl_comissao_indicacao i WHERE i.id_tenant_indicado = t.id)")
    elif indicado == 0:
        where.append("NOT EXISTS (SELECT 1 FROM tbl_comissao_indicacao i WHERE i.id_tenant_indicado = t.id)")
    if desde:
        where.append("t.criado_em >= %s::timestamptz")
        params.append(desde)
    wh = " AND ".join(where)
    cur.execute(f"SELECT COUNT(*)::int FROM tbl_tenant t WHERE {wh}", params)
    total = int((cur.fetchone() or (0,))[0] or 0)
    offset = (page - 1) * per_page
    cur.execute(
        f"""
        SELECT t.id, t.nome, t.documento, t.cidade, t.uf, t.criado_em, t.plano,
               COALESCE(t.eh_fornecedor_fundador, FALSE),
               COALESCE(t.fornecedor_fundador_ativo, FALSE),
               t.fornecedor_fundador_em, t.sistema_erp,
               t.fornecedor_fase, t.fornecedor_fase_em, t.fornecedor_triagem
          FROM tbl_tenant t
         WHERE {wh}
         ORDER BY t.criado_em DESC NULLS LAST, t.id DESC
         LIMIT %s OFFSET %s
        """,
        (*params, per_page, offset),
    )
    rows = cur.fetchall()
    itens = []
    for r in rows:
        tid = int(r[0])
        resumo = _resumo_numeros(cur, tid)
        prazo = prazo_ativacao_fundador(r[9], resumo["produtos_publicados"])
        uc = listar_contatos(cur, tid, limite=1)
        contato = None
        if uc:
            contato = {
                "data": uc[0].get("criado_em"),
                "canal": uc[0].get("canal"),
                "resumo": uc[0].get("resumo"),
            }
        dono = _contato_dono(cur, tid)
        tri = r[13] if isinstance(r[13], dict) else None
        itens.append(
            {
                "id": tid,
                "nome": r[1] or "",
                "documento": r[2] or "",
                "cidade": r[3] or "",
                "uf": r[4] or "",
                "criado_em": r[5].isoformat() if r[5] else None,
                "ultimo_acesso_em": _ultimo_acesso_dono(cur, tid),
                "plano": r[6] or "",
                "eh_fundador": bool(r[7]),
                "fundador_ativo": bool(r[8]),
                "fundador_em": r[9].isoformat() if r[9] else None,
                "prazo_ativacao": prazo.get("prazo_em"),
                "prazo_ativacao_cor": prazo.get("prazo_cor"),
                "sistema_erp": r[10] or "",
                "indicado_por": _indicado_por_nome(cur, tid) or None,
                "fase": r[11],
                "fase_em": r[12].isoformat() if r[12] else None,
                "fase_rotulo": FASE_ROTULO.get(r[11] or "", ""),
                "ultimo_contato": contato,
                "whatsapp": dono["whatsapp"],
                "email": dono["email"],
                "triagem": tri,
                "triagem_rotulo": triagem_rotulo(tri),
                "resumo": resumo,
            }
        )
    return {
        "itens": itens,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page) if total else 1,
    }


def _motivos_produto(cur, id_produto: int, row: tuple) -> list[str]:
    """row: sku, nome, preco, id_categoria, descricao, peso_bruto, altura, largura, profundidade, publicado."""
    motivos = []
    preco = row[2]
    if preco is None or float(preco or 0) <= 0:
        motivos.append("preço zerado" if preco is not None and float(preco or 0) == 0 else "sem preço")
    if not row[3]:
        motivos.append("sem categoria")
    desc = (row[4] or "").strip()
    if len(desc) < 10:
        motivos.append("sem descrição curta")
    if not row[5] or float(row[5] or 0) <= 0:
        motivos.append("sem peso/dimensões")
    elif not (row[6] and row[7] and row[8]):
        motivos.append("sem peso/dimensões")
    cur.execute(
        "SELECT 1 FROM tbl_produto_imagem WHERE id_produto = %s LIMIT 1",
        (int(id_produto),),
    )
    if not cur.fetchone():
        motivos.append("sem foto")
    cur.execute(
        """
        SELECT COALESCE(SUM(pe.quantidade), 0)
          FROM tbl_produto_estoque pe
         WHERE pe.id_produto = %s
        """,
        (int(id_produto),),
    )
    est = cur.fetchone()
    try:
        qtd = float(est[0] or 0) if est else 0
    except Exception:
        qtd = 0
    if qtd <= 0:
        # variantes?
        cur.execute(
            """
            SELECT COALESCE(SUM(ve.quantidade), 0)
              FROM tbl_produto_variante v
              JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
             WHERE v.id_produto = %s
            """,
            (int(id_produto),),
        )
        est2 = cur.fetchone()
        try:
            qtd2 = float(est2[0] or 0) if est2 else 0
        except Exception:
            qtd2 = 0
        if qtd2 <= 0:
            motivos.append("sem estoque")
    cur.execute(
        "SELECT COUNT(*)::int FROM tbl_produto_variante WHERE id_produto = %s",
        (int(id_produto),),
    )
    # se formato sugere variação e não há — best effort skip
    return motivos


def _fixar_produtos_incompletos(cur, id_tenant: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, sku, nome, preco, id_categoria, descricao,
               peso_bruto_kg, altura_cm, largura_cm, profundidade_cm, COALESCE(publicado, FALSE)
          FROM tbl_produto
         WHERE id_tenant = %s
         ORDER BY id DESC
         LIMIT 500
        """,
        (int(id_tenant),),
    )
    rows = cur.fetchall()
    incompletos = []
    contagem: dict[str, int] = {}
    for r in rows:
        motivos = _motivos_produto(cur, int(r[0]), r[1:])
        if not motivos:
            continue
        for m in motivos:
            contagem[m] = contagem.get(m, 0) + 1
        incompletos.append(
            {"id": int(r[0]), "sku": r[1] or "", "nome": r[2] or "", "motivos": motivos}
        )
    cur.execute(
        """
        SELECT COUNT(*)::int,
               COUNT(*) FILTER (WHERE COALESCE(publicado, FALSE))=TRUE,
               COUNT(*) FILTER (WHERE COALESCE(publicado, FALSE))=FALSE
          FROM tbl_produto WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    tot, pub, ina = cur.fetchone() or (0, 0, 0)
    return {
        "total": int(tot or 0),
        "publicados": int(pub or 0),
        "inativos": int(ina or 0),
        "incompletos": incompletos[:50],
        "incompletos_total": len(incompletos),
        "contagem_motivos": contagem,
    }


def detalhe_fornecedor(cur, id_tenant: int) -> dict[str, Any] | None:
    if not _eh_fornecedor(cur, id_tenant):
        return None
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT t.id, t.nome, t.documento, t.cidade, t.uf, t.criado_em, t.plano,
               COALESCE(t.eh_fornecedor_fundador, FALSE),
               COALESCE(t.fornecedor_fundador_ativo, FALSE),
               t.fornecedor_fundador_em, t.sistema_erp,
               t.fornecedor_fase, t.fornecedor_fase_em, t.fornecedor_triagem,
               t.ativo
          FROM tbl_tenant t WHERE t.id = %s
        """,
        (tid,),
    )
    r = cur.fetchone()
    if not r:
        return None
    resumo = _resumo_numeros(cur, tid)
    prazo = prazo_ativacao_fundador(r[9], resumo["produtos_publicados"])
    dono = _contato_dono(cur, tid)
    tri = r[13] if isinstance(r[13], dict) else None
    cur.execute(
        """
        SELECT u.nome, pf.codigo, pf.nome, ut.ultimo_acesso_em, COALESCE(u.ativo, TRUE), COALESCE(ut.ativo, TRUE)
          FROM tbl_usuario_tenant ut
          JOIN tbl_usuario u ON u.id = ut.id_usuario
          JOIN tbl_perfil pf ON pf.id = ut.id_perfil
         WHERE ut.id_tenant = %s
         ORDER BY ut.id
        """,
        (tid,),
    )
    usuarios = []
    for u in cur.fetchall():
        usuarios.append(
            {
                "nome": u[0] or "",
                "perfil": u[1] or "",
                "perfil_nome": u[2] or "",
                "ultimo_acesso_em": u[3].isoformat() if u[3] else None,
                "ativo": bool(u[4] and u[5]),
            }
        )
    produtos = _fixar_produtos_incompletos(cur, tid)
    pedidos = _bloco_pedidos(cur, tid)
    desempenho = _bloco_desempenho(cur, tid)
    rede = _bloco_rede(cur, tid)
    integracoes = _bloco_integracoes(cur, tid)
    contatos = listar_contatos(cur, tid, limite=200)
    return {
        "cadastro": {
            "id": tid,
            "nome": r[1] or "",
            "documento": r[2] or "",
            "cidade": r[3] or "",
            "uf": r[4] or "",
            "criado_em": r[5].isoformat() if r[5] else None,
            "ultimo_acesso_em": _ultimo_acesso_dono(cur, tid),
            "plano": r[6] or "",
            "ativo": bool(r[14]),
            "eh_fundador": bool(r[7]),
            "fundador_ativo": bool(r[8]),
            "fundador_em": r[9].isoformat() if r[9] else None,
            "prazo_ativacao": prazo,
            "sistema_erp": r[10] or "",
            "indicado_por": _indicado_por_nome(cur, tid) or None,
            "fase": r[11],
            "fase_em": r[12].isoformat() if r[12] else None,
            "whatsapp": dono["whatsapp"],
            "email": dono["email"],
            "triagem": tri,
            "triagem_rotulo": triagem_rotulo(tri),
            "usuarios": usuarios,
        },
        "produtos": produtos,
        "pedidos": pedidos,
        "desempenho": desempenho,
        "rede": rede,
        "integracoes": integracoes,
        "acompanhamento": {
            "fase": r[11],
            "fase_rotulo": FASE_ROTULO.get(r[11] or "", ""),
            "prazo": prazo,
            "contatos": contatos,
        },
        "resumo": resumo,
    }


def _bloco_pedidos(cur, id_tenant: int) -> dict[str, Any]:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    tid = int(id_tenant)

    def _por_status(dias: int) -> dict[str, int]:
        cur.execute(
            f"""
            SELECT COALESCE(ped.{col_st}, 'sem_status'), COUNT(*)::int
              FROM tbl_pedido ped
             WHERE ped.id_tenant_fornecedor = %s
               AND ped.criado_em >= NOW() - (%s || ' days')::interval
             GROUP BY 1
            """,
            (tid, str(dias)),
        )
        return {str(a or "sem_status"): int(b or 0) for a, b in cur.fetchall()}

    atrasados = []
    try:
        cur.execute(
            f"""
            SELECT ped.id, ped.numero, ped.criado_em, COALESCE(ped.{col_st}, ''),
                   COALESCE(ped.total_centavos, 0)
              FROM tbl_pedido ped
             WHERE ped.id_tenant_fornecedor = %s
               AND COALESCE(ped.{col_st}, '') IN ('pago', 'em_expedicao', 'aguardando_confirmacao')
               AND ped.criado_em < NOW() - INTERVAL '48 hours'
             ORDER BY ped.criado_em ASC
             LIMIT 50
            """,
            (tid,),
        )
        now = datetime.now(timezone.utc)
        for row in cur.fetchall():
            criado = row[2]
            if criado and criado.tzinfo is None:
                criado = criado.replace(tzinfo=timezone.utc)
            horas = int((now - criado).total_seconds() // 3600) if criado else 0
            atrasados.append(
                {
                    "id": int(row[0]),
                    "numero": row[1] or "",
                    "criado_em": row[2].isoformat() if row[2] else None,
                    "status": row[3] or "",
                    "horas_em_atraso": max(0, horas - 48),
                    "valor_centavos": int(row[4] or 0),
                    "cidade": "",
                    "uf": "",
                }
            )
    except Exception:
        atrasados = []
        try:
            cur.connection.rollback()
        except Exception:
            pass

    cur.execute(
        f"""
        SELECT COUNT(*)::int FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND ped.criado_em >= NOW() - INTERVAL '30 days'
           AND COALESCE(ped.{col_st}, '') = 'cancelado'
        """,
        (tid,),
    )
    canc = int((cur.fetchone() or (0,))[0] or 0)
    return {
        "por_status_30d": _por_status(30),
        "por_status_90d": _por_status(90),
        "atrasados": atrasados,
        "cancelados_30d": canc,
        "devolvidos_30d": 0,
    }


def _bloco_desempenho(cur, id_tenant: int) -> dict[str, Any]:
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    tid = int(id_tenant)

    def _agg(dias: int) -> dict[str, Any]:
        cur.execute(
            f"""
            SELECT COUNT(*)::int,
                   COALESCE(SUM(COALESCE(ped.total_centavos, 0)), 0)::bigint
              FROM tbl_pedido ped
             WHERE ped.id_tenant_fornecedor = %s
               AND ped.criado_em >= NOW() - (%s || ' days')::interval
               AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
            """,
            (tid, str(dias)),
        )
        n, fat = cur.fetchone() or (0, 0)
        n = int(n or 0)
        fat = int(fat or 0)
        return {
            "pedidos": n,
            "faturamento_centavos": fat,
            "ticket_medio_centavos": int(fat / n) if n else 0,
        }

    a30 = _agg(30)
    a90 = _agg(90)
    cur.execute(
        f"""
        SELECT MAX(ped.criado_em) FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
        """,
        (tid,),
    )
    ult = cur.fetchone()
    return {
        "30d": a30,
        "90d": a90,
        "taxa_cancelamento_30d": None,
        "tempo_medio_pago_expedido_horas": None,
        "ultimo_pedido_em": ult[0].isoformat() if ult and ult[0] else None,
        "top_produtos_30d": [],
    }


def _bloco_rede(cur, id_tenant: int) -> dict[str, Any]:
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'ativo')::int,
          COUNT(*) FILTER (WHERE status = 'aguardando')::int,
          MIN(criado_em) FILTER (WHERE status = 'aguardando')
          FROM tbl_vinculo_vendedor_fornecedor
         WHERE id_tenant_fornecedor = %s
        """,
        (tid,),
    )
    row = cur.fetchone() or (0, 0, None)
    dias_espera = None
    if row[2]:
        agora = datetime.now(timezone.utc)
        cri = row[2]
        if cri.tzinfo is None:
            cri = cri.replace(tzinfo=timezone.utc)
        dias_espera = max(0, int((agora - cri).total_seconds() // 86400))
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    cur.execute(
        f"""
        SELECT COUNT(DISTINCT ped.id_tenant_vendedor)::int
          FROM tbl_pedido ped
         WHERE ped.id_tenant_fornecedor = %s
           AND ped.id_tenant_vendedor IS NOT NULL
           AND ped.criado_em >= NOW() - INTERVAL '30 days'
           AND COALESCE(ped.{col_st}, '') NOT IN ('rascunho', 'cancelado')
        """,
        (tid,),
    )
    com_ped = int((cur.fetchone() or (0,))[0] or 0)
    return {
        "vendedores_conectados": int(row[0] or 0),
        "vendedores_aguardando": int(row[1] or 0),
        "aguardando_mais_antigo_dias": dias_espera,
        "vendedores_com_pedido_30d": com_ped,
    }


def _bloco_integracoes(cur, id_tenant: int) -> list[dict[str, Any]]:
    out = []
    tid = int(id_tenant)
    for tabela, nome in (
        ("tbl_integracao_bling", "Bling"),
        ("tbl_integracao_olist", "Tiny/Olist"),
    ):
        try:
            cur.execute(
                f"""
                SELECT ativo, ultima_sync_em, ultima_mensagem
                  FROM {tabela}
                 WHERE id_tenant = %s
                 LIMIT 1
                """,
                (tid,),
            )
            row = cur.fetchone()
            if row:
                out.append(
                    {
                        "nome": nome,
                        "ligado": bool(row[0]),
                        "ultima_sincronizacao": row[1].isoformat() if row[1] else None,
                        "ultimo_erro": (row[2] or "")[:200] if row[2] else "",
                        "fila_imagens_pendentes": 0,
                    }
                )
        except Exception:
            try:
                cur.connection.rollback()
            except Exception:
                pass
    return out


def listar_produtos_pagina(
    cur, id_tenant: int, *, status: str | None = None, page: int = 1, per_page: int = 50
) -> dict[str, Any]:
    if not _eh_fornecedor(cur, id_tenant):
        raise ValueError("Fornecedor não encontrado.")
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 100))
    where = ["p.id_tenant = %s"]
    params: list[Any] = [int(id_tenant)]
    st = (status or "").strip().lower()
    if st == "publicado":
        where.append("COALESCE(p.publicado, FALSE) = TRUE")
    elif st == "inativo":
        where.append("COALESCE(p.publicado, FALSE) = FALSE")
    wh = " AND ".join(where)
    cur.execute(f"SELECT COUNT(*)::int FROM tbl_produto p WHERE {wh}", params)
    total = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute(
        f"""
        SELECT p.id, p.sku, p.nome, p.preco, COALESCE(p.publicado, FALSE), p.atualizado_em,
               p.id_categoria, p.descricao, p.peso_bruto_kg, p.altura_cm, p.largura_cm, p.profundidade_cm
          FROM tbl_produto p
         WHERE {wh}
         ORDER BY p.id DESC
         LIMIT %s OFFSET %s
        """,
        (*params, per_page, (page - 1) * per_page),
    )
    itens = []
    for r in cur.fetchall():
        motivos = _motivos_produto(cur, int(r[0]), (r[1], r[2], r[3], r[6], r[7], r[8], r[9], r[10], r[11], r[4]))
        if st == "incompleto" and not motivos:
            continue
        itens.append(
            {
                "id": int(r[0]),
                "sku": r[1] or "",
                "nome": r[2] or "",
                "preco": float(r[3] or 0),
                "estoque": None,
                "publicado": bool(r[4]),
                "motivos": motivos,
                "atualizado_em": r[5].isoformat() if r[5] else None,
            }
        )
    if st == "incompleto":
        # re-filter path already handled; recount roughly
        pass
    return {
        "itens": itens,
        "page": page,
        "per_page": per_page,
        "total": total if st != "incompleto" else len(itens),
    }


def listar_pedidos_pagina(
    cur,
    id_tenant: int,
    *,
    status: str | None = None,
    atrasados: int = 0,
    desde: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    if not _eh_fornecedor(cur, id_tenant):
        raise ValueError("Fornecedor não encontrado.")
    from core.pedidos.servico import col_status_vendedor

    col_st = col_status_vendedor(cur)
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 100))
    where = ["ped.id_tenant_fornecedor = %s"]
    params: list[Any] = [int(id_tenant)]
    if status:
        where.append(f"COALESCE(ped.{col_st}, '') = %s")
        params.append(status)
    if atrasados:
        where.append(f"COALESCE(ped.{col_st}, '') IN ('pago', 'em_expedicao', 'aguardando_confirmacao')")
        where.append("ped.criado_em < NOW() - INTERVAL '48 hours'")
    if desde:
        where.append("ped.criado_em >= %s::timestamptz")
        params.append(desde)
    wh = " AND ".join(where)
    try:
        cur.execute(f"SELECT COUNT(*)::int FROM tbl_pedido ped WHERE {wh}", params)
        total = int((cur.fetchone() or (0,))[0] or 0)
        cur.execute(
            f"""
            SELECT ped.id, ped.numero, ped.criado_em, COALESCE(ped.{col_st}, ''),
                   COALESCE(ped.total_centavos, 0),
                   COALESCE(ped.cidade_entrega, ''), COALESCE(ped.uf_entrega, '')
              FROM tbl_pedido ped
             WHERE {wh}
             ORDER BY ped.criado_em DESC
             LIMIT %s OFFSET %s
            """,
            (*params, per_page, (page - 1) * per_page),
        )
        itens = []
        now = datetime.now(timezone.utc)
        for row in cur.fetchall():
            criado = row[2]
            if criado and criado.tzinfo is None:
                criado = criado.replace(tzinfo=timezone.utc)
            horas = int((now - criado).total_seconds() // 3600) if criado else 0
            itens.append(
                {
                    "id": int(row[0]),
                    "numero": row[1] or "",
                    "criado_em": row[2].isoformat() if row[2] else None,
                    "status": row[3] or "",
                    "horas_em_atraso": max(0, horas - 48) if atrasados else None,
                    "valor_centavos": int(row[4] or 0),
                    "cidade": row[5] or "",
                    "uf": row[6] or "",
                }
            )
        return {"itens": itens, "page": page, "per_page": per_page, "total": total}
    except Exception as e:
        raise ValueError("Falha ao listar pedidos.") from e


def painel_resumo(cur) -> dict[str, Any]:
    from sistema.planos.fornecedor_fundador import status_programa

    cur.execute(
        """
        SELECT COALESCE(fornecedor_fase, 'sem_fase'), COUNT(*)::int
          FROM tbl_tenant
         WHERE tipo_negocio IN ('fornecedor', 'hibrido')
         GROUP BY 1
        """
    )
    por_fase = {str(a): int(b or 0) for a, b in cur.fetchall()}
    st = status_programa(cur)
    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_tenant t
         WHERE t.tipo_negocio IN ('fornecedor', 'hibrido')
           AND COALESCE(t.eh_fornecedor_fundador, FALSE) = TRUE
           AND COALESCE(t.fornecedor_fundador_ativo, FALSE) = TRUE
           AND (SELECT COUNT(*) FROM tbl_produto p
                 WHERE p.id_tenant = t.id AND COALESCE(p.publicado, FALSE) = TRUE) < 20
        """
    )
    cat_baixo = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute(
        """
        SELECT COUNT(DISTINCT v.id_tenant_fornecedor)::int
          FROM tbl_vinculo_vendedor_fornecedor v
          JOIN tbl_tenant t ON t.id = v.id_tenant_fornecedor
         WHERE v.status = 'aguardando'
           AND t.tipo_negocio IN ('fornecedor', 'hibrido')
        """
    )
    aguard = int((cur.fetchone() or (0,))[0] or 0)
    return {
        "por_fase": por_fase,
        "fundadores": {
            "ativos": st.get("vagas_usadas"),
            "vagas_max": st.get("vagas_max"),
            "vagas_restantes": st.get("vagas_restantes"),
        },
        "fornecedores_catalogo_lt_20": cat_baixo,
        "fornecedores_com_vendedores_aguardando": aguard,
        "pedidos_atrasados_total": None,
    }


def post_contato(cur, id_tenant: int, body: dict, *, aprovado_por: str | None = None) -> dict:
    if not _eh_fornecedor(cur, id_tenant):
        raise ValueError("Fornecedor não encontrado.")
    if eh_indicado(cur, id_tenant):
        raise PermissionError("Fornecedor indicado por parceiro: contato não permitido pelo assistente")
    autor = "Assistente"
    if aprovado_por:
        autor = f"Assistente (aprovado por {str(aprovado_por).strip()[:80]})"
    return registrar_contato(
        cur,
        int(id_tenant),
        canal=body.get("canal") or "whatsapp",
        direcao=body.get("direcao") or "enviado",
        resumo=body.get("resumo") or "",
        fase_apos=body.get("fase_apos"),
        autor=autor,
        aplicar_fase=True,
    )


def post_fase(cur, id_tenant: int, body: dict, *, aprovado_por: str | None = None) -> dict:
    if not _eh_fornecedor(cur, id_tenant):
        raise ValueError("Fornecedor não encontrado.")
    if eh_indicado(cur, id_tenant):
        raise PermissionError("Fornecedor indicado por parceiro: contato não permitido pelo assistente")
    autor = "Assistente"
    if aprovado_por:
        autor = f"Assistente (aprovado por {str(aprovado_por).strip()[:80]})"
    return definir_fase(
        cur,
        int(id_tenant),
        body.get("fase"),
        autor=autor,
        motivo=(body.get("motivo") or "").strip() or None,
        registrar_historico=True,
    )
