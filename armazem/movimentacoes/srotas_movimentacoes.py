# armazem/movimentacoes — entrada / saída / ajuste de estoque
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from fornecedor.catalogo.catalogo import sincronizar_total_variante
from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_movimentacoes_bp = Blueprint(
    "az_movimentacoes",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/armazem/movimentacoes",
)


def init_app(app):
    app.register_blueprint(az_movimentacoes_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _id_usuario() -> int | None:
    uid = session.get("id_usuario")
    return int(uid) if uid else None


def _exigir_armazem_tenant():
    if session.get("tenant_tipo_negocio") in ("armazem",) or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é armazém."), 403


def garantir_tabela_mov(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_armazem_movimentacao (
          id BIGSERIAL PRIMARY KEY,
          id_tenant_armazem BIGINT NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
          id_produto BIGINT NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
          id_variante BIGINT NOT NULL REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
          id_deposito BIGINT NOT NULL REFERENCES tbl_deposito_expedicao(id) ON DELETE RESTRICT,
          id_armazem_fornecedor BIGINT REFERENCES tbl_armazem_fornecedor(id) ON DELETE SET NULL,
          tipo VARCHAR(20) NOT NULL,
          quantidade INTEGER NOT NULL,
          saldo_apos INTEGER,
          observacao TEXT,
          id_usuario INTEGER,
          criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT tbl_armazem_movimentacao_tipo_check
            CHECK (tipo IN ('entrada', 'saida', 'ajuste')),
          CONSTRAINT tbl_armazem_movimentacao_qtd_check
            CHECK (quantidade > 0)
        )
        """
    )


@az_movimentacoes_bp.get("/armazem/movimentacoes")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_movimentacoes.ver")
def pagina():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template("frm_az_movimentacoes.html", nav_ativo="az_movimentacoes")


@az_movimentacoes_bp.get("/armazem/movimentacoes/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_movimentacoes.ver")
def dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_mov(cur)
        conn.commit()
        cur.execute(
            """
            SELECT m.id, m.tipo, m.quantidade, m.saldo_apos, m.observacao, m.criado_em,
                   p.nome, COALESCE(d.nome,''), COALESCE(af.nome_fantasia, af.nome, '')
            FROM tbl_armazem_movimentacao m
            JOIN tbl_produto p ON p.id = m.id_produto
            JOIN tbl_deposito_expedicao d ON d.id = m.id_deposito
            LEFT JOIN tbl_armazem_fornecedor af ON af.id = m.id_armazem_fornecedor
            WHERE m.id_tenant_armazem = %s
            ORDER BY m.criado_em DESC
            LIMIT 200
            """,
            (id_tenant,),
        )
        dados = [
            {
                "id": r[0],
                "tipo": r[1],
                "quantidade": int(r[2]),
                "saldo_apos": int(r[3] or 0),
                "observacao": r[4] or "",
                "criado_em": r[5].isoformat() if r[5] else None,
                "produto": r[6],
                "deposito": r[7],
                "fornecedor": r[8] or "",
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@az_movimentacoes_bp.get("/armazem/movimentacoes/combos")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_movimentacoes.ver")
def combos():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id, p.nome, p.id_variante_padrao, p.id_armazem_fornecedor
            FROM tbl_produto p
            WHERE p.id_tenant = %s AND p.id_variante_padrao IS NOT NULL
            ORDER BY p.nome
            LIMIT 500
            """,
            (id_tenant,),
        )
        produtos = [
            {
                "id": r[0],
                "nome": r[1],
                "id_variante": r[2],
                "id_armazem_fornecedor": r[3],
            }
            for r in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT id, nome FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY principal DESC, nome
            """,
            (id_tenant,),
        )
        depositos = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(success=True, produtos=produtos, depositos=depositos)
    finally:
        conn.close()


@az_movimentacoes_bp.post("/armazem/movimentacoes/lancar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_movimentacoes.editar")
def lancar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    tipo = (body.get("tipo") or "").strip().lower()
    if tipo not in ("entrada", "saida", "ajuste"):
        return jsonify(success=False, message="Tipo inválido."), 400
    try:
        id_produto = int(body.get("id_produto"))
        id_deposito = int(body.get("id_deposito"))
        quantidade = int(body.get("quantidade"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Dados inválidos."), 400
    if quantidade <= 0:
        return jsonify(success=False, message="Quantidade deve ser maior que zero."), 400
    obs = (body.get("observacao") or "").strip() or None

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_mov(cur)
        cur.execute(
            """
            SELECT id_variante_padrao, id_armazem_fornecedor
            FROM tbl_produto
            WHERE id = %s AND id_tenant = %s
            """,
            (id_produto, id_tenant),
        )
        prow = cur.fetchone()
        if not prow or not prow[0]:
            return jsonify(success=False, message="Produto não encontrado."), 404
        id_variante = int(prow[0])
        id_forn = prow[1]
        cur.execute(
            """
            SELECT 1 FROM tbl_deposito_expedicao
            WHERE id = %s AND id_tenant = %s AND ativo = TRUE
            """,
            (id_deposito, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Depósito inválido."), 400

        cur.execute(
            """
            SELECT COALESCE(quantidade, 0)
            FROM tbl_produto_estoque_deposito
            WHERE id_variante = %s AND id_deposito = %s
            """,
            (id_variante, id_deposito),
        )
        row = cur.fetchone()
        atual = int(row[0] or 0) if row else 0
        if tipo == "entrada":
            novo = atual + quantidade
        elif tipo == "saida":
            if quantidade > atual:
                return jsonify(success=False, message=f"Estoque insuficiente (atual: {atual})."), 400
            novo = atual - quantidade
        else:
            novo = quantidade

        agora = agora_utc()
        cur.execute(
            """
            INSERT INTO tbl_produto_estoque_deposito
                (id_variante, id_deposito, quantidade, atualizado_em)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_variante, id_deposito) DO UPDATE SET
                quantidade = EXCLUDED.quantidade,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_variante, id_deposito, novo, agora),
        )
        sincronizar_total_variante(cur, id_variante)
        cur.execute(
            """
            INSERT INTO tbl_armazem_movimentacao (
                id_tenant_armazem, id_produto, id_variante, id_deposito,
                id_armazem_fornecedor, tipo, quantidade, saldo_apos,
                observacao, id_usuario
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                id_tenant,
                id_produto,
                id_variante,
                id_deposito,
                id_forn,
                tipo,
                quantidade if tipo != "ajuste" else abs(novo - atual) or quantidade,
                novo,
                obs,
                _id_usuario(),
            ),
        )
        mid = cur.fetchone()[0]
        conn.commit()
        return jsonify(success=True, id=mid, saldo=novo, message="Movimentação lançada.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()
