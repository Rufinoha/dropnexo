"""Cadastro/atualização do emitente (sua empresa) no Hub H74 (/v2/empresas)."""
from __future__ import annotations

import base64

from global_utils import db_execute, somente_digitos
from sistema.fiscal.nfse.crypto_certificado import descriptografar
from sistema.fiscal.nfse.tenant_fiscal import carregar_empresa_fiscal


def _escopo_hub_empresas() -> str:
    from api.fiscal.focus_nfe import token_configurado

    return "nfe" if token_configurado(escopo="nfe") else "nfse"


def _ambiente_empresa(emp: dict) -> str:
    ambiente = (emp.get("ambiente") or emp.get("ambiente_nfse") or "homologacao").strip().lower()
    return "producao" if ambiente == "producao" else "homologacao"


def pendencias_empresa_fiscal(emp: dict | None) -> list[str]:
    """Campos obrigatórios da Empresa fiscal (mensagens para o cliente)."""
    emp = emp or {}
    erros: list[str] = []
    if not emp.get("eh_pj", True):
        erros.append(
            "A emissão de notas exige cadastro como pessoa jurídica (PJ). "
            "Atualize em Minha empresa."
        )
        return erros
    cnpj = somente_digitos(emp.get("cnpj") or "")
    if len(cnpj) != 14:
        erros.append("CNPJ da sua empresa ausente ou inválido. Corrija em Minha empresa.")
    if not (emp.get("razao_social") or "").strip():
        erros.append("Razão social da sua empresa ausente. Corrija em Minha empresa.")
    ibge = somente_digitos(emp.get("municipio_ibge_codigo") or "")
    if len(ibge) != 7:
        erros.append("Informe o código IBGE do município (7 dígitos) em Parâmetros → Empresa fiscal.")
    if not (emp.get("municipio_nome") or "").strip():
        erros.append("Informe o município em Parâmetros → Empresa fiscal.")
    uf = (emp.get("uf") or "").strip().upper()
    if len(uf) != 2:
        erros.append("Informe a UF da sua empresa em Parâmetros → Empresa fiscal.")
    return erros


