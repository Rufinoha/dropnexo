"""Impressão da NFS-e a partir do XML autorizado."""
from __future__ import annotations

import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fitz
import qrcode
from lxml import etree

PRETO = (0, 0, 0)
# Code 128, índices 0–105. O padrão de parada é acrescentado na hora de desenhar.
_BARRAS = (
    "11011001100", "11001101100", "11001100110", "10010011000", "10010001100",
    "10001001100", "10011001000", "10011000100", "10001100100", "11001001000",
    "11001000100", "11000100100", "10110011100", "10011011100", "10011001110",
    "10111001100", "10011101100", "10011100110", "11001110010", "11001011100",
    "11001001110", "11011100100", "11001110100", "11101101110", "11101001100",
    "11100101100", "11100100110", "11101100100", "11100110100", "11100110010",
    "11011011000", "11011000110", "11000110110", "10100011000", "10001011000",
    "10001000110", "10110001000", "10001101000", "10001100010", "11010001000",
    "11000101000", "11000100010", "10110111000", "10110001110", "10001101110",
    "10111011000", "10111000110", "10001110110", "11101110110", "11010001110",
    "11000101110", "11011101000", "11011100010", "11011101110", "11101011000",
    "11101000110", "11100010110", "11101101000", "11101100010", "11100011010",
    "11101111010", "11001000010", "11110001010", "10100110000", "10100001100",
    "10010110000", "10010000110", "10000101100", "10000100110", "10110010000",
    "10110000100", "10011010000", "10011000010", "10000110100", "10000110010",
    "11000010010", "11001010000", "11110111010", "11000010100", "10001111010",
    "10100111100", "10010111100", "10010011110", "10111100100", "10011110100",
    "10011110010", "11110100100", "11110010100", "11110010010", "11011011110",
    "11011110110", "11110110110", "10101111000", "10100011110", "10001011110",
    "10111101000", "10111100010", "11110101000", "11110100010", "10111011110",
    "10111101110", "11101011110", "11110101110", "11010000100", "11010010000",
    "11010011100",
)
_PARADA = "1100011101011"

SIMPLES = {
    "1": "Não optante do Simples Nacional",
    "2": "Optante - MEI",
    "3": "Optante - ME/EPP",
}
APURACAO_SN = {
    "1": "Federais e ISS pelo Simples",
    "2": "Federais pelo Simples e ISS fora",
    "3": "Federais e ISS fora do Simples",
}
ISS = {
    "1": "Operação tributável",
    "2": "Imunidade",
    "3": "Exportação",
    "4": "Não incidência",
}
RETENCAO_ISS = {
    "1": "Não retido",
    "2": "Retido pelo tomador",
    "3": "Retido pelo intermediário",
}
RETENCAO_PIS = {
    "0": "PIS/COFINS/CSLL não retidos",
    "1": "PIS/COFINS retidos",
    "2": "PIS/COFINS não retidos",
    "3": "PIS/COFINS/CSLL retidos",
    "4": "PIS/COFINS retidos, CSLL não",
    "5": "PIS retido",
    "6": "COFINS retido",
    "7": "COFINS/CSLL retidos",
    "8": "CSLL retido",
    "9": "PIS/CSLL retidos",
}
_UF_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


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


def _bruto(pai, nome: str) -> str:
    item = _filho(pai, nome)
    if item is None or not (item.text or "").strip():
        return ""
    return " ".join(item.text.split())


