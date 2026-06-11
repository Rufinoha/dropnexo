
from pathlib import Path
from flask import Blueprint, render_template
from global_utils import exigir_modulo, login_obrigatorio
from srotas_plataforma import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent
vd_pedidos_bp = Blueprint(
    "vd_pedidos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/pedidos",
)

def init_app(app):
    app.register_blueprint(vd_pedidos_bp)

@vd_pedidos_bp.get("/vendedor/pedidos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
def pedidos():
    return render_template("frm_em_breve.html", nav_ativo="vd_pedidos", titulo="Pedidos")
