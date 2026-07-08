from __future__ import annotations

import json
from datetime import datetime, timezone

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from core.dominio import inativar_vinculo, montar_snapshot_vendedor
from sistema.plataforma.sessao import MODULO_FORNECEDOR

_MOD = Path(__file__).resolve().parent

fn_vendedores_bp = Blueprint(
    "fn_vendedores",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/vendedores",
)


def init_app(app):
    app.register_blueprint(fn_vendedores_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_fornecedor_tenant():
    if session.get("tenant_tipo_negocio") in ("fornecedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é fornecedor."), 403


def _parse_snapshot(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _tempo_na_plataforma(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dias = (datetime.now(timezone.utc) - dt).days
        if dias < 30:
            return f"{max(dias, 1)} dia(s) na plataforma"
        meses = dias // 30
        if meses < 12:
            return f"{meses} mês(es) na plataforma"
        anos = meses // 12
        return f"{anos} ano(s) na plataforma"
    except Exception:
        return "—"


@fn_vendedores_bp.get("/fornecedor/vendedores")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_vendedores.ver")
def vendedores():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    return render_template("frm_fn_vendedores.html", nav_ativo="fn_vendedores")


@fn_vendedores_bp.get("/fornecedor/vendedores/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
def vendedores_dados():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_forn = _id_tenant()
    if not id_forn:
        return jsonify(success=False, message="Sessão inválida."), 403
    status = (request.args.get("status") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        where = ["v.id_tenant_fornecedor = %s"]
        params: list = [id_forn]
        if status:
            where.append("v.status = %s")
            params.append(status)
        cur.execute(
            f"""
            SELECT v.id, v.status, v.solicitado_em, v.respondido_em,
                   COALESCE(t.nome_fantasia, t.nome), t.cidade, t.uf,
                   t.email_comercial, t.telefone_comercial,
                   v.snapshot_vendedor, v.mensagem_solicitacao, v.mensagem_resposta
            FROM tbl_vinculo_vendedor_fornecedor v
            JOIN tbl_tenant t ON t.id = v.id_tenant_vendedor
            WHERE {' AND '.join(where)}
            ORDER BY
                CASE v.status WHEN 'aguardando' THEN 0 WHEN 'ativo' THEN 1 ELSE 2 END,
                v.solicitado_em DESC
            LIMIT 200
            """,
            params,
        )
        dados = []
        for row in cur.fetchall():
            snap = _parse_snapshot(row[9])
            dados.append(
                {
                    "id": row[0],
                    "status": row[1],
                    "solicitado_em": row[2].isoformat() if row[2] else "",
                    "respondido_em": row[3].isoformat() if row[3] else "",
                    "nome": row[4],
                    "cidade": row[5] or "",
                    "uf": row[6] or "",
                    "email": row[7] or snap.get("email_comercial") or snap.get("usuario_email") or "",
                    "telefone": row[8] or snap.get("celular_comercial") or snap.get("telefone_comercial") or "",
                    "mensagem_solicitacao": row[10] or "",
                    "mensagem_resposta": row[11] or "",
                }
            )
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@fn_vendedores_bp.get("/fornecedor/vendedores/detalhe/<int:id_vinculo>")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_vendedores.ver")
def vendedores_detalhe(id_vinculo: int):
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_forn = _id_tenant()
    if not id_forn:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT v.id, v.status, v.solicitado_em, v.respondido_em,
                   v.mensagem_solicitacao, v.mensagem_resposta, v.snapshot_vendedor,
                   v.id_tenant_vendedor
            FROM tbl_vinculo_vendedor_fornecedor v
            WHERE v.id = %s AND v.id_tenant_fornecedor = %s
            """,
            (id_vinculo, id_forn),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Solicitação não encontrada."), 404

        id_vendedor = row[7]
        snap = _parse_snapshot(row[6])
        live = montar_snapshot_vendedor(cur, id_vendedor, snap.get("id_usuario"))

        merged = {**live, **{k: v for k, v in snap.items() if v not in (None, "")}}

        return jsonify(
            success=True,
            vinculo={
                "id": row[0],
                "status": row[1],
                "solicitado_em": row[2].isoformat() if row[2] else "",
                "respondido_em": row[3].isoformat() if row[3] else "",
                "mensagem_solicitacao": row[4] or "",
                "mensagem_resposta": row[5] or "",
            },
            vendedor={
                "nome": merged.get("nome_fantasia") or merged.get("tenant_nome") or merged.get("nome_completo"),
                "razao_social": merged.get("razao_social") or "",
                "documento": merged.get("documento_formatado") or merged.get("documento") or "",
                "tipo_pessoa": merged.get("tipo_pessoa") or "",
                "endereco": merged.get("endereco") or "",
                "cidade": merged.get("cidade") or "",
                "uf": merged.get("uf") or "",
                "cep": merged.get("cep") or "",
                "email": merged.get("email_comercial") or merged.get("usuario_email") or "",
                "telefone": merged.get("telefone_comercial") or merged.get("celular_comercial") or "",
                "whatsapp": merged.get("usuario_whatsapp") or merged.get("celular_comercial") or "",
                "contato_nome": merged.get("usuario_nome") or "",
                "site": merged.get("site") or "",
                "faturamento_ultimo_ano": merged.get("faturamento_ultimo_ano") or "",
                "tamanho_empresa": merged.get("tamanho_empresa") or "",
                "tempo_plataforma": _tempo_na_plataforma(merged.get("cadastro_desde") or ""),
                "qtd_fornecedores_ativos": merged.get("qtd_fornecedores_ativos", 0),
                "qtd_produtos_vitrine": merged.get("qtd_produtos_vitrine", 0),
                "aceite_requisitos": merged.get("aceite_requisitos"),
                "requisitos_aceitos": merged.get("requisitos_aceitos") or {},
            },
        )
    finally:
        conn.close()


@fn_vendedores_bp.post("/fornecedor/vendedores/responder")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_vendedores.editar")
def vendedores_responder():
    if (r := _exigir_fornecedor_tenant()) is not None:
        return r
    id_forn = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        id_vinculo = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Vínculo inválido."), 400
    acao = (body.get("acao") or "").strip().lower()
    if acao not in ("aprovar", "recusar", "inativar"):
        return jsonify(success=False, message="Ação inválida."), 400

    mensagem = (body.get("mensagem") or "").strip()
    if acao == "recusar" and len(mensagem) < 5:
        return jsonify(success=False, message="Informe o motivo da recusa (mínimo 5 caracteres)."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if acao == "inativar":
            inativar_vinculo(cur, id_vinculo, id_forn)
            conn.commit()
            return jsonify(success=True, message="Vínculo encerrado. Produtos desativados e estoque zerado na vitrine.")

        novo = "ativo" if acao == "aprovar" else "recusado"
        cur.execute(
            """
            UPDATE tbl_vinculo_vendedor_fornecedor
            SET status = %s, respondido_em = NOW(),
                mensagem_resposta = %s
            WHERE id = %s AND id_tenant_fornecedor = %s AND status = 'aguardando'
            """,
            (novo, mensagem or None, id_vinculo, id_forn),
        )
        if cur.rowcount == 0:
            return jsonify(success=False, message="Solicitação não encontrada ou já respondida."), 404
        conn.commit()
        msg = "Vendedor aprovado." if novo == "ativo" else "Solicitação recusada. O vendedor verá o motivo informado."
        return jsonify(success=True, message=msg)
    finally:
        conn.close()
