# Fornecedores DropNexo — vendedor busca produtos publicados na rede
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, login_obrigatorio, exigir_permissao, url_imagem_produto
from srotas_plataforma import MODULO_VENDEDOR

_MOD_DIR = Path(__file__).resolve().parent

vd_fornecedores_bp = Blueprint(
    "vd_fornecedores",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/fornecedores",
)



def _id_tenant_sessao() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _where_rede(id_tenant: int, busca: str, id_fornecedor: str, id_categoria: str) -> tuple[str, list]:
    where = [
        "p.id_tenant <> %s",
        "p.publicado = TRUE",
        "p.ativo = TRUE",
        "v.ativo = TRUE",
        "t.ativo = TRUE",
        "t.tipo_negocio IN ('fornecedor', 'hibrido')",
    ]
    params: list = [id_tenant]

    if busca:
        where.append(
            "(p.nome ILIKE %s OR v.sku ILIKE %s OR v.nome_exibicao ILIKE %s OR t.nome ILIKE %s)"
        )
        like = f"%{busca}%"
        params.extend([like, like, like, like])
    if id_fornecedor:
        where.append("p.id_tenant = %s")
        params.append(int(id_fornecedor))
    if id_categoria:
        where.append("p.id_categoria = %s")
        params.append(int(id_categoria))

    return " AND ".join(where), params


@vd_fornecedores_bp.get("/fornecedores")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def pagina():
    return render_template("frm_fornecedores.html", nav_ativo="fornecedores")


