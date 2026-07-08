import os
import importlib
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask.json.provider import DefaultJSONProvider

from api.bling.srotas_bling import init_app as api_bling_init
from api.mercadopago.srotas_mercadopago import init_app as api_mercadopago_init
from api.pix_manual.srotas_pix_manual import init_app as api_pix_manual_init
from api.melhor_envio.srotas_melhor_envio import init_app as api_melhor_envio_init
from api.mercado_livre.srotas_mercado_livre import init_app as api_mercado_livre_init
from api.brevo.srotas_brevo import init_app as api_brevo_init
from api.efi.srotas_efi import init_app as api_efi_init
from api.whatsapp.srotas_whatsapp import init_app as api_whatsapp_init
from global_utils import init_app as global_init, registrar_templates_modulos
from sistema.acesso.srotas import init_app as acesso_init

load_dotenv()


class DNJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, date) and not isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, datetime):
            if o.tzinfo is None:
                o = o.replace(tzinfo=timezone.utc)
            return o.isoformat()
        return super().default(o)


def registrar_modulos(app: Flask) -> None:
    raiz = Path(__file__).resolve().parent
    for pasta in ("fornecedor", "vendedor", "sistema"):
        for arquivo in sorted((raiz / pasta).rglob("srotas_*.py")):
            mod_name = ".".join(arquivo.relative_to(raiz).with_suffix("").parts)
            mod = importlib.import_module(mod_name)
            init = getattr(mod, "init_app", None)
            if callable(init):
                init(app)


app = Flask(__name__)
app.json = DNJSONProvider(app)

app.secret_key = os.getenv("SECRET_KEY", "troque-esta-chave-no-env")
app.config["SESSION_COOKIE_NAME"] = os.getenv("SESSION_COOKIE_NAME", "dropnexo_session")

acesso_init(app)
global_init(app)
api_brevo_init(app)
api_whatsapp_init(app)
api_efi_init(app)
api_bling_init(app)
api_mercadopago_init(app)
api_pix_manual_init(app)
api_melhor_envio_init(app)
api_mercado_livre_init(app)
registrar_modulos(app)
registrar_templates_modulos(app)


if __name__ == "__main__":
    modo_producao = os.getenv("MODO_PRODUCAO", "false").lower() == "true"
    porta = int(os.getenv("PORTA", "5260"))
    app.run(
        host="0.0.0.0" if modo_producao else "127.0.0.1",
        port=porta,
        debug=not modo_producao,
        use_reloader=False,
    )
