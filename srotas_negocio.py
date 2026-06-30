# DropNexo — negócio: categorias, precificação/vínculos e hub de integrações
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from flask import render_template, session, url_for

from pathlib import Path

_RAIZ_PROJETO = Path(__file__).resolve().parent
_ICONES_API_DIR = _RAIZ_PROJETO / "static" / "imge" / "icone_api"

# slug da integração → arquivo em static/imge/icone_api/
ICONES_API_ARQUIVOS: dict[str, str] = {
    "bling": "icone_bling.png",
    "olist": "icone_olist.png",
    "conta-azul": "icone_contaazul.png",
}

# ── Categorias (fornecedor) ───────────────────────────────────────────

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


# ── Precificação e vínculos V2 ────────────────────────────────────────

def calcular_preco_venda(preco_fornecedor: float | Decimal, regra: dict) -> float:
    """Aplica percentuais sobre o preço do fornecedor (preço nunca altera no mestre)."""
    base = float(preco_fornecedor or 0)
    if base <= 0:
        return 0.0
    pct = (
        float(regra.get("pct_marketplace") or 0)
        + float(regra.get("pct_impostos") or 0)
        + float(regra.get("pct_taxas") or 0)
        + float(regra.get("pct_margem_lucro") or 0)
    )
    return round(base * (1 + pct / 100), 2)


def buscar_regra_precificacao(cur, id_vendedor: int, id_segmento: int | None, id_categoria: int | None) -> dict | None:
    if id_categoria:
        cur.execute(
            """
            SELECT pct_marketplace, pct_impostos, pct_taxas, pct_margem_lucro
            FROM tbl_vendedor_precificacao
            WHERE id_tenant_vendedor = %s AND escopo = 'categoria' AND id_categoria = %s AND ativo = TRUE
            LIMIT 1
            """,
            (id_vendedor, id_categoria),
        )
        row = cur.fetchone()
        if row:
            return _row_regra(row)
    if id_segmento:
        cur.execute(
            """
            SELECT pct_marketplace, pct_impostos, pct_taxas, pct_margem_lucro
            FROM tbl_vendedor_precificacao
            WHERE id_tenant_vendedor = %s AND escopo = 'segmento' AND id_segmento = %s AND ativo = TRUE
            LIMIT 1
            """,
            (id_vendedor, id_segmento),
        )
        row = cur.fetchone()
        if row:
            return _row_regra(row)
    cur.execute(
        """
        SELECT pct_marketplace, pct_impostos, pct_taxas, pct_margem_lucro
        FROM tbl_vendedor_precificacao
        WHERE id_tenant_vendedor = %s AND escopo = 'global' AND ativo = TRUE
        LIMIT 1
        """,
        (id_vendedor,),
    )
    row = cur.fetchone()
    return _row_regra(row) if row else None


def _row_regra(row) -> dict:
    return {
        "pct_marketplace": float(row[0] or 0),
        "pct_impostos": float(row[1] or 0),
        "pct_taxas": float(row[2] or 0),
        "pct_margem_lucro": float(row[3] or 0),
    }


def aplicar_precificacao_tenant(cur, id_vendedor: int, escopo: str, id_segmento: int | None, id_categoria: int | None) -> int:
    regra = None
    if escopo == "global":
        regra = buscar_regra_precificacao(cur, id_vendedor, None, None)
    elif escopo == "segmento" and id_segmento:
        regra = buscar_regra_precificacao(cur, id_vendedor, id_segmento, None)
    elif escopo == "categoria" and id_categoria:
        regra = buscar_regra_precificacao(cur, id_vendedor, None, id_categoria)
    if not regra:
        return 0

    where = ["pv.id_tenant_vendedor = %s", "pv.ativo = TRUE", "pv.preco_manual = FALSE"]
    params: list[Any] = [id_vendedor]
    if escopo == "segmento":
        where.append("c.id_segmento = %s")
        params.append(id_segmento)
    elif escopo == "categoria":
        where.append("p.id_categoria = %s")
        params.append(id_categoria)

    cur.execute(
        f"""
        SELECT pv.id, pv.preco_fornecedor
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
        WHERE {' AND '.join(where)}
        """,
        params,
    )
    rows = cur.fetchall()
    n = 0
    for pid, preco_forn in rows:
        novo = calcular_preco_venda(preco_forn, regra)
        cur.execute(
            "UPDATE tbl_produto_vendedor SET preco_venda = %s, atualizado_em = NOW() WHERE id = %s",
            (novo, pid),
        )
        n += 1
    return n


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


# ── Hub de integrações ────────────────────────────────────────────────

