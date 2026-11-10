"""Transporte mTLS e normalização da API Nacional NFS-e."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests
from lxml import etree
from requests_pkcs12 import get as pkcs12_get, post

from sistema.fiscal.nfse.dps import gunzip_b64, gzip_b64

URLS = {
    "homologacao": "https://sefin.producaorestrita.nfse.gov.br/SefinNacional/nfse",
    "producao": "https://sefin.nfse.gov.br/SefinNacional/nfse",
}
URL_DANFSE = "https://adn.nfse.gov.br/danfse"
URL_ADN = {
    "homologacao": "https://adn.producaorestrita.nfse.gov.br/contribuintes",
    "producao": "https://adn.nfse.gov.br/contribuintes",
}


@dataclass(frozen=True)
class ResultadoEmissao:
    sucesso: bool
    codigo: str
    mensagem: str
    numero_nfse: str | None = None
    chave_nfse: str | None = None
    xml_nfse: bytes | None = None
    metadados: dict[str, Any] | None = None
    incerto: bool = False
    http_status: int | None = None


class NFSeAdapter(ABC):
    @abstractmethod
    def emitir(self, xml_dps: bytes, pfx: bytes, senha: str) -> ResultadoEmissao:
        """Transmite uma DPS e devolve o resultado normalizado."""
        raise NotImplementedError


def garantir_producao_habilitada(ambiente: str) -> None:
    """Produção é liberada ao salvar Ambiente = Produção nos parâmetros fiscais."""
    if ambiente not in URLS:
        raise ValueError("Ambiente NFS-e inválido.")


def _valor(item: dict, *chaves: str):
    normalizado = {str(chave).lower(): valor for chave, valor in item.items()}
    for chave in chaves:
        valor = normalizado.get(chave.lower())
        if valor not in (None, ""):
            return valor
    return None


def texto_rejeicao(dados: dict) -> tuple[str, str]:
    """Lê a rejeição da Sefin. O JSON oficial usa Codigo e Descricao."""
    bruto = _valor(dados, "erros", "erro", "mensagens") or []
    itens = [bruto] if isinstance(bruto, dict) else bruto if isinstance(bruto, list) else []
    partes = []
    codigo = ""
    for item in itens:
        if not isinstance(item, dict):
            if item:
                partes.append(str(item))
            continue
        cod = str(_valor(item, "codigo", "code") or "")
        desc = str(_valor(item, "descricao", "mensagem", "message") or "")
        extra = str(_valor(item, "complemento", "correcao") or "")
        if cod and not codigo:
            codigo = cod
        texto = ": ".join(parte for parte in (cod, desc) if parte)
        if extra:
            texto = f"{texto} ({extra})" if texto else extra
        if texto:
            partes.append(texto)
    if not codigo:
        codigo = str(_valor(dados, "codigo", "code", "status") or "REJEICAO")
    mensagem = " | ".join(partes) or str(
        _valor(dados, "mensagem", "message", "descricao") or "DPS rejeitada pela API Nacional."
    )
    return codigo[:80], mensagem[:2000]


def _texto_erro(dados: dict) -> tuple[str, str]:
    return texto_rejeicao(dados)


def parsear_sucesso(dados: dict) -> ResultadoEmissao:
    compactado = dados.get("nfseXmlGZipB64")
    if not compactado:
        return ResultadoEmissao(False, "RESPOSTA_INVALIDA", "Resposta 201 sem nfseXmlGZipB64.")
    xml = gunzip_b64(compactado)
    root = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    ids_nfse = root.xpath("//*[local-name()='infNFSe']/@Id")
    chave = dados.get("chaveAcesso") or (ids_nfse[0].removeprefix("NFS") if ids_nfse else None)
    numero = dados.get("nNFSe")
    if not numero:
        encontrados = root.xpath("//*[local-name()='nNFSe']/text()")
        numero = encontrados[0] if encontrados else None
    if not chave:
        encontrados = root.xpath("//*[local-name()='chaveAcesso']/text()")
        chave = encontrados[0] if encontrados else None
    return ResultadoEmissao(
        True, "AUTORIZADA", "NFS-e autorizada.", str(numero) if numero else None,
        str(chave) if chave else None, xml, _metadados_seguros(dados), http_status=201,
    )


def _metadados_seguros(dados: dict) -> dict:
    permitidos = {
        "ambiente", "tipoAmbiente", "versaoAplicativo", "dataHoraProcessamento",
        "chaveAcesso", "nNFSe", "codigo", "mensagem", "message", "status",
        "erros", "mensagens",
    }
    return {k: v for k, v in dados.items() if k in permitidos}


class AdapterNacional(NFSeAdapter):
    def __init__(self, ambiente: str, timeout: tuple[int, int] = (15, 60)):
        if ambiente not in URLS:
            raise ValueError("Ambiente NFS-e inválido.")
        garantir_producao_habilitada(ambiente)
        self.ambiente = ambiente
        self.timeout = timeout

    def emitir(self, xml_dps: bytes, pfx: bytes, senha: str) -> ResultadoEmissao:
        try:
            resposta = post(
                URLS[self.ambiente],
                json={"dpsXmlGZipB64": gzip_b64(xml_dps)},
                pkcs12_data=pfx,
                pkcs12_password=senha,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            return ResultadoEmissao(
                False, "RESULTADO_INCERTO",
                "Falha de rede/timeout após iniciar a transmissão. Mantenha em processamento e "
                "reconcilie pelo Id da DPS antes de qualquer reenvio.",
                incerto=True, metadados={"tipo_falha": type(exc).__name__},
            )
        try:
            dados = resposta.json()
            if not isinstance(dados, dict):
                dados = {}
        except (ValueError, json.JSONDecodeError):
            dados = {}
        if resposta.status_code == 201:
            try:
                resultado = parsear_sucesso(dados)
            except (ValueError, etree.XMLSyntaxError) as exc:
                return ResultadoEmissao(
                    False, "RESPOSTA_201_INVALIDA",
                    "A API retornou 201, mas o XML recebido é inválido. Reconcilie pelo Id da DPS.",
                    metadados={"tipo_falha": type(exc).__name__},
                    incerto=True, http_status=201,
                )
            return ResultadoEmissao(**{**resultado.__dict__, "http_status": 201})
        codigo, mensagem = _texto_erro(dados)
        if not dados and (resposta.text or "").strip():
            mensagem = " ".join(resposta.text.split())[:400]
        return ResultadoEmissao(
            False, codigo, mensagem, metadados=_metadados_seguros(dados),
            http_status=resposta.status_code,
        )

    def cancelar(self, chave: str, xml_evento: bytes, pfx: bytes, senha: str) -> ResultadoEmissao:
        try:
            resposta = post(
                f"{URLS[self.ambiente]}/{chave}/eventos",
                json={"pedidoRegistroEventoXmlGZipB64": gzip_b64(xml_evento)},
                pkcs12_data=pfx,
                pkcs12_password=senha,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            return ResultadoEmissao(
                False, "RESULTADO_INCERTO",
                "Falha de rede ao cancelar. Confira na Sefin antes de tentar de novo.",
                incerto=True, metadados={"tipo_falha": type(exc).__name__},
            )
        try:
            dados = resposta.json()
            if not isinstance(dados, dict):
                dados = {}
        except (ValueError, json.JSONDecodeError):
            dados = {}
        erros = dados.get("erros") or dados.get("erro") or dados.get("mensagens")
        if resposta.status_code in (200, 201) and not erros:
            return ResultadoEmissao(
                True, "CANCELADA", "NFS-e cancelada.",
                metadados=_metadados_seguros(dados), http_status=resposta.status_code,
            )
        codigo, mensagem = _texto_erro(dados)
        if mensagem == "DPS rejeitada pela API Nacional." and (resposta.text or "").strip():
            mensagem = " ".join(resposta.text.split())[:400]
        return ResultadoEmissao(
            False, codigo, mensagem, metadados=_metadados_seguros(dados),
            http_status=resposta.status_code, incerto=resposta.status_code >= 500,
        )

    def consultar_dfe(self, nsu: int, pfx: bytes, senha: str) -> ResultadoEmissao:
        """Lê o lote de DF-e posterior ao NSU informado. Não emite nota."""
        try:
            resposta = pkcs12_get(
                f"{URL_ADN[self.ambiente]}/DFe/{int(nsu)}",
                pkcs12_data=pfx,
                pkcs12_password=senha,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            return ResultadoEmissao(
                False, "FALHA_REDE",
                "Não foi possível consultar o Ambiente Nacional (ADN). Tente de novo em instantes.",
                metadados={"tipo_falha": type(exc).__name__},
            )
        if resposta.status_code == 404:
            return ResultadoEmissao(True, "NENHUM_DOCUMENTO_LOCALIZADO", "Nenhum documento novo.", http_status=404)
        try:
            dados = resposta.json()
            if not isinstance(dados, dict):
                dados = {}
        except (ValueError, json.JSONDecodeError):
            dados = {}
        status = str(_valor(dados, "StatusProcessamento", "statusProcessamento") or "")
        status_norm = status.upper().replace(" ", "").replace("_", "")
        if status_norm in {"NENHUMDOCUMENTOLOCALIZADO", "NENHUMDOCUMENTO"}:
            return ResultadoEmissao(
                True, "NENHUM_DOCUMENTO_LOCALIZADO", "Nenhum documento novo.",
                metadados=dados, http_status=resposta.status_code,
            )
        if resposta.status_code == 200 and status_norm != "REJEICAO":
            return ResultadoEmissao(
                True, status or "DOCUMENTOS_LOCALIZADOS", "Lote recebido.",
                metadados=dados, http_status=200,
            )
        tipo_consulta = str(_valor(dados, "TipoConsulta", "tipoConsulta") or "")
        codigo, mensagem = _texto_erro(dados)
        # texto_rejeicao usa fallback de emissão; aqui é consulta ADN.
        if status_norm == "REJEICAO" and tipo_consulta.lower() in {"inscricaocertificado", "inscricao_certificado"}:
            codigo = "ADN_INSCRICAO_CERTIFICADO"
            mensagem = (
                "O Ambiente Nacional (ADN) rejeitou a consulta pela inscrição do certificado "
                "(TipoConsulta=InscricaoCertificado). A emissão na Sefin pode funcionar, "
                "mas a distribuição DF-e deste CNPJ/certificado não está liberada ou não "
                "bate com o cadastro. Informe a chave de acesso do portal para reconciliar "
                "notas em processamento."
            )
        elif mensagem == "DPS rejeitada pela API Nacional.":
            partes = [f"Consulta ADN falhou (HTTP {resposta.status_code}"]
            if status:
                partes[0] += f", {status}"
            partes[0] += ")."
            if (resposta.text or "").strip():
                partes.append(" ".join(resposta.text.split())[:400])
            mensagem = " ".join(partes)
            codigo = codigo if codigo and codigo != "REJEICAO" else "ADN_CONSULTA"
        elif not dados and (resposta.text or "").strip():
            mensagem = " ".join(resposta.text.split())[:400]
        return ResultadoEmissao(
            False, codigo, mensagem, metadados=dados if dados else _metadados_seguros(dados),
            http_status=resposta.status_code,
        )

    def consultar_nfse(self, chave: str, pfx: bytes, senha: str) -> ResultadoEmissao:
        """Consulta a NFS-e autorizada na Sefin pela chave de acesso (traz o XML)."""
        chave = "".join(ch for ch in str(chave or "") if ch.isdigit())
        if len(chave) != 50:
            return ResultadoEmissao(False, "CHAVE_INVALIDA", "Chave de acesso deve ter 50 dígitos.")
        try:
            resposta = pkcs12_get(
                f"{URLS[self.ambiente]}/{chave}",
                pkcs12_data=pfx,
                pkcs12_password=senha,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            return ResultadoEmissao(
                False, "FALHA_REDE",
                "Não foi possível consultar a NFS-e na Sefin. Tente de novo em instantes.",
                metadados={"tipo_falha": type(exc).__name__},
            )
        try:
            dados = resposta.json()
            if not isinstance(dados, dict):
                dados = {}
        except (ValueError, json.JSONDecodeError):
            dados = {}
        if resposta.status_code in (200, 201) and (dados.get("nfseXmlGZipB64") or dados.get("chaveAcesso")):
            try:
                if dados.get("nfseXmlGZipB64"):
                    resultado = parsear_sucesso(dados)
                    return ResultadoEmissao(**{**resultado.__dict__, "http_status": resposta.status_code})
            except (ValueError, etree.XMLSyntaxError) as exc:
                return ResultadoEmissao(
                    False, "XML_INVALIDO",
                    "A Sefin devolveu a NFS-e, mas o XML veio inválido.",
                    metadados={"tipo_falha": type(exc).__name__},
                    http_status=resposta.status_code,
                )
        codigo, mensagem = _texto_erro(dados)
        if mensagem == "DPS rejeitada pela API Nacional.":
            mensagem = (
                f"Consulta da NFS-e na Sefin falhou (HTTP {resposta.status_code})."
            )
            if (resposta.text or "").strip():
                mensagem += " " + " ".join(resposta.text.split())[:400]
            codigo = "SEFIN_CONSULTA"
        return ResultadoEmissao(
            False, codigo, mensagem, metadados=dados or None,
            http_status=resposta.status_code,
        )

    def baixar_danfse(self, chave: str, pfx: bytes, senha: str) -> bytes | None:
        try:
            resposta = pkcs12_get(
                f"{URL_DANFSE}/{chave}",
                pkcs12_data=pfx,
                pkcs12_password=senha,
                timeout=(10, 40),
                headers={"Accept": "application/pdf"},
            )
        except requests.RequestException:
            return None
        if resposta.status_code == 200 and resposta.content.startswith(b"%PDF"):
            return resposta.content
        return None
