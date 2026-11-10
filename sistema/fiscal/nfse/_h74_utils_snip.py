"""Utilitários globais do sistema H74 (PostgreSQL)."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import timedelta
from functools import wraps
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from flask import Blueprint, has_request_context, jsonify, redirect, request, session

load_dotenv()

ROOT = Path(__file__).resolve().parent

_VIACEP = "https://viacep.com.br/ws/{}/json/"
_BRASILAPI_CNPJ = "https://brasilapi.com.br/api/cnpj/v1/{}"

global_bp = Blueprint("global", __name__)


def init_app(app):
    app.register_blueprint(global_bp)
    app.permanent_session_lifetime = timedelta(hours=12)

    @app.before_request
    def _sessao_permanente():
        if session.get("id_usuario"):
            session.permanent = True


def modo_producao() -> bool:
    return str(os.getenv("MODO_PRODUCAO", "false")).strip().lower() in (
        "1",
        "true",
        "yes",
        "sim",
    )


def obter_base_url_app() -> str:
    chave = "BASE_URL_PROD" if modo_producao() else "BASE_URL_DEV"
    base = (os.getenv(chave) or "").strip().rstrip("/")
    if base:
        return base
    if has_request_context():
        return request.host_url.rstrip("/")
    return "http://127.0.0.1:5080"


def Var_ConectarBanco():
    """Conexão PostgreSQL (DEV/PROD via .env)."""
    sufixo = "PROD" if modo_producao() else "DEV"
    conn = psycopg2.connect(
        user=os.getenv(f"DB_USER_{sufixo}"),
        password=os.getenv(f"DB_PASSWORD_{sufixo}"),
        dbname=os.getenv(f"DB_NAME_{sufixo}"),
        host=os.getenv(f"DB_HOST_{sufixo}", "127.0.0.1"),
        port=os.getenv(f"DB_PORT_{sufixo}", "5432"),
    )
    schema = (os.getenv(f"DB_SCHEMA_{sufixo}") or "public").strip() or "public"
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}")
    conn.commit()
    return conn


def db_execute(conn, sql: str, params=None):
    """Executa SQL com placeholders %s (PostgreSQL)."""
    cur = conn.cursor()
    cur.execute(sql, params or ())
    return cur


def login_obrigatorio():
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("id_usuario"):
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"success": False, "message": "Faça login novamente."}), 401
                session["proxima_url"] = request.url
                return redirect("/login")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def somente_digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def validar_cnpj(cnpj) -> bool:
    c = somente_digitos(cnpj)
    if len(c) != 14 or len(set(c)) == 1:
        return False

    def _digito(base, pesos):
        s = sum(int(base[i]) * pesos[i] for i in range(len(pesos)))
        r = s % 11
        return 0 if r < 2 else 11 - r

    peso1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    peso2 = [6] + peso1
    d1 = _digito(c[:12], peso1)
    d2 = _digito(c[:12] + str(d1), peso2)
    return c[-2:] == f"{d1}{d2}"


def formatar_cnpj(cnpj) -> str:
    d = somente_digitos(cnpj)
    if len(d) != 14:
        return str(cnpj or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def validar_cpf(cpf) -> bool:
    c = somente_digitos(cpf)
    if len(c) != 11 or len(set(c)) == 1:
        return False
    s = sum(int(c[i]) * (10 - i) for i in range(9))
    d1 = (s * 10) % 11
    d1 = 0 if d1 == 10 else d1
    if d1 != int(c[9]):
        return False
    s = sum(int(c[i]) * (11 - i) for i in range(10))
    d2 = (s * 10) % 11
    d2 = 0 if d2 == 10 else d2
    return d2 == int(c[10])


def formatar_cpf(cpf) -> str:
    d = somente_digitos(cpf)
    if len(d) != 11:
        return str(cpf or "")
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def consultar_cep_viacep(cep):
    cep = somente_digitos(cep)
    if len(cep) != 8:
        return None, "CEP deve ter 8 dígitos."
    url = _VIACEP.format(cep)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "H74/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return None, f"ViaCEP HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"Falha de rede (ViaCEP): {e.reason}"
    except json.JSONDecodeError:
        return None, "Resposta ViaCEP inválida."

    if data.get("erro"):
        return None, "CEP não encontrado."

    return {
        "cep": somente_digitos(data.get("cep") or cep),
        "logradouro": (data.get("logradouro") or "").strip(),
        "complemento": (data.get("complemento") or "").strip(),
        "bairro": (data.get("bairro") or "").strip(),
        "municipio": (data.get("localidade") or "").strip(),
        "uf": (data.get("uf") or "").strip().upper()[:2],
    }, None


def consultar_cnpj_brasilapi(cnpj):
    cnpj = somente_digitos(cnpj)
    if len(cnpj) != 14:
        return None, "CNPJ deve ter 14 dígitos."
    if not validar_cnpj(cnpj):
        return None, "CNPJ inválido (dígitos verificadores)."

    url = _BRASILAPI_CNPJ.format(cnpj)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "H74/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, "CNPJ não localizado na base pública."
        return None, f"BrasilAPI HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"Falha de rede (BrasilAPI): {e.reason}"
    except json.JSONDecodeError:
        return None, "Resposta BrasilAPI inválida."

    telefone = ""
    ddd = (data.get("ddd_telefone_1") or "").strip()
    tel = (data.get("telefone_1") or "").strip()
    if ddd or tel:
        telefone = f"{ddd}{tel}".strip()

    logradouro = " ".join(
        x
        for x in [
            (data.get("descricao_tipo_logradouro") or "").strip(),
            (data.get("logradouro") or "").strip(),
        ]
        if x
    ).strip()

    return {
        "cnpj": cnpj,
        "razao_social": (data.get("razao_social") or "").strip(),
        "nome_fantasia": (data.get("nome_fantasia") or "").strip(),
        "email": (data.get("email") or "").strip() or None,
        "telefone": telefone or None,
        "cep": somente_digitos(data.get("cep") or "") or None,
        "endereco": logradouro or None,
        "numero": (data.get("numero") or "").strip() or None,
        "complemento": (data.get("complemento") or "").strip() or None,
        "bairro": (data.get("bairro") or "").strip() or None,
        "cidade": (data.get("municipio") or "").strip() or None,
        "uf": ((data.get("uf") or "").strip().upper()[:2] or None),
        "codigo_municipio_ibge": somente_digitos(data.get("codigo_municipio_ibge")) or None,
        "opcao_pelo_simples": data.get("opcao_pelo_simples"),
        "opcao_pelo_mei": data.get("opcao_pelo_mei"),
        "situacao_ativa": data.get("situacao_cadastral") == 2,
    }, None
