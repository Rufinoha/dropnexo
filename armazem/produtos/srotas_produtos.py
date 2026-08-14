# armazem/produtos — catálogo operacional do armazém
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from fornecedor.catalogo.catalogo import (
    garantir_linhas_estoque_depositos,
    sincronizar_total_variante,
)
from fornecedor.catalogo.srotas_catalogo import garantir_variante_padrao
from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_produtos_bp = Blueprint(
    "az_produtos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/armazem/produtos",
)


def init_app(app):
    app.register_blueprint(az_produtos_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_armazem_tenant():
    if session.get("tenant_tipo_negocio") in ("armazem",) or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é armazém."), 403


def garantir_coluna_dono(cur) -> None:
    cur.execute(
        """
        ALTER TABLE tbl_produto
          ADD COLUMN IF NOT EXISTS id_armazem_fornecedor BIGINT
            REFERENCES tbl_armazem_fornecedor(id) ON DELETE SET NULL
        """
    )


@az_produtos_bp.get("/armazem/produtos")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_produtos.ver")
def pagina():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template("frm_az_produtos.html", nav_ativo="az_produtos")


@az_produtos_bp.get("/armazem/produtos/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_produtos.ver")
def dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    busca = (request.args.get("busca") or "").strip()
    id_forn = request.args.get("id_fornecedor")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_coluna_dono(cur)
        conn.commit()
        where = ["p.id_tenant = %s"]
        params: list = [id_tenant]
        if busca:
            where.append("(p.nome ILIKE %s OR COALESCE(p.sku,'') ILIKE %s)")
            like = f"%{busca}%"
            params.extend([like, like])
        if id_forn:
            where.append("p.id_armazem_fornecedor = %s")
            params.append(int(id_forn))
        cur.execute(
            f"""
            SELECT p.id, p.nome, COALESCE(p.sku,''), COALESCE(p.preco,0),
                   COALESCE(p.publicado, FALSE), p.id_armazem_fornecedor,
                   COALESCE(af.nome_fantasia, af.nome, ''),
                   p.id_deposito_expedicao,
                   COALESCE(e.quantidade, 0)
            FROM tbl_produto p
            LEFT JOIN tbl_armazem_fornecedor af ON af.id = p.id_armazem_fornecedor
            LEFT JOIN tbl_produto_variante_estoque e
              ON e.id_variante = p.id_variante_padrao
            WHERE {' AND '.join(where)}
            ORDER BY p.nome
            LIMIT 500
            """,
            params,
        )
        dados = [
            {
                "id": r[0],
                "nome": r[1],
                "sku": r[2],
                "preco": float(r[3] or 0),
                "publicado": bool(r[4]),
                "id_armazem_fornecedor": r[5],
                "fornecedor_nome": r[6] or "",
                "id_deposito_expedicao": r[7],
                "estoque": int(r[8] or 0),
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@az_produtos_bp.get("/armazem/produtos/combos")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_produtos.ver")
def combos():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, COALESCE(nome_fantasia, nome)
            FROM tbl_armazem_fornecedor
            WHERE id_tenant_armazem = %s AND ativo = TRUE
            ORDER BY 2
            """,
            (id_tenant,),
        )
        fornecedores = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        cur.execute(
            """
            SELECT id, nome FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY principal DESC, nome
            """,
            (id_tenant,),
        )
        depositos = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(success=True, fornecedores=fornecedores, depositos=depositos)
    finally:
        conn.close()


@az_produtos_bp.post("/armazem/produtos/apoio")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_produtos.editar")
def apoio():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    pid = body.get("id")
    if not pid:
        return jsonify(success=True, dados=None)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_coluna_dono(cur)
        cur.execute(
            """
            SELECT p.id, p.nome, COALESCE(p.sku,''), COALESCE(p.preco,0),
                   COALESCE(p.publicado, FALSE), p.id_armazem_fornecedor,
                   p.id_deposito_expedicao, p.id_variante_padrao,
                   COALESCE(e.quantidade, 0)
            FROM tbl_produto p
            LEFT JOIN tbl_produto_variante_estoque e
              ON e.id_variante = p.id_variante_padrao
            WHERE p.id = %s AND p.id_tenant = %s
            """,
            (int(pid), id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Produto não encontrado."), 404
        estoques = []
        if row[7]:
            cur.execute(
                """
                SELECT d.id, d.nome, COALESCE(ped.quantidade, 0)
                FROM tbl_deposito_expedicao d
                LEFT JOIN tbl_produto_estoque_deposito ped
                  ON ped.id_deposito = d.id AND ped.id_variante = %s
                WHERE d.id_tenant = %s AND d.ativo = TRUE
                ORDER BY d.principal DESC, d.nome
                """,
                (int(row[7]), id_tenant),
            )
            estoques = [
                {"id_deposito": r[0], "nome": r[1], "quantidade": int(r[2] or 0)}
                for r in cur.fetchall()
            ]
        return jsonify(
            success=True,
            dados={
                "id": row[0],
                "nome": row[1],
                "sku": row[2],
                "preco": float(row[3] or 0),
                "publicado": bool(row[4]),
                "id_armazem_fornecedor": row[5],
                "id_deposito_expedicao": row[6],
                "id_variante": row[7],
                "estoque_total": int(row[8] or 0),
                "estoques": estoques,
            },
        )
    finally:
        conn.close()


@az_produtos_bp.post("/armazem/produtos/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_produtos.editar")
def salvar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if len(nome) < 2:
        return jsonify(success=False, message="Informe o nome do produto."), 400
    try:
        id_forn = int(body.get("id_armazem_fornecedor"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Selecione o fornecedor dono do produto."), 400
    sku = (body.get("sku") or "").strip() or None
    try:
        preco = max(0.0, float(body.get("preco") or 0))
    except (TypeError, ValueError):
        preco = 0.0
    publicado = bool(body.get("publicado"))
    id_dep = body.get("id_deposito_expedicao")
    id_dep = int(id_dep) if id_dep else None
    estoques = body.get("estoques") or []
    agora = agora_utc()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_coluna_dono(cur)
        cur.execute(
            """
            SELECT 1 FROM tbl_armazem_fornecedor
            WHERE id = %s AND id_tenant_armazem = %s AND ativo = TRUE
            """,
            (id_forn, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Fornecedor inválido."), 400
        if id_dep:
            cur.execute(
                """
                SELECT 1 FROM tbl_deposito_expedicao
                WHERE id = %s AND id_tenant = %s AND ativo = TRUE
                """,
                (id_dep, id_tenant),
            )
            if not cur.fetchone():
                return jsonify(success=False, message="Depósito inválido."), 400

        pid = body.get("id")
        if pid:
            cur.execute(
                """
                UPDATE tbl_produto SET
                    nome=%s, sku=%s, preco=%s, valor_atacado=%s,
                    publicado=%s, id_armazem_fornecedor=%s,
                    id_deposito_expedicao=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant=%s
                RETURNING id
                """,
                (
                    nome,
                    sku,
                    preco,
                    preco,
                    publicado,
                    id_forn,
                    id_dep,
                    agora,
                    int(pid),
                    id_tenant,
                ),
            )
            row = cur.fetchone()
            if not row:
                return jsonify(success=False, message="Produto não encontrado."), 404
            pid = int(row[0])
        else:
            cur.execute(
                """
                INSERT INTO tbl_produto (
                    id_tenant, nome, sku, preco, valor_atacado, publicado,
                    formato, id_armazem_fornecedor, id_deposito_expedicao, atualizado_em
                ) VALUES (%s,%s,%s,%s,%s,%s,'S',%s,%s,%s)
                RETURNING id
                """,
                (
                    id_tenant,
                    nome,
                    sku,
                    preco,
                    preco,
                    publicado,
                    id_forn,
                    id_dep,
                    agora,
                ),
            )
            pid = int(cur.fetchone()[0])

        vid = garantir_variante_padrao(cur, pid, id_tenant)
        cur.execute(
            """
            UPDATE tbl_produto_variante SET
                nome_exibicao=%s, sku=%s, preco=%s, atualizado_em=%s
            WHERE id=%s
            """,
            (nome, sku, preco, agora, vid),
        )
        garantir_linhas_estoque_depositos(cur, id_tenant, vid)
        for item in estoques:
            try:
                dep_id = int(item.get("id_deposito"))
                qtd = max(0, int(item.get("quantidade") or 0))
            except (TypeError, ValueError):
                continue
            cur.execute(
                """
                INSERT INTO tbl_produto_estoque_deposito
                    (id_variante, id_deposito, quantidade, atualizado_em)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id_variante, id_deposito) DO UPDATE SET
                    quantidade = EXCLUDED.quantidade,
                    atualizado_em = EXCLUDED.atualizado_em
                """,
                (vid, dep_id, qtd, agora),
            )
        sincronizar_total_variante(cur, vid)
        conn.commit()
        return jsonify(success=True, id=pid, message="Produto salvo.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@az_produtos_bp.post("/armazem/produtos/excluir")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_produtos.editar")
def excluir():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        pid = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Produto inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_produto SET publicado = FALSE, atualizado_em = %s
            WHERE id = %s AND id_tenant = %s
            """,
            (agora_utc(), pid, id_tenant),
        )
        if cur.rowcount == 0:
            return jsonify(success=False, message="Produto não encontrado."), 404
        conn.commit()
        return jsonify(success=True, message="Produto despublicado.")
    finally:
        conn.close()
