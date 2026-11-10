"""Leitura das NFS-e já autorizadas no Ambiente Nacional. Não transmite DPS."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from sistema.fiscal.nfse.dps import ErroDPS, gunzip_b64


def cnpj_emitente_na_chave(chave: str) -> str:
    digitos = re.sub(r"\D", "", chave or "")
    if len(digitos) != 50 or digitos[8] != "2":
        return ""
    return digitos[9:23]


def numero_nfse_da_chave(chave: str) -> str | None:
    """Extrai o nNFSe da chave de acesso (bloco após município + tipo + CNPJ)."""
    digitos = re.sub(r"\D", "", chave or "")
    if len(digitos) != 50 or digitos[8] != "2":
        return None
    # Layout da chave nacional: [0:7] mun, [8] tipo, [9:23] CNPJ, [23:36] nNFSe (13).
    bruto = digitos[23:36]
    if not bruto.isdigit():
        return None
    numero = int(bruto)
    return str(numero) if numero > 0 else None


def _filho(pai, nome: str):
    if pai is None:
        return None
    for item in pai:
        if etree.QName(item).localname == nome:
            return item
    return None


def _primeiro(raiz, nome: str):
    if raiz is None:
        return None
    for item in raiz.iter():
        if etree.QName(item).localname == nome:
            return item
    return None


def _texto(pai, nome: str) -> str:
    item = _filho(pai, nome)
    if item is None or not (item.text or "").strip():
        return ""
    return " ".join(item.text.split())


def xml_do_arquivo(conteudo: str) -> bytes | None:
    bruto = (conteudo or "").strip()
    if not bruto:
        return None
    if bruto.startswith("<"):
        return bruto.encode("utf-8")
    try:
        return gunzip_b64(bruto)
    except ErroDPS:
        return None


def chave_cancelamento(xml: bytes) -> str:
    try:
        raiz = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError:
        return ""
    if _primeiro(raiz, "e101101") is None:
        return ""
    return re.sub(r"\D", "", _texto(_primeiro(raiz, "infPedReg"), "chNFSe") or _texto(_primeiro(raiz, "infEvento"), "chNFSe"))


def ler_nfse(xml: bytes) -> dict | None:
    try:
        raiz = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError:
        return None
    inf = _primeiro(raiz, "infNFSe")
    dps = _primeiro(raiz, "infDPS")
    if inf is None or dps is None:
        return None
    emit = _filho(inf, "emit")
    toma = _filho(dps, "toma")
    serv = _filho(dps, "serv")
    cserv = _filho(serv, "cServ")
    valores = _filho(_filho(dps, "valores"), "vServPrest")
    mun = _filho(_filho(_filho(dps, "valores"), "trib"), "tribMun")
    chave = ""
    if (inf.get("Id") or "").startswith("NFS"):
        chave = inf.get("Id")[3:]
    competencia = _data(_texto(dps, "dCompet")) or _data(_texto(inf, "dhProc"))
    try:
        valor = Decimal(_texto(valores, "vServ") or "0")
    except InvalidOperation:
        valor = Decimal("0")
    aliquota = _texto(mun, "pAliq") or "0"
    try:
        aliquota_num = Decimal(aliquota)
    except InvalidOperation:
        aliquota_num = Decimal("0")
    return {
        "chave": re.sub(r"\D", "", chave),
        "cnpj_prestador": re.sub(r"\D", "", _texto(emit, "CNPJ")),
        "numero_nfse": _texto(inf, "nNFSe"),
        "serie_dps": _texto(dps, "serie")[:10],
        "numero_dps": _texto(dps, "nDPS"),
        "id_dps": (dps.get("Id") or "")[:45],
        "competencia": competencia,
        "valor": valor,
        "tomador": _texto(toma, "xNome") or "Tomador não identificado no XML",
        "tomador_doc": re.sub(r"\D", "", _texto(toma, "CNPJ") or _texto(toma, "CPF")),
        "codigo_servico": (_texto(cserv, "cTribMun") or "")[:40],
        "codigo_tributacao": (_texto(cserv, "cTribNac") or "")[:20],
        "nbs": (_texto(cserv, "cNBS") or "")[:20] or None,
        "descricao": _texto(cserv, "xDescServ") or "Serviço importado do Ambiente Nacional.",
        "municipio": re.sub(r"\D", "", _texto(_filho(serv, "locPrest"), "cLocPrestacao"))[:7],
        "iss_retido": _texto(mun, "tpRetISSQN") == "2",
        "aliquota": aliquota_num,
        "autorizada_em": _texto(inf, "dhProc"),
        "cancelada": bool(chave_cancelamento(xml)),
    }


def _data(valor: str) -> date | None:
    texto = (valor or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        return date.fromisoformat(texto)
    if re.fullmatch(r"\d{4}-\d{2}", (valor or "")[:7]):
        return date.fromisoformat((valor or "")[:7] + "-01")
    return None


def documentos_do_lote(dados: dict) -> list[dict]:
    lote = dados.get("LoteDFe") or dados.get("loteDFe") or []
    if isinstance(lote, dict):
        lote = [lote]
    saida = []
    for item in lote:
        if not isinstance(item, dict):
            continue
        try:
            nsu = int(item.get("NSU") if item.get("NSU") is not None else item.get("nsu"))
        except (TypeError, ValueError):
            continue
        saida.append({
            "nsu": nsu,
            "tipo": str(item.get("TipoDocumento") or item.get("tipoDocumento") or "").upper(),
            "chave": re.sub(r"\D", "", str(item.get("ChaveAcesso") or item.get("chaveAcesso") or "")),
            "arquivo": str(item.get("ArquivoXml") or item.get("arquivoXml") or ""),
        })
    return saida


def avancar_cursor(cursor: int, documentos: list[dict]) -> tuple[list[dict], int, bool]:
    """Devolve os documentos novos e o maior NSU. Para quando o lote não avança."""
    novos = [item for item in documentos if item["nsu"] > cursor]
    if not novos:
        return [], cursor, False
    return novos, max(item["nsu"] for item in novos), True
