# Emissão de NF-e do vendedor (Focus NFe) e os dados fiscais que ela usa.
from __future__ import annotations

import base64
import hashlib
import os
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from api.fiscal.focus_nfe import FocusNfeError, baixar, request_json, token_configurado

_RAIZ = Path(__file__).resolve().parents[2]
_TZ = ZoneInfo("America/Sao_Paulo")


def _digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _chave() -> bytes:
    segredo = os.getenv("SECRET_KEY") or "dropnexo"
    return hashlib.sha256(segredo.encode()).digest()


def _cifrar(texto: str) -> str:
    bruto = (texto or "").encode()
    nonce = os.urandom(16)
    fluxo = _fluxo(len(bruto), nonce)
    cifra = nonce + bytes(a ^ b for a, b in zip(bruto, fluxo))
    return base64.urlsafe_b64encode(cifra).decode()


def _decifrar(texto: str) -> str:
    if not texto:
        return ""
    try:
        blob = base64.urlsafe_b64decode(texto.encode())
    except Exception:
        return ""
    if len(blob) < 17:
        return ""
    nonce, cifra = blob[:16], blob[16:]
    fluxo = _fluxo(len(cifra), nonce)
    return bytes(a ^ b for a, b in zip(cifra, fluxo)).decode(errors="ignore")


def _fluxo(n: int, nonce: bytes) -> bytes:
    saida = b""
    contador = 0
    chave = _chave()
    while len(saida) < n:
        saida += hashlib.sha256(chave + nonce + contador.to_bytes(4, "big")).digest()
        contador += 1
    return saida[:n]


