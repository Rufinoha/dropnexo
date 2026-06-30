"""Requisitos do fornecedor para vínculo com vendedores."""
from __future__ import annotations

from decimal import Decimal


def _row_para_dict(row) -> dict:
    if not row:
        return requisitos_padrao()
    return {
        "exige_cnpj": bool(row[0]),
        "exige_nf": bool(row[1]),
        "cobra_taxa_vinculo": bool(row[2]),
        "valor_taxa_vinculo": float(row[3] or 0),
        "cobra_taxa_mensal": bool(row[4]),
        "valor_taxa_mensal": float(row[5] or 0),
        "texto_adicional": row[6] or "",
        "cobra_taxa_pedido": bool(row[7]) if len(row) > 7 else False,
        "valor_taxa_pedido": float(row[8] or 0) if len(row) > 8 else 0.0,
        "mostrar_contato_vendedor": bool(row[9]) if len(row) > 9 else True,
    }


def requisitos_padrao() -> dict:
    return {
        "exige_cnpj": False,
        "exige_nf": False,
        "cobra_taxa_vinculo": False,
        "valor_taxa_vinculo": 0.0,
        "cobra_taxa_mensal": False,
        "valor_taxa_mensal": 0.0,
        "cobra_taxa_pedido": False,
        "valor_taxa_pedido": 0.0,
        "texto_adicional": "",
        "mostrar_contato_vendedor": True,
    }


def carregar_requisitos_raw(cur, id_fornecedor: int) -> tuple[dict, bool]:
    cur.execute(
        """
        SELECT exige_cnpj, exige_nf, cobra_taxa_vinculo, valor_taxa_vinculo,
               cobra_taxa_mensal, valor_taxa_mensal, texto_adicional,
               cobra_taxa_pedido, valor_taxa_pedido, mostrar_contato_vendedor
        FROM tbl_fornecedor_requisitos_vendedor
        WHERE id_tenant = %s
        """,
        (id_fornecedor,),
    )
    row = cur.fetchone()
    return _row_para_dict(row), row is not None


def carregar_requisitos(cur, id_fornecedor: int) -> dict:
    req, _ = carregar_requisitos_raw(cur, id_fornecedor)
    return req


def carregar_contato_responsavel_fornecedor(cur, id_fornecedor: int) -> dict | None:
    """Nome, e-mail e WhatsApp do dono/responsável (para exibir ao vendedor)."""
    cur.execute(
        """
        SELECT u.nome, u.email, COALESCE(u.whatsapp, '')
        FROM tbl_usuario u
        INNER JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id AND ut.ativo = TRUE
        INNER JOIN tbl_perfil pf ON pf.id = ut.id_perfil AND pf.codigo = 'dono'
        WHERE ut.id_tenant = %s AND u.ativo = TRUE
        ORDER BY ut.id
        LIMIT 1
        """,
        (id_fornecedor,),
    )
    row = cur.fetchone()
    if row:
        return {"nome": row[0] or "", "email": row[1] or "", "whatsapp": row[2] or ""}

    cur.execute(
        """
        SELECT COALESCE(t.nome_fantasia, t.nome), COALESCE(t.email_comercial, ''),
               COALESCE(NULLIF(t.celular_comercial, ''), t.telefone_comercial, '')
        FROM tbl_tenant t
        WHERE t.id = %s
        """,
        (id_fornecedor,),
    )
    t = cur.fetchone()
    if not t:
        return None
    return {"nome": t[0] or "", "email": t[1] or "", "whatsapp": t[2] or ""}


def salvar_requisitos(cur, id_fornecedor: int, dados: dict) -> None:
    exige_cnpj = bool(dados.get("exige_cnpj"))
    exige_nf = bool(dados.get("exige_nf"))
    cobra_vinculo = bool(dados.get("cobra_taxa_vinculo"))
    cobra_mensal = bool(dados.get("cobra_taxa_mensal"))
    cobra_pedido = bool(dados.get("cobra_taxa_pedido"))
    mostrar_contato = bool(dados.get("mostrar_contato_vendedor", True))
    valor_vinculo = max(0, float(dados.get("valor_taxa_vinculo") or 0))
    valor_mensal = max(0, float(dados.get("valor_taxa_mensal") or 0))
    valor_pedido = max(0, float(dados.get("valor_taxa_pedido") or 0))
    texto = (dados.get("texto_adicional") or "").strip() or None

    cur.execute(
        """
        INSERT INTO tbl_fornecedor_requisitos_vendedor
            (id_tenant, exige_cnpj, exige_nf, cobra_taxa_vinculo, valor_taxa_vinculo,
             cobra_taxa_mensal, valor_taxa_mensal, cobra_taxa_pedido, valor_taxa_pedido,
             mostrar_contato_vendedor, texto_adicional, atualizado_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (id_tenant) DO UPDATE SET
            exige_cnpj = EXCLUDED.exige_cnpj,
            exige_nf = EXCLUDED.exige_nf,
            cobra_taxa_vinculo = EXCLUDED.cobra_taxa_vinculo,
            valor_taxa_vinculo = EXCLUDED.valor_taxa_vinculo,
            cobra_taxa_mensal = EXCLUDED.cobra_taxa_mensal,
            valor_taxa_mensal = EXCLUDED.valor_taxa_mensal,
            cobra_taxa_pedido = EXCLUDED.cobra_taxa_pedido,
            valor_taxa_pedido = EXCLUDED.valor_taxa_pedido,
            mostrar_contato_vendedor = EXCLUDED.mostrar_contato_vendedor,
            texto_adicional = EXCLUDED.texto_adicional,
            atualizado_em = NOW()
        """,
        (
            id_fornecedor,
            exige_cnpj,
            exige_nf,
            cobra_vinculo,
            Decimal(str(valor_vinculo)),
            cobra_mensal,
            Decimal(str(valor_mensal)),
            cobra_pedido,
            Decimal(str(valor_pedido)),
            mostrar_contato,
            texto,
        ),
    )


def requisitos_tem_conteudo(req: dict) -> bool:
    if not req:
        return False
    if req.get("exige_cnpj") or req.get("exige_nf"):
        return True
    if req.get("cobra_taxa_vinculo"):
        return True
    if req.get("cobra_taxa_mensal"):
        return True
    if req.get("cobra_taxa_pedido"):
        return True
    if float(req.get("valor_taxa_vinculo") or 0) > 0:
        return True
    if float(req.get("valor_taxa_mensal") or 0) > 0:
        return True
    if float(req.get("valor_taxa_pedido") or 0) > 0:
        return True
    if (req.get("texto_adicional") or "").strip():
        return True
    return False