def _certificado_ativo(conn, id_tenant: int) -> dict | None:
    cur = db_execute(
        conn,
        """
        SELECT id, conteudo_encriptado, senha_encriptada, cnpj_certificado, dt_fim_validade
          FROM tbl_nfse_certificado
         WHERE id_tenant=%s AND ativo=TRUE AND dt_fim_validade > NOW()
         ORDER BY dt_fim_validade DESC
         LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def pendencias_emitente_hub(conn, id_tenant: int, *, ambiente: str | None = None) -> list[str]:
    """Tudo que falta para cadastrar/atualizar o emitente no Hub e emitir notas."""
    from api.fiscal.focus_nfe import token_configurado

    emp = carregar_empresa_fiscal(conn, int(id_tenant))
    erros = pendencias_empresa_fiscal(emp)
    amb = (ambiente or _ambiente_empresa(emp)).strip().lower()
    if amb != "producao":
        amb = "homologacao"

    if not (token_configurado(escopo="nfe") or token_configurado(escopo="nfse")):
        erros.append(
            "Configure a URL e os tokens do Hub H74 em Configurações → Hub H74 "
            "antes de emitir notas."
        )
    elif not token_configurado(escopo="nfse"):
        erros.append(
            "Configure o token de NFS-e do Hub H74 em Configurações → Hub H74."
        )

    cert = _certificado_ativo(conn, id_tenant)
    if not cert:
        erros.append(
            "Nenhum certificado A1 ativo e válido. Envie em Parâmetros → Certificados A1."
        )
    else:
        cnpj = somente_digitos(emp.get("cnpj") or "")
        cnpj_cert = somente_digitos(cert.get("cnpj_certificado") or "")
        if cnpj and cnpj_cert and cnpj != cnpj_cert:
            erros.append(
                "O CNPJ do certificado A1 é diferente do CNPJ da sua empresa. "
                "Envie um certificado compatível."
            )
    return erros


def sincronizar_emitente_hub(conn, id_tenant: int, *, ambiente: str | None = None) -> dict:
    """
    Cria ou atualiza a empresa emitente no Hub (/v2/empresas).
    Levanta ValueError com mensagem amigável se faltar dado ou o Hub recusar.
    """
    from api.fiscal.focus_nfe import FocusNfeError, request_json

    emp = carregar_empresa_fiscal(conn, int(id_tenant))
    amb = (ambiente or _ambiente_empresa(emp)).strip().lower()
    if amb != "producao":
        amb = "homologacao"

    pendencias = pendencias_emitente_hub(conn, id_tenant, ambiente=amb)
    if pendencias:
        raise ValueError("\n".join(pendencias))

    cert = _certificado_ativo(conn, id_tenant)
    assert cert is not None

    cnpj = somente_digitos(emp.get("cnpj") or "")
    nome = (emp.get("razao_social") or "").strip()
    ibge = somente_digitos(emp.get("municipio_ibge_codigo") or "")
    uf = (emp.get("uf") or "").strip().upper()
    regime = str(emp.get("regime_tributario") or "simples_nacional").strip().lower()
    crt = 1 if regime in {"simples_nacional", "mei", "1"} else 3

    pfx = descriptografar(cert["conteudo_encriptado"])
    senha = descriptografar(cert["senha_encriptada"]).decode("utf-8")

    body = {
        "cnpj": cnpj,
        "nome": nome[:160],
        "nome_fantasia": (emp.get("nome_fantasia") or nome)[:160],
        "inscricao_estadual": "ISENTO",
        "inscricao_municipal": (emp.get("inscricao_municipal") or "").strip() or None,
        "regime_tributario": crt,
        "optante_simples": bool(emp.get("optante_simples", True)),
        "regime_especial_tributacao": (emp.get("regime_especial_tributacao") or "").strip() or None,
        "percentual_tributos_sn": emp.get("percentual_tributos_sn") or None,
        "email": (emp.get("email_comercial") or "").strip() or None,
        "telefone": somente_digitos(emp.get("telefone_comercial") or "")[:14] or None,
        "logradouro": (emp.get("logradouro") or "Nao informado")[:160],
        "numero": (emp.get("numero") or "S/N")[:20],
        "complemento": (emp.get("complemento") or "").strip() or None,
        "bairro": (emp.get("bairro") or "Centro")[:120],
        "cep": somente_digitos(emp.get("cep") or "")[:8] or "00000000",
        "municipio": (emp.get("municipio_nome") or "")[:120],
        "uf": uf,
        "codigo_municipio": ibge,
        "arquivo_certificado_base64": base64.b64encode(pfx).decode("ascii"),
        "senha_certificado": senha,
    }
    if isinstance(body.get("percentual_tributos_sn"), str) and body["percentual_tributos_sn"]:
        try:
            body["percentual_tributos_sn"] = float(
                str(body["percentual_tributos_sn"]).replace(",", ".")
            )
        except ValueError:
            body["percentual_tributos_sn"] = None

    escopo = _escopo_hub_empresas()
    try:
        _, lista = request_json(amb, "GET", "/v2/empresas", timeout=30, escopo=escopo)
    except FocusNfeError as exc:
        raise ValueError(f"Não foi possível consultar empresas no Hub H74: {exc}") from exc

    empresa_id = ""
    itens = lista if isinstance(lista, list) else (
        (lista.get("dados") or lista.get("empresas") or lista.get("items") or lista.get("data") or [])
        if isinstance(lista, dict) else []
    )
    for item in itens:
        if not isinstance(item, dict):
            continue
        if somente_digitos(item.get("cnpj")) != cnpj:
            continue
        amb_item = str(item.get("ambiente") or "").strip().lower()
        if amb_item and amb_item != amb:
            continue
        empresa_id = str(item.get("id") or "").strip()
        if empresa_id:
            break

    try:
        if empresa_id:
            _, resp = request_json(
                amb,
                "PUT",
                f"/v2/empresas/{empresa_id}",
                json_body=body,
                timeout=60,
                escopo=escopo,
            )
            acao = "atualizado"
        else:
            _, resp = request_json(
                amb,
                "POST",
                "/v2/empresas",
                json_body=body,
                timeout=60,
                escopo=escopo,
            )
            acao = "cadastrado"
            if isinstance(resp, dict) and resp.get("id"):
                empresa_id = str(resp.get("id")).strip()
    except FocusNfeError as exc:
        raise ValueError(
            f"Não foi possível cadastrar/atualizar sua empresa no Hub H74: {exc}"
        ) from exc

    return {
        "empresa_id": empresa_id,
        "ambiente": amb,
        "acao": acao,
        "cnpj": cnpj,
    }


def tentar_sincronizar_emitente_hub(conn, id_tenant: int, *, ambiente: str | None = None) -> dict:
    """
    Tenta sync sem lançar se só faltarem pré-requisitos.
    Retorna dict com ok, pendencias, erro, resultado.
    """
    amb_emp = carregar_empresa_fiscal(conn, int(id_tenant))
    amb = ambiente or _ambiente_empresa(amb_emp)
    pendencias = pendencias_emitente_hub(conn, id_tenant, ambiente=amb)
    if pendencias:
        return {
            "ok": False,
            "hub_sincronizado": False,
            "pendencias": pendencias,
            "erro": None,
            "resultado": None,
        }
    try:
        resultado = sincronizar_emitente_hub(conn, id_tenant, ambiente=amb)
        return {
            "ok": True,
            "hub_sincronizado": True,
            "pendencias": [],
            "erro": None,
            "resultado": resultado,
        }
    except ValueError as exc:
        return {
            "ok": False,
            "hub_sincronizado": False,
            "pendencias": [],
            "erro": str(exc),
            "resultado": None,
        }
