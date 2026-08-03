from pathlib import Path

from flask import Blueprint, jsonify, render_template, session

from global_utils import Var_ConectarBanco, exigir_modulo, login_obrigatorio
from sistema.plataforma.sessao import MODULO_FORNECEDOR, MODULO_VENDEDOR

_MOD_DIR = Path(__file__).resolve().parent

dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/sistema/dashboard",
)


def init_app(app):
    app.register_blueprint(dashboard_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


@dashboard_bp.get("/index")
@login_obrigatorio()
def index():
    from sistema.plataforma.sessao import garantir_modulo_sessao, rotulo_modulo

    tipo = session.get("tenant_tipo_negocio", "vendedor")
    modulo = garantir_modulo_sessao()
    return render_template(
        "index.html",
        nav_ativo="inicio",
        tipo_negocio=tipo,
        modulo_ativo=modulo,
        modulo_ativo_rotulo=rotulo_modulo(modulo),
    )


@dashboard_bp.get("/index/dados-vendedor")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
def dados_vendedor():
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    tipo = session.get("tenant_tipo_negocio")
    if tipo not in ("vendedor", "hibrido") and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Conta não é vendedor."), 403

    from sistema.dashboard.servico_dashboard_vendedor import montar_dashboard_vendedor

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = montar_dashboard_vendedor(cur, id_tenant)
        return jsonify(success=True, dados=dados)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify(success=False, message=f"Falha ao carregar dashboard: {e}"), 500
    finally:
        conn.close()


@dashboard_bp.get("/index/dados-fornecedor")
@login_obrigatorio()
@exigir_modulo(MODULO_FORNECEDOR)
def dados_fornecedor():
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    tipo = session.get("tenant_tipo_negocio")
    if tipo not in ("fornecedor", "hibrido") and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Conta não é fornecedor."), 403

    from sistema.dashboard.servico_dashboard_fornecedor import montar_dashboard_fornecedor

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = montar_dashboard_fornecedor(cur, id_tenant)
        return jsonify(success=True, dados=dados)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify(success=False, message=f"Falha ao carregar dashboard: {e}"), 500
    finally:
        conn.close()
