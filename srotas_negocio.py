# DropNexo — negócio: categorias, precificação/vínculos e hub de integrações
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from flask import render_template, session, url_for
from srotas_plataforma import MODULO_FORNECEDOR, MODULO_VENDEDOR, garantir_modulo_sessao

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

from vendedor.precificacao.servico_precificacao_vendedor import (  # noqa: E402
    aplicar_precificacao_tenant,
    buscar_regra_precificacao,
    calcular_preco_venda_vendedor as calcular_preco_venda,
)


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

HUB_COPY_INTEGRACOES = {
    MODULO_FORNECEDOR: {
        "titulo": "Integrações",
        "descricao": "Receba pagamentos dos vendedores e sincronize seu catálogo com ERPs.",
    },
    MODULO_VENDEDOR: {
        "titulo": "Integrações",
        "descricao": "Importe pedidos das suas lojas, contrate fretes e acompanhe envios.",
    },
}

_MOD_VENDEDOR = [MODULO_VENDEDOR]
_MOD_FORNECEDOR = [MODULO_FORNECEDOR]

CATEGORIAS_INTEGRACOES = [
    {
        "id": "financeiro",
        "rotulo": "Recebimentos",
        "titulo": "Recebimentos",
        "subtitulo": "Formas de pagamento dos pedidos B2B (PIX e cartão).",
        "modulos": _MOD_FORNECEDOR,
        "itens": [
            {
                "slug": "mercado-pago",
                "nome": "Mercado Pago",
                "descricao": "PIX e cartão de crédito nos pedidos B2B.",
                "cor": "#009EE3",
                "iniciais": "MP",
                "modulos": _MOD_FORNECEDOR,
            },
            {
                "slug": "pix-manual",
                "nome": "PIX Manual",
                "descricao": "Sua chave PIX — o vendedor paga e envia o comprovante.",
                "cor": "#32BCAD",
                "iniciais": "PX",
                "modulos": _MOD_FORNECEDOR,
            },
            {"slug": "pagbank", "nome": "PagBank", "descricao": "Recebimentos PagBank.", "cor": "#1BB99A", "iniciais": "PB", "modulos": _MOD_FORNECEDOR},
            {"slug": "stripe", "nome": "Stripe", "descricao": "Pagamentos internacionais Stripe.", "cor": "#635BFF", "iniciais": "ST", "modulos": _MOD_FORNECEDOR},
            {"slug": "asaas", "nome": "Asaas", "descricao": "Cobranças e recebimentos Asaas.", "cor": "#0030B9", "iniciais": "AS", "modulos": _MOD_FORNECEDOR},
            {"slug": "pagar-me", "nome": "Pagar.me", "descricao": "Gateway Pagar.me.", "cor": "#65A300", "iniciais": "PM", "modulos": _MOD_FORNECEDOR},
            {"slug": "paypal", "nome": "PayPal", "descricao": "Pagamentos PayPal.", "cor": "#003087", "iniciais": "PP", "modulos": _MOD_FORNECEDOR},
        ],
    },
    {
        "id": "catalogo",
        "rotulo": "Catálogo e ERP",
        "titulo": "Catálogo e ERP",
        "subtitulo": "Sincronize produtos, estoque, categorias e NF-e.",
        "modulos": _MOD_FORNECEDOR,
        "itens": [
            {
                "slug": "bling",
                "nome": "Bling",
                "descricao": "Importe produtos, estoque e categorias do seu Bling.",
                "cor": "#28A745",
                "iniciais": "BL",
                "modulos": _MOD_FORNECEDOR,
                "papel": "catalogo",
            },
            {"slug": "olist", "nome": "Olist", "descricao": "Hub Olist para marketplaces e lojas.", "cor": "#6C2EB9", "iniciais": "OL", "modulos": _MOD_FORNECEDOR},
            {"slug": "conta-azul", "nome": "Conta Azul", "descricao": "Gestão financeira e emissão de notas.", "cor": "#0080FF", "iniciais": "CA", "modulos": _MOD_FORNECEDOR},
        ],
    },
    {
        "id": "pedidos",
        "rotulo": "Pedidos",
        "titulo": "Pedidos e lojas",
        "subtitulo": "Importe pedidos de marketplaces, e-commerce e ERP.",
        "modulos": _MOD_VENDEDOR,
        "itens": [
            {"slug": "mercado-livre", "nome": "Mercado Livre", "descricao": "Pedidos e anúncios do Mercado Livre.", "cor": "#FFE600", "iniciais": "ML", "modulos": _MOD_VENDEDOR},
            {"slug": "amazon", "nome": "Amazon", "descricao": "Pedidos da Amazon no seu painel.", "cor": "#FF9900", "iniciais": "AZ", "modulos": _MOD_VENDEDOR},
            {"slug": "magazine-luiza", "nome": "Magazine Luiza", "descricao": "Pedidos do marketplace Magalu.", "cor": "#0086FF", "iniciais": "MG", "modulos": _MOD_VENDEDOR},
            {"slug": "shopee", "nome": "Shopee", "descricao": "Pedidos da Shopee em um só lugar.", "cor": "#EE4D2D", "iniciais": "SH", "modulos": _MOD_VENDEDOR},
            {"slug": "americanas", "nome": "Americanas", "descricao": "Pedidos Americanas / B2W.", "cor": "#E60014", "iniciais": "AM", "modulos": _MOD_VENDEDOR},
            {"slug": "casas-bahia", "nome": "Casas Bahia", "descricao": "Pedidos Casas Bahia / Via.", "cor": "#0033A0", "iniciais": "CB", "modulos": _MOD_VENDEDOR},
            {"slug": "tray", "nome": "Tray", "descricao": "Pedidos da sua loja Tray.", "cor": "#7B2CFF", "iniciais": "TR", "modulos": _MOD_VENDEDOR},
            {"slug": "loja-integrada", "nome": "Loja Integrada", "descricao": "Pedidos da Loja Integrada.", "cor": "#00AEEF", "iniciais": "LI", "modulos": _MOD_VENDEDOR},
            {"slug": "nuvemshop", "nome": "Nuvemshop", "descricao": "Pedidos da sua Nuvemshop.", "cor": "#2C3E50", "iniciais": "NV", "modulos": _MOD_VENDEDOR},
            {"slug": "beezoo", "nome": "Beezoo", "descricao": "Pedidos de lojas Beezoo.", "cor": "#F5A623", "iniciais": "BZ", "modulos": _MOD_VENDEDOR},
            {"slug": "bagy", "nome": "Bagy", "descricao": "Pedidos da plataforma Bagy.", "cor": "#111827", "iniciais": "BG", "modulos": _MOD_VENDEDOR},
            {
                "slug": "bling",
                "nome": "Bling",
                "descricao": "Importe pedidos de venda pagos do seu Bling.",
                "cor": "#28A745",
                "iniciais": "BL",
                "modulos": _MOD_VENDEDOR,
                "papel": "pedidos",
            },
        ],
    },
    {
        "id": "frete",
        "rotulo": "Frete",
        "titulo": "Frete e logística",
        "subtitulo": "Cote fretes, contrate etiquetas e acompanhe rastreios.",
        "modulos": _MOD_VENDEDOR,
        "itens": [
            {
                "slug": "melhor-envio",
                "nome": "Melhor Envio",
                "descricao": "Cote e contrate fretes; o fornecedor só imprime a etiqueta.",
                "cor": "#00B2A9",
                "iniciais": "ME",
                "modulos": _MOD_VENDEDOR,
            },
            {"slug": "correios", "nome": "Correios", "descricao": "PAC, SEDEX e serviços dos Correios.", "cor": "#FFD100", "iniciais": "CR", "modulos": _MOD_VENDEDOR},
            {"slug": "frenet", "nome": "Frenet", "descricao": "Gateway de fretes para e-commerce.", "cor": "#0057A8", "iniciais": "FR", "modulos": _MOD_VENDEDOR},
        ],
    },
]


