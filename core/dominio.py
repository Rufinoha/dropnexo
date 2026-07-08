# core/dominio.py — categorias, CNPJ e vínculos vendedor×fornecedor
from __future__ import annotations

# ── categorias ────────────────────────────────────────

MAX_NIVEL_CATEGORIA = 3


def montar_arvore_categorias(rows: list[tuple]) -> list[dict]:
    """rows: id, nome, parent_id, ordem, nivel, qtd_produtos"""
    nodes = []
    for r in rows:
        nodes.append(
            {
                "id": r[0],
                "nome": r[1],
                "parent_id": r[2],
                "ordem": r[3],
                "nivel": int(r[4] or 1),
                "qtd_produtos": int(r[5] or 0),
                "filhos": [],
            }
        )
    by_id = {n["id"]: n for n in nodes}
    raiz = []
    for n in nodes:
        pid = n["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["filhos"].append(n)
        else:
            raiz.append(n)

    def ordenar(lst):
        lst.sort(key=lambda x: (x["ordem"], x["nome"]))
        for c in lst:
            ordenar(c["filhos"])

    ordenar(raiz)
    return raiz


def caminho_categoria(nome: str, parent_id: int | None, by_id: dict) -> str:
    partes = [nome]
    pid = parent_id
    while pid and pid in by_id:
        p = by_id[pid]
        partes.insert(0, p["nome"])
        pid = p.get("parent_id")
    return " › ".join(partes)


def flatten_arvore_com_caminho(raiz: list[dict], prefixo: str = "") -> list[dict]:
    """Lista plana para combos (produto): id, nome, caminho, nivel."""
    out = []
    for n in raiz:
        caminho = f"{prefixo}{n['nome']}" if prefixo else n["nome"]
        out.append(
            {
                "id": n["id"],
                "nome": n["nome"],
                "caminho": caminho,
                "nivel": n["nivel"],
            }
        )
        out.extend(flatten_arvore_com_caminho(n["filhos"], caminho + " › "))
    return out


# ── cnpj ──────────────────────────────────────────────

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


# ── vinculos ──────────────────────────────────────────

from flask import session


def inativar_vinculo(cur, id_vinculo: int, id_fornecedor: int) -> None:
    """Corte de vínculo: desativa produtos do vendedor e zera estoque vitrine; pedidos abertos seguem."""
    cur.execute(
        """
        UPDATE tbl_vinculo_vendedor_fornecedor
        SET status = 'inativo', inativado_em = NOW()
        WHERE id = %s AND id_tenant_fornecedor = %s
        """,
        (id_vinculo, id_fornecedor),
    )
    cur.execute(
        """
        SELECT id_tenant_vendedor FROM tbl_vinculo_vendedor_fornecedor WHERE id = %s
        """,
        (id_vinculo,),
    )
    row = cur.fetchone()
    if not row:
        return
    id_vendedor = row[0]
    cur.execute(
        """
        UPDATE tbl_produto_vendedor
        SET ativo = FALSE, estoque_vitrine = 0, atualizado_em = NOW()
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )


def snapshot_vendedor_sessao() -> dict:
    return {
        "tenant_nome": session.get("tenant_nome"),
        "tenant_slug": session.get("tenant_slug"),
        "usuario_nome": session.get("nome"),
        "usuario_email": session.get("email"),
        "id_tenant": session.get("id_tenant"),
        "id_usuario": session.get("id_usuario"),
    }


def _formatar_documento(doc: str | None, tipo: str | None) -> str:
    d = "".join(c for c in (doc or "") if c.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return doc or ""


def montar_snapshot_vendedor(cur, id_vendedor: int, id_usuario: int | None) -> dict:
    """Snapshot completo gravado na solicitação de vínculo (dados para decisão do fornecedor)."""
    base: dict = {"id_tenant": id_vendedor, "id_usuario": id_usuario}
    cur.execute(
        """
        SELECT COALESCE(t.nome_fantasia, t.nome), t.slug,
               t.tipo_pessoa, t.documento, t.nome_completo, COALESCE(t.nome_fantasia, t.nome),
               t.razao_social, t.cep, t.logradouro, t.numero, t.complemento,
               t.bairro, t.cidade, t.uf, t.telefone_comercial, t.celular_comercial,
               t.email_comercial, t.criado_em, t.tipo_negocio, t.site,
               t.faturamento_ultimo_ano, t.tamanho_empresa
        FROM tbl_tenant t
        WHERE t.id = %s
        """,
        (id_vendedor,),
    )
    row = cur.fetchone()
    if row:
        base["tenant_nome"] = row[0]
        base["tenant_slug"] = row[1]
        endereco_parts = [row[8], row[9], row[10], row[11], row[12], row[13]]
        endereco = ", ".join(p for p in endereco_parts if p)
        base.update(
            {
                "tipo_pessoa": row[2],
                "documento": row[3],
                "documento_formatado": _formatar_documento(row[3], row[2]),
                "nome_completo": row[4],
                "nome_fantasia": row[5],
                "razao_social": row[6] or "",
                "cep": row[7] or "",
                "endereco": endereco,
                "logradouro": row[8] or "",
                "numero": row[9] or "",
                "complemento": row[10] or "",
                "bairro": row[11] or "",
                "cidade": row[12] or "",
                "uf": row[13] or "",
                "telefone_comercial": row[14] or "",
                "celular_comercial": row[15] or "",
                "email_comercial": row[16] or "",
                "cadastro_desde": row[17].isoformat() if row[17] else "",
                "tipo_negocio": row[18] or "",
                "site": row[19] or "",
                "faturamento_ultimo_ano": row[20] or "",
                "tamanho_empresa": row[21] or "",
            }
        )

    if id_usuario:
        cur.execute(
            "SELECT nome, email, whatsapp FROM tbl_usuario WHERE id = %s",
            (id_usuario,),
        )
        u = cur.fetchone()
        if u:
            base["usuario_nome"] = u[0]
            base["usuario_email"] = u[1]
            base["usuario_whatsapp"] = u[2] or ""

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND status = 'ativo'
        """,
        (id_vendedor,),
    )
    base["qtd_fornecedores_ativos"] = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND ativo = TRUE
        """,
        (id_vendedor,),
    )
    base["qtd_produtos_vitrine"] = int(cur.fetchone()[0] or 0)

    return base