CATEGORIAS_INTEGRACOES = [
    {
        "id": "marketplace",
        "rotulo": "Marketplace",
        "titulo": "Marketplace",
        "subtitulo": "Centralize vendas de múltiplos marketplaces automaticamente.",
        "itens": [
            {"slug": "mercado-livre", "nome": "Mercado Livre", "descricao": "Anúncios, pedidos e estoque do Mercado Livre.", "cor": "#FFE600", "iniciais": "ML"},
            {"slug": "amazon", "nome": "Amazon", "descricao": "Vendas e logística da Amazon no seu painel.", "cor": "#FF9900", "iniciais": "AZ"},
            {"slug": "magazine-luiza", "nome": "Magazine Luiza", "descricao": "Integração com o marketplace Magalu.", "cor": "#0086FF", "iniciais": "MG"},
            {"slug": "shopee", "nome": "Shopee", "descricao": "Pedidos e catálogo da Shopee em um só lugar.", "cor": "#EE4D2D", "iniciais": "SH"},
            {"slug": "americanas", "nome": "Americanas", "descricao": "Marketplace Americanas / B2W.", "cor": "#E60014", "iniciais": "AM"},
            {"slug": "casas-bahia", "nome": "Casas Bahia", "descricao": "Vendas e estoque Casas Bahia / Via.", "cor": "#0033A0", "iniciais": "CB"},
        ],
    },
    {
        "id": "ecommerce",
        "rotulo": "E-commerce",
        "titulo": "Plataforma de e-commerce",
        "subtitulo": "Conecte sua loja virtual e sincronize pedidos e produtos.",
        "itens": [
            {"slug": "tray", "nome": "Tray", "descricao": "Loja Tray — pedidos, produtos e estoque.", "cor": "#7B2CFF", "iniciais": "TR"},
            {"slug": "loja-integrada", "nome": "Loja Integrada", "descricao": "Integração com a Loja Integrada.", "cor": "#00AEEF", "iniciais": "LI"},
            {"slug": "nuvemshop", "nome": "Nuvemshop", "descricao": "Sincronize sua Nuvemshop com o DropNexo.", "cor": "#2C3E50", "iniciais": "NV"},
            {"slug": "beezoo", "nome": "Beezoo", "descricao": "Conector para lojas Beezoo.", "cor": "#F5A623", "iniciais": "BZ"},
            {"slug": "bagy", "nome": "Bagy", "descricao": "Integração com a plataforma Bagy.", "cor": "#111827", "iniciais": "BG"},
        ],
    },
    {
        "id": "frete",
        "rotulo": "Frete",
        "titulo": "Frete e logística",
        "subtitulo": "Cotações, etiquetas e rastreio de envios.",
        "itens": [
            {"slug": "melhor-envio", "nome": "Melhor Envio", "descricao": "Cotação e compra de fretes em um clique.", "cor": "#00B2A9", "iniciais": "ME"},
            {"slug": "correios", "nome": "Correios", "descricao": "PAC, SEDEX e serviços dos Correios.", "cor": "#FFD100", "iniciais": "CR"},
            {"slug": "frenet", "nome": "Frenet", "descricao": "Gateway de fretes para e-commerce.", "cor": "#0057A8", "iniciais": "FR"},
        ],
    },
    {
        "id": "erp",
        "rotulo": "ERP",
        "titulo": "ERP e gestão",
        "subtitulo": "Sincronize financeiro, estoque e notas fiscais.",
        "itens": [
            {"slug": "bling", "nome": "Bling", "descricao": "ERP Bling — pedidos, NF-e e estoque.", "cor": "#28A745", "iniciais": "BL"},
            {"slug": "olist", "nome": "Olist", "descricao": "Hub Olist para marketplaces e lojas.", "cor": "#6C2EB9", "iniciais": "OL"},
            {"slug": "conta-azul", "nome": "Conta Azul", "descricao": "Gestão financeira e emissão de notas.", "cor": "#0080FF", "iniciais": "CA"},
        ],
    },
]


def _arquivo_icone_api(slug: str) -> str | None:
    """Resolve PNG em static/imge/icone_api/ (mapa explícito ou convenção icone_{slug}.png)."""
    nome = ICONES_API_ARQUIVOS.get(slug)
    if nome and (_ICONES_API_DIR / nome).is_file():
        return nome
    conv = f"icone_{slug.replace('-', '')}.png"
    if (_ICONES_API_DIR / conv).is_file():
        return conv
    return None


def url_icone_integracao(slug: str, *, icones_base_url: str = "") -> str:
    """URL do ícone da integração (prioriza static/imge/icone_api/)."""
    arquivo = _arquivo_icone_api(slug)
    if arquivo:
        return url_for("static", filename=f"imge/icone_api/{arquivo}")
    base = icones_base_url if icones_base_url.endswith("/") else f"{icones_base_url}/"
    return f"{base}{slug}.png"


def catalogo_com_urls(icones_base_url: str) -> list[dict]:
    base = icones_base_url if icones_base_url.endswith("/") else icones_base_url + "/"
    out = []
    for cat in CATEGORIAS_INTEGRACOES:
        c = dict(cat)
        itens = []
        for item in cat["itens"]:
            i = dict(item)
            slug = item["slug"]
            arquivo_api = _arquivo_icone_api(slug)
            if arquivo_api:
                url_png = url_for("static", filename=f"imge/icone_api/{arquivo_api}")
                i["icone_png"] = url_png
                i["icone_svg"] = f"{base}{slug}.svg"
                i["icone_custom"] = True
            else:
                i["icone_png"] = f"{base}{slug}.png"
                i["icone_svg"] = f"{base}{slug}.svg"
            itens.append(i)
        c["itens"] = itens
        out.append(c)
    return out


def render_pagina_integracoes(*, nav_codigo: str, icones_base_url: str):
    return render_template(
        "frm_integracoes_hub.html",
        nav_codigo=nav_codigo,
        categorias_json=json.dumps(catalogo_com_urls(icones_base_url), ensure_ascii=False),
    )
