# fornecedor/segmentos/srotas_segmentos.py — redirect legado; gestao em Meu perfil
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, redirect, url_for

from global_utils import login_obrigatorio


_MOD = Path(__file__).resolve().parent

fn_segmentos_bp = Blueprint(
    "fn_segmentos",
    __name__,
    root_path=str(_MOD),
)


def init_app(app):
    app.register_blueprint(fn_segmentos_bp)


@fn_segmentos_bp.get("/fornecedor/segmentos")
@fn_segmentos_bp.get("/fornecedor/segmentos/dados")
@login_obrigatorio()
def segmentos():
    """Tela removida — segmentos/nichos ficam em Minha conta > Minha empresa."""
    return redirect(url_for("perfil.meu_perfil", aba="empresa"))
