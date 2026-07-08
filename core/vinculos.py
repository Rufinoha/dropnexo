# core/vinculos.py — vínculo vendedor × fornecedor
from __future__ import annotations

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
