from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from fornecedor.parametros.servico_precificacao import (
    MARGEM_REVENDA_PADRAO,
    aplicar_precificacao_catalogo,
    listar_regras_fornecedor,
    obter_modo_precificacao,
    salvar_modo_precificacao,
    salvar_regra_fornecedor,
)
from fornecedor.requisitos_vendedor import (
    carregar_requisitos,
    contar_produtos_ativos_fornecedor,
    salvar_requisitos,
    salvar_visivel_rede_vendedor,
)
from vendedor.meus_produtos.servico_vitrine_vendedor import (
    despausar_vitrine_fornecedor,
    pausar_vitrine_fornecedor,
)
from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_FORNECEDOR

_MOD = Path(__file__).resolve().parent

fn_parametros_bp = Blueprint(
    "fn_parametros",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/parametros",
)


def init_app(app):
    app.register_blueprint(fn_parametros_bp)


def _id_tenant() -> int:
    return int(session["id_tenant"])


@fn_parametros_bp.get("/fornecedor/parametros")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.ver")
def parametros_pagina():
    return render_template("frm_fn_parametros.html", nav_ativo="fn_parametros")


@fn_parametros_bp.get("/fornecedor/parametros/precificacao")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.ver")
def parametros_precificacao_apoio():
    return render_template("frm_parametros_precificacao.html")


@fn_parametros_bp.get("/fornecedor/parametros/precificacao/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.ver")
def parametros_precificacao_dados():
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        regras = listar_regras_fornecedor(cur, id_tenant)
        cur.execute(
            """
            SELECT id, nome, nivel FROM tbl_categoria
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY nivel, nome
            """,
            (id_tenant,),
        )
        categorias = [
            {"id": r[0], "nome": r[1], "nivel": int(r[2] or 1)}
            for r in cur.fetchall()
        ]
        modo = obter_modo_precificacao(cur, id_tenant)
        return jsonify(success=True, regras=regras, categorias=categorias, modo=modo)
    finally:
        conn.close()


@fn_parametros_bp.post("/fornecedor/parametros/precificacao/modo")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.editar")
def parametros_precificacao_modo():
    body = request.get_json(silent=True) or {}
    modo = (body.get("modo") or "global").strip().lower()
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        modo = salvar_modo_precificacao(cur, id_tenant, modo)
        conn.commit()
        return jsonify(success=True, modo=modo, message="Modo de precificação atualizado.")
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_parametros_bp.post("/fornecedor/parametros/precificacao/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.editar")
def parametros_precificacao_salvar():
    body = request.get_json(silent=True) or {}
    escopo = (body.get("escopo") or "global").strip().lower()
    id_cat = body.get("id_categoria")
    id_cat = int(id_cat) if id_cat not in (None, "") else None

    def pct(k: str, default: float = 0.0) -> float:
        try:
            val = body.get(k)
            if val in (None, ""):
                return default
            return float(val)
        except (TypeError, ValueError):
            return default

    aplicar = bool(body.get("aplicar_agora", False))
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        rid = salvar_regra_fornecedor(
            cur,
            id_tenant,
            escopo=escopo,
            id_categoria=id_cat,
            pct_ajuste=pct("pct_ajuste"),
            pct_taxas=pct("pct_taxas"),
            pct_comissao=pct("pct_comissao"),
            pct_margem_revenda=pct("pct_margem_revenda", MARGEM_REVENDA_PADRAO),
        )
        resumo = {"atualizados": 0, "ignorados": 0}
        if aplicar:
            resumo = aplicar_precificacao_catalogo(cur, id_tenant, marcar_publicado=True)
        conn.commit()
        msg = "Regra salva."
        if aplicar:
            msg = f"Precificação aplicada em {resumo['atualizados']} produto(s)."
        return jsonify(success=True, message=msg, id=rid, resumo=resumo)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_parametros_bp.get("/fornecedor/parametros/rede-visibilidade/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.ver")
def parametros_rede_visibilidade_dados():
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        req = carregar_requisitos(cur, id_tenant)
        qtd = contar_produtos_ativos_fornecedor(cur, id_tenant)
        visivel = bool(req.get("visivel_rede_vendedor"))
        return jsonify(
            success=True,
            visivel_rede_vendedor=visivel,
            qtd_produtos_ativos=qtd,
            aparece_na_rede=visivel and qtd > 0,
        )
    finally:
        conn.close()


@fn_parametros_bp.post("/fornecedor/parametros/rede-visibilidade")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.editar")
def parametros_rede_visibilidade_salvar():
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    visivel = bool(body.get("visivel_rede_vendedor"))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        salvar_visivel_rede_vendedor(cur, id_tenant, visivel)
        if visivel:
            despausar_vitrine_fornecedor(cur, id_tenant)
        else:
            pausar_vitrine_fornecedor(cur, id_tenant)
        qtd = contar_produtos_ativos_fornecedor(cur, id_tenant)
        conn.commit()
        msg = "Visibilidade na rede atualizada."
        if visivel and qtd == 0:
            msg = (
                "Opção ativada. Você só aparecerá para vendedores quando tiver "
                "ao menos 1 produto ativo no catálogo."
            )
        elif visivel:
            msg = "Sua empresa está visível na rede de vendedores."
        else:
            msg = "Sua empresa foi ocultada da rede de vendedores."
        return jsonify(
            success=True,
            message=msg,
            visivel_rede_vendedor=visivel,
            qtd_produtos_ativos=qtd,
            aparece_na_rede=visivel and qtd > 0,
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_parametros_bp.get("/fornecedor/parametros/requisitos-vendedor")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.ver")
def parametros_requisitos_vendedor_apoio():
    return render_template("frm_parametros_requisitos_vendedor.html")


@fn_parametros_bp.get("/fornecedor/parametros/requisitos-vendedor/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.ver")
def parametros_requisitos_vendedor_dados():
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(success=True, requisitos=carregar_requisitos(cur, id_tenant))
    finally:
        conn.close()


@fn_parametros_bp.post("/fornecedor/parametros/requisitos-vendedor/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.editar")
def parametros_requisitos_vendedor_salvar():
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        salvar_requisitos(cur, id_tenant, body)
        conn.commit()
        return jsonify(
            success=True,
            message="Requisitos salvos.",
            requisitos=carregar_requisitos(cur, id_tenant),
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_parametros_bp.post("/fornecedor/parametros/precificacao/aplicar")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
@exigir_permissao(codigo="fn_parametros.editar")
def parametros_precificacao_aplicar():
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        resumo = aplicar_precificacao_catalogo(cur, id_tenant, marcar_publicado=True)
        conn.commit()
        return jsonify(
            success=True,
            message=f"Precificação aplicada em {resumo['atualizados']} produto(s).",
            resumo=resumo,
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()
