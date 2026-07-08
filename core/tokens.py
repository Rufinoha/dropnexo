# core/tokens.py — criptografia reversível de tokens OAuth (derivada de SECRET_KEY)
from __future__ import annotations

import base64
import hashlib
import os


def _chave() -> bytes:
    secret = (os.getenv("SECRET_KEY") or "dev-inseguro").encode("utf-8")
    return hashlib.sha256(secret).digest()


def criptografar_token(valor: str) -> str:
    if not valor:
        return ""
    raw = valor.encode("utf-8")
    k = _chave()
    xored = bytes(b ^ k[i % len(k)] for i, b in enumerate(raw))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def descriptografar_token(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        xored = base64.urlsafe_b64decode(valor.encode("ascii"))
        k = _chave()
        return bytes(b ^ k[i % len(k)] for i, b in enumerate(xored)).decode("utf-8")
    except Exception:
        return ""
