# sistema/financeiro/srotas_financeiro.py — módulo Financeiro
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, login_obrigatorio
from sistema.financeiro.cobranca import (
    DIAS_GRACA_INADIMPLENCIA,
    assinar_plano,
    fatura_aberta_alerta,
    garantir_cobranca_tenant,
    listar_efi_logs,
    listar_faturas,
    obter_fatura,
    regenerar_cobranca,
)

_MOD = Path(__file__).resolve().parent

financeiro_bp = Blueprint(
    "financeiro",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/sistema/financeiro",
)


def init_app(app):
    app.register_blueprint(financeiro_bp)

    @app.context_processor
    def _inject_financeiro_banner():
        if not session.get("id_tenant"):
            return {}
        try:
            conn = Var_ConectarBanco()
            cur = conn.cursor()
            alerta = fatura_aberta_alerta(cur, int(session["id_tenant"]))
            conn.close()
            if not alerta:
                return {"financeiro_alerta": None}
            return {
                "financeiro_alerta": {
                    **alerta,
                    "dias_graca": DIAS_GRACA_INADIMPLENCIA,
                }
            }
        except Exception:
            return {"financeiro_alerta": None}


def _pode_financeiro() -> bool:
    if session.get("eh_desenvolvedor"):
        return True
    perfil = (session.get("perfil_codigo") or "").lower()
    return perfil in ("dono", "admin", "financeiro")


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


@financeiro_bp.get("/financeiro")
@login_obrigatorio()
def pagina():
    if not _pode_financeiro():
        return render_template("frm_financeiro.html", nav_ativo="", sem_acesso=True)
    from api.efi.efi import efi_disponivel, efi_front_config, efi_pix_chave

    efi_cfg = efi_front_config()
    return render_template(
        "frm_financeiro.html",
        nav_ativo="",
        sem_acesso=False,
        dias_graca=DIAS_GRACA_INADIMPLENCIA,
        efi_ok=efi_disponivel(),
        efi_pix_ok=bool(efi_pix_chave()),
        efi_payee_code=efi_cfg.get("payee_code") or "",
        efi_environment=efi_cfg.get("environment") or "sandbox",
        eh_dev=bool(session.get("eh_desenvolvedor")),
    )


@financeiro_bp.get("/api/financeiro/faturas")
@login_obrigatorio()
def api_faturas():
    if not _pode_financeiro():
        return jsonify(success=False, message="Sem permissão."), 403
    tid = _id_tenant()
    if not tid:
        return jsonify(success=False, message="Sessão inválida."), 403
    try:
        page = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_cobranca_tenant(cur, tid)
        conn.commit()
        data = listar_faturas(cur, tid, page=page)
        return jsonify(success=True, **data, dias_graca=DIAS_GRACA_INADIMPLENCIA)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@financeiro_bp.post("/api/financeiro/faturas/<int:id_fatura>/regenerar")
@login_obrigatorio()
def api_regenerar(id_fatura: int):
    if not _pode_financeiro():
        return jsonify(success=False, message="Sem permissão."), 403
    tid = _id_tenant()
    if not tid:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    forma = (body.get("forma_pagamento") or "").strip().lower() or None
    token = (body.get("payment_token") or "").strip() or None
    try:
        installments = max(1, min(12, int(body.get("installments") or 1)))
    except (TypeError, ValueError):
        installments = 1
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        fat = regenerar_cobranca(
            cur,
            tid,
            id_fatura,
            forma=forma,
            payment_token=token,
            installments=installments,
        )
        conn.commit()
        return jsonify(success=True, message="Cobrança regenerada.", fatura=fat)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@financeiro_bp.get("/api/financeiro/faturas/<int:id_fatura>")
@login_obrigatorio()
def api_fatura_detalhe(id_fatura: int):
    if not _pode_financeiro():
        return jsonify(success=False, message="Sem permissão."), 403
    tid = _id_tenant()
    if not tid:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        fat = obter_fatura(cur, tid, id_fatura)
        if not fat:
            return jsonify(success=False, message="Fatura não encontrada."), 404
        return jsonify(success=True, fatura=fat)
    finally:
        conn.close()


def _mapa_plano_vitrine(plano: str) -> str:
    from global_utils import plano_slug_banco

    return plano_slug_banco(plano)


@financeiro_bp.post("/api/financeiro/preview-assinatura")
@login_obrigatorio()
def api_preview_assinatura():
    if not _pode_financeiro():
        return jsonify(success=False, message="Sem permissão."), 403
    body = request.get_json(silent=True) or {}
    plano = _mapa_plano_vitrine(body.get("plano_slug") or "")
    periodo = (body.get("periodicidade") or "mensal").strip().lower()
    cupom = (body.get("cupom") or body.get("cupom_codigo") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cobranca import obter_plano_db
        from sistema.financeiro.cupom import preview_assinatura

        p = obter_plano_db(cur, plano)
        if not p or int(p["valor_centavos"] or 0) <= 0:
            return jsonify(success=False, message="Plano inválido para cobrança."), 400
        data = preview_assinatura(
            cur,
            valor_mensal_centavos=int(p["valor_centavos"]),
            periodo=periodo,
            cupom_codigo=cupom,
            id_tenant=_id_tenant(),
            plano_slug=plano,
        )
        data["plano_slug"] = plano
        data["plano_nome"] = p["nome"]
        return jsonify(**data)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@financeiro_bp.post("/api/financeiro/assinar")
@login_obrigatorio()
def api_assinar():
    if not _pode_financeiro():
        return jsonify(success=False, message="Sem permissão para assinar."), 403
    tid = _id_tenant()
    if not tid:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    plano = _mapa_plano_vitrine(body.get("plano_slug") or "")
    forma = (body.get("forma_pagamento") or "boleto").strip().lower()
    token = (body.get("payment_token") or "").strip() or None
    periodo = (body.get("periodicidade") or "mensal").strip().lower()
    cupom = (body.get("cupom") or body.get("cupom_codigo") or "").strip() or None
    try:
        installments = max(1, min(12, int(body.get("installments") or 1)))
    except (TypeError, ValueError):
        installments = 1
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        result = assinar_plano(
            cur,
            tid,
            plano,
            forma=forma,
            payment_token=token,
            installments=installments,
            periodicidade=periodo,
            cupom_codigo=cupom,
        )
        if result.get("liberado"):
            session["tenant_plano"] = plano
        conn.commit()
        return jsonify(success=True, **result)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@financeiro_bp.get("/api/financeiro/efi-logs")
@login_obrigatorio()
def api_efi_logs():
    if not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Somente desenvolvedor."), 403
    try:
        page = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    tid = request.args.get("id_tenant")
    id_tenant = int(tid) if tid and str(tid).isdigit() else None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        data = listar_efi_logs(cur, page=page, id_tenant=id_tenant)
        return jsonify(success=True, **data)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()
