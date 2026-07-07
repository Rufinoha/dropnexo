# api/pix_manual/payload.py — BR Code PIX (EMV) estático com TXID
from __future__ import annotations

import re


def _crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for ch in data:
        crc ^= ord(ch) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def normalizar_txid(referencia: str, *, max_len: int = 25) -> str:
    """TXID alfanumérico (BACEN) — ex.: PED-2026-00002 → PED202600002."""
    limpo = re.sub(r"[^A-Za-z0-9]", "", referencia or "")
    return (limpo or "PEDIDO")[:max_len]


def gerar_payload_pix(
    *,
    chave: str,
    nome_beneficiario: str,
    cidade: str,
    valor: float,
    txid: str,
) -> str:
    chave = (chave or "").strip()
    if not chave:
        raise ValueError("Chave PIX não configurada.")

    nome = (nome_beneficiario or "FORNECEDOR").strip()[:25].upper()
    cidade_fmt = (cidade or "BRASIL").strip()[:15].upper()
    txid_fmt = normalizar_txid(txid)

    merchant_account = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    payload = ""
    payload += _tlv("00", "01")
    payload += _tlv("26", merchant_account)
    payload += _tlv("52", "0000")
    payload += _tlv("53", "986")
    if valor and float(valor) > 0:
        payload += _tlv("54", f"{float(valor):.2f}")
    payload += _tlv("58", "BR")
    payload += _tlv("59", nome)
    payload += _tlv("60", cidade_fmt)
    if txid_fmt:
        payload += _tlv("62", _tlv("05", txid_fmt))

    sem_crc = payload + "6304"
    return sem_crc + _crc16_ccitt(sem_crc)
