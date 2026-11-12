"""Geração, validação, assinatura e codificação da DPS Nacional v1.01."""
from __future__ import annotations

import base64
import gzip
import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

FUSO_BRASILIA = timezone(timedelta(hours=-3))
MARGEM_RELOGIO = timedelta(minutes=2)
NS = "http://www.sped.fazenda.gov.br/nfse"
DS = "http://www.w3.org/2000/09/xmldsig#"
C14N_EXCLUSIVE = "http://www.w3.org/2001/10/xml-exc-c14n#"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
SCHEMAS = Path(__file__).resolve().parent / "schemas"


class ErroDPS(ValueError):
    """Erro de preenchimento ou conformidade da DPS."""


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def gerar_id_dps(municipio: str, documento: str, serie, numero) -> str:
    municipio, documento = _digits(municipio), _digits(documento)
    serie, numero = _digits(serie), _digits(numero)
    if len(municipio) != 7:
        raise ErroDPS("Município IBGE deve conter 7 dígitos.")
    if len(documento) not in (11, 14):
        raise ErroDPS("Documento do prestador deve ser CPF ou CNPJ válido em tamanho.")
    if not serie or len(serie) > 5 or not numero or len(numero) > 15 or int(numero) < 1:
        raise ErroDPS("Série ou número da DPS inválido.")
    tipo = "1" if len(documento) == 11 else "2"
    return f"DPS{municipio}{tipo}{documento.zfill(14)}{serie.zfill(5)}{numero.zfill(15)}"


def _data_emissao(agora: datetime | None) -> str:
    """Horário de Brasília, com folga para o relógio do servidor não ficar à frente da Sefin."""
    if agora is None:
        momento = datetime.now(timezone.utc).astimezone(FUSO_BRASILIA) - MARGEM_RELOGIO
    else:
        if agora.tzinfo is None or agora.utcoffset() is None:
            raise ErroDPS("Data/hora de emissão deve possuir fuso horário.")
        momento = agora.astimezone(FUSO_BRASILIA)
    return momento.replace(microsecond=0).isoformat(timespec="seconds")


def _add(parent, name: str, value=None):
    element = etree.SubElement(parent, f"{{{NS}}}{name}")
    if value is not None:
        element.text = str(value)
    return element


def _codigo_regime(config: dict) -> tuple[str, str | None, str]:
    regime = str(config.get("regime_tributario") or "").strip().lower()
    optante = bool(config.get("optante_simples"))
    if optante:
        if regime in {"mei", "simples_mei"}:
            op_simples, apuracao = "2", None
        elif regime in {"simples_nacional", "simples", "me_epp", "me/epp"}:
            op_simples, apuracao = "3", "1"
        else:
            raise ErroDPS("Regime tributário incompatível com a opção pelo Simples Nacional.")
    else:
        op_simples, apuracao = "1", None

    raw_especial = str(config.get("regime_especial_tributacao") or "").strip().lower()
    especiais = {
        "": "0", "0": "0", "nenhum": "0", "1": "1", "ato_cooperado": "1",
        "2": "2", "estimativa": "2", "3": "3", "microempresa_municipal": "3",
        "4": "4", "notario_registrador": "4", "5": "5", "profissional_autonomo": "5",
        "6": "6", "sociedade_profissionais": "6", "9": "9", "outros": "9",
    }
    if raw_especial not in especiais:
        raise ErroDPS("Regime especial de tributação não possui código nacional válido.")
    return op_simples, apuracao, especiais[raw_especial]


