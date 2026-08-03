"""Definição DropNexo dos campos de importação/exportação de catálogo.

Obrigatório é regra do sistema — o usuário só mapeia a coluna do arquivo.
"""

from __future__ import annotations

MAX_IMAGENS_IMPORT = 10

# Campos de produto simples / pai (sem variação)
_CAMPOS_PRODUTO = [
    ("sku", True, "SKU"),
    ("nome", True, "Nome"),
    ("preco", True, "Preço de venda"),
    ("unidade", True, "Unidade"),
    ("descricao", True, "Descrição"),
    ("categoria", True, "Categoria"),
    ("peso_bruto_kg", True, "Peso bruto (kg)"),
    ("altura_cm", True, "Altura (cm)"),
    ("largura_cm", True, "Largura (cm)"),
    ("profundidade_cm", True, "Comprimento (cm)"),
    ("ncm", True, "NCM"),
    ("gtin", True, "GTIN/EAN"),
    ("origem_fiscal", True, "Origem fiscal"),
    ("peso_liquido_kg", False, "Peso líquido (kg)"),
    ("preco_promocional", False, "Preço promocional"),
    ("preco_custo", False, "Preço de custo"),
    ("quantidade", False, "Quantidade / estoque"),
    ("marca", False, "Marca"),
    ("publicado", False, "Publicado na rede"),
    ("cest", False, "CEST"),
    ("condicao", False, "Condição"),
]

# Variação (obrigatórios só quando a linha for variação)
_CAMPOS_VARIACAO = [
    ("sku_pai", True, "SKU do produto pai"),
    ("atributos", True, "Atributos (ex.: Cor=Azul;Tamanho=P)"),
    ("nome_variacao", False, "Nome da variação"),
]

# Imagens — presença mínima de 1 URL é validada no motor
_CAMPOS_IMAGEM_UNICO = [
    ("imagens", True, "Imagens (URLs no mesmo campo)"),
]

_CAMPOS_IMAGEM_COLUNAS = [
    (f"imagem_{i}", i == 1, f"Imagem {i}") for i in range(1, MAX_IMAGENS_IMPORT + 1)
]


def _item(campo: str, obrigatorio: bool, rotulo: str, ordem: int) -> dict:
    return {
        "campo_interno": campo,
        "obrigatorio": obrigatorio,
        "rotulo": rotulo,
        "ordem": ordem,
        "coluna_arquivo": campo,
    }


def mapa_obrigatoriedade() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for campo, obr, _ in _CAMPOS_PRODUTO + _CAMPOS_VARIACAO:
        out[campo] = obr
    out["imagens"] = True
    for i in range(1, MAX_IMAGENS_IMPORT + 1):
        out[f"imagem_{i}"] = i == 1
    return out


def campos_base_catalogo(*, modo_imagens: str = "colunas") -> list[dict]:
    """Lista canônica para o editor de layout."""
    modo = (modo_imagens or "colunas").strip().lower()
    if modo not in ("colunas", "unico"):
        modo = "colunas"
    ordem = 1
    out: list[dict] = []
    for campo, obr, rotulo in _CAMPOS_PRODUTO:
        out.append(_item(campo, obr, rotulo, ordem))
        ordem += 1
    for campo, obr, rotulo in _CAMPOS_VARIACAO:
        out.append(_item(campo, obr, rotulo, ordem))
        ordem += 1
    img_campos = _CAMPOS_IMAGEM_UNICO if modo == "unico" else _CAMPOS_IMAGEM_COLUNAS
    for campo, obr, rotulo in img_campos:
        out.append(_item(campo, obr, rotulo, ordem))
        ordem += 1
    return out


def aplicar_obrigatoriedade_sistema(campos: list[dict]) -> list[dict]:
    """Garante obrigatorio do sistema, independentemente do que veio do cliente."""
    regra = mapa_obrigatoriedade()
    out = []
    for c in campos:
        campo = (c.get("campo_interno") or "").strip()
        if not campo:
            continue
        item = dict(c)
        item["campo_interno"] = campo
        item["coluna_arquivo"] = (c.get("coluna_arquivo") or campo).strip() or campo
        if campo in regra:
            item["obrigatorio"] = regra[campo]
        else:
            item["obrigatorio"] = bool(c.get("obrigatorio"))
        out.append(item)
    return out


# Colunas seguras na exportação (espelho do import, sem custo sensível no vendedor)
COLUNAS_EXPORT_FORNECEDOR = [
    "sku",
    "sku_pai",
    "atributos",
    "nome",
    "nome_variacao",
    "descricao",
    "preco",
    "preco_promocional",
    "preco_custo",
    "quantidade",
    "categoria",
    "unidade",
    "marca",
    "peso_liquido_kg",
    "peso_bruto_kg",
    "altura_cm",
    "largura_cm",
    "profundidade_cm",
    "ncm",
    "gtin",
    "origem_fiscal",
    "cest",
    "condicao",
    "publicado",
    "imagens",
]

COLUNAS_EXPORT_VENDEDOR = [
    c for c in COLUNAS_EXPORT_FORNECEDOR if c != "preco_custo"
]
