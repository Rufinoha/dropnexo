"""Dados do fornecedor de origem para o apoio de produto integrado (vendedor)."""

from __future__ import annotations

from fornecedor.requisitos_vendedor import carregar_contato_responsavel_fornecedor, carregar_requisitos


def _endereco_linha(
    logradouro: str | None,
    numero: str | None,
    complemento: str | None,
    bairro: str | None,
    cidade: str | None,
    uf: str | None,
    cep: str | None,
) -> str:
    partes: list[str] = []
    rua = " ".join(p for p in [(logradouro or "").strip(), (numero or "").strip()] if p)
    if rua:
        partes.append(rua)
    if (complemento or "").strip():
        partes.append(complemento.strip())
    if (bairro or "").strip():
        partes.append(bairro.strip())
    loc = ""
    if (cidade or "").strip():
        loc = cidade.strip()
    if (uf or "").strip():
        loc = f"{loc}/{uf.strip()}" if loc else uf.strip()
    if loc:
        partes.append(loc)
    if (cep or "").strip():
        partes.append(f"CEP {cep.strip()}")
    return " · ".join(partes)


def montar_fornecedor_produto_apoio(cur, id_vendedor: int, id_fornecedor: int) -> dict | None:
    cur.execute(
        """
        SELECT t.id,
               COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), t.nome),
               COALESCE(NULLIF(TRIM(t.razao_social), ''), t.nome),
               t.slug,
               t.documento,
               t.tipo_pessoa,
               t.cidade,
               t.uf,
               t.logradouro,
               t.numero,
               t.complemento,
               t.bairro,
               t.cep,
               t.telefone_comercial,
               t.celular_comercial,
               t.email_comercial,
               t.site,
               COALESCE(v.status, 'nenhum'),
               v.criado_em,
               (SELECT COUNT(*)::int FROM tbl_produto p
                WHERE p.id_tenant = t.id AND p.ativo = TRUE AND p.publicado = TRUE)
        FROM tbl_tenant t
        LEFT JOIN tbl_vinculo_vendedor_fornecedor v
            ON v.id_tenant_fornecedor = t.id AND v.id_tenant_vendedor = %s
        WHERE t.id = %s AND t.ativo = TRUE
        """,
        (id_vendedor, id_fornecedor),
    )
    row = cur.fetchone()
    if not row:
        return None

    cur.execute(
        """
        SELECT s.nome
        FROM tbl_fornecedor_segmento fs
        JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
        WHERE fs.id_tenant = %s
        ORDER BY s.nome
        LIMIT 12
        """,
        (id_fornecedor,),
    )
    segmentos = [r[0] for r in cur.fetchall()]

    req = carregar_requisitos(cur, id_fornecedor)
    contato = None
    if req.get("mostrar_contato_vendedor", True):
        contato = carregar_contato_responsavel_fornecedor(cur, id_fornecedor)

    telefone = (row[13] or "").strip() or (row[14] or "").strip()
    return {
        "id": int(row[0]),
        "nome": row[1] or "",
        "razao_social": row[2] or "",
        "slug": row[3] or "",
        "documento": row[4] or "",
        "tipo_pessoa": row[5] or "J",
        "cidade": row[6] or "",
        "uf": row[7] or "",
        "endereco": _endereco_linha(row[8], row[9], row[10], row[11], row[6], row[7], row[12]),
        "telefone": telefone,
        "celular": (row[14] or "").strip(),
        "email": (row[15] or "").strip(),
        "site": (row[16] or "").strip(),
        "status_vinculo": row[17] or "nenhum",
        "qtd_produtos": int(row[19] or 0),
        "segmentos": segmentos,
        "contato": contato,
        "url_loja": f"/fornecedores/loja?id={int(row[0])}",
    }