def _pessoa_opcional(pai, tag: str, documento, nome, fone, papel: str) -> None:
    documento = _digits(documento)
    nome = " ".join(str(nome or "").split())
    if not documento and not nome:
        return
    if len(documento) not in (11, 14) or not nome:
        raise ErroDPS(f"CPF/CNPJ e razão social do {papel} precisam estar preenchidos no cadastro.")
    if len(nome) > 300:
        raise ErroDPS(f"Razão social do {papel} passa de 300 caracteres.")
    pessoa = _add(pai, tag)
    _add(pessoa, "CNPJ" if len(documento) == 14 else "CPF", documento)
    _add(pessoa, "xNome", nome)
    telefone = _digits(fone)
    if telefone and not re.fullmatch(r"\d{6,20}", telefone):
        raise ErroDPS(f"Telefone do {papel} deve ter entre 6 e 20 dígitos.")
    if telefone:
        _add(pessoa, "fone", telefone)


def construir_dps(nota: dict, tenant: dict, config: dict, agora: datetime | None = None) -> bytes:
    """Constrói uma DPS básica doméstica; decisões fiscais avançadas não são inferidas."""
    documento_prest = _digits(tenant.get("cnpj") or tenant.get("cpf"))
    documento_toma = _digits(nota.get("tomador_cnpj_cpf"))
    municipio = _digits(tenant.get("municipio_ibge_codigo"))
    local = municipio
    trib_nac = _digits(nota.get("codigo_tributacao_nacional"))
    trib_mun = _digits(nota.get("codigo_servico"))
    nbs = _digits(nota.get("codigo_nbs"))
    obrigatorios = {
        "Razão social do prestador": tenant.get("razao_social"),
        "Razão social do tomador": nota.get("tomador_razao_social"),
        "Descrição do serviço": nota.get("descricao_servico"),
        "Competência": nota.get("competencia"),
    }
    faltantes = [nome for nome, valor in obrigatorios.items() if not valor]
    if faltantes:
        raise ErroDPS("Campos obrigatórios ausentes: " + ", ".join(faltantes) + ".")
    if len(documento_toma) not in (11, 14):
        raise ErroDPS("CPF/CNPJ do tomador é obrigatório e deve ter 11 ou 14 dígitos.")
    if len(trib_nac) != 6:
        raise ErroDPS("Código de tributação nacional deve conter 6 dígitos.")
    if trib_mun and len(trib_mun) != 3:
        raise ErroDPS("Código de tributação municipal, quando informado, deve conter 3 dígitos.")
    if nbs and len(nbs) != 9:
        raise ErroDPS("Código NBS, quando informado, deve conter 9 dígitos.")
    if len(local) != 7:
        raise ErroDPS("Município do prestador deve conter 7 dígitos.")

    serie, numero = str(nota["serie_dps"]), str(nota["numero_dps"])
    id_dps = gerar_id_dps(municipio, documento_prest, serie, numero)
    ambiente = str(config.get("ambiente") or "homologacao")
    if ambiente not in {"homologacao", "producao"}:
        raise ErroDPS("Ambiente fiscal inválido.")
    dh_emi = _data_emissao(agora)
    competencia = nota["competencia"].isoformat() if hasattr(nota["competencia"], "isoformat") else str(nota["competencia"])
    op_simples, apuracao, especial = _codigo_regime(config)

    root = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS}, versao="1.01")
    inf = _add(root, "infDPS")
    inf.set("Id", id_dps)
    # NT 009 (produção restrita desde ~out/2026; produção a partir de 01/12/2026):
    # finNFSe passa a ser filho direto de infDPS, obrigatório, antes de cLocEmi.
    # 0 = NFS-e regular. Sem esse campo a Sefin rejeita com E1235.
    cabecalho = [
        ("tpAmb", "2" if ambiente == "homologacao" else "1"),
        ("dhEmi", dh_emi),
        ("verAplic", "DropNexo-1.0"),
        ("serie", serie),
        ("nDPS", numero),
        ("dCompet", competencia),
        ("tpEmit", "1"),
    ]
    if ambiente == "homologacao":
        cabecalho.append(("finNFSe", "0"))
    cabecalho.append(("cLocEmi", municipio))
    for nome, valor in cabecalho:
        _add(inf, nome, valor)

    prest = _add(inf, "prest")
    _add(prest, "CNPJ" if len(documento_prest) == 14 else "CPF", documento_prest)
    reg = _add(prest, "regTrib")
    _add(reg, "opSimpNac", op_simples)
    if apuracao:
        _add(reg, "regApTribSN", apuracao)
    _add(reg, "regEspTrib", especial)

    toma = _add(inf, "toma")
    _add(toma, "CNPJ" if len(documento_toma) == 14 else "CPF", documento_toma)
    _add(toma, "xNome", nota["tomador_razao_social"])
    _pessoa_opcional(
        inf, "interm",
        nota.get("intermediario_cnpj_cpf"),
        nota.get("intermediario_razao_social"),
        nota.get("intermediario_fone"),
        "intermediário",
    )

    serv = _add(inf, "serv")
    _add(_add(serv, "locPrest"), "cLocPrestacao", local)
    cserv = _add(serv, "cServ")
    _add(cserv, "cTribNac", trib_nac)
    if trib_mun:
        _add(cserv, "cTribMun", trib_mun)
    descricao = " ".join(str(nota.get("descricao_servico") or "").split())
    observacoes = " ".join(str(nota.get("observacoes") or "").split())
    texto = observacoes or descricao
    if len(texto) > 2000:
        raise ErroDPS("Descrição do serviço passa de 2000 caracteres.")
    _add(cserv, "xDescServ", texto)
    if nbs:
        _add(cserv, "cNBS", nbs)

    valores = _add(inf, "valores")
    vserv = _add(valores, "vServPrest")
    valor = Decimal(str(nota["valor_servico"])).quantize(Decimal("0.01"))
    if valor <= 0:
        raise ErroDPS("Valor do serviço deve ser maior que zero.")
    _add(vserv, "vServ", f"{valor:.2f}")
    trib = _add(valores, "trib")
    trib_municipal = _add(trib, "tribMun")
    _add(trib_municipal, "tribISSQN", "1")
    _add(trib_municipal, "tpRetISSQN", "2" if nota.get("iss_retido") else "1")
    aliquota = Decimal(str(nota.get("aliquota_iss") or 0))
    if aliquota:
        _add(trib_municipal, "pAliq", f"{aliquota:.2f}")
    tot = _add(trib, "totTrib")
    percentual_sn = config.get("percentual_tributos_sn")
    if config.get("optante_simples") and percentual_sn not in (None, ""):
        percentual = Decimal(str(percentual_sn)).quantize(Decimal("0.01"))
        if percentual < 0 or percentual > Decimal("99.99"):
            raise ErroDPS("Percentual aproximado do Simples deve ficar entre 0 e 99,99.")
        if percentual > 0:
            _add(tot, "pTotTribSN", f"{percentual:.2f}")
        else:
            _add(tot, "indTotTrib", "0")
    else:
        _add(tot, "indTotTrib", "0")
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def validar_xml(xml: bytes, ambiente: str, leiaute: str = "DPS_v1.01.xsd") -> None:
    pasta = "producao_restrita/1.01" if ambiente == "homologacao" else "1.01"
    schema_path = SCHEMAS / pasta / leiaute
    schema = etree.XMLSchema(etree.parse(str(schema_path)))
    documento = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    if not schema.validate(documento):
        erros = "; ".join(str(item.message) for item in schema.error_log)
        raise ErroDPS(f"XML inválido no XSD {pasta}: {erros}")


