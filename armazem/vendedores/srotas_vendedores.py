from __future__ import annotations

import json
from datetime import datetime, timezone

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from core.dominio import (
    despausar_vinculo,
    encerrar_vinculo,
    montar_snapshot_vendedor,
    pausar_vinculo,
)
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_vendedores_bp = Blueprint(
    "az_vendedores",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/armazem/vendedores",
)


def init_app(app):
    app.register_blueprint(az_vendedores_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_armazem_tenant():
    if session.get("tenant_tipo_negocio") in ("armazem",) or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é armazém."), 403


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


@az_vendedores_bp.get("/armazem/vendedores")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_vendedores.ver")
def vendedores():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template("frm_az_vendedores.html", nav_ativo="az_vendedores")


@az_vendedores_bp.get("/armazem/vendedores/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
def vendedores_dados():
    if (r := _exigir_armazem_tenant()) is not None:
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
                   v.snapshot_vendedor, v.mensagem_solicitacao, v.mensagem_resposta,
                   COALESCE(t.razao_social, ''), COALESCE(t.documento, ''),
                   COALESCE(t.nome_completo, '')
            FROM tbl_vinculo_vendedor_fornecedor v
            JOIN tbl_tenant t ON t.id = v.id_tenant_vendedor
            WHERE {' AND '.join(where)}
            ORDER BY
                CASE v.status
                  WHEN 'pausado' THEN 0
                  WHEN 'aguardando' THEN 1
                  WHEN 'ativo' THEN 2
                  ELSE 3
                END,
                v.solicitado_em DESC
            LIMIT 200
            """,
            params,
        )
        dados = []
        for row in cur.fetchall():
            snap = _parse_snapshot(row[9])
            responsavel = (
                (snap.get("usuario_nome") or "").strip()
                or (row[14] or "").strip()
                or ""
            )
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
                    "razao_social": (row[12] or snap.get("razao_social") or "").strip(),
                    "documento": (row[13] or snap.get("documento") or "").strip(),
                    "responsavel": responsavel,
                }
            )
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@az_vendedores_bp.get("/armazem/vendedores/detalhe/<int:id_vinculo>")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_vendedores.ver")
def vendedores_detalhe(id_vinculo: int):
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_forn = _id_tenant()
    if not id_forn:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from core.dominio import garantir_colunas_vinculo_status

        garantir_colunas_vinculo_status(cur)
        cur.execute(
            """
            SELECT v.id, v.status, v.solicitado_em, v.respondido_em,
                   v.mensagem_solicitacao, v.mensagem_resposta, v.snapshot_vendedor,
                   v.id_tenant_vendedor, v.motivo_status, v.status_alterado_por_lado,
                   v.status_alterado_por_usuario
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
        uid = session.get("id_usuario")
        pode_despausar = (
            (row[1] or "") == "pausado"
            and (row[9] or "") == "fornecedor"
            and (
                row[10] is None
                or (uid is not None and int(row[10]) == int(uid))
            )
        )

        return jsonify(
            success=True,
            vinculo={
                "id": row[0],
                "status": row[1],
                "solicitado_em": row[2].isoformat() if row[2] else "",
                "respondido_em": row[3].isoformat() if row[3] else "",
                "mensagem_solicitacao": row[4] or "",
                "mensagem_resposta": row[5] or "",
                "motivo_status": row[8] or "",
                "status_alterado_por_lado": row[9] or "",
                "pode_despausar": pode_despausar,
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


@az_vendedores_bp.post("/armazem/vendedores/responder")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_vendedores.editar")
def vendedores_responder():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_forn = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        id_vinculo = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Vínculo inválido."), 400
    acao = (body.get("acao") or "").strip().lower()
    if acao not in ("aprovar", "recusar", "inativar", "pausar", "despausar"):
        return jsonify(success=False, message="Ação inválida."), 400

    mensagem = (body.get("mensagem") or body.get("motivo") or "").strip()
    if acao == "recusar" and len(mensagem) < 5:
        return jsonify(success=False, message="Informe o motivo da recusa (mínimo 5 caracteres)."), 400
    if acao in ("inativar", "pausar") and len(mensagem) < 5:
        return jsonify(
            success=False,
            message="Informe o motivo (mínimo 5 caracteres).",
        ), 400

    uid = session.get("id_usuario")
    uid_i = int(uid) if uid else None

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if acao == "inativar":
            encerrar_vinculo(
                cur,
                id_vinculo,
                id_tenant_ator=id_forn,
                lado="fornecedor",
                id_usuario=uid_i,
                motivo=mensagem,
            )
            conn.commit()
            return jsonify(
                success=True,
                message="Vínculo encerrado. Estoques zerados; o vendedor precisará solicitar novamente.",
            )
        if acao == "pausar":
            pausar_vinculo(
                cur,
                id_vinculo,
                id_tenant_ator=id_forn,
                lado="fornecedor",
                id_usuario=uid_i,
                motivo=mensagem,
            )
            conn.commit()
            return jsonify(
                success=True,
                message="Vínculo pausado. Estoques zerados e novos produtos bloqueados.",
            )
        if acao == "despausar":
            despausar_vinculo(
                cur,
                id_vinculo,
                id_tenant_ator=id_forn,
                lado="fornecedor",
                id_usuario=uid_i,
            )
            conn.commit()
            return jsonify(success=True, message="Vínculo retomado (despausado).")

        if acao == "aprovar":
            from sistema.planos.limites import limites_plano, mensagem_limite_conexoes

            lim = limites_plano(tipo_negocio="fornecedor")
            limite_vd = lim.get("conexoes")
            if limite_vd is not None:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM tbl_vinculo_vendedor_fornecedor
                    WHERE id_tenant_fornecedor = %s AND status IN ('ativo', 'pausado')
                    """,
                    (id_forn,),
                )
                aprovados = int(cur.fetchone()[0] or 0)
                if aprovados >= int(limite_vd):
                    return jsonify(
                        success=False,
                        message=mensagem_limite_conexoes(tipo="fornecedor", limite=int(limite_vd)),
                    ), 403

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
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=f"Falha ao processar vínculo: {e}"), 500
    finally:
        conn.close()
