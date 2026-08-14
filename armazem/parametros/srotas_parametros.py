# armazem/parametros — visibilidade A/B + mesmos recursos do fornecedor
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from fornecedor.parametros.precificacao import (
    MARGEM_REVENDA_PADRAO,
    aplicar_precificacao_catalogo,
    listar_regras_fornecedor,
    obter_modo_precificacao,
    salvar_modo_precificacao,
    salvar_regra_fornecedor,
)
from fornecedor.parametros.requisitos import (
    carregar_requisitos,
    carregar_requisitos_raw,
    contar_produtos_ativos_fornecedor,
    salvar_requisitos,
)
from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent

az_parametros_bp = Blueprint(
    "az_parametros",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/armazem/parametros",
)

MODO_VITRINE_ARMAZEM = "armazem"
MODO_VITRINE_FORNECEDORES = "fornecedores"
_PAR_API_BASE = "/armazem/parametros"


def init_app(app):
    app.register_blueprint(az_parametros_bp)


def _id_tenant() -> int:
    return int(session["id_tenant"])


def _exigir_armazem_tenant():
    if session.get("tenant_tipo_negocio") in ("armazem",) or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é armazém."), 403


def garantir_tabela_parametros(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_armazem_parametros (
            id_tenant BIGINT PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
            modo_vitrine VARCHAR(20) NOT NULL DEFAULT 'armazem',
            visivel_rede_vendedor BOOLEAN NOT NULL DEFAULT FALSE,
            aprovacao_automatica BOOLEAN NOT NULL DEFAULT FALSE,
            texto_adicional TEXT,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT tbl_armazem_parametros_modo_check
              CHECK (modo_vitrine IN ('armazem', 'fornecedores'))
        )
        """
    )


def carregar_parametros(cur, id_tenant: int) -> dict:
    garantir_tabela_parametros(cur)
    cur.execute(
        """
        SELECT modo_vitrine, visivel_rede_vendedor, aprovacao_automatica, texto_adicional
        FROM tbl_armazem_parametros
        WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "modo_vitrine": MODO_VITRINE_ARMAZEM,
            "visivel_rede_vendedor": False,
            "aprovacao_automatica": False,
            "texto_adicional": "",
        }
    return {
        "modo_vitrine": (row[0] or MODO_VITRINE_ARMAZEM).strip().lower(),
        "visivel_rede_vendedor": bool(row[1]),
        "aprovacao_automatica": bool(row[2]),
        "texto_adicional": row[3] or "",
    }


def sincronizar_requisitos_com_armazem(cur, id_tenant: int, az: dict | None = None) -> dict:
    """Garante linha em tbl_fornecedor_requisitos_vendedor alinhada aos params do armazém."""
    az = az or carregar_parametros(cur, id_tenant)
    req, tem = carregar_requisitos_raw(cur, id_tenant)
    if not tem:
        req = {
            **req,
            "aprovacao_automatica": bool(az.get("aprovacao_automatica")),
            "texto_adicional": az.get("texto_adicional") or "",
            "visivel_rede_vendedor": bool(az.get("visivel_rede_vendedor")),
        }
        salvar_requisitos(cur, id_tenant, req)
        return carregar_requisitos(cur, id_tenant)
    return req


def sincronizar_armazem_com_requisitos(cur, id_tenant: int, req: dict) -> None:
    """Espelha aprovação/texto dos requisitos em tbl_armazem_parametros."""
    garantir_tabela_parametros(cur)
    cur.execute(
        """
        INSERT INTO tbl_armazem_parametros (
            id_tenant, modo_vitrine, visivel_rede_vendedor,
            aprovacao_automatica, texto_adicional, atualizado_em
        )
        VALUES (
            %s,
            COALESCE((SELECT modo_vitrine FROM tbl_armazem_parametros WHERE id_tenant = %s), 'armazem'),
            COALESCE((SELECT visivel_rede_vendedor FROM tbl_armazem_parametros WHERE id_tenant = %s), FALSE),
            %s, %s, NOW()
        )
        ON CONFLICT (id_tenant) DO UPDATE SET
            aprovacao_automatica = EXCLUDED.aprovacao_automatica,
            texto_adicional = EXCLUDED.texto_adicional,
            atualizado_em = NOW()
        """,
        (
            id_tenant,
            id_tenant,
            id_tenant,
            bool(req.get("aprovacao_automatica")),
            (req.get("texto_adicional") or "").strip() or None,
        ),
    )


@az_parametros_bp.get("/armazem/parametros")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_pagina():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template("frm_az_parametros.html", nav_ativo="az_parametros")


