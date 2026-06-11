# api/whatsapp/srotas_whatsapp.py — reservado para canal WhatsApp.
from flask import Blueprint

whatsapp_bp = Blueprint("whatsapp", __name__)


def init_app(app):
    app.register_blueprint(whatsapp_bp)


def enviar_mensagem(destino: str, texto: str) -> None:
    raise NotImplementedError("WhatsApp ainda não implementado.")