def _doc(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return valor


def _data(valor: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor or ""):
        ano, mes, dia = valor.split("-")
        return f"{dia}/{mes}/{ano}"
    if valor and "T" in valor:
        data, hora = valor.split("T", 1)
        ano, mes, dia = data.split("-")
        return f"{dia}/{mes}/{ano} {hora[:8]}"
    return valor


def _moeda(valor: str) -> str:
    if not valor:
        return ""
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        return valor
    texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _pct(valor: str) -> str:
    if not valor:
        return ""
    return f"{valor.replace('.', ',')}%"


def _valor_aliq(valor: str, aliquota: str) -> str:
    return " - ".join(parte for parte in (_moeda(valor), _pct(aliquota)) if parte)


def _cep(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 8:
        return f"{digitos[:5]}-{digitos[5:]}"
    return valor


def _juntar(*partes: str) -> str:
    return ", ".join(parte for parte in partes if parte)


def _fone(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return valor


def _ie(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 12 and digitos == re.sub(r"\s", "", valor or ""):
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}.{digitos[9:]}"
    return valor


def _uf_ibge(codigo: str) -> str:
    digitos = re.sub(r"\D", "", codigo or "")
    return _UF_IBGE.get(digitos[:2], "") if len(digitos) >= 2 else ""


def _parte(no) -> dict:
    """Pessoa opcional da NFS-e. Sem o grupo no XML, os campos ficam vazios."""
    vazio = {chave: "" for chave in ("nome", "endereco", "cidade", "cep", "doc", "ie", "pais", "fone")}
    if no is None:
        return vazio
    end = _filho(no, "end")
    nac = _filho(end, "endNac") if end is not None else None
    ext = _filho(end, "endExt") if end is not None else None
    cidade = _bruto(end, "xMun") or _bruto(ext, "xCidade")
    uf = _bruto(end, "UF") or _bruto(ext, "xEstProvReg") or _uf_ibge(_bruto(nac, "cMun"))
    if cidade and uf:
        cidade = f"{cidade} / {uf}"
    elif uf:
        cidade = uf
    return {
        "nome": _bruto(no, "xNome"),
        "endereco": _juntar(
            _juntar(_bruto(end, "xLgr"), _bruto(end, "nro")),
            _bruto(end, "xCpl"),
            _bruto(end, "xBairro"),
        ),
        "cidade": cidade,
        "cep": _cep(_bruto(nac, "CEP") or _bruto(ext, "cEndPost")),
        "doc": _doc(_bruto(no, "CNPJ") or _bruto(no, "CPF") or _bruto(no, "NIF")),
        "ie": _ie(_bruto(no, "IE") or _bruto(end, "IE")),
        "pais": _bruto(end, "xPais") or _bruto(ext, "xPais") or _bruto(ext, "cPais"),
        "fone": _fone(_bruto(no, "fone")),
    }


def _completar_parte(parte: dict, nota: dict, prefixo: str) -> dict:
    """Preenche com o cadastro o que o XML não trouxe."""
    if not parte["nome"]:
        parte["nome"] = str(nota.get(f"{prefixo}_nome") or "").strip()
    if not parte["doc"]:
        parte["doc"] = _doc(str(nota.get(f"{prefixo}_doc") or ""))
    if not parte["endereco"]:
        parte["endereco"] = _juntar(
            _juntar(
                str(nota.get(f"{prefixo}_logradouro") or "").strip(),
                str(nota.get(f"{prefixo}_numero") or "").strip(),
            ),
            str(nota.get(f"{prefixo}_complemento") or "").strip(),
            str(nota.get(f"{prefixo}_bairro") or "").strip(),
        )
    if not parte["cidade"]:
        cidade = str(nota.get(f"{prefixo}_cidade") or "").strip()
        uf = str(nota.get(f"{prefixo}_uf") or "").strip()
        parte["cidade"] = f"{cidade} / {uf}" if cidade and uf else cidade or uf
    if not parte["cep"]:
        parte["cep"] = _cep(str(nota.get(f"{prefixo}_cep") or ""))
    if not parte["fone"]:
        parte["fone"] = _fone(str(nota.get(f"{prefixo}_fone") or ""))
    if not parte["ie"]:
        parte["ie"] = _ie(str(nota.get(f"{prefixo}_ie") or ""))
    return parte


def _grupos(chave: str) -> str:
    digitos = re.sub(r"\D", "", chave or "")
    return " ".join(digitos[i:i + 4] for i in range(0, len(digitos), 4))


def _extrair(xml: bytes | None, nota: dict) -> dict:
    raiz = None
    if xml:
        raiz = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    inf = _primeiro(raiz, "infNFSe")
    dps = _primeiro(raiz, "infDPS")
    emit = _filho(inf, "emit")
    ender = _filho(emit, "enderNac")
    toma = _filho(dps, "toma")
    toma_end = _filho(toma, "end")
    toma_nac = _filho(toma_end, "endNac") if toma_end is not None else None
    serv = _filho(dps, "serv")
    cserv = _filho(serv, "cServ")
    loc = _filho(serv, "locPrest")
    valores_dps = _filho(dps, "valores")
    vserv = _filho(valores_dps, "vServPrest")
    trib = _filho(valores_dps, "trib")
    mun = _filho(trib, "tribMun")
    fed = _filho(trib, "tribFed")
    tot = _filho(trib, "totTrib")
    valores_nf = _filho(inf, "valores")
    reg = _filho(_filho(dps, "prest"), "regTrib")
    chave = str(nota.get("chave_nfse") or "")
    if inf is not None and (inf.get("Id") or "").startswith("NFS"):
        chave = inf.get("Id")[3:]
    endereco_prest = _juntar(
        _juntar(_bruto(ender, "xLgr"), _bruto(ender, "nro")),
        _bruto(ender, "xCpl"),
        _bruto(ender, "xBairro"),
    )
    cidade_prest = " / ".join(p for p in (_bruto(inf, "xLocEmi"), _bruto(ender, "UF")) if p)
    if _bruto(ender, "CEP"):
        cidade_prest = _juntar(cidade_prest, f"CEP {_cep(_bruto(ender, 'CEP'))}")
    endereco_toma = _juntar(
        _juntar(_bruto(toma_end, "xLgr"), _bruto(toma_end, "nro")),
        _bruto(toma_end, "xCpl"),
    )
    codigo_mun_toma = _bruto(toma_nac, "cMun")
    desc = _filho(valores_dps, "vDescCondIncond")
    ded = _filho(valores_dps, "vDedRed")
    pis = _filho(fed, "piscofins")
    monet = _filho(tot, "vTotTrib")
    perc = _filho(tot, "pTotTrib")
    ibs = _filho(inf, "IBSCBS")
    ibs_val = _filho(ibs, "valores")
    ibs_tot = _filho(ibs, "totCIBS")
    g_ibs = _filho(ibs_tot, "gIBS")
    g_cbs = _filho(ibs_tot, "gCBS")
    ibs_dps = _filho(dps, "IBSCBS")
    clas = _primeiro(ibs_dps, "gIBSCBS")
    dest_no = _filho(ibs_dps, "dest")
    if dest_no is None:
        dest_no = _filho(inf, "dest")
    interm_no = _filho(dps, "interm")
    if interm_no is None:
        interm_no = _filho(inf, "interm")
    dest = _completar_parte(_parte(dest_no), nota, "dest")
    interm = _completar_parte(_parte(interm_no), nota, "interm")
    deducao = _moeda(_bruto(ded, "vDR")) or _pct(_bruto(ded, "pDR")) or _moeda(_bruto(valores_nf, "vCalcDR"))
    valor_servico = _moeda(_bruto(vserv, "vServ") or str(nota.get("valor_servico") or ""))
    liquido = _moeda(_bruto(valores_nf, "vLiq")) or valor_servico
    municipio_nota = (
        str(nota.get("prestador_municipio") or "").strip()
        or str(nota.get("municipio_nome") or "").strip()
    )
    local_nota = str(nota.get("incidencia_municipio_ibge") or "").strip() or municipio_nota
    emissao_nota = _data(str(nota.get("dt_autorizacao") or nota.get("dt_atualizacao") or ""))
    aliquota_nota = str(nota.get("aliquota_iss") if nota.get("aliquota_iss") is not None else "").strip()
    if aliquota_nota:
        try:
            aliquota_nota = f"{Decimal(aliquota_nota):.2f}".rstrip("0").rstrip(".")
        except (InvalidOperation, ValueError, TypeError):
            pass
    return {
        "numero": _bruto(inf, "nNFSe") or str(nota.get("numero_nfse") or ""),
        "chave": chave,
        "municipio": _bruto(inf, "xLocEmi") or municipio_nota,
        "local": _bruto(inf, "xLocPrestacao") or _bruto(loc, "cLocPrestacao") or local_nota,
        "incidencia": _bruto(inf, "xLocIncid") or local_nota,
        "competencia": _data(_bruto(dps, "dCompet") or str(nota.get("competencia") or "")[:10]),
        "emissao": _data(_bruto(inf, "dhProc")) or emissao_nota,
        "emissao_dps": _data(_bruto(dps, "dhEmi")) or emissao_nota,
        "serie": _bruto(dps, "serie") or str(nota.get("serie_dps") or ""),
        "ndps": _bruto(dps, "nDPS") or str(nota.get("numero_dps") or ""),
        "prestador": _bruto(emit, "xNome") or str(nota.get("prestador_razao") or ""),
        "prestador_doc": _doc(_bruto(emit, "CNPJ") or _bruto(emit, "CPF") or str(nota.get("prestador_cnpj") or "")),
        "prestador_im": _bruto(emit, "IM"),
        "prestador_end": endereco_prest,
        "prestador_cidade": cidade_prest or municipio_nota,
        "prestador_email": _bruto(emit, "email"),
        "prestador_fone": _fone(_bruto(emit, "fone")),
        "tomador": _bruto(toma, "xNome") or str(nota.get("tomador_razao_social") or ""),
        "tomador_doc": _doc(_bruto(toma, "CNPJ") or _bruto(toma, "CPF") or str(nota.get("tomador_cnpj_cpf") or "")),
        "tomador_end": endereco_toma or _juntar(
            _juntar(str(nota.get("tomador_logradouro") or "").strip(), str(nota.get("tomador_numero") or "").strip()),
            str(nota.get("tomador_complemento") or "").strip(),
        ),
        "tomador_bairro": _bruto(toma_end, "xBairro") or str(nota.get("tomador_bairro") or "").strip(),
        "tomador_cep": _cep(_bruto(toma_nac, "CEP")) or _cep(str(nota.get("tomador_cep") or "")),
        "tomador_cidade": _bruto(toma_end, "xMun") or _bruto(toma, "xMun") or str(nota.get("tomador_cidade") or "").strip(),
        "tomador_uf": (
            _bruto(toma_end, "UF") or _bruto(toma, "UF") or _uf_ibge(codigo_mun_toma)
            or str(nota.get("tomador_uf") or "").strip().upper()
        ),
        "tomador_ie": _ie(_bruto(toma, "IE") or str(nota.get("tomador_ie") or "")),
        "tomador_fone": _fone(_bruto(toma, "fone") or str(nota.get("tomador_telefone") or "")),
        "dest_nome": dest["nome"],
        "dest_endereco": dest["endereco"],
        "dest_cidade": dest["cidade"],
        "dest_cep": dest["cep"],
        "dest_doc": dest["doc"],
        "dest_ie": dest["ie"],
        "dest_pais": dest["pais"],
        "dest_fone": dest["fone"],
        "interm_nome": interm["nome"],
        "interm_endereco": interm["endereco"],
        "interm_cidade": interm["cidade"],
        "interm_cep": interm["cep"],
        "interm_doc": interm["doc"],
        "interm_ie": interm["ie"],
        "interm_pais": interm["pais"],
        "interm_fone": interm["fone"],
        "trib_nac": _bruto(cserv, "cTribNac") or str(nota.get("codigo_tributacao_nacional") or ""),
        "trib_nac_desc": _bruto(inf, "xTribNac"),
        "trib_mun": _bruto(cserv, "cTribMun") or str(nota.get("codigo_servico") or ""),
        "trib_mun_desc": _bruto(inf, "xTribMun"),
        "nbs": _bruto(cserv, "cNBS") or str(nota.get("codigo_nbs") or ""),
        "nbs_desc": _bruto(inf, "xNBS"),
        "descricao": _bruto(cserv, "xDescServ") or str(nota.get("descricao_servico") or nota.get("observacoes") or ""),
        "valor": valor_servico,
        "liquido": liquido,
        "base": _moeda(_bruto(valores_nf, "vBC")) or valor_servico,
        "iss_valor": _moeda(_bruto(valores_nf, "vISSQN")),
        "retencoes": _moeda(_bruto(valores_nf, "vTotalRet")),
        "iss_tipo": ISS.get(_bruto(mun, "tribISSQN"), "") or ("Operação tributável" if nota.get("aliquota_iss") is not None else ""),
        "iss_ret": RETENCAO_ISS.get(_bruto(mun, "tpRetISSQN"), "") or (
            "Retido pelo tomador" if nota.get("iss_retido") else "Não retido"
        ),
        "aliquota": _bruto(mun, "pAliq") or _bruto(valores_nf, "pAliqAplic") or aliquota_nota,
        "simples": SIMPLES.get(_bruto(reg, "opSimpNac"), ""),
        "apuracao": APURACAO_SN.get(_bruto(reg, "regApTribSN"), ""),
        "percentual_sn": _bruto(tot, "pTotTribSN"),
        "trib_fed": _moeda(_bruto(monet, "vTotTribFed")) or _pct(_bruto(perc, "pTotTribFed")),
        "trib_est": _moeda(_bruto(monet, "vTotTribEst")) or _pct(_bruto(perc, "pTotTribEst")),
        "trib_mun_tot": _moeda(_bruto(monet, "vTotTribMun")) or _pct(_bruto(perc, "pTotTribMun")),
        "desc_incond": _moeda(_bruto(desc, "vDescIncond")),
        "desc_cond": _moeda(_bruto(desc, "vDescCond")),
        "deducao": deducao,
        "pis": _valor_aliq(_bruto(pis, "vPis"), _bruto(pis, "pAliqPis")),
        "cofins": _valor_aliq(_bruto(pis, "vCofins"), _bruto(pis, "pAliqCofins")),
        "pis_cst": _bruto(pis, "CST"),
        "pis_ret": RETENCAO_PIS.get(_bruto(pis, "tpRetPisCofins"), ""),
        "ibs_cst": _bruto(clas, "CST"),
        "ibs_class": _bruto(clas, "cClassTrib"),
        "ibs_local": _bruto(ibs, "xLocalidadeIncid"),
        "ibs_base": _moeda(_bruto(ibs_val, "vBC")),
        "ibs_aliq_mun": _pct(_bruto(_filho(ibs_val, "mun"), "pAliqEfetMun")),
        "ibs_aliq_uf": _pct(_bruto(_filho(ibs_val, "uf"), "pAliqEfetUF")),
        "ibs_aliq_cbs": _pct(_bruto(_filho(ibs_val, "fed"), "pAliqEfetCBS")),
        "ibs_mun": _moeda(_bruto(_filho(g_ibs, "gIBSMunTot"), "vIBSMun")),
        "ibs_uf": _moeda(_bruto(_filho(g_ibs, "gIBSUFTot"), "vIBSUF")),
        "ibs_cbs": _moeda(_bruto(g_cbs, "vCBS")),
        "ibs_total": _moeda(_bruto(g_ibs, "vIBSTot")),
        "ibs_nf": _moeda(_bruto(ibs_tot, "vTotNF")),
        "irrf": _moeda(_bruto(fed, "vRetIRRF")),
        "csll": _moeda(_bruto(fed, "vRetCSLL")),
        "inss": _moeda(_bruto(fed, "vRetCP")),
        "extra": _bruto(inf, "xOutInf"),
        "cancelada": str(nota.get("status") or "") == "cancelada",
    }


def _qr(chave: str) -> bytes:
    url = (
        f"https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave}"
        if chave else "https://www.nfse.gov.br/ConsultaPublica/"
    )
    imagem = qrcode.make(url)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def _logo() -> bytes | None:
    caminho = Path(__file__).resolve().parents[2] / "static" / "imge" / "logoh74.png"
    if not caminho.is_file():
        return None
    return caminho.read_bytes()


def _bits_code128(chave: str) -> str:
    digitos = re.sub(r"\D", "", chave or "")
    if len(digitos) < 2:
        return ""
    if len(digitos) % 2:
        digitos = "0" + digitos
    valores = [105]
    valores.extend(int(digitos[i:i + 2]) for i in range(0, len(digitos), 2))
    soma = valores[0]
    for indice, valor in enumerate(valores[1:], start=1):
        soma += indice * valor
    valores.append(soma % 103)
    return "".join(_BARRAS[valor] for valor in valores) + _PARADA


def _barras(pagina, retangulo: fitz.Rect, chave: str):
    bits = _bits_code128(chave)
    if not bits:
        return
    passo = retangulo.width / (len(bits) + 20)
    x = retangulo.x0 + 10 * passo
    indice = 0
    while indice < len(bits):
        if bits[indice] == "1":
            fim = indice + 1
            while fim < len(bits) and bits[fim] == "1":
                fim += 1
            pagina.draw_rect(
                fitz.Rect(x, retangulo.y0, x + (fim - indice) * passo, retangulo.y1),
                color=PRETO, fill=PRETO, width=0,
            )
            x += (fim - indice) * passo
            indice = fim
        else:
            x += passo
            indice += 1


def _caixa(pagina, x, y, w, h, espessura=0.55):
    pagina.draw_rect(fitz.Rect(x, y, x + w, y + h), color=PRETO, width=espessura)


def _picote(pagina, x, y, w):
    pagina.draw_line(
        fitz.Point(x, y), fitz.Point(x + w, y),
        color=PRETO, width=0.7, dashes="[2 1.6] 0",
    )


def _celula(pagina, x, y, w, h, rotulo, valor, tamanho=8, negrito=False, alinhar=0, espessura=0.55):
    _caixa(pagina, x, y, w, h, espessura)
    if rotulo:
        pagina.insert_text((x + 3, y + 6.2), str(rotulo).upper(), fontsize=4.6, fontname="helv", color=PRETO)
    texto = valor or ""
    if not texto:
        return
    fonte = "hebo" if negrito else "helv"
    limite = max(8, w - 6)
    while tamanho > 5.5 and fitz.get_text_length(texto, fontname=fonte, fontsize=tamanho) > limite:
        tamanho -= 0.3
    if alinhar == 1:
        _centralizar(pagina, x, y + h - 3.2, w, texto, tamanho, fonte)
        return
    if alinhar == 2:
        largura_texto = fitz.get_text_length(texto, fontname=fonte, fontsize=tamanho)
        pagina.insert_text(
            (x + w - 3 - largura_texto, y + h - 3.2),
            texto, fontsize=tamanho, fontname=fonte, color=PRETO,
        )
        return
    pagina.insert_text((x + 3, y + h - 3.2), texto, fontsize=tamanho, fontname=fonte, color=PRETO)


def _linha(pagina, x, y, w, h, campos, alinhar=0):
    total = sum(campo[2] for campo in campos) or 1
    cursor = x
    for indice, campo in enumerate(campos):
        rotulo, valor, peso = campo[:3]
        negrito = bool(campo[3]) if len(campo) > 3 else False
        tamanho = campo[4] if len(campo) > 4 else (9 if negrito else 7.5)
        largura = (x + w - cursor) if indice == len(campos) - 1 else w * peso / total
        _celula(
            pagina, cursor, y, largura, h, rotulo, valor,
            tamanho=tamanho, negrito=negrito, alinhar=alinhar,
            espessura=1.05 if negrito else 0.55,
        )
        cursor += largura


def _rotulo(pagina, x, y, w, h, rotulo, valor, tamanho=7.5, fonte="helv", alinhar=0):
    pagina.insert_text((x + 4, y + 7), str(rotulo).upper(), fontsize=4.6, fontname="helv", color=PRETO)
    texto = valor or "-"
    rect = fitz.Rect(x + 3, y + 8, x + w - 3, y + h - 1)
    if pagina.insert_textbox(rect, texto, fontsize=tamanho, fontname=fonte, color=PRETO, align=alinhar) < 0:
        pagina.insert_textbox(rect, texto, fontsize=6, fontname=fonte, color=PRETO, align=alinhar)


def _centralizar(pagina, x, y, w, texto, tamanho, fonte="hebo"):
    if not texto:
        return
    largura = fitz.get_text_length(texto, fontname=fonte, fontsize=tamanho)
    pagina.insert_text((x + max(0, (w - largura) / 2), y), texto, fontsize=tamanho, fontname=fonte, color=PRETO)


def _canhoto(pagina, dados: dict, nota: dict, esq: float, direita: float):
    largura = direita - esq
    y = 688
    _picote(pagina, esq, y, largura)
    prestador = dados["prestador"] or "O PRESTADOR"
    pagina.insert_textbox(
        fitz.Rect(esq, y + 3, direita, y + 22),
        f"RECEBEMOS DE {prestador} OS SERVIÇOS CONSTANTES DA NOTA FISCAL DE SERVIÇO ELETRÔNICA INDICADA NESTE CANHOTO.",
        fontsize=6, fontname="helv", color=PRETO, align=1,
    )
    topo, alto = y + 24, 78
    _caixa(pagina, esq, topo, largura, alto, 0.7)
    cortes = (esq + 122, esq + 252, esq + 332, esq + 478)
    for x in cortes:
        pagina.draw_line(fitz.Point(x, topo), fitz.Point(x, topo + alto), color=PRETO, width=0.5)
    pagina.draw_line(fitz.Point(esq, topo + 40), fitz.Point(cortes[0], topo + 40), color=PRETO, width=0.5)

    pagina.insert_text((esq + 4, topo + 10), "NOME", fontsize=5.2, fontname="helv", color=PRETO)
    pagina.draw_line(fitz.Point(esq + 28, topo + 22), fitz.Point(cortes[0] - 6, topo + 22), color=PRETO, width=0.4)
    pagina.insert_text((esq + 4, topo + 52), "RG", fontsize=5.2, fontname="helv", color=PRETO)
    pagina.draw_line(fitz.Point(esq + 18, topo + 64), fitz.Point(cortes[0] - 6, topo + 64), color=PRETO, width=0.4)

    _centralizar(pagina, cortes[0], topo + 12, cortes[1] - cortes[0], "ASSINATURA / CARIMBO", 5.4, "helv")

    pagina.insert_text((cortes[1] + 4, topo + 10), "NFS-e", fontsize=5, fontname="helv", color=PRETO)
    _centralizar(pagina, cortes[1], topo + 28, cortes[2] - cortes[1], dados["numero"] or "-", 12)
    pagina.insert_text((cortes[1] + 4, topo + 48), "SÉRIE DPS", fontsize=5, fontname="helv", color=PRETO)
    _centralizar(pagina, cortes[1], topo + 62, (cortes[2] - cortes[1]) / 2, dados["serie"] or "-", 8)
    pagina.insert_text((cortes[1] + 42, topo + 48), "DPS", fontsize=5, fontname="helv", color=PRETO)
    _centralizar(pagina, cortes[1] + 40, topo + 62, cortes[2] - cortes[1] - 40, dados["ndps"] or "-", 8)

    if dados["chave"]:
        _barras(pagina, fitz.Rect(cortes[2] + 6, topo + 14, cortes[3] - 6, topo + 48), dados["chave"])
        _centralizar(pagina, cortes[2], topo + 64, cortes[3] - cortes[2], _grupos(dados["chave"]), 3.6, "helv")

    pagina.insert_textbox(
        fitz.Rect(cortes[3] + 3, topo + 2, direita - 3, topo + 16),
        "DATA DO RECEBIMENTO", fontsize=5, fontname="helv", color=PRETO,
    )
    pagina.draw_line(fitz.Point(cortes[3] + 6, topo + 36), fitz.Point(direita - 6, topo + 36), color=PRETO, width=0.4)
    pagina.insert_text((cortes[3] + 4, topo + 50), "HORA", fontsize=5, fontname="helv", color=PRETO)
    pagina.draw_line(fitz.Point(cortes[3] + 24, topo + 64), fitz.Point(direita - 6, topo + 64), color=PRETO, width=0.4)

    rodape = "Documento auxiliar. A NFS-e oficial é o XML autorizado pela Sefin Nacional."
    if nota.get("modelo"):
        rodape = "MODELO DE LAYOUT, sem valor fiscal. " + rodape
    empresa = " - ".join(parte for parte in (dados["prestador"], dados["prestador_doc"] and f"CNPJ {dados['prestador_doc']}") if parte)
    pagina.insert_text((esq, topo + alto + 11), rodape, fontsize=5.4, fontname="helv", color=PRETO)
    if empresa:
        largura_empresa = fitz.get_text_length(empresa, fontname="helv", fontsize=5.4)
        pagina.insert_text((direita - largura_empresa, topo + alto + 22), empresa, fontsize=5.4, fontname="helv", color=PRETO)


def gerar_danfse(xml: bytes | None, nota: dict) -> bytes:
    d = _extrair(xml, nota)
    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    esq, direita = 14.0, 581.0
    largura = direita - esq
    y = 14.0
    alt_cab = 104.0
    alt_chave = 33.0
    x_meio = esq + 214
    x_qr = direita - 84
    _caixa(pagina, esq, y, x_meio - esq, alt_cab, 0.8)
    _caixa(pagina, x_meio, y, x_qr - x_meio, alt_cab, 0.8)
    _caixa(pagina, x_qr, y, direita - x_qr, 16, 0.8)
    _caixa(pagina, x_qr, y + 16, direita - x_qr, alt_cab - 16, 0.8)

    logo = _logo()
    if logo:
        pagina.insert_image(fitz.Rect(esq + 8, y + 5, esq + 168, y + 56), stream=logo, keep_proportion=True)
    cursor = y + (62 if logo else 14)
    cabecalho = [
        d["prestador"],
        _juntar(
            f"CNPJ {d['prestador_doc']}" if d["prestador_doc"] else "",
            f"IM {d['prestador_im']}" if d["prestador_im"] else "",
        ),
        d["prestador_end"],
        d["prestador_cidade"],
        _juntar(
            f"Fone {d['prestador_fone']}" if d["prestador_fone"] else "",
            d["prestador_email"],
        ),
    ]
    for indice, linha in enumerate(parte for parte in cabecalho if parte):
        pagina.insert_text(
            (esq + 8, cursor + indice * 9),
            linha,
            fontsize=8 if indice == 0 else 6.3,
            fontname="hebo" if indice == 0 else "helv",
            color=PRETO,
        )

    meio_w = x_qr - x_meio
    _centralizar(pagina, x_meio, y + 12, meio_w, "DANFSe", 13)
    _centralizar(pagina, x_meio, y + 22, meio_w, "DOCUMENTO AUXILIAR DA NFS-e", 5.5, "helv")
    if nota.get("modelo"):
        _centralizar(pagina, x_meio, y + 31, meio_w, "MODELO - SEM VALOR FISCAL", 5.8)
    elif d["cancelada"]:
        _centralizar(pagina, x_meio, y + 31, meio_w, "CANCELADA", 7)
    else:
        _centralizar(pagina, x_meio, y + 31, meio_w, d["municipio"], 6, "helv")
    grade_y = y + 34
    campos_cab = (
        ("NFS-e", d["numero"], 0.85, 9),
        ("Série", d["serie"], 0.65, 9),
        ("DPS", d["ndps"], 0.65, 9),
        ("Competência", d["competencia"], 1.05, 7),
        ("Emissão", d["emissao"], 1.45, 5.6),
    )
    cursor_x = x_meio
    soma_peso = sum(campo[2] for campo in campos_cab)
    for indice, (rotulo, valor, peso, tamanho) in enumerate(campos_cab):
        largura_campo = (x_qr - cursor_x) if indice == len(campos_cab) - 1 else meio_w * peso / soma_peso
        _caixa(pagina, cursor_x, grade_y, largura_campo, 22, 0.55)
        pagina.insert_text((cursor_x + 2, grade_y + 7), rotulo.upper(), fontsize=4.6, fontname="helv", color=PRETO)
        _centralizar(pagina, cursor_x, grade_y + 18, largura_campo, valor or "", tamanho)
        cursor_x += largura_campo
    if d["chave"]:
        _barras(pagina, fitz.Rect(x_meio + 6, grade_y + 25, x_qr - 6, y + alt_cab - 4), d["chave"])

    _centralizar(pagina, x_qr, y + 11, direita - x_qr, "FOLHA 1/1", 5.5, "helv")
    if d["chave"]:
        lado = min(58, direita - x_qr - 12, alt_cab - 22)
        qr_x = x_qr + (direita - x_qr - lado) / 2
        qr_y = y + 16 + (alt_cab - 16 - lado) / 2
        pagina.insert_image(fitz.Rect(qr_x, qr_y, qr_x + lado, qr_y + lado), stream=_qr(d["chave"]))

    y += alt_cab
    metade = (x_meio - esq) / 2
    chave_txt = _grupos(d["chave"]) or "-"
    largura_chave = direita - x_meio
    miolo = largura_chave - 8
    medida = fitz.get_text_length(chave_txt, fontname="helv", fontsize=10) or miolo
    tamanho_chave = min(16, 10 * miolo / medida)
    faixa = (
        (esq, metade, "Local da prestação", d["local"] or "-", 7.5, "hebo"),
        (esq + metade, x_meio - (esq + metade), "Município emissor", d["municipio"] or "-", 7.5, "hebo"),
        (x_meio, largura_chave, "Chave de acesso", chave_txt, tamanho_chave, "helv"),
    )
    for esquerda, largura_faixa, rotulo, valor, tamanho, fonte in faixa:
        _caixa(pagina, esquerda, y, largura_faixa, alt_chave, 0.7)
        pagina.insert_text((esquerda + 4, y + 8), rotulo.upper(), fontsize=5, fontname="helv", color=PRETO)
        pagina.insert_text(
            (esquerda + 4, y + alt_chave - 5),
            valor, fontsize=tamanho, fontname=fonte, color=PRETO,
        )
    y += alt_chave

    alto_toma, faixa_toma = 74, 22
    _caixa(pagina, esq, y, largura, alto_toma, 0.9)
    pagina.insert_text((esq + 5, y + 8), "TOMADOR DO SERVIÇO", fontsize=5.5, fontname="hebo", color=PRETO)
    pagina.insert_text((esq + 5, y + 17), "RAZÃO SOCIAL", fontsize=4.6, fontname="helv", color=PRETO)
    nome_toma = d["tomador"] or "-"
    tamanho_nome = 10
    while tamanho_nome > 7 and fitz.get_text_length(nome_toma, fontname="hebo", fontsize=tamanho_nome) > largura - 12:
        tamanho_nome -= 0.4
    pagina.insert_text((esq + 5, y + 28), nome_toma, fontsize=tamanho_nome, fontname="hebo", color=PRETO)
    corte_toma = y + 32
    pagina.draw_line(fitz.Point(esq, corte_toma), fitz.Point(direita, corte_toma), color=PRETO, width=0.55)
    pagina.draw_line(
        fitz.Point(esq, corte_toma + faixa_toma),
        fitz.Point(direita, corte_toma + faixa_toma),
        color=PRETO, width=0.45,
    )

    def _colunas_toma(y0, campos):
        total = sum(campo[2] for campo in campos) or 1
        cursor = esq
        for indice, campo in enumerate(campos):
            rotulo_campo, valor_campo, peso = campo[:3]
            tamanho = campo[3] if len(campo) > 3 else 7.5
            fonte = campo[4] if len(campo) > 4 else "helv"
            alinhar = campo[5] if len(campo) > 5 else 0
            largura_campo = (direita - cursor) if indice == len(campos) - 1 else largura * peso / total
            if indice:
                pagina.draw_line(
                    fitz.Point(cursor, y0), fitz.Point(cursor, y0 + faixa_toma),
                    color=PRETO, width=0.45,
                )
            _rotulo(
                pagina, cursor, y0, largura_campo, faixa_toma,
                rotulo_campo, valor_campo, tamanho, fonte, alinhar,
            )
            cursor += largura_campo

    _colunas_toma(corte_toma, (
        ("Endereço", d["tomador_end"], 2.35),
        ("Bairro", d["tomador_bairro"], 1.15),
        ("CEP", d["tomador_cep"], 0.75),
        ("Fone", d["tomador_fone"], 1.05),
    ))
    _colunas_toma(corte_toma + faixa_toma, (
        ("Município", d["tomador_cidade"], 1.85, 8, "hebo"),
        ("UF", d["tomador_uf"], 0.42, 9, "hebo", 1),
        ("CPF/CNPJ", d["tomador_doc"], 1.35, 8, "hebo"),
        ("IE", d["tomador_ie"], 1.1, 8, "helv"),
    ))
    y += alto_toma

    def _tem_parte(prefixo):
        return any(
            d[f"{prefixo}_{campo}"]
            for campo in ("nome", "endereco", "cidade", "cep", "doc", "ie", "pais", "fone")
        )

    dest_ok, interm_ok = _tem_parte("dest"), _tem_parte("interm")
    alto_parte = 62 if dest_ok or interm_ok else 15
    meio_parte = esq + largura / 2
    _caixa(pagina, esq, y, largura, alto_parte, 0.9)
    pagina.draw_line(fitz.Point(meio_parte, y), fitz.Point(meio_parte, y + alto_parte), color=PRETO, width=0.7)

    def _caber(x0, y0, texto, limite):
        tamanho = 6.1
        while tamanho > 4.6 and fitz.get_text_length(texto, fontname="helv", fontsize=tamanho) > limite:
            tamanho -= 0.2
        pagina.insert_text((x0, y0), texto, fontsize=tamanho, fontname="helv", color=PRETO)

    def _bloco_parte(x, w, titulo, prefixo, informado):
        if not informado:
            pagina.insert_text(
                (x + 4, y + 10.5), f"{titulo} = Não Informado",
                fontsize=6.2, fontname="hebo", color=PRETO,
            )
            return
        pagina.insert_text((x + 4, y + 8), titulo, fontsize=5.4, fontname="hebo", color=PRETO)
        nome = d[f"{prefixo}_nome"]
        tamanho_parte = 8
        while nome and tamanho_parte > 6 and fitz.get_text_length(nome, fontname="hebo", fontsize=tamanho_parte) > w - 10:
            tamanho_parte -= 0.3
        if nome:
            pagina.insert_text((x + 4, y + 18), nome, fontsize=tamanho_parte, fontname="hebo", color=PRETO)
        metade_texto = w * 0.48
        _caber(x + 4, y + 28, f"ENDEREÇO: {d[f'{prefixo}_endereco']}".rstrip(), w - 10)
        _caber(x + 4, y + 37, f"CIDADE: {d[f'{prefixo}_cidade']}".rstrip(), metade_texto)
        _caber(x + w * 0.50, y + 37, f"CEP: {d[f'{prefixo}_cep']}".rstrip(), metade_texto)
        _caber(x + 4, y + 46, f"CNPJ/CPF: {d[f'{prefixo}_doc']}".rstrip(), metade_texto)
        _caber(x + w * 0.50, y + 46, f"IE: {d[f'{prefixo}_ie']}".rstrip(), metade_texto)
        _caber(x + 4, y + 55, f"PAÍS: {d[f'{prefixo}_pais']}".rstrip(), metade_texto)
        _caber(x + w * 0.50, y + 55, f"FONE: {d[f'{prefixo}_fone']}".rstrip(), metade_texto)

    _bloco_parte(esq, meio_parte - esq, "DESTINATÁRIO DA OPERAÇÃO", "dest", dest_ok)
    _bloco_parte(meio_parte, direita - meio_parte, "INTERMEDIÁRIO DA OPERAÇÃO", "interm", interm_ok)
    y += alto_parte

    def _reais(valor):
        return valor or "R$ 0,00"

    def _pct_ou_zero(valor):
        return valor or "0,00%"

    def _traco(valor):
        return valor or "-"

    def _quebrar(texto, fonte, tamanho, largura_texto):
        palavras = " ".join(str(texto or "").split()).split(" ")
        if not palavras or palavras == [""]:
            return []
        linhas, atual = [], ""
        for palavra in palavras:
            candidato = f"{atual} {palavra}".strip()
            if fitz.get_text_length(candidato, fontname=fonte, fontsize=tamanho) <= largura_texto:
                atual = candidato
                continue
            if atual:
                linhas.append(atual)
            if fitz.get_text_length(palavra, fontname=fonte, fontsize=tamanho) <= largura_texto:
                atual = palavra
                continue
            pedaco = ""
            for letra in palavra:
                if fitz.get_text_length(pedaco + letra, fontname=fonte, fontsize=tamanho) <= largura_texto:
                    pedaco += letra
                else:
                    if pedaco:
                        linhas.append(pedaco)
                    pedaco = letra
            atual = pedaco
        if atual:
            linhas.append(atual)
        return linhas

    def _bloco_codigo(codigo, descricao, largura_texto):
        codigo = (codigo or "").strip()
        descricao = " ".join(str(descricao or "").split())
        separador = " - " if codigo and descricao else ""
        largura_prefixo = fitz.get_text_length(codigo, fontname="hebo", fontsize=11) if codigo else 0
        if separador:
            largura_prefixo += fitz.get_text_length(separador, fontname="helv", fontsize=9)
        resto = max(0, largura_texto - largura_prefixo)
        palavras = descricao.split(" ") if descricao else []
        primeira, usadas = "", 0
        if palavras and resto >= 8:
            atual = ""
            for indice, palavra in enumerate(palavras):
                candidato = f"{atual} {palavra}".strip()
                if fitz.get_text_length(candidato, fontname="helv", fontsize=9) <= resto:
                    atual = candidato
                    usadas = indice + 1
                    continue
                break
            primeira = atual
        restantes = " ".join(palavras[usadas:])
        linhas = _quebrar(restantes, "helv", 9, largura_texto) if restantes else []
        return codigo, separador, primeira, linhas, 18 + len(linhas) * 11 + 4

    campos_codigo = (
        ("Tributação nacional", d["trib_nac"], d["trib_nac_desc"], 1.45),
        ("NBS", d["nbs"], d["nbs_desc"], 1),
    )
    soma_codigo = sum(campo[3] for campo in campos_codigo)
    larguras_codigo = []
    cursor_codigo = esq
    for indice, campo in enumerate(campos_codigo):
        largura_campo = (direita - cursor_codigo) if indice == len(campos_codigo) - 1 else largura * campo[3] / soma_codigo
        larguras_codigo.append(largura_campo)
        cursor_codigo += largura_campo
    blocos_codigo = [
        _bloco_codigo(campo[1], campo[2], larguras_codigo[indice] - 8)
        for indice, campo in enumerate(campos_codigo)
    ]
    alto_codigo = max(bloco[4] for bloco in blocos_codigo)
    cursor_codigo = esq
    for indice, campo in enumerate(campos_codigo):
        largura_campo = larguras_codigo[indice]
        codigo, separador, primeira, linhas, _altura = blocos_codigo[indice]
        _caixa(pagina, cursor_codigo, y, largura_campo, alto_codigo, 0.55)
        pagina.insert_text(
            (cursor_codigo + 3, y + 6.2), campo[0].upper(),
            fontsize=4.6, fontname="helv", color=PRETO,
        )
        base = y + 18
        x_texto = cursor_codigo + 3
        if codigo:
            pagina.insert_text((x_texto, base), codigo, fontsize=11, fontname="hebo", color=PRETO)
            x_texto += fitz.get_text_length(codigo, fontname="hebo", fontsize=11)
        elif not primeira and not linhas:
            pagina.insert_text((x_texto, base), "-", fontsize=11, fontname="hebo", color=PRETO)
        if separador:
            pagina.insert_text((x_texto, base), separador, fontsize=9, fontname="helv", color=PRETO)
            x_texto += fitz.get_text_length(separador, fontname="helv", fontsize=9)
        if primeira:
            pagina.insert_text((x_texto, base), primeira, fontsize=9, fontname="helv", color=PRETO)
        for linha in linhas:
            base += 11
            pagina.insert_text((cursor_codigo + 3, base), linha, fontsize=9, fontname="helv", color=PRETO)
        cursor_codigo += largura_campo
    y += alto_codigo

    def _faixa(campos, altura=19, alinhar=2):
        nonlocal y
        _linha(pagina, esq, y, largura, altura, campos, alinhar=alinhar)
        y += altura

    def _categoria(titulo):
        nonlocal y
        _caixa(pagina, esq, y, largura, 9, 0.7)
        pagina.insert_text((esq + 4, y + 6.8), titulo, fontsize=6.2, fontname="hebo", color=PRETO)
        y += 9

    municipal = " - ".join(parte for parte in (d["trib_mun"], d["trib_mun_desc"]) if parte)
    iss = " - ".join(parte for parte in (d["iss_tipo"], d["iss_ret"]) if parte)
    aliquota = f"{d['aliquota'].replace('.', ',')}%" if d["aliquota"] else ""
    simples = f"{d['percentual_sn'].replace('.', ',')}%" if d["percentual_sn"] else ""
    _categoria("TRIBUTAÇÃO MUNICIPAL (ISSQN)")
    _celula(pagina, esq, y, largura, 19, "Código de tributação municipal", _traco(municipal), tamanho=7.5)
    y += 19
    _linha(pagina, esq, y, largura, 20, [
        ("Regime tributário", _traco(d["simples"]), 1.2),
        ("Apuração", _traco(d["apuracao"]), 1.15),
        ("ISSQN", _traco(iss), 1),
    ])
    y += 20
    _faixa([
        ("Base de cálculo", _reais(d["base"]), 1),
        ("Alíquota", _pct_ou_zero(aliquota), 1),
        ("Valor do ISS", _reais(d["iss_valor"]), 1),
        ("Dedução da base", _reais(d["deducao"]), 1),
    ])
    _categoria("TRIBUTAÇÃO FEDERAL (EXCETO CBS)")
    _faixa([
        ("IRRF retido", _reais(d["irrf"]), 1),
        ("CSLL retida", _reais(d["csll"]), 1),
        ("INSS retido", _reais(d["inss"]), 1),
        ("Tributos aprox. SN", _pct_ou_zero(simples), 1),
    ])
    _faixa([
        ("PIS", _reais(d["pis"]), 1),
        ("COFINS", _reais(d["cofins"]), 1),
        ("CST PIS/COFINS", _traco(d["pis_cst"]), 1),
        ("Retenção PIS/COFINS", _traco(d["pis_ret"]), 1),
    ])
    _faixa([
        ("Tributos federais", _reais(d["trib_fed"]), 1),
        ("Tributos estaduais", _reais(d["trib_est"]), 1),
        ("Tributos municipais", _reais(d["trib_mun_tot"]), 1),
        ("Total de retenções", _reais(d["retencoes"]), 1),
    ])
    _categoria("TRIBUTAÇÃO IBS/CBS")
    _faixa([
        ("CST", _traco(d["ibs_cst"]), 1),
        ("Classificação", _traco(d["ibs_class"]), 1),
        ("Local de incidência", _traco(d["ibs_local"]), 1),
        ("Base de cálculo", _reais(d["ibs_base"]), 1),
    ])
    _faixa([
        ("Alíquota IBS municipal", _pct_ou_zero(d["ibs_aliq_mun"]), 1),
        ("Alíquota IBS estadual", _pct_ou_zero(d["ibs_aliq_uf"]), 1),
        ("Alíquota CBS", _pct_ou_zero(d["ibs_aliq_cbs"]), 1),
        ("Valor IBS municipal", _reais(d["ibs_mun"]), 1),
    ])
    _faixa([
        ("Valor IBS estadual", _reais(d["ibs_uf"]), 1),
        ("Valor CBS", _reais(d["ibs_cbs"]), 1),
        ("Total IBS", _reais(d["ibs_total"]), 1),
        ("Valor líquido + IBS/CBS", _reais(d["ibs_nf"]), 1),
    ])
    _categoria("VALOR TOTAL DA NFS-e")
    _faixa([
        ("Valor do serviço", _reais(d["valor"]), 1),
        ("Desconto incondicional", _reais(d["desc_incond"]), 1),
        ("Desconto condicionado", _reais(d["desc_cond"]), 1),
        ("Valor líquido", _reais(d["liquido"]), 1, True, 8),
    ])
    _celula(pagina, esq, y, largura, 17, "Informações complementares", _traco(d["extra"]), tamanho=7)
    y += 17

    fim = 676
    if y > fim - 52:
        y = fim - 52
    alto = fim - y
    _caixa(pagina, esq, y, largura, alto, 1.2)
    pagina.draw_rect(
        fitz.Rect(esq + 2.4, y + 2.4, direita - 2.4, y + alto - 2.4),
        color=PRETO, width=0.35,
    )
    pagina.insert_text((esq + 8, y + 13), "DESCRIÇÃO DO SERVIÇO / OBSERVAÇÕES", fontsize=8, fontname="hebo", color=PRETO)
    pagina.draw_line(fitz.Point(esq + 8, y + 17), fitz.Point(direita - 8, y + 17), color=PRETO, width=0.7)
    pagina.insert_textbox(
        fitz.Rect(esq + 8, y + 22, direita - 8, y + alto - 6),
        d["descricao"] or "Não informada no XML.",
        fontsize=9.5, fontname="helv", color=PRETO,
    )
    _canhoto(pagina, d, nota, esq, direita)
    pdf = doc.tobytes()
    doc.close()
    return pdf


def gerar_danfse_modelo() -> bytes:
    """PDF de exemplo para validar o layout. Não representa uma NFS-e emitida."""
    xml = """<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><infNFSe Id="NFS35273062264702941000150000000000000026100000000000">
      <xLocEmi>Louveira</xLocEmi><xLocPrestacao>Louveira</xLocPrestacao><xLocIncid>Louveira</xLocIncid>
      <nNFSe>000</nNFSe><xTribNac>Licenciamento de programas de computador não customizáveis</xTribNac>
      <xNBS>Licenciamento de software</xNBS>
      <dhProc>2026-10-05T11:11:52-03:00</dhProc>
      <xOutInf>Informação complementar devolvida pela prefeitura, quando existir no XML.</xOutInf>
      <emit><CNPJ>64702941000150</CNPJ><IM>719842</IM><xNome>H74 SISTEMAS LTDA</xNome>
        <enderNac><xLgr>RUA LUIGI MARTINI</xLgr><nro>39</nro><xBairro>JARDIM BANDEIRANTES</xBairro>
          <cMun>3527306</cMun><UF>SP</UF><CEP>13290226</CEP></enderNac>
        <fone>19999990000</fone><email>hazael@h74.com.br</email></emit>
      <valores><vBC>500.00</vBC><pAliqAplic>2.00</pAliqAplic><vISSQN>10.00</vISSQN><vCalcDR>20.00</vCalcDR><vLiq>500.00</vLiq></valores>
      <IBSCBS>
        <cLocalidadeIncid>3527306</cLocalidadeIncid><xLocalidadeIncid>Louveira / SP</xLocalidadeIncid>
        <valores><vBC>470.00</vBC>
          <uf><pIBSUF>0.10</pIBSUF><pAliqEfetUF>0.10</pAliqEfetUF></uf>
          <mun><pIBSMun>0.05</pIBSMun><pAliqEfetMun>0.05</pAliqEfetMun></mun>
          <fed><pCBS>0.90</pCBS><pAliqEfetCBS>0.90</pAliqEfetCBS></fed>
        </valores>
        <totCIBS><vTotNF>505.00</vTotNF>
          <gIBS><vIBSTot>0.70</vIBSTot>
            <gIBSUFTot><vIBSUF>0.47</vIBSUF></gIBSUFTot>
            <gIBSMunTot><vIBSMun>0.23</vIBSMun></gIBSMunTot>
          </gIBS>
          <gCBS><vCBS>4.23</vCBS></gCBS>
        </totCIBS>
      </IBSCBS>
      <DPS><infDPS><dhEmi>2026-10-05T11:09:00-03:00</dhEmi><dCompet>2026-10-05</dCompet><serie>1</serie><nDPS>1</nDPS>
        <prest><regTrib><opSimpNac>3</opSimpNac><regApTribSN>1</regApTribSN></regTrib></prest>
        <toma><CNPJ>44650822000193</CNPJ><IE>149548220114</IE><xNome>BARACAT GESTAO EMPRESARIAL LTDA</xNome>
          <end><endNac><cMun>3550308</cMun><CEP>01001000</CEP></endNac>
            <xLgr>Rua de exemplo</xLgr><nro>100</nro><xCpl>Sala 12</xCpl><xBairro>Centro</xBairro>
            <xMun>São Paulo</xMun><UF>SP</UF></end>
          <fone>1140000000</fone></toma>
        <serv><locPrest><cLocPrestacao>3527306</cLocPrestacao></locPrest>
          <cServ><cTribNac>010501</cTribNac><cNBS>111032200</cNBS>
            <xDescServ>Licenciamento de software. Competência outubro/2026. Vencimento 15/10/2026. Referência do contrato 2026-014.</xDescServ>
          </cServ></serv>
        <valores><vServPrest><vServ>500.00</vServ></vServPrest>
          <vDescCondIncond><vDescIncond>10.00</vDescIncond><vDescCond>5.00</vDescCond></vDescCondIncond>
          <vDedRed><vDR>20.00</vDR></vDedRed>
          <trib><tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN><pAliq>2.00</pAliq></tribMun>
            <tribFed>
              <piscofins><CST>01</CST><vBCPisCofins>500.00</vBCPisCofins><pAliqPis>0.65</pAliqPis><pAliqCofins>3.00</pAliqCofins><vPis>3.25</vPis><vCofins>15.00</vCofins><tpRetPisCofins>1</tpRetPisCofins></piscofins>
              <vRetIRRF>0.00</vRetIRRF><vRetCSLL>0.00</vRetCSLL><vRetCP>0.00</vRetCP>
            </tribFed>
            <totTrib>
              <pTotTribSN>6.00</pTotTribSN>
              <vTotTrib><vTotTribFed>25.00</vTotTribFed><vTotTribEst>2.00</vTotTribEst><vTotTribMun>5.00</vTotTribMun></vTotTrib>
            </totTrib></trib></valores>
        <IBSCBS><finNFSe>0</finNFSe><cIndOp>100301</cIndOp>
          <valores><trib><gIBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></gIBSCBS></trib></valores>
        </IBSCBS>
      </infDPS></DPS></infNFSe></NFSe>""".encode()
    return gerar_danfse(xml, {
        "modelo": True,
        "status": "autorizada",
        "chave_nfse": "35273062264702941000150000000000000026100000000000",
    })