@az_parametros_bp.get("/armazem/parametros/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = carregar_parametros(cur, id_tenant)
        sincronizar_requisitos_com_armazem(cur, id_tenant, dados)
        qtd = contar_produtos_ativos_fornecedor(cur, id_tenant)
        conn.commit()
        visivel = bool(dados.get("visivel_rede_vendedor"))
        return jsonify(
            success=True,
            parametros=dados,
            qtd_produtos_ativos=qtd,
            aparece_na_rede=visivel and qtd > 0,
        )
    finally:
        conn.close()


@az_parametros_bp.post("/armazem/parametros/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.editar")
def parametros_salvar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    body = request.get_json(silent=True) or {}
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        atual = carregar_parametros(cur, id_tenant)
        modo = (body.get("modo_vitrine") or atual.get("modo_vitrine") or MODO_VITRINE_ARMAZEM)
        modo = str(modo).strip().lower()
        if modo not in (MODO_VITRINE_ARMAZEM, MODO_VITRINE_FORNECEDORES):
            return jsonify(success=False, message="Modo de vitrine inválido."), 400
        visivel = (
            bool(body["visivel_rede_vendedor"])
            if "visivel_rede_vendedor" in body
            else bool(atual.get("visivel_rede_vendedor"))
        )
        auto = bool(atual.get("aprovacao_automatica"))
        texto = atual.get("texto_adicional") or None
        # Se o cliente ainda enviar (legado), aceita
        if "aprovacao_automatica" in body:
            auto = bool(body.get("aprovacao_automatica"))
        if "texto_adicional" in body:
            texto = (body.get("texto_adicional") or "").strip() or None

        garantir_tabela_parametros(cur)
        cur.execute(
            """
            INSERT INTO tbl_armazem_parametros (
                id_tenant, modo_vitrine, visivel_rede_vendedor,
                aprovacao_automatica, texto_adicional, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (id_tenant) DO UPDATE SET
                modo_vitrine = EXCLUDED.modo_vitrine,
                visivel_rede_vendedor = EXCLUDED.visivel_rede_vendedor,
                aprovacao_automatica = EXCLUDED.aprovacao_automatica,
                texto_adicional = EXCLUDED.texto_adicional,
                atualizado_em = NOW()
            """,
            (id_tenant, modo, visivel, auto, texto),
        )
        # Mantém visibilidade espelhada nos requisitos comerciais
        req = sincronizar_requisitos_com_armazem(cur, id_tenant)
        req["visivel_rede_vendedor"] = visivel
        req["aprovacao_automatica"] = auto
        if texto is not None:
            req["texto_adicional"] = texto or ""
        salvar_requisitos(cur, id_tenant, req)

        qtd = contar_produtos_ativos_fornecedor(cur, id_tenant)
        conn.commit()
        msg = "Parâmetros salvos."
        if visivel and qtd == 0:
            msg = (
                "Opção ativada. O armazém só aparecerá para vendedores quando tiver "
                "ao menos 1 produto publicado no catálogo."
            )
        elif visivel:
            msg = "Armazém visível na rede de vendedores."
        elif "visivel_rede_vendedor" in body and not visivel:
            msg = "Armazém ocultado da rede de vendedores."
        return jsonify(
            success=True,
            message=msg,
            parametros=carregar_parametros(cur, id_tenant),
            qtd_produtos_ativos=qtd,
            aparece_na_rede=visivel and qtd > 0,
        )
    finally:
        conn.close()


@az_parametros_bp.get("/armazem/parametros/precificacao")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_precificacao_apoio():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template(
        "frm_parametros_precificacao.html",
        par_api_base=_PAR_API_BASE,
    )


@az_parametros_bp.get("/armazem/parametros/precificacao/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_precificacao_dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
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


@az_parametros_bp.post("/armazem/parametros/precificacao/modo")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.editar")
def parametros_precificacao_modo():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
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


@az_parametros_bp.post("/armazem/parametros/precificacao/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.editar")
def parametros_precificacao_salvar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
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


@az_parametros_bp.post("/armazem/parametros/precificacao/aplicar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.editar")
def parametros_precificacao_aplicar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
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


@az_parametros_bp.get("/armazem/parametros/requisitos-vendedor")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_requisitos_vendedor_apoio():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template(
        "frm_parametros_requisitos_vendedor.html",
        par_api_base=_PAR_API_BASE,
    )


@az_parametros_bp.get("/armazem/parametros/requisitos-vendedor/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.ver")
def parametros_requisitos_vendedor_dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        req = sincronizar_requisitos_com_armazem(cur, id_tenant)
        conn.commit()
        return jsonify(success=True, requisitos=req)
    finally:
        conn.close()


@az_parametros_bp.post("/armazem/parametros/requisitos-vendedor/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_parametros.editar")
def parametros_requisitos_vendedor_salvar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        # Não deixa a tela de requisitos sobrescrever a visibilidade da rede
        az = carregar_parametros(cur, id_tenant)
        body = {**body, "visivel_rede_vendedor": bool(az.get("visivel_rede_vendedor"))}
        salvar_requisitos(cur, id_tenant, body)
        req = carregar_requisitos(cur, id_tenant)
        sincronizar_armazem_com_requisitos(cur, id_tenant, req)
        conn.commit()
        return jsonify(success=True, message="Requisitos salvos.", requisitos=req)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()