def _tem_coluna(cur, tabela: str, coluna: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s AND column_name = %s
        """,
        (tabela, coluna),
    )
    return cur.fetchone() is not None


def _tem_tabela(cur, tabela: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        (tabela,),
    )
    return cur.fetchone() is not None


def _exigir_tabelas(cur) -> None:
    if not _tem_tabela(cur, "tbl_fiscal_config") or not _tem_tabela(cur, "tbl_nfe"):
        raise ValueError(
            "As tabelas da nota fiscal ainda não existem neste banco. "
            "Rode o SQL informado no chat."
        )


def crt_de_regime(codigo: str) -> int:
    c = (codigo or "").strip().lower()
    if c in ("presumido", "real", "3"):
        return 3
    return 1


def codigo_municipio_tenant(cur, id_tenant: int) -> str:
    if not _tem_coluna(cur, "tbl_tenant", "codigo_municipio"):
        return ""
    cur.execute(
        "SELECT COALESCE(codigo_municipio, '') FROM tbl_tenant WHERE id = %s",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return (row[0] or "") if row else ""


def gravar_codigo_municipio(cur, id_tenant: int, codigo: str) -> None:
    if not _tem_coluna(cur, "tbl_tenant", "codigo_municipio"):
        return
    cur.execute(
        "UPDATE tbl_tenant SET codigo_municipio = %s WHERE id = %s",
        ((_digitos(codigo)[:7] or None), int(id_tenant)),
    )


def _config_padrao() -> dict:
    return {
        "ambiente": "homologacao",
        "serie": 1,
        "proximo_numero": 1,
        "natureza_operacao": "Venda de mercadoria",
        "cfop_interno": "5102",
        "cfop_interestadual": "6102",
        "cfop_consumidor_interestadual": "6108",
        "icms_situacao": "102",
        "icms_aliquota": None,
        "pis_situacao": "49",
        "cofins_situacao": "49",
        "certificado_nome": "",
        "tem_certificado": False,
        "certificado": {
            "instalado": False,
            "titular": "",
            "emissor": "",
            "valido_de": "",
            "valido_ate": "",
            "dias": None,
            "situacao": "ausente",
        },
        "focus_empresa_id": "",
        "token_configurado": False,
    }


def ler_config(cur, id_tenant: int) -> dict:
    base = _config_padrao()
    base["token_configurado"] = token_configurado(base["ambiente"])
    if not _tem_tabela(cur, "tbl_fiscal_config"):
        base["tabela_ok"] = False
        return base
    cur.execute(
        """
        SELECT ambiente, serie, proximo_numero, natureza_operacao,
               cfop_interno, cfop_interestadual, cfop_consumidor_interestadual,
               icms_situacao, icms_aliquota, pis_situacao, cofins_situacao,
               certificado_nome, certificado_caminho, focus_empresa_id
        FROM tbl_fiscal_config WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        base["tabela_ok"] = True
        base["token_configurado"] = token_configurado("homologacao")
        return base
    ambiente = row[0] if row[0] in ("homologacao", "producao") else "homologacao"
    return {
        "tabela_ok": True,
        "ambiente": ambiente,
        "serie": int(row[1] or 1),
        "proximo_numero": int(row[2] or 1),
        "natureza_operacao": row[3] or "Venda de mercadoria",
        "cfop_interno": row[4] or "5102",
        "cfop_interestadual": row[5] or "6102",
        "cfop_consumidor_interestadual": row[6] or "6108",
        "icms_situacao": row[7] or "102",
        "icms_aliquota": float(row[8]) if row[8] is not None else None,
        "pis_situacao": row[9] or "49",
        "cofins_situacao": row[10] or "49",
        "certificado_nome": row[11] or "",
        "tem_certificado": bool(row[12]),
        "certificado": info_certificado(cur, id_tenant),
        "focus_empresa_id": row[13] or "",
        "token_configurado": token_configurado(ambiente),
    }


def _cfop4(valor, padrao: str) -> str:
    d = _digitos(valor)[:4]
    return d if len(d) == 4 else padrao


def salvar_config(
    cur,
    id_tenant: int,
    body: dict,
    arquivo: tuple[str, bytes] | None,
    senha: str,
    editar_regras: bool = False,
) -> dict:
    _exigir_tabelas(cur)
    atual = ler_config(cur, id_tenant)
    if editar_regras:
        ambiente = (body.get("ambiente") or atual["ambiente"] or "homologacao").strip().lower()
        if ambiente not in ("homologacao", "producao"):
            ambiente = "homologacao"
        natureza = (body.get("natureza_operacao") or "Venda de mercadoria").strip()[:80]
        serie = max(1, int(body.get("serie") or atual["serie"] or 1))
        proximo = max(1, int(body.get("proximo_numero") or atual["proximo_numero"] or 1))
        cfop_int = _cfop4(body.get("cfop_interno"), "5102")
        cfop_ie = _cfop4(body.get("cfop_interestadual"), "6102")
        cfop_cf = _cfop4(body.get("cfop_consumidor_interestadual"), "6108")
        icms = (_digitos(body.get("icms_situacao")) or "102")[:4]
        aliq = body.get("icms_aliquota") if body.get("icms_aliquota") not in (None, "") else None
        pis = (_digitos(body.get("pis_situacao")) or "49")[:2]
        cofins = (_digitos(body.get("cofins_situacao")) or "49")[:2]
    else:
        ambiente = atual["ambiente"] if atual["ambiente"] in ("homologacao", "producao") else "homologacao"
        natureza = (atual["natureza_operacao"] or "Venda de mercadoria")[:80]
        serie = max(1, int(atual["serie"] or 1))
        proximo = max(1, int(atual["proximo_numero"] or 1))
        cfop_int = atual["cfop_interno"] or "5102"
        cfop_ie = atual["cfop_interestadual"] or "6102"
        cfop_cf = atual["cfop_consumidor_interestadual"] or "6108"
        icms = atual["icms_situacao"] or "102"
        aliq = atual["icms_aliquota"]
        pis = atual["pis_situacao"] or "49"
        cofins = atual["cofins_situacao"] or "49"
    caminho = None
    nome = atual.get("certificado_nome") or ""
    senha_cifrada = None
    if arquivo and arquivo[1]:
        nome_arq, conteudo = arquivo
        if not nome_arq.lower().endswith((".pfx", ".p12")):
            raise ValueError("Envie o certificado A1 nos formatos .pfx ou .p12.")
        if not (senha or "").strip():
            raise ValueError("Informe a senha do certificado.")
        pasta = _RAIZ / "upload" / f"tenant{int(id_tenant)}" / "fiscal"
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / "certificado.pfx"
        destino.write_bytes(conteudo)
        caminho = f"upload/tenant{int(id_tenant)}/fiscal/certificado.pfx"
        nome = Path(nome_arq).name[:180]
        senha_cifrada = _cifrar(senha.strip())
    elif (senha or "").strip() and atual.get("tem_certificado"):
        senha_cifrada = _cifrar(senha.strip())

    cur.execute("SELECT 1 FROM tbl_fiscal_config WHERE id_tenant = %s", (int(id_tenant),))
    existe = cur.fetchone() is not None
    if existe:
        sets = [
            "ambiente = %s",
            "serie = %s",
            "proximo_numero = %s",
            "natureza_operacao = %s",
            "cfop_interno = %s",
            "cfop_interestadual = %s",
            "cfop_consumidor_interestadual = %s",
            "icms_situacao = %s",
            "icms_aliquota = %s",
            "pis_situacao = %s",
            "cofins_situacao = %s",
            "atualizado_em = NOW()",
        ]
        valores = [
            ambiente,
            serie,
            proximo,
            natureza,
            cfop_int,
            cfop_ie,
            cfop_cf,
            icms,
            aliq,
            pis,
            cofins,
        ]
        if caminho:
            sets += ["certificado_caminho = %s", "certificado_nome = %s"]
            valores += [caminho, nome]
        if senha_cifrada:
            sets.append("certificado_senha = %s")
            valores.append(senha_cifrada)
        valores.append(int(id_tenant))
        cur.execute(
            f"UPDATE tbl_fiscal_config SET {', '.join(sets)} WHERE id_tenant = %s",
            valores,
        )
    else:
        cur.execute(
            """
            INSERT INTO tbl_fiscal_config (
              id_tenant, ambiente, serie, proximo_numero, natureza_operacao,
              cfop_interno, cfop_interestadual, cfop_consumidor_interestadual,
              icms_situacao, icms_aliquota, pis_situacao, cofins_situacao,
              certificado_caminho, certificado_nome, certificado_senha, atualizado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            """,
            (
                int(id_tenant),
                ambiente,
                serie,
                proximo,
                natureza,
                cfop_int,
                cfop_ie,
                cfop_cf,
                icms,
                aliq,
                pis,
                cofins,
                caminho,
                nome or None,
                senha_cifrada,
            ),
        )
    return ler_config(cur, id_tenant)


def _nome_cert(obj, oid) -> str:
    attrs = obj.get_attributes_for_oid(oid)
    return str(attrs[0].value) if attrs else ""


def info_certificado(cur, id_tenant: int) -> dict:
    """Dados públicos do A1. A senha não sai daqui."""
    vazio = {
        "instalado": False,
        "titular": "",
        "emissor": "",
        "valido_de": "",
        "valido_ate": "",
        "dias": None,
        "situacao": "ausente",
    }
    try:
        dados, senha = _ler_senha(cur, id_tenant)
    except ValueError as e:
        msg = str(e)
        if "senha" in msg.lower():
            return {**vazio, "instalado": True, "situacao": "sem_senha"}
        if "não está mais" in msg:
            return {**vazio, "situacao": "arquivo"}
        return vazio
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID

        _chave, cert, _extras = pkcs12.load_key_and_certificates(dados, senha.encode())
    except Exception:
        return {**vazio, "instalado": True, "situacao": "ilegivel"}
    if cert is None:
        return {**vazio, "instalado": True, "situacao": "ilegivel"}
    ini = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
    fim = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    if ini.tzinfo is None:
        ini = ini.replace(tzinfo=ZoneInfo("UTC"))
    if fim.tzinfo is None:
        fim = fim.replace(tzinfo=ZoneInfo("UTC"))
    agora = datetime.now(ZoneInfo("UTC"))
    dias = (fim.date() - agora.date()).days
    if dias < 0:
        situacao = "vencido"
    elif dias <= 30:
        situacao = "vence"
    else:
        situacao = "valido"
    return {
        "instalado": True,
        "titular": _nome_cert(cert.subject, NameOID.COMMON_NAME),
        "emissor": _nome_cert(cert.issuer, NameOID.COMMON_NAME),
        "valido_de": ini.astimezone(_TZ).strftime("%d/%m/%Y"),
        "valido_ate": fim.astimezone(_TZ).strftime("%d/%m/%Y"),
        "dias": dias,
        "situacao": situacao,
    }


def _ler_senha(cur, id_tenant: int) -> tuple[bytes, str]:
    cur.execute(
        """
        SELECT certificado_caminho, certificado_senha
        FROM tbl_fiscal_config WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        raise ValueError("Envie o certificado A1 em Parâmetros, na aba Fiscal.")
    caminho = _RAIZ / str(row[0]).replace("\\", "/")
    if not caminho.is_file():
        raise ValueError("O arquivo do certificado não está mais no servidor. Envie de novo.")
    senha = _decifrar(row[1] or "")
    if not senha:
        raise ValueError("Informe a senha do certificado e salve de novo em Parâmetros.")
    return caminho.read_bytes(), senha


def _empresa(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT tipo_pessoa, documento, nome_completo, razao_social, nome_fantasia, nome,
               inscricao_estadual, ie_isento, inscricao_municipal, codigo_regime_tributario,
               cep, logradouro, numero, complemento, bairro, cidade, uf,
               telefone_comercial, email_comercial
        FROM tbl_tenant WHERE id = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Empresa não encontrada.")
    if (row[0] or "F").upper() != "J":
        raise ValueError("A nota fiscal exige pessoa jurídica. Converta a conta em Minha empresa.")
    cnpj = _digitos(row[1])
    if len(cnpj) != 14:
        raise ValueError("Informe o CNPJ em Minha empresa.")
    ibge = codigo_municipio_tenant(cur, id_tenant)
    if len(ibge) != 7:
        raise ValueError("Busque o CEP de novo em Minha empresa para gravar o código da cidade.")
    if not (row[11] and row[12] and row[14] and row[15] and row[16] and row[10]):
        raise ValueError("Complete o endereço da empresa em Minha empresa.")
    ie = (row[6] or "").strip()
    if not ie and not row[7]:
        raise ValueError("Informe a inscrição estadual ou marque isento em Minha empresa.")
    return {
        "cnpj": cnpj,
        "nome": (row[3] or row[2] or row[5] or "").strip(),
        "nome_fantasia": (row[4] or row[5] or "").strip(),
        "inscricao_estadual": "ISENTO" if row[7] or not ie else ie,
        "inscricao_municipal": (row[8] or "").strip(),
        "regime_tributario": crt_de_regime(row[9] or ""),
        "cep": _digitos(row[10]),
        "logradouro": row[11] or "",
        "numero": row[12] or "S/N",
        "complemento": row[13] or "",
        "bairro": row[14] or "",
        "municipio": row[15] or "",
        "uf": (row[16] or "").strip().upper(),
        "codigo_municipio": ibge,
        "telefone": _digitos(row[17])[:14],
        "email": (row[18] or "").strip(),
    }


def sincronizar_empresa(cur, id_tenant: int) -> dict:
    _exigir_tabelas(cur)
    cfg = ler_config(cur, id_tenant)
    emp = _empresa(cur, id_tenant)
    conteudo, senha = _ler_senha(cur, id_tenant)
    payload = {
        "nome": emp["nome"][:60],
        "nome_fantasia": (emp["nome_fantasia"] or emp["nome"])[:60],
        "cnpj": emp["cnpj"],
        "inscricao_estadual": emp["inscricao_estadual"],
        "regime_tributario": emp["regime_tributario"],
        "email": emp["email"] or None,
        "telefone": emp["telefone"] or None,
        "logradouro": emp["logradouro"],
        "numero": emp["numero"],
        "complemento": emp["complemento"] or None,
        "bairro": emp["bairro"],
        "cep": emp["cep"],
        "municipio": emp["municipio"],
        "uf": emp["uf"],
        "codigo_municipio": emp["codigo_municipio"],
        "habilita_nfe": True,
        "arquivo_certificado_base64": base64.b64encode(conteudo).decode(),
        "senha_certificado": senha,
        "discrimina_impostos": True,
        "enviar_email_destinatario": False,
    }
    if emp["inscricao_municipal"]:
        payload["inscricao_municipal"] = emp["inscricao_municipal"]
    ambiente = cfg["ambiente"]
    empresa_id = (cfg.get("focus_empresa_id") or "").strip()
    try:
        if empresa_id:
            status, body = request_json(ambiente, "PUT", f"/v2/empresas/{empresa_id}", json_body=payload)
        else:
            status, body = request_json(ambiente, "POST", "/v2/empresas", json_body=payload)
    except FocusNfeError as e:
        if e.status == 422 and not empresa_id:
            empresa_id = _achar_empresa(ambiente, emp["cnpj"])
            if not empresa_id:
                raise ValueError(str(e)) from e
            status, body = request_json(ambiente, "PUT", f"/v2/empresas/{empresa_id}", json_body=payload)
        else:
            raise ValueError(str(e)) from e
    if isinstance(body, dict):
        empresa_id = str(body.get("id") or empresa_id or "")
    if empresa_id:
        cur.execute(
            "UPDATE tbl_fiscal_config SET focus_empresa_id = %s, atualizado_em = NOW() WHERE id_tenant = %s",
            (empresa_id, int(id_tenant)),
        )
    return {"focus_empresa_id": empresa_id, "status": status}


def _achar_empresa(ambiente: str, cnpj: str) -> str:
    try:
        _, body = request_json(ambiente, "GET", "/v2/empresas")
    except FocusNfeError:
        return ""
    lista = body if isinstance(body, list) else (body.get("data") if isinstance(body, dict) else [])
    if not isinstance(lista, list):
        return ""
    for item in lista:
        if isinstance(item, dict) and _digitos(item.get("cnpj")) == cnpj:
            return str(item.get("id") or "")
    return ""


def ler_tributacao_produto(cur, id_produto: int) -> dict:
    vazio = {"cfop": "", "icms_situacao": "", "pis_situacao": "", "cofins_situacao": ""}
    if not _tem_coluna(cur, "tbl_produto", "cfop"):
        return vazio
    cur.execute(
        """
        SELECT COALESCE(cfop, ''), COALESCE(icms_situacao, ''),
               COALESCE(pis_situacao, ''), COALESCE(cofins_situacao, '')
        FROM tbl_produto WHERE id = %s
        """,
        (int(id_produto),),
    )
    row = cur.fetchone()
    if not row:
        return vazio
    return {
        "cfop": row[0] or "",
        "icms_situacao": row[1] or "",
        "pis_situacao": row[2] or "",
        "cofins_situacao": row[3] or "",
    }


def gravar_tributacao_produto(cur, id_produto: int, body: dict) -> None:
    campos = ("cfop", "icms_situacao", "pis_situacao", "cofins_situacao")
    if not any(k in body for k in campos):
        return
    preenchido = any(str(body.get(k) or "").strip() for k in campos)
    if not _tem_coluna(cur, "tbl_produto", "cfop"):
        if preenchido:
            raise ValueError("As colunas fiscais do produto ainda não existem neste banco.")
        return
    cur.execute(
        """
        UPDATE tbl_produto
        SET cfop = %s, icms_situacao = %s, pis_situacao = %s, cofins_situacao = %s
        WHERE id = %s
        """,
        (
            _digitos(body.get("cfop"))[:4] or None,
            _digitos(body.get("icms_situacao"))[:4] or None,
            _digitos(body.get("pis_situacao"))[:2] or None,
            _digitos(body.get("cofins_situacao"))[:2] or None,
            int(id_produto),
        ),
    )


def gravar_pedido_fiscal(cur, ids_pedido: list[int], dados: dict) -> None:
    if not ids_pedido or not _tem_tabela(cur, "tbl_pedido_fiscal"):
        return
    ind = str(dados.get("indicador_ie") or dados.get("cliente_ind_ie") or "9").strip()[:1]
    if ind not in ("1", "2", "9"):
        ind = "9"
    ie = (dados.get("inscricao_estadual") or dados.get("cliente_ie") or "").strip()[:20] or None
    ibge = _digitos(dados.get("codigo_municipio") or dados.get("entrega_codigo_municipio"))[:7] or None
    for pid in ids_pedido:
        cur.execute(
            """
            INSERT INTO tbl_pedido_fiscal (id_pedido, indicador_ie, inscricao_estadual, codigo_municipio)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_pedido) DO UPDATE SET
              indicador_ie = EXCLUDED.indicador_ie,
              inscricao_estadual = EXCLUDED.inscricao_estadual,
              codigo_municipio = EXCLUDED.codigo_municipio
            """,
            (int(pid), ind, ie, ibge),
        )


def ler_pedido_fiscal(cur, id_pedido: int) -> dict:
    vazio = {"indicador_ie": "9", "inscricao_estadual": "", "codigo_municipio": ""}
    if not _tem_tabela(cur, "tbl_pedido_fiscal"):
        return vazio
    cur.execute(
        """
        SELECT indicador_ie, COALESCE(inscricao_estadual, ''), COALESCE(codigo_municipio, '')
        FROM tbl_pedido_fiscal WHERE id_pedido = %s
        """,
        (int(id_pedido),),
    )
    row = cur.fetchone()
    if not row:
        return vazio
    return {
        "indicador_ie": row[0] or "9",
        "inscricao_estadual": row[1] or "",
        "codigo_municipio": row[2] or "",
    }


def _dinheiro(valor) -> float:
    q = Decimal(str(valor or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(q)


def _item_catalogo(cur, id_produto: int | None, id_variante: int | None) -> dict:
    if not id_produto:
        return {}
    ncm_var = ""
    if id_variante and _tem_coluna(cur, "tbl_produto_variante", "ncm"):
        cur.execute("SELECT COALESCE(ncm, '') FROM tbl_produto_variante WHERE id = %s", (int(id_variante),))
        row = cur.fetchone()
        ncm_var = (row[0] or "") if row else ""
    extra = ""
    if _tem_coluna(cur, "tbl_produto", "cfop"):
        extra = ", COALESCE(cfop, ''), COALESCE(icms_situacao, ''), COALESCE(pis_situacao, ''), COALESCE(cofins_situacao, '')"
    cur.execute(
        f"""
        SELECT COALESCE(ncm, ''), COALESCE(cest, ''), COALESCE(origem_fiscal, ''),
               COALESCE(unidade, 'UN'), COALESCE(gtin, ''){extra}
        FROM tbl_produto WHERE id = %s
        """,
        (int(id_produto),),
    )
    row = cur.fetchone()
    if not row:
        return {}
    dados = {
        "ncm": _digitos(ncm_var or row[0])[:8],
        "cest": _digitos(row[1])[:7],
        "origem": (row[2] or "0").strip()[:1] or "0",
        "unidade": (row[3] or "UN").strip()[:6] or "UN",
        "gtin": _digitos(row[4])[:14],
        "cfop": "",
        "icms_situacao": "",
        "pis_situacao": "",
        "cofins_situacao": "",
    }
    if extra:
        dados["cfop"] = _digitos(row[5])[:4]
        dados["icms_situacao"] = _digitos(row[6])[:4]
        dados["pis_situacao"] = _digitos(row[7])[:2]
        dados["cofins_situacao"] = _digitos(row[8])[:2]
    return dados


def _cfop_item(cfg: dict, prod: dict, mesma_uf: bool, indicador_ie: str) -> str:
    if prod.get("cfop"):
        return prod["cfop"]
    if mesma_uf:
        return cfg["cfop_interno"]
    if indicador_ie == "9":
        return cfg["cfop_consumidor_interestadual"]
    return cfg["cfop_interestadual"]


def _montar_item(numero: int, bruto: dict, cfg: dict, mesma_uf: bool, indicador_ie: str) -> dict:
    qtd = _dinheiro(bruto.get("quantidade") or 1)
    if qtd <= 0:
        qtd = 1
    unit = _dinheiro(bruto.get("valor_unitario"))
    if unit <= 0:
        raise ValueError(f"Informe o preço de venda de {bruto.get('descricao') or 'um item'}.")
    ncm = _digitos(bruto.get("ncm"))[:8]
    if len(ncm) != 8:
        raise ValueError(f"O produto {bruto.get('descricao') or ''} precisa de NCM com 8 dígitos.")
    icms = (bruto.get("icms_situacao") or cfg["icms_situacao"] or "102").strip()
    item = {
        "numero_item": numero,
        "codigo_produto": (bruto.get("codigo") or str(numero))[:60],
        "descricao": (bruto.get("descricao") or "Produto")[:120],
        "cfop": _cfop_item(cfg, bruto, mesma_uf, indicador_ie),
        "unidade_comercial": (bruto.get("unidade") or "UN")[:6],
        "quantidade_comercial": qtd,
        "valor_unitario_comercial": unit,
        "valor_bruto": _dinheiro(qtd * unit),
        "unidade_tributavel": (bruto.get("unidade") or "UN")[:6],
        "quantidade_tributavel": qtd,
        "valor_unitario_tributavel": unit,
        "codigo_ncm": ncm,
        "icms_origem": (bruto.get("origem") or "0")[:1],
        "icms_situacao_tributaria": icms,
        "pis_situacao_tributaria": (bruto.get("pis_situacao") or cfg["pis_situacao"] or "49")[:2],
        "cofins_situacao_tributaria": (bruto.get("cofins_situacao") or cfg["cofins_situacao"] or "49")[:2],
        "inclui_no_total": 1,
    }
    if bruto.get("cest"):
        item["cest"] = _digitos(bruto["cest"])[:7]
    if bruto.get("gtin"):
        item["codigo_barras_comercial"] = bruto["gtin"]
        item["codigo_barras_tributavel"] = bruto["gtin"]
    if icms in ("00", "20") and cfg.get("icms_aliquota"):
        item["icms_aliquota"] = _dinheiro(cfg["icms_aliquota"])
    return item


def _destinatario_de_pedido(cur, ped: dict, fiscal: dict) -> dict:
    doc = _digitos(ped.get("cliente_documento"))
    ibge = fiscal.get("codigo_municipio") or ""
    if len(ibge) != 7 and ped.get("entrega_cep"):
        ibge = ""
    return {
        "nome": ped.get("cliente_nome") or "",
        "documento": doc,
        "email": ped.get("cliente_email") or "",
        "indicador_ie": fiscal.get("indicador_ie") or "9",
        "ie": fiscal.get("inscricao_estadual") or "",
        "cep": _digitos(ped.get("entrega_cep")),
        "logradouro": ped.get("entrega_logradouro") or "",
        "numero": ped.get("entrega_numero") or "S/N",
        "complemento": ped.get("entrega_complemento") or "",
        "bairro": ped.get("entrega_bairro") or "",
        "municipio": ped.get("entrega_cidade") or "",
        "uf": (ped.get("entrega_uf") or "").strip().upper(),
        "codigo_municipio": ibge,
    }


def _validar_destinatario(dest: dict) -> None:
    doc = _digitos(dest.get("documento"))
    if len(doc) not in (11, 14):
        raise ValueError("O cliente precisa de CPF ou CNPJ.")
    if not (dest.get("nome") or "").strip():
        raise ValueError("Informe o nome do cliente.")
    if dest.get("indicador_ie") == "1" and not (dest.get("ie") or "").strip():
        raise ValueError("Cliente contribuinte precisa da inscrição estadual.")
    if len(_digitos(dest.get("codigo_municipio"))) != 7:
        raise ValueError("Busque o CEP do cliente para gravar o código da cidade.")
    for campo, rotulo in (
        ("logradouro", "logradouro"),
        ("bairro", "bairro"),
        ("municipio", "cidade"),
        ("uf", "UF"),
        ("cep", "CEP"),
    ):
        if not (dest.get(campo) or "").strip():
            raise ValueError(f"Informe o {rotulo} do cliente.")


def _payload(emp: dict, cfg: dict, dest: dict, itens: list[dict], frete: float, numero: int) -> dict:
    mesma = dest["uf"] == emp["uf"]
    indicador = dest.get("indicador_ie") or "9"
    doc = _digitos(dest.get("documento"))
    corpo = {
        "natureza_operacao": cfg["natureza_operacao"],
        "data_emissao": datetime.now(_TZ).replace(microsecond=0).isoformat(),
        "tipo_documento": 1,
        "local_destino": 1 if mesma else 2,
        "finalidade_emissao": 1,
        "consumidor_final": 1 if indicador == "9" else 0,
        "presenca_comprador": 2,
        "serie": cfg["serie"],
        "numero": numero,
        "cnpj_emitente": emp["cnpj"],
        "nome_emitente": emp["nome"][:60],
        "nome_fantasia_emitente": (emp["nome_fantasia"] or emp["nome"])[:60],
        "logradouro_emitente": emp["logradouro"],
        "numero_emitente": emp["numero"],
        "bairro_emitente": emp["bairro"],
        "municipio_emitente": emp["municipio"],
        "uf_emitente": emp["uf"],
        "cep_emitente": emp["cep"],
        "inscricao_estadual_emitente": emp["inscricao_estadual"],
        "regime_tributario_emitente": emp["regime_tributario"],
        "nome_destinatario": dest["nome"][:60],
        "indicador_inscricao_estadual_destinatario": int(indicador),
        "logradouro_destinatario": dest["logradouro"],
        "numero_destinatario": dest.get("numero") or "S/N",
        "bairro_destinatario": dest["bairro"],
        "municipio_destinatario": dest["municipio"],
        "uf_destinatario": dest["uf"],
        "cep_destinatario": dest["cep"],
        "codigo_municipio_destinatario": dest["codigo_municipio"],
        "modalidade_frete": 0 if frete > 0 else 9,
        "items": [
            _montar_item(i + 1, item, cfg, mesma, indicador) for i, item in enumerate(itens)
        ],
    }
    if frete > 0:
        corpo["valor_frete"] = _dinheiro(frete)
    if len(doc) == 11:
        corpo["cpf_destinatario"] = doc
    else:
        corpo["cnpj_destinatario"] = doc
    if indicador == "1":
        corpo["inscricao_estadual_destinatario"] = dest["ie"]
    if dest.get("email"):
        corpo["email_destinatario"] = dest["email"]
    if dest.get("complemento"):
        corpo["complemento_destinatario"] = dest["complemento"]
    return corpo


def _gravar_arquivos(id_tenant: int, id_nfe: int, pdf: bytes, xml: bytes) -> tuple[str, str]:
    pasta = _RAIZ / "upload" / f"tenant{int(id_tenant)}" / "nfe"
    pasta.mkdir(parents=True, exist_ok=True)
    pdf_rel = xml_rel = ""
    if pdf[:4] == b"%PDF":
        destino = pasta / f"{id_nfe}.pdf"
        destino.write_bytes(pdf)
        pdf_rel = f"upload/tenant{int(id_tenant)}/nfe/{id_nfe}.pdf"
    if xml[:1] == b"<" or xml[:5] == b"<?xml":
        destino = pasta / f"{id_nfe}.xml"
        destino.write_bytes(xml)
        xml_rel = f"upload/tenant{int(id_tenant)}/nfe/{id_nfe}.xml"
    return pdf_rel, xml_rel


def _anexar_pedido(cur, id_vendedor: int, id_pedido: int, pdf_rel: str, id_usuario: int | None) -> None:
    if not pdf_rel:
        return
    from core.pedidos.servico import listar_anexos_pedido, registrar_anexo_pedido

    for anexo in listar_anexos_pedido(cur, int(id_pedido), id_vendedor=id_vendedor):
        if str(anexo.get("nome_original") or "").startswith("danfe_dropnexo_"):
            return
    caminho = _RAIZ / pdf_rel
    registrar_anexo_pedido(
        cur,
        id_vendedor,
        int(id_pedido),
        "nf",
        f"danfe_dropnexo_{id_pedido}.pdf",
        pdf_rel,
        caminho.stat().st_size if caminho.is_file() else 0,
        id_usuario,
    )


def _consultar_remoto(ambiente: str, ref: str) -> dict:
    _, body = request_json(ambiente, "GET", f"/v2/nfe/{ref}")
    return body if isinstance(body, dict) else {}


def _baixar_danfe_xml(ambiente: str, ref: str, id_tenant: int, id_nfe: int) -> tuple[str, str]:
    pdf = b""
    xml = b""
    try:
        pdf = baixar(ambiente, f"/v2/nfe/{ref}.pdf")
    except FocusNfeError:
        pdf = b""
    try:
        xml = baixar(ambiente, f"/v2/nfe/{ref}.xml")
    except FocusNfeError:
        xml = b""
    return _gravar_arquivos(id_tenant, id_nfe, pdf, xml)


def _aplicar_retorno(cur, id_nfe: int, body: dict, pdf_rel: str = "", xml_rel: str = "") -> None:
    status = str(body.get("status") or "processando_autorizacao")
    cur.execute(
        """
        UPDATE tbl_nfe SET
          status = %s,
          numero = COALESCE(%s, numero),
          serie = COALESCE(%s, serie),
          chave = COALESCE(%s, chave),
          mensagem = %s,
          xml_caminho = COALESCE(NULLIF(%s, ''), xml_caminho),
          danfe_caminho = COALESCE(NULLIF(%s, ''), danfe_caminho),
          atualizado_em = NOW()
        WHERE id = %s
        """,
        (
            status[:40],
            int(body["numero"]) if str(body.get("numero") or "").isdigit() else None,
            int(body["serie"]) if str(body.get("serie") or "").isdigit() else None,
            (body.get("chave_nfe") or body.get("chave") or "")[:44] or None,
            (body.get("mensagem_sefaz") or body.get("mensagem") or "")[:500] or None,
            xml_rel,
            pdf_rel,
            int(id_nfe),
        ),
    )


def emitir(conn, id_tenant: int, dest: dict, itens: list[dict], *, frete: float = 0, id_pedido: int | None = None, id_grupo: int | None = None, ids_anexo: list[int] | None = None, id_usuario: int | None = None) -> dict:
    cur = conn.cursor()
    _exigir_tabelas(cur)
    cfg = ler_config(cur, id_tenant)
    if not cfg.get("tem_certificado"):
        raise ValueError("Envie o certificado A1 em Parâmetros, na aba Fiscal.")
    emp = _empresa(cur, id_tenant)
    _validar_destinatario(dest)
    if not itens:
        raise ValueError("A nota precisa de ao menos um item.")
    if not cfg.get("focus_empresa_id"):
        sincronizar_empresa(cur, id_tenant)
        conn.commit()
        cfg = ler_config(cur, id_tenant)
    numero = int(cfg["proximo_numero"] or 1)
    cur.execute(
        """
        INSERT INTO tbl_nfe (
          id_tenant, id_pedido, id_grupo, ref, serie, numero, status,
          natureza, destinatario_nome, valor_total
        ) VALUES (%s,%s,%s,'pendente',%s,%s,'preparando',%s,%s,0)
        RETURNING id
        """,
        (
            int(id_tenant),
            int(id_pedido) if id_pedido else None,
            int(id_grupo) if id_grupo else None,
            cfg["serie"],
            numero,
            cfg["natureza_operacao"],
            (dest.get("nome") or "")[:180],
        ),
    )
    id_nfe = int(cur.fetchone()[0])
    ref = f"dn{id_nfe}"
    cur.execute("UPDATE tbl_nfe SET ref = %s WHERE id = %s", (ref, id_nfe))
    payload = _payload(emp, cfg, dest, itens, frete, numero)
    total = sum(i["valor_bruto"] for i in payload["items"])
    cur.execute("UPDATE tbl_nfe SET valor_total = %s WHERE id = %s", (total, id_nfe))
    try:
        status_http, body = request_json(
            cfg["ambiente"], "POST", "/v2/nfe", params={"ref": ref}, json_body=payload
        )
    except FocusNfeError as e:
        cur.execute(
            "UPDATE tbl_nfe SET status = 'erro', mensagem = %s, atualizado_em = NOW() WHERE id = %s",
            (str(e)[:500], id_nfe),
        )
        conn.commit()
        raise ValueError(str(e)) from e
    if not isinstance(body, dict):
        body = {}
    if status_http == 202 and body.get("status") in (None, "", "processando_autorizacao"):
        try:
            body = _consultar_remoto(cfg["ambiente"], ref) or body
        except FocusNfeError:
            body.setdefault("status", "processando_autorizacao")
    status_nota = str(body.get("status") or ("autorizado" if status_http == 201 else "processando_autorizacao"))
    pdf_rel = xml_rel = ""
    if status_nota == "autorizado":
        pdf_rel, xml_rel = _baixar_danfe_xml(cfg["ambiente"], ref, id_tenant, id_nfe)
        for pid in ids_anexo or ([] if not id_pedido else [id_pedido]):
            try:
                _anexar_pedido(cur, id_tenant, int(pid), pdf_rel, id_usuario)
            except Exception:
                pass
    _aplicar_retorno(cur, id_nfe, {**body, "status": status_nota}, pdf_rel, xml_rel)
    if status_nota in ("autorizado", "processando_autorizacao"):
        cur.execute(
            """
            UPDATE tbl_fiscal_config
            SET proximo_numero = GREATEST(proximo_numero, %s), atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (numero + 1, int(id_tenant)),
        )
    conn.commit()
    if status_nota not in ("autorizado", "processando_autorizacao"):
        raise ValueError(body.get("mensagem_sefaz") or body.get("mensagem") or "A SEFAZ não autorizou a nota.")
    return obter_nfe(cur, id_tenant, id_nfe)