def construir_cancelamento(chave: str, cnpj: str, ambiente: str, codigo: str, motivo: str, agora: datetime | None = None) -> bytes:
    """Pedido de cancelamento e101101. A própria empresa é o emitente."""
    chave = _digits(chave)
    cnpj = _digits(cnpj)
    if len(chave) != 50:
        raise ErroDPS("Chave da NFS-e deve ter 50 dígitos.")
    if len(cnpj) != 14:
        raise ErroDPS("CNPJ do prestador deve ter 14 dígitos.")
    if ambiente not in {"homologacao", "producao"}:
        raise ErroDPS("Ambiente fiscal inválido.")
    if str(codigo) not in {"1", "2", "9"}:
        raise ErroDPS("Motivo de cancelamento inválido.")
    texto = " ".join(str(motivo or "").split())
    if len(texto) < 15 or len(texto) > 255:
        raise ErroDPS("A justificativa do cancelamento deve ter entre 15 e 255 caracteres.")
    root = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS}, versao="1.01")
    inf = _add(root, "infPedReg")
    inf.set("Id", f"PRE{chave}101101")
    _add(inf, "tpAmb", "2" if ambiente == "homologacao" else "1")
    _add(inf, "verAplic", "H74-1.0")
    _add(inf, "dhEvento", _data_emissao(agora))
    _add(inf, "CNPJAutor", cnpj)
    _add(inf, "chNFSe", chave)
    evento = _add(inf, "e101101")
    _add(evento, "xDesc", "Cancelamento de NFS-e")
    _add(evento, "cMotivo", str(codigo))
    _add(evento, "xMotivo", texto)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def assinar_dps(xml: bytes, pfx: bytes, senha: str, tag: str = "infDPS") -> bytes:
    try:
        chave, certificado, _ = pkcs12.load_key_and_certificates(
            pfx, senha.encode("utf-8") if senha else None
        )
    except Exception as exc:
        raise ErroDPS("Não foi possível abrir o certificado A1.") from exc
    if chave is None or certificado is None:
        raise ErroDPS("Certificado A1 não contém chave privada e certificado.")
    root = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    inf = root.find(f"{{{NS}}}{tag}")
    if inf is None or not inf.get("Id"):
        raise ErroDPS(f"{tag}/Id não encontrado para assinatura.")

    signature = etree.Element(f"{{{DS}}}Signature", nsmap={None: DS})
    signed_info = etree.SubElement(signature, f"{{{DS}}}SignedInfo")
    etree.SubElement(signed_info, f"{{{DS}}}CanonicalizationMethod", Algorithm=C14N_EXCLUSIVE)
    etree.SubElement(signed_info, f"{{{DS}}}SignatureMethod", Algorithm=RSA_SHA256)
    reference = etree.SubElement(signed_info, f"{{{DS}}}Reference", URI=f"#{inf.get('Id')}")
    transforms = etree.SubElement(reference, f"{{{DS}}}Transforms")
    etree.SubElement(transforms, f"{{{DS}}}Transform", Algorithm=ENVELOPED)
    etree.SubElement(transforms, f"{{{DS}}}Transform", Algorithm=C14N_EXCLUSIVE)
    etree.SubElement(reference, f"{{{DS}}}DigestMethod", Algorithm=SHA256)
    digest = hashlib.sha256(etree.tostring(inf, method="c14n", exclusive=True)).digest()
    etree.SubElement(reference, f"{{{DS}}}DigestValue").text = base64.b64encode(digest).decode("ascii")
    assinatura = chave.sign(
        etree.tostring(signed_info, method="c14n", exclusive=True),
        padding.PKCS1v15(), hashes.SHA256(),
    )
    etree.SubElement(signature, f"{{{DS}}}SignatureValue").text = base64.b64encode(assinatura).decode("ascii")
    key_info = etree.SubElement(signature, f"{{{DS}}}KeyInfo")
    x509_data = etree.SubElement(key_info, f"{{{DS}}}X509Data")
    der = certificado.public_bytes(serialization.Encoding.DER)
    etree.SubElement(x509_data, f"{{{DS}}}X509Certificate").text = base64.b64encode(der).decode("ascii")
    root.insert(root.index(inf) + 1, signature)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def gzip_b64(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml, mtime=0)).decode("ascii")


def gunzip_b64(valor: str) -> bytes:
    try:
        return gzip.decompress(base64.b64decode(valor, validate=True))
    except Exception as exc:
        raise ErroDPS("Conteúdo XML compactado/base64 inválido na resposta.") from exc
