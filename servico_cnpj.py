# servico_cnpj.py — consulta CNPJ (BrasilAPI)
from __future__ import annotations

import re

import requests

_BRASIL_API = "https://brasilapi.com.br/api/cnpj/v1"


def _so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def consultar_cnpj(cnpj: str) -> dict:
    """Consulta dados públicos do CNPJ. Levanta ValueError se inválido/não encontrado."""
    doc = _so_digitos(cnpj)
    if len(doc) != 14:
        raise ValueError("CNPJ inválido.")

    try:
        r = requests.get(f"{_BRASIL_API}/{doc}", timeout=15)
    except requests.RequestException as exc:
        raise ValueError(f"Não foi possível consultar o CNPJ: {exc}") from exc

    if r.status_code == 404:
        raise ValueError("CNPJ não encontrado na base pública. Preencha os dados manualmente.")
    if r.status_code == 429:
        raise ValueError("Consulta de CNPJ temporariamente indisponível. Aguarde um minuto ou preencha manualmente.")
    if r.status_code >= 400:
        raise ValueError(
            f"Serviço de consulta CNPJ indisponível (HTTP {r.status_code}). Preencha os dados manualmente."
        )

    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("Resposta inválida da consulta CNPJ.")

    cep = _so_digitos(str(data.get("cep") or ""))
    return {
        "cnpj": doc,
        "razao_social": (data.get("razao_social") or "").strip(),
        "nome_fantasia": (data.get("nome_fantasia") or data.get("razao_social") or "").strip(),
        "situacao_cadastral": (data.get("descricao_situacao_cadastral") or "").strip(),
        "cnae_principal": str(data.get("cnae_fiscal") or data.get("cnae") or "").strip(),
        "cep": cep,
        "logradouro": (data.get("logradouro") or "").strip(),
        "numero": (data.get("numero") or "").strip(),
        "complemento": (data.get("complemento") or "").strip(),
        "bairro": (data.get("bairro") or "").strip(),
        "cidade": (data.get("municipio") or "").strip(),
        "uf": (data.get("uf") or "").strip().upper(),
    }