def emitir_pedido(conn, id_tenant: int, id_pedido: int, id_usuario: int | None = None) -> dict:
    from core.pedidos.servico import STATUS_CANCELADO, col_status_vendedor, listar_itens_pedido, obter_pedido

    cur = conn.cursor()
    ped = obter_pedido(cur, int(id_pedido), id_vendedor=int(id_tenant))
    if not ped:
        raise ValueError("Pedido não encontrado.")
    ids = [int(id_pedido)]
    id_grupo = ped.get("id_grupo")
    if id_grupo:
        cv = col_status_vendedor(cur)
        cur.execute(
            f"""
            SELECT id FROM tbl_pedido
            WHERE id_grupo = %s AND id_tenant_vendedor = %s AND {cv} != %s
            ORDER BY id
            """,
            (int(id_grupo), int(id_tenant), STATUS_CANCELADO),
        )
        ids = [int(r[0]) for r in cur.fetchall()] or ids
    fiscal = ler_pedido_fiscal(cur, int(id_pedido))
    dest = _destinatario_de_pedido(cur, ped, fiscal)
    itens = []
    frete = 0.0
    for pid in ids:
        atual = obter_pedido(cur, pid, id_vendedor=int(id_tenant)) or {}
        frete += float(atual.get("valor_frete") or 0)
        for item in listar_itens_pedido(cur, pid):
            cat = _item_catalogo(cur, item.get("id_produto"), item.get("id_variante"))
            preco = float(item.get("preco_venda") or 0) or float(item.get("valor_drop") or 0)
            itens.append(
                {
                    "codigo": item.get("sku") or str(item.get("id_produto") or ""),
                    "descricao": item.get("nome_produto") or "Produto",
                    "quantidade": item.get("quantidade") or 1,
                    "valor_unitario": preco,
                    **cat,
                }
            )
    return emitir(
        conn,
        id_tenant,
        dest,
        itens,
        frete=frete,
        id_pedido=int(id_pedido),
        id_grupo=int(id_grupo) if id_grupo else None,
        ids_anexo=ids,
        id_usuario=id_usuario,
    )