@vd_fornecedores_bp.get("/fornecedores/combos")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def combos():
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.id, t.nome, COUNT(p.id)::int
            FROM tbl_tenant t
            INNER JOIN tbl_produto p ON p.id_tenant = t.id
                AND p.publicado = TRUE AND p.ativo = TRUE
            WHERE t.id <> %s
              AND t.ativo = TRUE
              AND t.tipo_negocio IN ('fornecedor', 'hibrido')
            GROUP BY t.id, t.nome
            ORDER BY t.nome
            """,
            (id_tenant,),
        )
        fornecedores = [{"id": r[0], "nome": r[1], "qtd_produtos": r[2]} for r in cur.fetchall()]
        return jsonify(success=True, fornecedores=fornecedores)
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/categorias")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def categorias():
    id_tenant = _id_tenant_sessao()
    id_fornecedor = (request.args.get("id_fornecedor") or "").strip()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    if not id_fornecedor:
        return jsonify(success=True, categorias=[])

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT c.id, c.nome
            FROM tbl_categoria c
            INNER JOIN tbl_produto p ON p.id_categoria = c.id
                AND p.id_tenant = c.id_tenant
                AND p.publicado = TRUE AND p.ativo = TRUE
            WHERE c.id_tenant = %s AND c.ativo = TRUE
            ORDER BY c.nome
            """,
            (int(id_fornecedor),),
        )
        cats = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(success=True, categorias=cats)
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/dados")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def dados():
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = max(1, min(int(request.args.get("porPagina", 20)), 100))
    busca = (request.args.get("busca") or "").strip()
    id_fornecedor = (request.args.get("id_fornecedor") or "").strip()
    id_categoria = (request.args.get("id_categoria") or "").strip()
    offset = (pagina - 1) * por_pagina

    where_sql, params = _where_rede(id_tenant, busca, id_fornecedor, id_categoria)

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            WHERE {where_sql}
            """,
            params,
        )
        total = int(cur.fetchone()[0] or 0)
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

        cur.execute(
            f"""
            SELECT v.id, v.sku, v.nome_exibicao, p.nome, v.preco, v.preco_promocional,
                   COALESCE(v.imagem_url, p.imagem_url), p.unidade,
                   c.nome AS categoria, COALESCE(e.quantidade, 0),
                   t.id AS id_fornecedor, t.nome AS fornecedor_nome, t.slug AS fornecedor_slug,
                   t.cidade, t.uf, p.formato, p.id AS id_produto
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE {where_sql}
            ORDER BY t.nome, p.nome, v.nome_exibicao
            LIMIT %s OFFSET %s
            """,
            params + [por_pagina, offset],
        )
        dados = [
            {
                "id": r[0],
                "id_variante": r[0],
                "id_produto": r[16],
                "sku": r[1] or "",
                "nome": f"{r[3]} — {r[2]}" if r[2] and r[2] != r[3] else (r[3] or r[2]),
                "preco": float(r[4] or 0),
                "preco_promocional": float(r[5]) if r[5] is not None else None,
                "imagem_url": url_imagem_produto(r[6]),
                "unidade": r[7] or "UN",
                "categoria": r[8] or "",
                "estoque": int(r[9] or 0),
                "id_fornecedor": r[10],
                "fornecedor_nome": r[11],
                "fornecedor_slug": r[12],
                "fornecedor_cidade": r[13] or "",
                "fornecedor_uf": r[14] or "",
                "formato": r[15],
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


@vd_fornecedores_bp.get("/fornecedores/variante/<int:id_variante>")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def variante_detalhe(id_variante: int):
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT v.id, v.sku, v.nome_exibicao, p.nome, p.descricao, v.preco, v.preco_promocional,
                   COALESCE(v.imagem_url, p.imagem_url), p.unidade, c.nome,
                   COALESCE(e.quantidade, 0), t.id, t.nome, t.slug, t.cidade, t.uf, p.formato, p.id
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE v.id = %s AND p.id_tenant <> %s
              AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
              AND t.ativo = TRUE AND t.tipo_negocio IN ('fornecedor', 'hibrido')
            """,
            (id_variante, id_tenant),
        )
        r = cur.fetchone()
        if not r:
            return jsonify(success=False, message="Produto não encontrado na rede."), 404

        return jsonify(
            success=True,
            produto={
                "id": r[0],
                "id_variante": r[0],
                "id_produto": r[17],
                "sku": r[1] or "",
                "nome": f"{r[3]} — {r[2]}" if r[2] and r[2] != r[3] else (r[3] or r[2]),
                "descricao": r[4] or "",
                "preco": float(r[5] or 0),
                "preco_promocional": float(r[6]) if r[6] is not None else None,
                "imagem_url": url_imagem_produto(r[7]),
                "unidade": r[8] or "UN",
                "categoria": r[9] or "",
                "estoque": int(r[10] or 0),
                "id_fornecedor": r[11],
                "fornecedor_nome": r[12],
                "fornecedor_slug": r[13],
                "fornecedor_cidade": r[14] or "",
                "fornecedor_uf": r[15] or "",
                "formato": r[16] or "S",
            },
        )
    finally:
        conn.close()

