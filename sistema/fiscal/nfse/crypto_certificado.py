"""Criptografia e leitura segura de certificados A1 do módulo NFS-e."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import timezone

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.serialization import pkcs12

from global_utils import modo_producao, somente_digitos

log = logging.getLogger(__name__)


def _fernet() -> tuple[Fernet, bool]:
    """Retorna o cifrador e se está usando o fallback inseguro de DEV."""
    master = (os.getenv("NFSE_MASTER_KEY") or "").strip()
    if master:
        try:
            return Fernet(master.encode("ascii")), False
        except (ValueError, TypeError):
            # Aceita um segredo forte qualquer e o transforma em chave Fernet.
            chave = base64.urlsafe_b64encode(hashlib.sha256(master.encode("utf-8")).digest())
            return Fernet(chave), False

    if modo_producao():
        raise RuntimeError("NFSE_MASTER_KEY é obrigatória em produção.")

    # INSEGURO — somente DEV: determinístico para permitir reabrir certificados
    # após reiniciar. Nunca promover este fallback para produção.
    secret = os.getenv("SECRET_KEY", "h74_dev_secret")
    chave = base64.urlsafe_b64encode(
        hashlib.sha256(f"h74-nfse-dev::{secret}".encode("utf-8")).digest()
    )
    log.warning("NFS-e usando fallback criptográfico INSEGURO de desenvolvimento.")
    return Fernet(chave), True


def validar_configuracao_criptografica() -> bool:
    """Falha cedo em produção e informa se DEV está em fallback."""
    _, inseguro = _fernet()
    return inseguro


def criptografar(valor: bytes) -> bytes:
    return _fernet()[0].encrypt(valor)


def descriptografar(valor: bytes) -> bytes:
    return _fernet()[0].decrypt(bytes(valor))


def _cnpj_do_certificado(certificado) -> str | None:
    # ICP-Brasil costuma expor CNPJ em atributo do subject. Extraímos somente
    # quando há uma sequência inequívoca de 14 dígitos; se não houver, N/D.
    candidatos = []
    for atributo in certificado.subject:
        digitos = somente_digitos(atributo.value)
        if atributo.oid.dotted_string == "2.16.76.1.3.3" and len(digitos) >= 14:
            candidatos.append(digitos[-14:])
        elif len(digitos) == 14:
            candidatos.append(digitos)
    unicos = sorted(set(candidatos))
    return unicos[0] if len(unicos) == 1 else None


def ler_pkcs12(conteudo: bytes, senha: str) -> dict:
    try:
        chave, certificado, _cadeia = pkcs12.load_key_and_certificates(
            conteudo, senha.encode("utf-8") if senha else None
        )
    except Exception as exc:
        raise ValueError("Certificado PFX/P12 inválido ou senha incorreta.") from exc

    if not chave or not certificado:
        raise ValueError("O arquivo não contém certificado e chave privada A1.")

    inicio = getattr(certificado, "not_valid_before_utc", None)
    fim = getattr(certificado, "not_valid_after_utc", None)
    if inicio is None:
        inicio = certificado.not_valid_before.replace(tzinfo=timezone.utc)
    if fim is None:
        fim = certificado.not_valid_after.replace(tzinfo=timezone.utc)

    return {
        "serial": format(certificado.serial_number, "X"),
        "titular": certificado.subject.rfc4514_string(),
        "cnpj": _cnpj_do_certificado(certificado),
        "inicio": inicio,
        "fim": fim,
    }