def emitir_avulsa(conn, id_tenant: int, body: dict, id_usuario: int | None = None) -> dict:
    dest = body.get("destinatario") or body
    itens = body.get("itens") or []
    if not isinstance(itens, list):
        raise ValueError("Informe os itens da nota.")
    return emitir(
        conn,
        id_tenant,
        {
            "nome": dest.get("nome") or "",
            "documento": dest.get("documento") or "",
            "email": dest.get("email") or "",
            "indicador_ie": str(dest.get("indicador_ie") or "9"),
            "ie": dest.get("ie") or "",
            "cep": dest.get("cep") or "",
            "logradouro": dest.get("logradouro") or "",
            "numero": dest.get("numero") or "",
            "complemento": dest.get("complemento") or "",
            "bairro": dest.get("bairro") or "",
            "municipio": dest.get("municipio") or dest.get("cidade") or "",
            "uf": dest.get("uf") or "",
            "codigo_municipio": dest.get("codigo_municipio") or "",
        },
        itens,
        frete=float(body.get("valor_frete") or 0),
        id_usuario=id_usuario,
    )


def atualizar_status(conn, id_tenant: int, id_nfe: int) -> dict:
    cur = conn.cursor()
    _exigir_tabelas(cur)
    cur.execute(
        "SELECT ref, status FROM tbl_nfe WHERE id = %s AND id_tenant = %s",
        (int(id_nfe), int(id_tenant)),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Nota não encontrada.")
    cfg = ler_config(cur, id_tenant)
    body = _consultar_remoto(cfg["ambiente"], row[0])
    pdf_rel = xml_rel = ""
    if str(body.get("status") or "") == "autorizado":
        pdf_rel, xml_rel = _baixar_danfe_xml(cfg["ambiente"], row[0], id_tenant, id_nfe)
    _aplicar_retorno(cur, id_nfe, body, pdf_rel, xml_rel)
    conn.commit()
    return obter_nfe(cur, id_tenant, id_nfe)


def listar_nfe(cur, id_tenant: int) -> list[dict]:
    if not _tem_tabela(cur, "tbl_nfe"):
        return []
    cur.execute(
        """
        SELECT id, numero, serie, chave, status, destinatario_nome, valor_total,
               id_pedido, mensagem, criado_em, danfe_caminho, xml_caminho
        FROM tbl_nfe
        WHERE id_tenant = %s
        ORDER BY id DESC
        LIMIT 200
        """,
        (int(id_tenant),),
    )
    itens = []
    for r in cur.fetchall():
        itens.append(
            {
                "id": int(r[0]),
                "numero": r[1],
                "serie": r[2],
                "chave": r[3] or "",
                "status": r[4] or "",
                "destinatario_nome": r[5] or "",
                "valor_total": float(r[6] or 0),
                "id_pedido": r[7],
                "mensagem": r[8] or "",
                "criado_em": r[9].isoformat() if r[9] else "",
                "tem_danfe": bool(r[10]),
                "tem_xml": bool(r[11]),
            }
        )
    return itens


def obter_nfe(cur, id_tenant: int, id_nfe: int) -> dict:
    cur.execute(
        """
        SELECT id, numero, serie, chave, status, destinatario_nome, valor_total,
               id_pedido, mensagem, criado_em, danfe_caminho, xml_caminho, ref
        FROM tbl_nfe WHERE id = %s AND id_tenant = %s
        """,
        (int(id_nfe), int(id_tenant)),
    )
    r = cur.fetchone()
    if not r:
        raise ValueError("Nota não encontrada.")
    return {
        "id": int(r[0]),
        "numero": r[1],
        "serie": r[2],
        "chave": r[3] or "",
        "status": r[4] or "",
        "destinatario_nome": r[5] or "",
        "valor_total": float(r[6] or 0),
        "id_pedido": r[7],
        "mensagem": r[8] or "",
        "criado_em": r[9].isoformat() if r[9] else "",
        "tem_danfe": bool(r[10]),
        "tem_xml": bool(r[11]),
        "ref": r[12] or "",
    }


def caminho_arquivo_nfe(cur, id_tenant: int, id_nfe: int, tipo: str) -> Path:
    coluna = "danfe_caminho" if tipo == "pdf" else "xml_caminho"
    cur.execute(
        f"SELECT {coluna} FROM tbl_nfe WHERE id = %s AND id_tenant = %s",
        (int(id_nfe), int(id_tenant)),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        raise ValueError("Arquivo ainda não disponível.")
    rel = str(row[0]).replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("Arquivo inválido.")
    caminho = _RAIZ / rel
    if not caminho.is_file():
        raise ValueError("Arquivo não encontrado.")
    return caminho
