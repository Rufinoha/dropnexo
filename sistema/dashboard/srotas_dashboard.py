from pathlib import Path

from flask import Blueprint, render_template, session

from global_utils import login_obrigatorio

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


@dashboard_bp.get("/index")
@login_obrigatorio()
def index():
    return render_template(
        "index.html",
        nav_ativo="inicio",
        tipo_negocio=session.get("tenant_tipo_negocio", "vendedor"),
    )