def _visivel_integracao_modulo(entidade: dict, modulo: str) -> bool:
    mods = entidade.get("modulos")
    if mods:
        return modulo in mods
    if entidade.get("somente_fornecedor"):
        return modulo == MODULO_FORNECEDOR
    return True


def hub_copy_integracoes(modulo: str | None = None) -> dict[str, str]:
    mod = modulo or garantir_modulo_sessao()
    return dict(HUB_COPY_INTEGRACOES.get(mod, HUB_COPY_INTEGRACOES[MODULO_VENDEDOR]))


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
    """URL do ícone da integração (prioriza static/imge/icone_api/ ou módulo api/)."""
    if slug == "mercado-pago":
        return url_for("mercadopago.static", filename="imge/icone_mercadopago.png")
    if slug == "melhor-envio":
        return url_for("melhor_envio.static", filename="imge/icone_melhorenvio.png")
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
            i["icone_png"] = url_icone_integracao(slug, icones_base_url=base)
            i["icone_svg"] = f"{base}{slug}.svg"
            if _arquivo_icone_api(slug) or slug in ("mercado-pago", "melhor-envio"):
                i["icone_custom"] = True
            if item.get("papel"):
                i["bling_papel"] = item["papel"]
            itens.append(i)
        c["itens"] = itens
        out.append(c)
    return out


def catalogo_integracoes_modulo(icones_base_url: str, modulo: str | None = None) -> list[dict]:
    """Catálogo filtrado pelo módulo ativo (fornecedor ou vendedor)."""
    mod = modulo or garantir_modulo_sessao()
    cats_out: list[dict] = []
    for cat in catalogo_com_urls(icones_base_url):
        if not _visivel_integracao_modulo(cat, mod):
            continue
        itens = [i for i in cat.get("itens", []) if _visivel_integracao_modulo(i, mod)]
        if not itens:
            continue
        c = dict(cat)
        c["itens"] = itens
        cats_out.append(c)
    return cats_out


def render_pagina_integracoes(*, nav_codigo: str, icones_base_url: str):
    mod = garantir_modulo_sessao()
    copy = hub_copy_integracoes(mod)
    return render_template(
        "frm_integracoes_hub.html",
        nav_codigo=nav_codigo,
        hub_titulo=copy["titulo"],
        hub_descricao=copy["descricao"],
        modulo_ativo=mod,
        categorias_json=json.dumps(
            catalogo_integracoes_modulo(icones_base_url, mod),
            ensure_ascii=False,
        ),
    )
