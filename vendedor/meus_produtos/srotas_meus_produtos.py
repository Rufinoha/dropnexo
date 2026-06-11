from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import (
    Var_ConectarBanco,
    agora_utc,
    exigir_modulo,
    exigir_permissao,
    login_obrigatorio,
    url_imagem_produto,
    usuario_tem_permissao,
)
from srotas_plataforma import MODULO_VENDEDOR
from fornecedor.catalogo.srotas_catalogo import (
    estoque_kit_componentes,
    preco_sugerido_kit,
    variante_rede_valida,
)

_MOD_DIR = Path(__file__).resolve().parent

vd_meus_produtos_bp = Blueprint(
    "vd_meus_produtos",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/meus_produtos",
)


def init_app(app):
    app.register_blueprint(vd_meus_produtos_bp)


def _id_tenant_sessao() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _pode_editar_favoritos():
    return session.get("eh_desenvolvedor") or usuario_tem_permissao("produtos.editar")


def _resolver_id_variante(cur, id_tenant: int, id_variante: int = 0, id_produto: int = 0) -> int | None:
    if id_variante and variante_rede_valida(cur, id_variante, id_tenant):
        return id_variante
    if id_produto:
        cur.execute(
            """
            SELECT v.id FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE p.id = %s AND p.id_tenant <> %s AND p.publicado = TRUE AND v.ativo = TRUE
            ORDER BY CASE WHEN v.id = p.id_variante_padrao THEN 0 ELSE 1 END, v.id
            LIMIT 1
            """,
            (id_produto, id_tenant),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None
    return None


@vd_meus_produtos_bp.get("/meus-produtos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="produtos.ver")
def pagina():
    return render_template("frm_meus_produtos.html", nav_ativo="produtos")


@vd_meus_produtos_bp.get("/meus-produtos/dados")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def dados():
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = max(1, min(int(request.args.get("porPagina", 20)), 100))
    busca = (request.args.get("busca") or "").strip()
    offset = (pagina - 1) * por_pagina

    where = ["f.id_tenant = %s"]
    params: list = [id_tenant]
    if busca:
        where.append("(p.nome ILIKE %s OR p.sku ILIKE %s OR t.nome ILIKE %s)")
        like = f"%{busca}%"
        params.extend([like, like, like])
    where_sql = " AND ".join(where)

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM tbl_produto_favorito f
            INNER JOIN tbl_produto p ON p.id = f.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            WHERE {where_sql}
            """,
            params,
        )
        total = int(cur.fetchone()[0] or 0)
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

        cur.execute(
            f"""
            SELECT v.id, v.sku, v.nome_exibicao, p.nome, v.preco, v.preco_promocional, v.imagem_url,
                   p.unidade, c.nome AS categoria, COALESCE(e.quantidade, 0),
                   t.nome AS fornecedor_nome, f.criado_em, p.formato
            FROM tbl_produto_favorito f
            INNER JOIN tbl_produto_variante v ON v.id = COALESCE(f.id_variante, (
                SELECT id FROM tbl_produto_variante WHERE id_produto = f.id_produto ORDER BY id LIMIT 1
            ))
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE {where_sql}
            ORDER BY f.criado_em DESC
            LIMIT %s OFFSET %s
            """,
            params + [por_pagina, offset],
        )
        dados = [
            {
                "id_variante": r[0],
                "id": r[0],
                "sku": r[1] or "",
                "nome": f"{r[3]} — {r[2]}" if r[2] and r[2] != r[3] else (r[3] or r[2]),
                "preco": float(r[4] or 0),
                "preco_promocional": float(r[5]) if r[5] is not None else None,
                "imagem_url": url_imagem_produto(r[6]),
                "unidade": r[7] or "UN",
                "categoria": r[8] or "",
                "estoque": int(r[9] or 0),
                "fornecedor_nome": r[10],
                "salvo_em": r[11].isoformat() if r[11] else None,
                "formato": r[12],
            }
            for r in cur.fetchall()
        ]
        return jsonify(
            success=True,
            dados=dados,
            total=total,
            total_paginas=total_paginas,
            pagina=pagina,
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/ids")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def ids_favoritos():
    """IDs de produtos já salvos pelo tenant (para marcar na rede)."""
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(id_variante, id_produto) FROM tbl_produto_favorito WHERE id_tenant = %s",
            (id_tenant,),
        )
        ids = [r[0] for r in cur.fetchall()]
        return jsonify(success=True, ids=ids)
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/favoritar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def favoritar():
    if not _pode_editar_favoritos():
        return jsonify(success=False, message="Sem permissão para salvar produtos."), 403

    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    id_variante = int(body.get("id_variante") or body.get("id") or 0)
    id_produto = int(body.get("id_produto") or 0)
    if not id_tenant:
        return jsonify(success=False, message="Dados inválidos."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        vid = _resolver_id_variante(cur, id_tenant, id_variante, id_produto)
        if not vid:
            return jsonify(success=False, message="Produto indisponível na rede."), 404
        cur.execute("SELECT id_produto FROM tbl_produto_variante WHERE id = %s", (vid,))
        pid_row = cur.fetchone()
        id_produto = pid_row[0] if pid_row else id_produto

        cur.execute(
            """
            INSERT INTO tbl_produto_favorito (id_tenant, id_produto, id_variante)
            VALUES (%s, %s, %s)
            ON CONFLICT (id_tenant, id_produto) DO UPDATE SET id_variante = EXCLUDED.id_variante
            """,
            (id_tenant, id_produto, vid),
        )
        conn.commit()
        return jsonify(success=True, message="Produto salvo em Meus produtos.")
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/desfavoritar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def desfavoritar():
    if not _pode_editar_favoritos():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = _id_tenant_sessao()
    body = request.get_json(silent=True) or {}
    id_variante = int(body.get("id_variante") or body.get("id") or 0)
    id_produto = int(body.get("id_produto") or 0)
    if not id_tenant:
        return jsonify(success=False, message="Dados inválidos."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_variante:
            cur.execute(
                "DELETE FROM tbl_produto_favorito WHERE id_tenant = %s AND id_variante = %s",
                (id_tenant, id_variante),
            )
        elif id_produto:
            cur.execute(
                "DELETE FROM tbl_produto_favorito WHERE id_tenant = %s AND id_produto = %s",
                (id_tenant, id_produto),
            )
        else:
            return jsonify(success=False, message="Dados inválidos."), 400
        conn.commit()
        return jsonify(success=True, message="Produto removido de Meus produtos.")
    finally:
        conn.close()


def _exigir_edicao():
    from global_utils import usuario_tem_permissao

    if session.get("eh_desenvolvedor") or usuario_tem_permissao("produtos.editar"):
        return None
    return jsonify(success=False, message="Sem permissão."), 403


def _id_tenant():
    tid = session.get("id_tenant")
    return int(tid) if tid else None


@vd_meus_produtos_bp.get("/meus-produtos/kits/incluir")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_incluir_pagina():
    return render_template("frm_kit_vendedor_apoio.html")


@vd_meus_produtos_bp.get("/meus-produtos/kits/editar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_editar_pagina():
    return render_template("frm_kit_vendedor_apoio.html")


@vd_meus_produtos_bp.get("/meus-produtos/kits/dados")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def kits_lista():
    id_tenant = _id_tenant()
    busca = (request.args.get("busca") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["k.id_tenant = %s"]
        params: list = [id_tenant]
        if busca:
            where.append("k.nome ILIKE %s")
            params.append(f"%{busca}%")
        cur.execute(
            f"""
            SELECT k.id, k.nome, k.preco_venda, k.usar_preco_sugerido, k.ativo,
                   (SELECT COUNT(*) FROM tbl_kit_vendedor_item i WHERE i.id_kit = k.id)
            FROM tbl_kit_vendedor k
            WHERE {" AND ".join(where)}
            ORDER BY k.atualizado_em DESC
            """,
            params,
        )
        kits = [
            {
                "id": r[0],
                "nome": r[1],
                "preco_venda": float(r[2] or 0),
                "usar_preco_sugerido": bool(r[3]),
                "ativo": bool(r[4]),
                "qtd_itens": int(r[5] or 0),
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, kits=kits)
    finally:
        conn.close()


@vd_meus_produtos_bp.get("/meus-produtos/rede-opcoes")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def rede_opcoes():
    """Produtos/variantes da rede para montar kit (favoritos + busca)."""
    id_tenant = _id_tenant()
    busca = (request.args.get("busca") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = [
            "p.id_tenant <> %s",
            "p.publicado = TRUE",
            "p.ativo = TRUE",
            "v.ativo = TRUE",
        ]
        params: list = [id_tenant]
        if busca:
            where.append(
                "(p.nome ILIKE %s OR v.sku ILIKE %s OR v.nome_exibicao ILIKE %s OR t.nome ILIKE %s)"
            )
            like = f"%{busca}%"
            params.extend([like, like, like, like])
        cur.execute(
            f"""
            SELECT v.id, v.sku, v.nome_exibicao, v.preco, v.preco_promocional, v.imagem_url,
                   p.nome AS produto_nome, t.nome AS fornecedor_nome,
                   COALESCE(e.quantidade, 0), p.formato
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE {" AND ".join(where)}
            ORDER BY t.nome, p.nome, v.nome_exibicao
            LIMIT 80
            """,
            params,
        )
        itens = [
            {
                "id_variante": r[0],
                "sku": r[1] or "",
                "nome_exibicao": r[2],
                "preco": float(r[3] or 0),
                "preco_promocional": float(r[4]) if r[4] is not None else None,
                "imagem_url": url_imagem_produto(r[5]),
                "produto_nome": r[6],
                "fornecedor_nome": r[7],
                "estoque": int(r[8] or 0),
                "formato": r[9],
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/kits/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.ver")
def kit_apoio():
    kid = int((request.get_json(silent=True) or {}).get("id") or 0)
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, descricao, preco_venda, usar_preco_sugerido, ativo FROM tbl_kit_vendedor WHERE id = %s AND id_tenant = %s",
            (kid, id_tenant),
        )
        k = cur.fetchone()
        if not k:
            return jsonify(success=False, message="Kit não encontrado."), 404
        cur.execute(
            """
            SELECT i.id, i.id_variante, i.quantidade, i.ordem,
                   v.sku, v.nome_exibicao, v.preco, v.imagem_url,
                   p.nome, t.nome, COALESCE(e.quantidade, 0)
            FROM tbl_kit_vendedor_item i
            JOIN tbl_produto_variante v ON v.id = i.id_variante
            JOIN tbl_produto p ON p.id = v.id_produto
            JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE i.id_kit = %s
            ORDER BY i.ordem, i.id
            """,
            (kid,),
        )
        itens = [
            {
                "id": r[0],
                "id_variante": r[1],
                "quantidade": r[2],
                "sku": r[4] or "",
                "nome_exibicao": r[5],
                "preco": float(r[6] or 0),
                "imagem_url": url_imagem_produto(r[7]),
                "produto_nome": r[8],
                "fornecedor_nome": r[9],
                "estoque": int(r[10] or 0),
            }
            for r in cur.fetchall()
        ]
        comp = [(x["id_variante"], x["quantidade"]) for x in itens]
        sugerido = float(preco_sugerido_kit(cur, comp))
        estoque_kit = estoque_kit_componentes(cur, comp)
        return jsonify(
            success=True,
            dados={
                "id": k[0],
                "nome": k[1],
                "descricao": k[2] or "",
                "preco_venda": float(k[3] or 0),
                "usar_preco_sugerido": bool(k[4]),
                "ativo": bool(k[5]),
                "preco_sugerido": sugerido,
                "estoque_disponivel": estoque_kit,
                "itens": itens,
            },
        )
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/kits/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_salvar():
    if (resp := _exigir_edicao()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome do kit."), 400
    itens_in = body.get("itens") or []
    if not itens_in:
        return jsonify(success=False, message="Adicione ao menos um item ao kit."), 400

    id_tenant = _id_tenant()
    usar_sug = str(body.get("usar_preco_sugerido", "true")).lower() in ("1", "true", "t", "yes", "sim")
    preco_venda = Decimal(str(body.get("preco_venda") or 0))

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        comp: list[tuple[int, int]] = []
        for raw in itens_in:
            vid = int(raw.get("id_variante") or 0)
            qtd = max(1, int(raw.get("quantidade") or 1))
            if not variante_rede_valida(cur, vid, id_tenant):
                return jsonify(success=False, message=f"Variante {vid} indisponível na rede."), 400
            comp.append((vid, qtd))

        if usar_sug:
            preco_venda = preco_sugerido_kit(cur, comp)

        kid = body.get("id")
        if kid:
            cur.execute(
                """
                UPDATE tbl_kit_vendedor SET nome=%s, descricao=%s, preco_venda=%s,
                    usar_preco_sugerido=%s, ativo=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant=%s RETURNING id
                """,
                (
                    nome,
                    (body.get("descricao") or "").strip(),
                    preco_venda,
                    usar_sug,
                    str(body.get("ativo", "true")).lower() in ("1", "true", "t", "yes", "sim"),
                    agora_utc(),
                    kid,
                    id_tenant,
                ),
            )
            if not cur.fetchone():
                return jsonify(success=False, message="Kit não encontrado."), 404
            kit_id = int(kid)
            cur.execute("DELETE FROM tbl_kit_vendedor_item WHERE id_kit = %s", (kit_id,))
        else:
            cur.execute(
                """
                INSERT INTO tbl_kit_vendedor (id_tenant, nome, descricao, preco_venda, usar_preco_sugerido, ativo, atualizado_em)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    id_tenant,
                    nome,
                    (body.get("descricao") or "").strip(),
                    preco_venda,
                    usar_sug,
                    str(body.get("ativo", "true")).lower() in ("1", "true", "t", "yes", "sim"),
                    agora_utc(),
                ),
            )
            kit_id = cur.fetchone()[0]

        for idx, (vid, qtd) in enumerate(comp):
            cur.execute(
                """
                INSERT INTO tbl_kit_vendedor_item (id_kit, id_variante, quantidade, ordem)
                VALUES (%s, %s, %s, %s)
                """,
                (kit_id, vid, qtd, idx),
            )
        conn.commit()
        return jsonify(success=True, message="Kit salvo.", id=kit_id)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@vd_meus_produtos_bp.post("/meus-produtos/kits/delete")
@login_obrigatorio()
@exigir_permissao(codigo="produtos.editar")
def kit_delete():
    if (resp := _exigir_edicao()) is not None:
        return resp
    kid = int((request.get_json(silent=True) or {}).get("id") or 0)
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_kit_vendedor WHERE id = %s AND id_tenant = %s", (kid, id_tenant))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(success=False, message="Kit não encontrado."), 404
        return jsonify(success=True, message="Kit excluído.")
    finally:
        conn.close()