@vd_fornecedores_bp.get("/fornecedores/rede")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def rede():
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403
    busca = (request.args.get("busca") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = [
            "t.id <> %s",
            "t.ativo = TRUE",
            "t.tipo_negocio IN ('fornecedor', 'hibrido')",
        ]
        params: list = [id_vendedor]
        if busca:
            where.append("(t.nome ILIKE %s OR t.cidade ILIKE %s OR t.razao_social ILIKE %s)")
            like = f"%{busca}%"
            params.extend([like, like, like])
        cur.execute(
            f"""
            SELECT t.id, COALESCE(t.nome_fantasia, t.nome), t.cidade, t.uf,
                   t.telefone_comercial, t.email_comercial,
                   v.id AS id_vinculo, COALESCE(v.status, 'nenhum')
            FROM tbl_tenant t
            LEFT JOIN tbl_vinculo_vendedor_fornecedor v
                ON v.id_tenant_fornecedor = t.id AND v.id_tenant_vendedor = %s
            WHERE {' AND '.join(where)}
            ORDER BY t.nome
            LIMIT 120
            """,
            [id_vendedor] + params,
        )
        cards = []
        for row in cur.fetchall():
            tid = row[0]
            cur.execute(
                """
                SELECT DISTINCT s.nome
                FROM tbl_fornecedor_segmento fs
                JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
                WHERE fs.id_tenant = %s
                ORDER BY s.nome
                LIMIT 8
                """,
                (tid,),
            )
            segmentos = [r[0] for r in cur.fetchall()]
            st = row[7] or "nenhum"
            cards.append(
                {
                    "id": tid,
                    "nome": row[1],
                    "cidade": row[2] or "",
                    "uf": row[3] or "",
                    "telefone": row[4] or "",
                    "email": row[5] or "",
                    "segmentos": segmentos,
                    "status_vinculo": st,
                    "id_vinculo": row[6],
                }
            )
        return jsonify(success=True, fornecedores=cards)
    finally:
        conn.close()

@vd_fornecedores_bp.post("/fornecedores/solicitar-vinculo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def solicitar_vinculo():
    id_vendedor = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    try:
        id_forn = int(body.get("id_fornecedor"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Fornecedor inválido."), 400
    if id_forn == id_vendedor:
        return jsonify(success=False, message="Operação inválida."), 400

    snap = snapshot_vendedor_sessao()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status FROM tbl_vinculo_vendedor_fornecedor
            WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
            """,
            (id_vendedor, id_forn),
        )
        row = cur.fetchone()
        if row:
            st = row[0]
            if st == "ativo":
                return jsonify(success=False, message="Você já está conectado a este fornecedor."), 409
            if st == "aguardando":
                return jsonify(success=False, message="Solicitação já enviada. Aguarde aprovação."), 409
            cur.execute(
                """
                UPDATE tbl_vinculo_vendedor_fornecedor
                SET status = 'aguardando', solicitado_em = NOW(), respondido_em = NULL,
                    snapshot_vendedor = %s::jsonb,
                    mensagem_solicitacao = %s
                WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
                """,
                (
                    json.dumps(snap, ensure_ascii=False),
                    (body.get("mensagem") or "").strip() or None,
                    id_vendedor,
                    id_forn,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_vinculo_vendedor_fornecedor
                    (id_tenant_vendedor, id_tenant_fornecedor, status, snapshot_vendedor, mensagem_solicitacao)
                VALUES (%s, %s, 'aguardando', %s::jsonb, %s)
                """,
                (
                    id_vendedor,
                    id_forn,
                    json.dumps(snap, ensure_ascii=False),
                    (body.get("mensagem") or "").strip() or None,
                ),
            )
        conn.commit()
        return jsonify(success=True, message="Solicitação enviada. Aguardando aprovação do fornecedor.")
    finally:
        conn.close()

@vd_fornecedores_bp.get("/fornecedores/<int:id_fornecedor>/catalogo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def catalogo_fornecedor(id_fornecedor: int):
    id_vendedor = session.get("id_tenant")
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = min(48, max(12, int(request.args.get("porPagina", 24))))
    offset = (pagina - 1) * por_pagina
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE p.id_tenant = %s AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
            """,
            (id_fornecedor,),
        )
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT v.id, p.nome, v.nome_exibicao, v.preco,
                   COALESCE(v.imagem_url, p.imagem_url), COALESCE(e.quantidade, 0)
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE p.id_tenant = %s AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
            ORDER BY p.nome
            LIMIT %s OFFSET %s
            """,
            (id_fornecedor, por_pagina, offset),
        )
        produtos = [
            {
                "id_variante": r[0],
                "nome": f"{r[1]} — {r[2]}" if r[2] and r[2] != r[1] else r[1],
                "preco": float(r[3] or 0),
                "imagem_url": url_imagem_produto(r[4]),
                "estoque": int(r[5] or 0),
            }
            for r in cur.fetchall()
        ]
        return jsonify(
            success=True,
            produtos=produtos,
            total=total,
            pagina=pagina,
            total_paginas=max(1, (total + por_pagina - 1) // por_pagina),
        )
    finally:
        conn.close()


def init_app(app):
    app.register_blueprint(vd_fornecedores_bp)
