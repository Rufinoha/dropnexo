from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, session


_MOD = Path(__file__).resolve().parent

fn_catalogo_bp = Blueprint(
    "fn_catalogo",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/catalogo",
)


def init_app(app):
    app.register_blueprint(fn_catalogo_bp)

# --- catalogo_db ---


import itertools
import json
import re
from decimal import Decimal
from typing import Any

from flask import jsonify, session

from global_utils import agora_utc, url_imagem_produto, usuario_tem_permissao


def exigir_catalogo_escrita():
    if session.get("eh_desenvolvedor") or usuario_tem_permissao("catalogos.editar"):
        return None
    return jsonify(success=False, message="Sem permissão para editar catálogo."), 403


def sync_pai_de_variante_padrao(cur, id_produto: int) -> None:
    """Mantém colunas legadas em tbl_produto alinhadas à variante padrão (SKU do pai não muda)."""
    cur.execute(
        """
        UPDATE tbl_produto p SET
            preco = v.preco,
            preco_promocional = v.preco_promocional,
            preco_custo = COALESCE(v.preco_custo, p.preco_custo),
            imagem_url = COALESCE(v.imagem_url, p.imagem_url),
            atualizado_em = %s
        FROM tbl_produto_variante v
        WHERE p.id = %s AND v.id = p.id_variante_padrao
        """,
        (agora_utc(), id_produto),
    )


def garantir_variante_padrao(cur, id_produto: int, id_tenant: int) -> int:
    cur.execute("SELECT id_variante_padrao, nome FROM tbl_produto WHERE id = %s AND id_tenant = %s", (id_produto, id_tenant))
    row = cur.fetchone()
    if not row:
        raise ValueError("Produto não encontrado.")
    if row[0]:
        return int(row[0])
    cur.execute(
        """
        INSERT INTO tbl_produto_variante (id_produto, nome_exibicao, preco, ativo, ordem, atualizado_em)
        VALUES (%s, %s, 0, TRUE, 0, %s)
        RETURNING id
        """,
        (id_produto, row[1] or "Padrão", agora_utc()),
    )
    vid = cur.fetchone()[0]
    cur.execute(
        "UPDATE tbl_produto SET id_variante_padrao = %s, formato = COALESCE(formato, 'S') WHERE id = %s",
        (vid, id_produto),
    )
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
        VALUES (%s, 0, %s) ON CONFLICT (id_variante) DO NOTHING
        """,
        (vid, agora_utc()),
    )
    return int(vid)


def _f(row, idx, default=None):
    if row is None or len(row) <= idx:
        return default
    return row[idx]


def variante_dict(row, *, incluir_produto: bool = False) -> dict[str, Any]:
    caminho_img = row[8] or ""
    d = {
        "id": row[0],
        "id_produto": row[1],
        "sku": row[2] or "",
        "nome_exibicao": row[3],
        "preco": float(row[4] or 0),
        "preco_promocional": float(row[5]) if row[5] is not None else None,
        "preco_custo": float(row[6]) if row[6] is not None else None,
        "atributos": row[7] if isinstance(row[7], dict) else (json.loads(row[7]) if row[7] else {}),
        "imagem_url": url_exibicao(caminho_img),
        "imagem_caminho": caminho_img,
        "ativo": bool(row[9]),
        "ordem": int(row[10] or 0),
        "estoque": int(row[11] or 0) if len(row) > 11 else 0,
    }
    if len(row) > 12 and not incluir_produto:
        d["herda_pai"] = bool(_f(row, 12, True))
        d["peso_liquido_kg"] = float(_f(row, 13)) if _f(row, 13) is not None else None
        d["peso_bruto_kg"] = float(_f(row, 14)) if _f(row, 14) is not None else None
        d["altura_cm"] = float(_f(row, 15)) if _f(row, 15) is not None else None
        d["largura_cm"] = float(_f(row, 16)) if _f(row, 16) is not None else None
        d["profundidade_cm"] = float(_f(row, 17)) if _f(row, 17) is not None else None
        d["gtin"] = _f(row, 18) or ""
        d["ncm"] = _f(row, 19) or ""
        d["id_imagem_principal"] = int(_f(row, 20)) if _f(row, 20) else None
    if incluir_produto and len(row) > 12:
        d["produto_nome"] = row[12]
        d["fornecedor_nome"] = row[13] if len(row) > 13 else ""
        d["formato"] = row[14] if len(row) > 14 else "S"
    return d


SQL_VARIANTE_LISTA = """
    SELECT v.id, v.id_produto, v.sku, v.nome_exibicao, v.preco, v.preco_promocional,
           v.preco_custo, v.atributos,
           COALESCE(img.caminho, v.imagem_url) AS imagem_efetiva,
           v.ativo, v.ordem,
           COALESCE(e.quantidade, 0),
           v.herda_pai, v.peso_liquido_kg, v.peso_bruto_kg, v.altura_cm, v.largura_cm,
           v.profundidade_cm, v.gtin, v.ncm, v.id_imagem_principal
    FROM tbl_produto_variante v
    LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
    LEFT JOIN tbl_produto_imagem img ON img.id = v.id_imagem_principal
"""


def produto_pai_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "sku": row[1] or "",
        "nome": row[2],
        "descricao": row[3] or "",
        "preco": float(row[4] or 0),
        "preco_promocional": float(row[5]) if row[5] is not None else None,
        "preco_custo": float(row[6]) if row[6] is not None else None,
        "gtin": row[7] or "",
        "ncm": row[8] or "",
        "peso_liquido_kg": float(row[9]) if row[9] is not None else None,
        "peso_bruto_kg": float(row[10]) if row[10] is not None else None,
        "altura_cm": float(row[11]) if row[11] is not None else None,
        "largura_cm": float(row[12]) if row[12] is not None else None,
        "profundidade_cm": float(row[13]) if row[13] is not None else None,
        "imagem_url": row[14] or "",
        "referencia": row[15] or "",
        "formato": row[16] or "S",
    }


def merge_variante_exibicao(variante: dict[str, Any], pai: dict[str, Any]) -> dict[str, Any]:
    """Campos efetivos para exibição (herda do pai quando herda_pai)."""
    out = dict(variante)
    if not variante.get("herda_pai", True):
        return out
    for k in (
        "preco",
        "preco_promocional",
        "preco_custo",
        "gtin",
        "ncm",
        "peso_liquido_kg",
        "peso_bruto_kg",
        "altura_cm",
        "largura_cm",
        "profundidade_cm",
    ):
        if out.get(k) in (None, "", 0) and pai.get(k) not in (None, ""):
            out[k] = pai[k]
    if pai.get("imagem_url"):
        out["imagem_url"] = url_exibicao(pai["imagem_url"])
        out["imagem_caminho"] = pai["imagem_url"]
    return out


def rotulo_atributos(atributos: dict) -> str:
    if not atributos:
        return ""
    return ", ".join(f"{k}: {v}" for k, v in atributos.items() if v)


def valores_atributos_texto(atributos: dict) -> str:
    """Valores das variações separados por espaço (sem travessão)."""
    if not atributos:
        return ""
    return " ".join(str(v).strip() for v in atributos.values() if str(v).strip())


def nome_exibicao_variante(pai_nome: str, atributos: dict) -> str:
    base = (pai_nome or "").strip()
    sufixo = valores_atributos_texto(atributos)
    if base and sufixo:
        return f"{base} {sufixo}"[:255]
    return (base or sufixo or "Padrão")[:255]


def descricao_variante(pai_descricao: str, atributos: dict) -> str:
    """Anexa variação à descrição do pai com um espaço (texto simples)."""
    base = (pai_descricao or "").strip()
    sufixo = valores_atributos_texto(atributos)
    if not sufixo:
        return base
    if not base:
        return sufixo
    return f"{base} {sufixo}"


def sku_raiz_produto(sku: str | None, id_produto: int, referencia: str | None = None) -> str:
    """SKU raiz do pai (ex.: 33). Ignora sufixos de variações antigas colados no campo."""
    for candidato in ((referencia or "").strip(), (sku or "").strip()):
        if not candidato:
            continue
        raiz = candidato.split("-", 1)[0] if "-" in candidato else candidato
        if raiz:
            return raiz[:64]
    return f"P{id_produto}"


def recuperar_e_fixar_sku_raiz(
    cur,
    id_produto: int,
    sku: str | None,
    referencia: str | None = None,
) -> str:
    """Normaliza o SKU do pai no banco e devolve só a raiz (nunca reaproveita sufixos antigos)."""
    raiz = sku_raiz_produto(sku, id_produto, referencia)
    cur.execute("UPDATE tbl_produto SET sku = %s WHERE id = %s", (raiz, id_produto))
    return raiz


def _slugs_atributos_ordenados(nomes_ordem: list[str], atributos: dict) -> list[str]:
    partes: list[str] = []
    visto: set[str] = set()
    for nome in nomes_ordem:
        valor = atributos.get(nome)
        if valor is None or str(valor).strip() == "":
            continue
        slug = _slug_sku_var(str(valor))
        if slug and slug not in visto:
            partes.append(slug)
            visto.add(slug)
    return partes


def montar_sku_variacao(
    sku_raiz: str,
    nomes_ordem: list[str],
    atributos: dict,
    *,
    seq: int = 0,
) -> str:
    """
    Monta SKU sempre do zero: {raiz}-{slug attr 1}-{slug attr 2}…
    seq>0 acrescenta sufixo numérico só para desempate no tenant.
    """
    raiz = (sku_raiz or "").strip()
    if "-" in raiz:
        raiz = raiz.split("-", 1)[0]
    if not raiz:
        raiz = "P"
    raiz = raiz[:64]
    partes = _slugs_atributos_ordenados(nomes_ordem, atributos)
    if not partes:
        sufixo = f"V{seq or 1}"
        return f"{raiz}-{sufixo}"[:64]
    corpo = "-".join(partes)
    if seq > 0:
        corpo = f"{corpo}-{seq}"
    return f"{raiz}-{corpo}"[:64]


def sku_conflito_tenant(
    cur,
    id_tenant: int,
    sku: str,
    *,
    ignorar_id_produto: int | None = None,
    ignorar_id_variante: int | None = None,
) -> str | None:
    """
    Verifica se o SKU já existe no catálogo do fornecedor (tenant).
    Ignora variantes do mesmo produto pai (produto simples com SKU igual na variante padrão).
    """
    sku = (sku or "").strip()
    if not sku:
        return None

    cur.execute(
        """
        SELECT nome FROM tbl_produto
        WHERE id_tenant = %s AND TRIM(sku) = %s
          AND (%s IS NULL OR id <> %s)
        LIMIT 1
        """,
        (id_tenant, sku, ignorar_id_produto, ignorar_id_produto),
    )
    row = cur.fetchone()
    if row:
        return f"SKU «{sku}» já está no produto «{row[0]}» deste fornecedor."

    cur.execute(
        """
        SELECT p.nome, v.nome_exibicao
        FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        WHERE p.id_tenant = %s AND TRIM(v.sku) = %s
          AND (%s IS NULL OR v.id_produto <> %s)
          AND (%s IS NULL OR v.id <> %s)
        LIMIT 1
        """,
        (id_tenant, sku, ignorar_id_produto, ignorar_id_produto, ignorar_id_variante, ignorar_id_variante),
    )
    row = cur.fetchone()
    if row:
        return f"SKU «{sku}» já está na variação «{row[1]}» do produto «{row[0]}» deste fornecedor."
    return None


def exigir_sku_unico_tenant(
    cur,
    id_tenant: int,
    sku: str,
    *,
    ignorar_id_produto: int | None = None,
    ignorar_id_variante: int | None = None,
) -> None:
    msg = sku_conflito_tenant(
        cur,
        id_tenant,
        sku,
        ignorar_id_produto=ignorar_id_produto,
        ignorar_id_variante=ignorar_id_variante,
    )
    if msg:
        raise ValueError(msg)


def resolver_sku_unico_tenant(
    cur,
    id_tenant: int,
    sku_raiz: str,
    nomes_ordem: list[str],
    atributos: dict,
    id_produto: int,
    ja_reservados: set[str] | None = None,
) -> str:
    """Garante SKU único no tenant, sempre remontado a partir da raiz e dos atributos."""
    reservados = ja_reservados or set()
    for seq in range(0, 100):
        candidato = montar_sku_variacao(sku_raiz, nomes_ordem, atributos, seq=seq)
        if candidato not in reservados and sku_conflito_tenant(
            cur, id_tenant, candidato, ignorar_id_produto=id_produto
        ) is None:
            return candidato
    base = montar_sku_variacao(sku_raiz, nomes_ordem, atributos)
    raise ValueError(
        f"Não foi possível gerar SKU único para «{base}» neste fornecedor. "
        "Verifique se outro produto já usa esse código."
    )


def limpar_variantes_produto(cur, id_produto: int) -> None:
    cur.execute("UPDATE tbl_produto SET id_variante_padrao = NULL WHERE id = %s", (id_produto,))
    cur.execute("DELETE FROM tbl_produto_variante WHERE id_produto = %s", (id_produto,))


def variante_rede_valida(cur, id_variante: int, id_tenant_vendedor: int) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM tbl_produto_variante v
        INNER JOIN tbl_produto p ON p.id = v.id_produto
        INNER JOIN tbl_tenant t ON t.id = p.id_tenant
        WHERE v.id = %s
          AND p.id_tenant <> %s
          AND p.publicado = TRUE
          AND p.ativo = TRUE
          AND v.ativo = TRUE
          AND t.ativo = TRUE
          AND t.tipo_negocio IN ('fornecedor', 'hibrido')
        """,
        (id_variante, id_tenant_vendedor),
    )
    return cur.fetchone() is not None


def estoque_kit_componentes(cur, itens: list[tuple[int, int]]) -> int:
    """itens = [(id_variante, quantidade), ...] → estoque máximo montável."""
    if not itens:
        return 0
    minimo = None
    for id_var, qtd in itens:
        if qtd <= 0:
            return 0
        cur.execute(
            "SELECT COALESCE(quantidade, 0) FROM tbl_produto_variante_estoque WHERE id_variante = %s",
            (id_var,),
        )
        row = cur.fetchone()
        disp = int(row[0] or 0) // qtd if row else 0
        minimo = disp if minimo is None else min(minimo, disp)
    return minimo or 0


def preco_sugerido_kit(cur, itens: list[tuple[int, int]]) -> Decimal:
    total = Decimal("0")
    for id_var, qtd in itens:
        cur.execute("SELECT preco, preco_promocional FROM tbl_produto_variante WHERE id = %s", (id_var,))
        row = cur.fetchone()
        if not row:
            continue
        preco = Decimal(str(row[1] if row[1] is not None and row[1] < row[0] else row[0] or 0))
        total += preco * qtd
    return total


def categorias_arvore(cur, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        SELECT id, nome, parent_id, ordem
        FROM tbl_categoria
        WHERE id_tenant = %s AND ativo = TRUE
        ORDER BY ordem, nome
        """,
        (id_tenant,),
    )
    rows = [{"id": r[0], "nome": r[1], "parent_id": r[2], "ordem": r[3], "filhos": []} for r in cur.fetchall()]
    by_id = {c["id"]: c for c in rows}
    raiz = []
    for c in rows:
        pid = c["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["filhos"].append(c)
        else:
            raiz.append(c)
    return raiz


def _slug_sku_var(parte: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "", (parte or "").upper())[:12]
    return s or "VAR"


def _atributos_produto(cur, id_produto: int) -> list[tuple[str, list[str]]]:
    cur.execute(
        "SELECT nome, valores, ordem FROM tbl_produto_atributo WHERE id_produto = %s ORDER BY ordem, nome",
        (id_produto,),
    )
    attrs = []
    nomes_vistos: set[str] = set()
    for nome_attr, vals, _ord in cur.fetchall():
        chave = (nome_attr or "").strip().lower()
        if not chave or chave in nomes_vistos:
            continue
        nomes_vistos.add(chave)
        lista = vals if isinstance(vals, list) else (json.loads(vals) if vals else [])
        valores_unicos: list[str] = []
        vistos_val: set[str] = set()
        for v in lista:
            txt = str(v).strip()
            if not txt:
                continue
            chave_v = txt.lower()
            if chave_v in vistos_val:
                continue
            vistos_val.add(chave_v)
            valores_unicos.append(txt)
        if valores_unicos:
            attrs.append((nome_attr, valores_unicos))
    return attrs


def salvar_atributo_produto(cur, id_produto: int, nome: str, valores: list, ordem: int = 0) -> int:
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Nome do atributo obrigatório.")
    cur.execute(
        """
        INSERT INTO tbl_produto_atributo (id_produto, nome, valores, ordem)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_produto, nome) DO UPDATE SET valores = EXCLUDED.valores, ordem = EXCLUDED.ordem
        RETURNING id
        """,
        (id_produto, nome, json.dumps(valores), ordem),
    )
    aid = cur.fetchone()[0]
    cur.execute("UPDATE tbl_produto SET formato = 'E' WHERE id = %s AND formato = 'S'", (id_produto,))
    return int(aid)


def variantes_precisam_regenerar(cur, id_produto: int, id_tenant: int) -> bool:
    """True quando variantes/SKUs não batem com os atributos atuais ou estão legados."""
    cur.execute(
        "SELECT sku, referencia FROM tbl_produto WHERE id = %s AND id_tenant = %s",
        (id_produto, id_tenant),
    )
    row_p = cur.fetchone()
    if not row_p:
        return False

    attrs = _atributos_produto(cur, id_produto)
    if not attrs:
        return False

    nomes_attr = [a[0] for a in attrs]
    listas = [a[1] for a in attrs]
    combos = list(itertools.product(*listas))
    if len(combos) <= 1:
        return False

    sku_raiz = sku_raiz_produto(row_p[0], id_produto, row_p[1])
    esperados = {
        montar_sku_variacao(sku_raiz, nomes_attr, dict(zip(nomes_attr, combo)))
        for combo in combos
    }

    cur.execute(
        "SELECT sku, atributos FROM tbl_produto_variante WHERE id_produto = %s",
        (id_produto,),
    )
    rows = cur.fetchall()
    if len(rows) != len(combos):
        return True

    atuais: set[str] = set()
    for sku_v, atr_raw in rows:
        atr = atr_raw if isinstance(atr_raw, dict) else (json.loads(atr_raw) if atr_raw else {})
        if not atr:
            return True
        sku_txt = (sku_v or "").strip()
        atuais.add(sku_txt)
        partes = sku_txt.split("-")
        if len(partes) > len(set(partes)):
            return True

    return atuais != esperados


def sincronizar_variantes_se_necessario(cur, id_produto: int, id_tenant: int) -> bool:
    if not variantes_precisam_regenerar(cur, id_produto, id_tenant):
        return False
    gerar_variantes_produto(cur, id_produto, id_tenant)
    return True


def gerar_variantes_produto(cur, id_produto: int, id_tenant: int) -> int:
    """Remove variantes antigas e recria todas pela combinação cartesiana dos atributos."""
    cur.execute(
        """
        SELECT nome, sku, descricao, preco, preco_promocional, preco_custo, referencia
        FROM tbl_produto WHERE id = %s AND id_tenant = %s
        """,
        (id_produto, id_tenant),
    )
    pai = cur.fetchone()
    if not pai:
        raise ValueError("Produto não encontrado.")

    limpar_variantes_produto(cur, id_produto)
    attrs = _atributos_produto(cur, id_produto)
    if not attrs:
        cur.execute("UPDATE tbl_produto SET formato = 'S' WHERE id = %s", (id_produto,))
        return 0

    nomes_attr = [a[0] for a in attrs]
    listas = [a[1] for a in attrs]
    combos = list(itertools.product(*listas))
    if len(combos) <= 1:
        cur.execute("UPDATE tbl_produto SET formato = 'S' WHERE id = %s", (id_produto,))
        return 0

    sku_raiz = recuperar_e_fixar_sku_raiz(cur, id_produto, pai[1], pai[6])
    exigir_sku_unico_tenant(cur, id_tenant, sku_raiz, ignorar_id_produto=id_produto)
    pai_nome = (pai[0] or "").strip()
    criadas = 0
    primeiro_vid = None
    skus_usados: set[str] = set()

    for ordem, combo in enumerate(combos, start=1):
        atributos = dict(zip(nomes_attr, combo))
        sku_var = resolver_sku_unico_tenant(
            cur,
            id_tenant,
            sku_raiz,
            nomes_attr,
            atributos,
            id_produto,
            skus_usados,
        )
        skus_usados.add(sku_var)
        nome_var = nome_exibicao_variante(pai_nome, atributos)
        cur.execute(
            """
            INSERT INTO tbl_produto_variante (
                id_produto, sku, nome_exibicao, preco, preco_promocional, preco_custo,
                atributos, ativo, ordem, herda_pai, atualizado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s,TRUE,%s)
            RETURNING id
            """,
            (
                id_produto,
                sku_var,
                nome_var,
                pai[3],
                pai[4],
                pai[5],
                json.dumps(atributos, ensure_ascii=False),
                ordem,
                agora_utc(),
            ),
        )
        vid = cur.fetchone()[0]
        if primeiro_vid is None:
            primeiro_vid = vid
        cur.execute(
            """
            INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
            VALUES (%s, 0, %s) ON CONFLICT (id_variante) DO NOTHING
            """,
            (vid, agora_utc()),
        )
        criadas += 1

    cur.execute(
        "UPDATE tbl_produto SET formato = 'E', id_variante_padrao = %s WHERE id = %s",
        (primeiro_vid, id_produto),
    )
    sync_pai_de_variante_padrao(cur, id_produto)
    return criadas

# --- srotas principal ---
# Catálogos DropNexo — produtos do tenant (fornecedor / operação)


import csv
import io
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, session

from global_utils import (
    Var_ConectarBanco,
    agora_utc,
    exigir_modulo,
    exigir_permissao,
    login_obrigatorio,
    url_imagem_produto,
    usuario_tem_permissao,
)
from fornecedor.catalogo.servico_estoque_deposito import (
    atualizar_saldo_deposito,
    listar_estoque_por_deposito,
    sincronizar_estoque_produtos_bling,
)
from fornecedor.catalogo.servico_imagens import (
    classificar_origem_manual,
    exigir_modo_compativel,
    listar_regras_atributo_imagem,
    obter_imagem_modo,
    salvar_regra_atributo_imagem,
    sincronizar_cache_variante,
    sincronizar_imagem_principal_produto,
    url_exibicao,
    validar_id_imagem_produto,
)
from fornecedor.parametros.servico_precificacao import (
    aplicar_valor_drop_produto_e_variantes,
    salvar_valor_drop_manual,
)


_MOD_DIR = Path(__file__).resolve().parent
_RAIZ_PROJETO = _MOD_DIR.parents[2]


_TAGS_PERIGOSOS_HTML = re.compile(
    r"<\s*(script|iframe|object|embed|form|input|button|meta|link|base)\b[^>]*>.*?</\s*\1\s*>|"
    r"<\s*(script|iframe|object|embed|form|input|button|meta|link|base)\b[^>]*/?\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ON_EVENTS_HTML = re.compile(r"\s+on\w+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
_JS_HREF_HTML = re.compile(r"javascript\s*:", re.IGNORECASE)


def _sanitizar_descricao_html(raw: str) -> str:
    """Remove tags e atributos perigosos; mantém formatação segura da descrição."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = _TAGS_PERIGOSOS_HTML.sub("", s)
    s = _ON_EVENTS_HTML.sub("", s)
    s = _JS_HREF_HTML.sub("", s)
    return s.strip()


EXTENSOES_IMAGEM = frozenset({".png", ".jpg", ".jpeg", ".webp"})
MAX_BYTES_IMAGEM = 2 * 1024 * 1024
MAX_IMAGENS_PRODUTO = 10
MAX_LINHAS_CSV = 500
COLUNAS_CSV = (
    "sku",
    "nome",
    "descricao",
    "preco",
    "preco_promocional",
    "quantidade",
    "categoria",
    "unidade",
    "publicado",
    "ativo",
)



def _normalizar_bool(valor, padrao=False):
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "on", "yes", "sim")


def _exigir_catalogo_escrita():
    return exigir_catalogo_escrita()


def _parse_decimal(valor, padrao="0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(padrao)
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal(padrao)


def _pasta_imagens_tenant(id_tenant: int) -> Path:
    pasta = _RAIZ_PROJETO / "static" / "imge" / "produtos" / str(id_tenant)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _extensao_imagem(nome: str) -> str | None:
    ext = Path(nome or "").suffix.lower()
    return ext if ext in EXTENSOES_IMAGEM else None


def _caminho_db_imagem(id_tenant: int, id_produto: int, ext: str) -> str:
    return f"imge/produtos/{id_tenant}/{id_produto}{ext}"


def _remover_imagem_disco(caminho_db: str | None) -> None:
    if not caminho_db:
        return
    rel = (caminho_db or "").replace("\\", "/").strip().lstrip("/")
    if rel.lower().startswith("static/"):
        rel = rel[7:]
    if ".." in rel.split("/") or not rel.lower().startswith("imge/produtos/"):
        return
    p = _RAIZ_PROJETO / "static" / rel.replace("/", os.sep)
    if p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


def _resolver_categoria(cur, id_tenant: int, nome_cat: str | None) -> int | None:
    nome = (nome_cat or "").strip()
    if not nome:
        return None
    cur.execute(
        """
        INSERT INTO tbl_categoria (id_tenant, nome)
        VALUES (%s, %s)
        ON CONFLICT (id_tenant, nome) DO UPDATE SET ativo = TRUE
        RETURNING id
        """,
        (id_tenant, nome),
    )
    return cur.fetchone()[0]


def _imagem_url_resposta(valor: str | None) -> str:
    return url_imagem_produto(valor) if valor else ""


def _caminho_eh_url(caminho: str | None) -> bool:
    c = (caminho or "").strip().lower()
    return c.startswith("http://") or c.startswith("https://")


def _extensao_de_caminho(caminho: str | None) -> str:
    if not caminho:
        return ""
    if _caminho_eh_url(caminho):
        ext = Path(caminho.split("?")[0]).suffix.lower()
        return ext.lstrip(".") or "url"
    ext = Path(caminho).suffix.lower()
    return ext.lstrip(".") or ""


def _tamanho_imagem_disco(caminho_db: str | None) -> int | None:
    if not caminho_db or _caminho_eh_url(caminho_db):
        return None
    rel = (caminho_db or "").replace("\\", "/").strip().lstrip("/")
    if rel.lower().startswith("static/"):
        rel = rel[7:]
    if ".." in rel.split("/") or not rel.lower().startswith("imge/produtos/"):
        return None
    p = _RAIZ_PROJETO / "static" / rel.replace("/", os.sep)
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return None
    return None


def _contar_imagens_produto(cur, id_produto: int) -> int:
    cur.execute(
        "SELECT COUNT(*) FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL",
        (id_produto,),
    )
    n = int(cur.fetchone()[0] or 0)
    if n:
        return n
    cur.execute("SELECT imagem_url FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    return 1 if row and row[0] else 0


def _tipo_de_caminho(caminho: str | None) -> str:
    return "link" if _caminho_eh_url(caminho) else "upload"


def _imagem_dict_row(row) -> dict:
    caminho = row[1] or ""
    origem = row[4] if len(row) > 4 and row[4] else _tipo_de_caminho(caminho)
    if origem in ("link", "upload"):
        origem = "manual_url" if origem == "link" else "manual_upload"
    tamanho = _tamanho_imagem_disco(caminho)
    return {
        "id": row[0],
        "caminho": caminho,
        "url": _imagem_url_resposta(caminho) if not _caminho_eh_url(caminho) else caminho,
        "ordem": row[2],
        "principal": bool(row[3]),
        "tipo": _tipo_de_caminho(caminho),
        "origem": origem,
        "extensao": _extensao_de_caminho(caminho),
        "tamanho_bytes": tamanho,
    }


def _exigir_tipo_imagem_compativel(cur, id_produto: int, tipo: str) -> None:
    exigir_modo_compativel(cur, id_produto, tipo)


def _tipo_galeria_existente(cur, id_produto: int) -> str | None:
    return obter_imagem_modo(cur, id_produto)


def _migrar_imagem_legada(cur, id_produto: int) -> None:
    cur.execute(
        "SELECT COUNT(*) FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL",
        (id_produto,),
    )
    if int(cur.fetchone()[0] or 0) > 0:
        return
    cur.execute("SELECT imagem_url FROM tbl_produto WHERE id = %s", (id_produto,))
    row = cur.fetchone()
    if row and row[0]:
        cur.execute(
            """
            INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal, origem)
            VALUES (%s, %s, 0, TRUE, %s)
            """,
            (id_produto, row[0], classificar_origem_manual(row[0])),
        )


def _sincronizar_imagem_principal(cur, id_produto: int) -> None:
    sincronizar_imagem_principal_produto(cur, id_produto)
    cur.execute("SELECT id FROM tbl_produto_variante WHERE id_produto = %s", (id_produto,))
    for row in cur.fetchall():
        sincronizar_cache_variante(cur, int(row[0]))


@fn_catalogo_bp.get("/catalogos")
@login_obrigatorio()
@exigir_modulo("fornecedor")
@exigir_permissao(codigo="catalogos.ver")
def pagina():
    id_tenant = session.get("id_tenant")
    bling_conectado = False
    if id_tenant:
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
                (id_tenant,),
            )
            row = cur.fetchone()
            bling_conectado = bool(row and row[0] == "conectado")
        finally:
            conn.close()
    return render_template(
        "frm_catalogos.html",
        nav_ativo="catalogos",
        bling_conectado=bling_conectado,
    )


def _catalogo_montar_linhas_pai(
    dados: list[dict],
    variantes_por_produto: dict[int, list],
    *,
    expandir_variantes: bool,
    somente_ativos: bool,
) -> list[dict]:
    linhas: list[dict] = []
    for p in dados:
        vars_p = variantes_por_produto.get(p["id"], [])
        if somente_ativos:
            vars_p = [v for v in vars_p if v.get("ativo")]
        estoque_total = (
            sum(int(v.get("estoque") or 0) for v in vars_p)
            if p["formato"] == "E"
            else int(p.get("estoque") or 0)
        )

        if expandir_variantes and p["formato"] == "E":
            if not vars_p:
                continue
            linhas.append(
                {
                    "tipo": "pai",
                    "id": p["id"],
                    "id_produto": p["id"],
                    "sku": p["sku"],
                    "nome": p["nome"],
                    "formato": p["formato"],
                    "unidade": p["unidade"],
                    "preco": p["preco"],
                    "preco_min": p["preco_min"],
                    "preco_max": p["preco_max"],
                    "estoque": None,
                    "estoque_total": estoque_total,
                    "qtd_variantes": len(vars_p),
                    "ativo": p["ativo"],
                    "imagem_url": p["imagem_url"],
                }
            )
            for i, v in enumerate(vars_p):
                linhas.append(
                    {
                        "tipo": "variante",
                        "id": v["id"],
                        "id_produto": p["id"],
                        "sku": v["sku"],
                        "nome": v["nome_exibicao"],
                        "produto_pai": p["nome"],
                        "atributos": v.get("atributos") or {},
                        "unidade": p["unidade"],
                        "formato": "E",
                        "preco": v["preco"],
                        "estoque": v["estoque"],
                        "ativo": v["ativo"],
                        "ultima_variante": i == len(vars_p) - 1,
                        "primeira_variante": i == 0,
                        "imagem_url": v.get("imagem_url") or p["imagem_url"],
                    }
                )
            continue

        linhas.append(
            {
                "tipo": "pai",
                "id": p["id"],
                "id_produto": p["id"],
                "sku": p["sku"],
                "nome": p["nome"],
                "formato": p["formato"],
                "unidade": p["unidade"],
                "preco": p["preco"],
                "preco_min": p["preco_min"],
                "preco_max": p["preco_max"],
                "estoque": p["estoque"] if p["formato"] != "E" else None,
                "estoque_total": estoque_total,
                "qtd_variantes": len(vars_p) if p["formato"] == "E" else int(p.get("qtd_variantes") or 0),
                "ativo": p["ativo"],
                "imagem_url": p["imagem_url"],
            }
        )
    return linhas


@fn_catalogo_bp.get("/catalogos/dados")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def catalogos_dados():
    id_tenant = session.get("id_tenant")
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = max(1, min(int(request.args.get("porPagina", 100)), 100))
    busca = (request.args.get("busca") or "").strip()
    id_categoria = (request.args.get("id_categoria") or "").strip()
    filtro_tipo = (request.args.get("tipo") or "").strip().lower()
    somente_ativos = (request.args.get("ativos") or "sim").strip().lower() != "nao"
    offset = (pagina - 1) * por_pagina

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()

        if filtro_tipo == "somente_variacoes":
            where = ["p.id_tenant = %s", "p.formato = 'E'"]
            params: list = [id_tenant]
            if busca:
                where.append("(p.nome ILIKE %s OR v.sku ILIKE %s OR v.nome_exibicao ILIKE %s)")
                like = f"%{busca}%"
                params.extend([like, like, like])
            if id_categoria:
                where.append("p.id_categoria = %s")
                params.append(int(id_categoria))
            if somente_ativos:
                where.append("p.ativo = TRUE")
                where.append("v.ativo = TRUE")
            where_sql = " AND ".join(where)

            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM tbl_produto_variante v
                JOIN tbl_produto p ON p.id = v.id_produto
                WHERE {where_sql}
                """,
                params,
            )
            total = int(cur.fetchone()[0] or 0)
            cur.execute(
                f"""
                SELECT v.id, v.id_produto, v.sku, v.nome_exibicao, v.preco, v.ativo,
                       COALESCE(e.quantidade, 0),
                       COALESCE(v.imagem_url, vp.imagem_url, p.imagem_url),
                       p.nome, COALESCE(p.unidade, 'UN')
                FROM tbl_produto_variante v
                JOIN tbl_produto p ON p.id = v.id_produto
                LEFT JOIN tbl_produto_variante vp ON vp.id = p.id_variante_padrao
                LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
                WHERE {where_sql}
                ORDER BY p.nome, v.ordem, v.nome_exibicao
                LIMIT %s OFFSET %s
                """,
                params + [por_pagina, offset],
            )
            linhas = [
                {
                    "tipo": "variante",
                    "id": r[0],
                    "id_produto": r[1],
                    "sku": r[2] or "",
                    "nome": r[3],
                    "produto_pai": r[8],
                    "unidade": r[9] or "UN",
                    "formato": "E",
                    "preco": float(r[4] or 0),
                    "estoque": int(r[6] or 0),
                    "ativo": bool(r[5]),
                    "imagem_url": _imagem_url_resposta(r[7]),
                }
                for r in cur.fetchall()
            ]
            total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
            return jsonify(
                success=True,
                dados=[],
                linhas=linhas,
                total=total,
                pagina_atual=pagina,
                total_paginas=total_paginas,
            )

        where = ["p.id_tenant = %s"]
        params = [id_tenant]
        if busca:
            where.append(
                """(
                p.nome ILIKE %s OR p.sku ILIKE %s
                OR EXISTS (
                    SELECT 1 FROM tbl_produto_variante vx
                    WHERE vx.id_produto = p.id AND (vx.sku ILIKE %s OR vx.nome_exibicao ILIKE %s)
                )
                )"""
            )
            like = f"%{busca}%"
            params.extend([like, like, like, like])
        if id_categoria:
            where.append("p.id_categoria = %s")
            params.append(int(id_categoria))
        if filtro_tipo == "simples":
            where.append("p.formato = 'S'")
        elif filtro_tipo == "com_variacoes":
            where.append("p.formato = 'E'")
        if somente_ativos:
            where.append("p.ativo = TRUE")

        where_sql = " AND ".join(where)
        filtro_var_ativo = " AND v.ativo" if somente_ativos else ""
        cur.execute(
            f"""
            SELECT COUNT(*) FROM tbl_produto p WHERE {where_sql}
            """,
            params,
        )
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            f"""
            SELECT p.id, p.sku, p.nome, p.formato, p.publicado, p.ativo,
                   COALESCE(p.unidade, 'UN'),
                   c.nome AS categoria,
                   (SELECT COUNT(*) FROM tbl_produto_variante v WHERE v.id_produto = p.id{filtro_var_ativo}),
                   (SELECT COALESCE(MIN(v.preco), 0) FROM tbl_produto_variante v WHERE v.id_produto = p.id{filtro_var_ativo}),
                   (SELECT COALESCE(MAX(v.preco), 0) FROM tbl_produto_variante v WHERE v.id_produto = p.id{filtro_var_ativo}),
                   (SELECT COALESCE(SUM(e2.quantidade), 0) FROM tbl_produto_variante v2
                    LEFT JOIN tbl_produto_variante_estoque e2 ON e2.id_variante = v2.id
                    WHERE v2.id_produto = p.id),
                   COALESCE(vp.imagem_url, p.imagem_url)
            FROM tbl_produto p
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante vp ON vp.id = p.id_variante_padrao
            WHERE {where_sql}
            ORDER BY p.atualizado_em DESC, p.nome
            LIMIT %s OFFSET %s
            """,
            params + [por_pagina, offset],
        )
        dados = [
            {
                "id": r[0],
                "sku": r[1] or "",
                "nome": r[2],
                "formato": r[3] or "S",
                "publicado": bool(r[4]),
                "ativo": bool(r[5]),
                "unidade": r[6] or "UN",
                "categoria": r[7] or "",
                "qtd_variantes": int(r[8] or 0),
                "preco_min": float(r[9] or 0),
                "preco_max": float(r[10] or 0),
                "preco": float(r[9] or 0),
                "estoque": int(r[11] or 0),
                "imagem_url": _imagem_url_resposta(r[12]),
            }
            for r in cur.fetchall()
        ]

        expandir_variantes = filtro_tipo in ("", "com_variacoes")
        variantes_por_produto: dict[int, list] = {}
        if expandir_variantes:
            ids_var = [p["id"] for p in dados if p["formato"] == "E"]
            if ids_var:
                var_clause = "v.id_produto = ANY(%s)"
                var_params: list = [ids_var]
                if somente_ativos:
                    var_clause += " AND v.ativo = TRUE"
                cur.execute(
                    f"""
                    {SQL_VARIANTE_LISTA}
                    WHERE {var_clause}
                    ORDER BY v.id_produto, v.ordem, v.nome_exibicao
                    """,
                    tuple(var_params),
                )
                for row in cur.fetchall():
                    v = variante_dict(row)
                    variantes_por_produto.setdefault(v["id_produto"], []).append(v)

        linhas = _catalogo_montar_linhas_pai(
            dados,
            variantes_por_produto,
            expandir_variantes=expandir_variantes,
            somente_ativos=somente_ativos,
        )
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        return jsonify(
            success=True,
            dados=dados,
            linhas=linhas,
            total=total,
            pagina_atual=pagina,
            total_paginas=total_paginas,
        )
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/combos")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def catalogos_combos():
    from srotas_negocio import flatten_arvore_com_caminho, montar_arvore_categorias

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome, parent_id, ordem, COALESCE(nivel, 1), 0
            FROM tbl_categoria
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY ordem, nome
            """,
            (id_tenant,),
        )
        arvore = montar_arvore_categorias(cur.fetchall())
        categorias = [
            {"id": c["id"], "nome": c["caminho"], "caminho": c["caminho"], "nivel": c["nivel"]}
            for c in flatten_arvore_com_caminho(arvore)
        ]
        depositos = []
        try:
            cur.execute(
                """
                SELECT id, nome, cep, cidade, uf
                FROM tbl_deposito_expedicao
                WHERE id_tenant = %s AND ativo = TRUE
                ORDER BY principal DESC, nome
                """,
                (id_tenant,),
            )
            depositos = [
                {"id": r[0], "nome": r[1], "cep": r[2], "cidade": r[3], "uf": r[4]}
                for r in cur.fetchall()
            ]
        except Exception:
            depositos = []
        return jsonify(
            success=True,
            categorias=categorias,
            depositos=depositos,
            unidades=["UN", "CX", "KG", "PC", "PAR"],
        )
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/incluir")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_incluir():
    return render_template("frm_catalogo_apoio.html")


@fn_catalogo_bp.get("/catalogos/editar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_editar():
    return render_template("frm_catalogo_apoio.html")


@fn_catalogo_bp.post("/catalogos/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def catalogos_apoio():
    _id = int((request.get_json(silent=True) or {}).get("id") or 0)
    if not _id:
        return jsonify(success=False, message="ID inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id, p.sku, p.nome, p.descricao, p.preco, p.preco_promocional,
                   p.unidade, p.id_categoria, p.imagem_url, p.ativo, p.publicado,
                   p.formato, p.tipo, p.preco_custo, p.gtin, p.ncm, p.referencia,
                   p.peso_liquido_kg, p.peso_bruto_kg, p.altura_cm, p.largura_cm, p.profundidade_cm,
                   p.prazo_envio_dias, p.moq, p.id_variante_padrao,
                   COALESCE(ve.quantidade, 0),
                   p.marca, p.grupo, p.valor_atacado, p.valor_dropshipping,
                   p.reposicao_estoque, p.dimensao_caixa_cm, p.peso_gramas, p.id_deposito_expedicao,
                   p.condicao, p.cest, p.origem_fiscal, p.frete_gratis, p.volumes, p.producao, p.valor_drop,
                   COALESCE(p.valor_drop_manual, FALSE)
            FROM tbl_produto p
            LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = p.id_variante_padrao
            WHERE p.id = %s AND p.id_tenant = %s
            """,
            (_id, id_tenant),
        )
        r = cur.fetchone()
        if not r:
            return jsonify(success=False, message="Produto não encontrado."), 404
        return jsonify(
            success=True,
            dados={
                "id": r[0],
                "sku": r[1] or "",
                "nome": r[2],
                "descricao": r[3] or "",
                "preco": float(r[4] or 0),
                "preco_promocional": float(r[5]) if r[5] is not None else None,
                "unidade": r[6] or "UN",
                "id_categoria": r[7],
                "imagem_url": _imagem_url_resposta(r[8]),
                "imagem_caminho": r[8] or "",
                "ativo": bool(r[9]),
                "publicado": bool(r[10]),
                "formato": r[11] or "S",
                "tipo": r[12] or "P",
                "preco_custo": float(r[13]) if r[13] is not None else None,
                "gtin": r[14] or "",
                "ncm": r[15] or "",
                "referencia": r[16] or "",
                "condicao": r[34] or r[16] or "",
                "peso_liquido_kg": float(r[17]) if r[17] is not None else None,
                "peso_bruto_kg": float(r[18]) if r[18] is not None else None,
                "altura_cm": float(r[19]) if r[19] is not None else None,
                "largura_cm": float(r[20]) if r[20] is not None else None,
                "profundidade_cm": float(r[21]) if r[21] is not None else None,
                "prazo_envio_dias": r[22],
                "moq": int(r[23] or 1),
                "id_variante_padrao": r[24],
                "quantidade": int(r[25] or 0),
                "marca": r[26] or "",
                "grupo": r[27] or "",
                "valor_atacado": float(r[28]) if r[28] is not None else float(r[4] or 0),
                "valor_dropshipping": float(r[29]) if r[29] is not None else None,
                "reposicao_estoque": bool(r[30]),
                "dimensao_caixa_cm": r[31] or "",
                "peso_gramas": int(r[32]) if r[32] is not None else None,
                "id_deposito": r[33],
                "cest": r[35] or "",
                "origem_fiscal": r[36] or "",
                "frete_gratis": bool(r[37]),
                "volumes": int(r[38]) if r[38] is not None else None,
                "producao": r[39] or "",
                "valor_drop": float(r[40]) if r[40] is not None else None,
                "valor_drop_manual": bool(r[41]),
                "status_promocao": r[5] is not None and r[4] and float(r[5]) < float(r[4]),
            },
        )
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/estoque/depositos")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def catalogos_estoque_depositos():
    id_produto = int(request.args.get("id_produto") or 0)
    if not id_produto:
        return jsonify(success=False, message="Produto inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        id_variante, itens, integrado = listar_estoque_por_deposito(cur, id_tenant, id_produto)
        return jsonify(
            success=True,
            id_variante=id_variante,
            integrado_bling=integrado,
            depositos=itens,
        )
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/estoque/depositos/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_estoque_deposito_salvar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    try:
        id_produto = int(body.get("id_produto") or 0)
        id_deposito = int(body.get("id_deposito") or 0)
        quantidade = int(body.get("quantidade") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Dados inválidos."), 400
    sincronizar_bling = bool(body.get("sincronizar_bling", False))
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = atualizar_saldo_deposito(
            cur,
            id_tenant,
            id_produto=id_produto,
            id_deposito=id_deposito,
            quantidade=quantidade,
            sincronizar_bling=sincronizar_bling,
        )
        conn.commit()
        msg = "Saldo atualizado."
        if res.get("bling_sincronizado"):
            msg += " Sincronizado com o Bling."
        elif res.get("integrado_bling") and sincronizar_bling and res.get("bling_mensagem"):
            msg += f" Bling: {res['bling_mensagem']}"
        return jsonify(success=True, message=msg, dados=res)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/valor-drop/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_valor_drop_salvar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    try:
        id_produto = int(body.get("id_produto") or body.get("id") or 0)
        valor_drop = float(body.get("valor_drop") or 0)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Valor inválido."), 400
    if not id_produto:
        return jsonify(success=False, message="Salve o produto antes de alterar o valor Drop."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        vd = salvar_valor_drop_manual(cur, id_tenant, id_produto, valor_drop)
        conn.commit()
        return jsonify(
            success=True,
            message="Valor Drop atualizado manualmente.",
            valor_drop=vd,
            valor_drop_manual=True,
        )
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_salvar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome do produto."), 400

    id_tenant = session.get("id_tenant")
    sku = (body.get("sku") or "").strip() or None
    preco = _parse_decimal(body.get("valor_atacado") or body.get("preco"))
    preco_promo = body.get("valor_dropshipping") or body.get("preco_promocional")
    preco_promocional = _parse_decimal(preco_promo) if preco_promo not in (None, "") else None
    valor_atacado = preco
    valor_dropshipping = preco_promocional
    id_deposito = body.get("id_deposito") or body.get("id_deposito_expedicao")
    id_deposito = int(id_deposito) if id_deposito not in (None, "") else None
    peso_gramas = body.get("peso_gramas")
    peso_gramas = int(peso_gramas) if peso_gramas not in (None, "") else None
    quantidade = max(0, int(body.get("quantidade") or 0))
    id_categoria = body.get("id_categoria") or None
    formato = (body.get("formato") or "S").strip().upper()
    if formato not in ("S", "E"):
        formato = "S"
    if sku and formato == "E" and "-" in sku:
        sku = sku.split("-", 1)[0].strip() or sku
    pcusto = body.get("preco_custo")
    preco_custo = _parse_decimal(pcusto) if pcusto not in (None, "") else None
    condicao = (body.get("condicao") or body.get("referencia") or "").strip() or None
    cest = (body.get("cest") or "").strip() or None
    origem_fiscal = (body.get("origem_fiscal") or "").strip() or None
    producao = (body.get("producao") or "").strip() or None
    frete_gratis = bool(body.get("frete_gratis"))
    volumes = body.get("volumes")
    volumes = int(volumes) if volumes not in (None, "") else None

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        _id = body.get("id")
        campos = (
            nome,
            _sanitizar_descricao_html(body.get("descricao") or ""),
            sku,
            preco,
            preco_promocional,
            (body.get("unidade") or "UN").strip()[:20],
            int(id_categoria) if id_categoria else None,
            (body.get("imagem_url") or "").strip() or None,
            _normalizar_bool(body.get("ativo"), True),
            _normalizar_bool(body.get("publicado"), False),
            formato,
            (body.get("tipo") or "P").strip()[:2],
            preco_custo,
            (body.get("gtin") or "").strip() or None,
            (body.get("ncm") or "").strip() or None,
            condicao,
            condicao,
            body.get("peso_liquido_kg") or None,
            body.get("peso_bruto_kg") or None,
            body.get("altura_cm") or None,
            body.get("largura_cm") or None,
            body.get("profundidade_cm") or None,
            int(body.get("prazo_envio_dias")) if body.get("prazo_envio_dias") not in (None, "") else None,
            max(1, int(body.get("moq") or 1)),
            (body.get("marca") or "").strip() or None,
            (body.get("grupo") or "").strip() or None,
            valor_atacado,
            valor_dropshipping,
            bool(body.get("reposicao_estoque")),
            (body.get("dimensao_caixa_cm") or "").strip() or None,
            peso_gramas,
            id_deposito,
            cest,
            origem_fiscal,
            frete_gratis,
            volumes,
            producao,
            agora_utc(),
        )
        if _id:
            cur.execute(
                """
                UPDATE tbl_produto SET
                    nome=%s, descricao=%s, sku=%s, preco=%s, preco_promocional=%s,
                    unidade=%s, id_categoria=%s, imagem_url=%s, ativo=%s, publicado=%s,
                    formato=%s, tipo=%s, preco_custo=%s, gtin=%s, ncm=%s, referencia=%s, condicao=%s,
                    peso_liquido_kg=%s, peso_bruto_kg=%s, altura_cm=%s, largura_cm=%s,
                    profundidade_cm=%s, prazo_envio_dias=%s, moq=%s,
                    marca=%s, grupo=%s, valor_atacado=%s, valor_dropshipping=%s,
                    reposicao_estoque=%s, dimensao_caixa_cm=%s, peso_gramas=%s,
                    id_deposito_expedicao=%s, cest=%s, origem_fiscal=%s, frete_gratis=%s,
                    volumes=%s, producao=%s,
                    origem = CASE WHEN origem IN ('arquivo', 'integracao') THEN 'editado' ELSE origem END,
                    atualizado_em=%s
                WHERE id=%s AND id_tenant=%s
                RETURNING id
                """,
                campos + (_id, id_tenant),
            )
            row = cur.fetchone()
            if not row:
                return jsonify(success=False, message="Produto não encontrado."), 404
            prod_id = row[0]
        else:
            cur.execute(
                """
                INSERT INTO tbl_produto (
                    id_tenant, nome, descricao, sku, preco, preco_promocional,
                    unidade, id_categoria, imagem_url, ativo, publicado, formato, tipo,
                    preco_custo, gtin, ncm, referencia, condicao, peso_liquido_kg, peso_bruto_kg,
                    altura_cm, largura_cm, profundidade_cm, prazo_envio_dias, moq,
                    marca, grupo, valor_atacado, valor_dropshipping, reposicao_estoque,
                    dimensao_caixa_cm, peso_gramas, id_deposito_expedicao,
                    cest, origem_fiscal, frete_gratis, volumes, producao, atualizado_em
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                RETURNING id
                """,
                (id_tenant,) + campos,
            )
            prod_id = cur.fetchone()[0]

        if sku:
            exigir_sku_unico_tenant(cur, id_tenant, sku, ignorar_id_produto=prod_id)

        if formato == "S":
            vid = garantir_variante_padrao(cur, prod_id, id_tenant)
            cur.execute(
                """
                UPDATE tbl_produto_variante SET
                    sku = COALESCE(%s, sku), nome_exibicao = %s, preco = %s,
                    preco_promocional = %s, preco_custo = %s, imagem_url = %s, ativo = %s, atualizado_em = %s
                WHERE id = %s
                """,
                (
                    sku,
                    nome,
                    preco,
                    preco_promocional,
                    preco_custo,
                    (body.get("imagem_url") or "").strip() or None,
                    _normalizar_bool(body.get("ativo"), True),
                    agora_utc(),
                    vid,
                ),
            )
            from fornecedor.catalogo.servico_estoque_deposito import (
                garantir_linhas_estoque_depositos,
                sincronizar_total_variante,
            )

            garantir_linhas_estoque_depositos(cur, id_tenant, vid)
            sincronizar_total_variante(cur, vid)
            sync_pai_de_variante_padrao(cur, prod_id)
        aplicar_valor_drop_produto_e_variantes(cur, id_tenant, prod_id, publicar=False)
        conn.commit()
        return jsonify(success=True, message="Produto salvo.", id=prod_id)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 409
    except Exception as e:
        conn.rollback()
        err = str(e)
        if "uq_produto_tenant_sku" in err:
            return jsonify(success=False, message="SKU já cadastrado neste fornecedor."), 409
        return jsonify(success=False, message=err), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/delete")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_delete():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    _id = int((request.get_json(silent=True) or {}).get("id") or 0)
    if not _id:
        return jsonify(success=False, message="ID inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT imagem_url FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (_id, id_tenant),
        )
        row_img = cur.fetchone()
        cur.execute(
            "DELETE FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (_id, id_tenant),
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(success=False, message="Produto não encontrado."), 404
        if row_img and row_img[0] and str(row_img[0]).startswith("imge/produtos/"):
            _remover_imagem_disco(row_img[0])
        return jsonify(success=True, message="Produto excluído.")
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/delete/lote")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_delete_lote():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    raw = body.get("ids") or []
    ids = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))
    if not ids:
        return jsonify(success=False, message="Nenhum produto selecionado."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        excluidos = 0
        for pid in ids:
            cur.execute(
                "SELECT imagem_url FROM tbl_produto WHERE id = %s AND id_tenant = %s",
                (pid, id_tenant),
            )
            row_img = cur.fetchone()
            cur.execute(
                "DELETE FROM tbl_produto WHERE id = %s AND id_tenant = %s",
                (pid, id_tenant),
            )
            if cur.rowcount:
                excluidos += 1
                if row_img and row_img[0] and str(row_img[0]).startswith("imge/produtos/"):
                    _remover_imagem_disco(row_img[0])
        conn.commit()
        return jsonify(
            success=True,
            message=f"{excluidos} produto(s) excluído(s).",
            excluidos=excluidos,
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/categoria/associar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_categoria_associar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    raw = body.get("ids") or []
    ids = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))
    if not ids:
        return jsonify(success=False, message="Nenhum produto selecionado."), 400
    id_categoria = body.get("id_categoria")
    try:
        id_categoria = int(id_categoria) if id_categoria not in (None, "") else None
    except (TypeError, ValueError):
        id_categoria = None
    if not id_categoria:
        return jsonify(success=False, message="Selecione uma categoria."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM tbl_categoria WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
            (id_categoria, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Categoria inválida."), 400
        cur.execute(
            """
            UPDATE tbl_produto SET id_categoria = %s, atualizado_em = %s
            WHERE id_tenant = %s AND id = ANY(%s)
            """,
            (id_categoria, agora_utc(), id_tenant, ids),
        )
        conn.commit()
        return jsonify(
            success=True,
            message=f"Categoria associada a {cur.rowcount} produto(s).",
            atualizados=cur.rowcount,
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/estoque/sincronizar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_estoque_sincronizar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    raw = body.get("ids") or []
    ids = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))
    if not ids:
        return jsonify(success=False, message="Nenhum produto selecionado."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de sincronizar estoque."), 400
        resumo = sincronizar_estoque_produtos_bling(cur, id_tenant, ids)
        conn.commit()
        msg = f"Estoque sincronizado em {resumo['sincronizados']} de {resumo['total']} produto(s)."
        if resumo["falhas"]:
            msg += f" {len(resumo['falhas'])} com aviso."
        return jsonify(success=True, message=msg, resumo=resumo)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/imagens/lista")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def catalogos_imagens_lista():
    id_produto = int(request.args.get("id_produto") or 0)
    if not id_produto:
        return jsonify(success=False, message="Produto inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        cur.execute(
            """
            SELECT id, caminho, ordem, principal, origem
            FROM tbl_produto_imagem
            WHERE id_produto = %s AND id_variante IS NULL
            ORDER BY ordem ASC, id ASC
            """,
            (id_produto,),
        )
        imagens = [_imagem_dict_row(r) for r in cur.fetchall()]
        if not imagens:
            cur.execute(
                "SELECT imagem_url FROM tbl_produto WHERE id = %s",
                (id_produto,),
            )
            row = cur.fetchone()
            if row and row[0]:
                cam = row[0]
                imagens.append(
                    {
                        "id": None,
                        "caminho": cam,
                        "url": _imagem_url_resposta(cam)
                        if not _caminho_eh_url(cam)
                        else cam,
                        "ordem": 0,
                        "principal": True,
                        "tipo": _tipo_de_caminho(cam),
                        "extensao": _extensao_de_caminho(cam),
                        "tamanho_bytes": _tamanho_imagem_disco(cam),
                    }
                )
        return jsonify(
            success=True,
            imagens=imagens,
            total=len(imagens),
            tipo_galeria=_tipo_galeria_existente(cur, id_produto),
            imagem_modo=obter_imagem_modo(cur, id_produto),
            regras_atributo=listar_regras_atributo_imagem(cur, id_produto),
        )
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/imagens/link")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_imagens_link():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    url = (body.get("url") or "").strip()
    if not id_produto or not url:
        return jsonify(success=False, message="Informe produto e URL."), 400
    if not url.lower().startswith(("http://", "https://")):
        return jsonify(success=False, message="URL inválida."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        _exigir_tipo_imagem_compativel(cur, id_produto, "link")
        _migrar_imagem_legada(cur, id_produto)
        if _contar_imagens_produto(cur, id_produto) >= MAX_IMAGENS_PRODUTO:
            return jsonify(success=False, message="Máximo de 10 imagens por produto."), 400
        cur.execute(
            "SELECT COALESCE(MAX(ordem), -1) + 1 FROM tbl_produto_imagem WHERE id_produto = %s",
            (id_produto,),
        )
        ordem = int(cur.fetchone()[0] or 0)
        principal = ordem == 0
        cur.execute(
            """
            INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal, origem)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, caminho, ordem, principal, origem
            """,
            (id_produto, url, ordem, principal, "manual_url"),
        )
        row = cur.fetchone()
        _sincronizar_imagem_principal(cur, id_produto)
        conn.commit()
        return jsonify(success=True, message="Imagem incluída.", imagem=_imagem_dict_row(row))
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/imagens/upload")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_imagens_upload():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    id_produto = int(request.form.get("id_produto") or 0)
    arquivo = request.files.get("arquivo")
    if not id_produto or not arquivo or not arquivo.filename:
        return jsonify(success=False, message="Informe o produto e o arquivo."), 400
    ext = _extensao_imagem(arquivo.filename)
    if not ext:
        return jsonify(success=False, message="Use PNG, JPG ou WEBP."), 400
    stream = arquivo.stream
    stream.seek(0, os.SEEK_END)
    tamanho = stream.tell()
    stream.seek(0)
    if tamanho <= 0:
        return jsonify(success=False, message="Arquivo vazio."), 400
    if tamanho > MAX_BYTES_IMAGEM:
        return jsonify(success=False, message="Imagem deve ter no máximo 2 MB."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        _exigir_tipo_imagem_compativel(cur, id_produto, "upload")
        _migrar_imagem_legada(cur, id_produto)
        if _contar_imagens_produto(cur, id_produto) >= MAX_IMAGENS_PRODUTO:
            return jsonify(success=False, message="Máximo de 10 imagens por produto."), 400
        cur.execute(
            """
            INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal, origem)
            VALUES (%s, '', 999, FALSE, 'manual_upload')
            RETURNING id
            """,
            (id_produto,),
        )
        id_img = cur.fetchone()[0]
        pasta = _pasta_imagens_tenant(int(id_tenant))
        destino = pasta / f"{id_produto}_{id_img}{ext}"
        arquivo.save(str(destino))
        caminho_db = f"imge/produtos/{id_tenant}/{id_produto}_{id_img}{ext}"
        cur.execute(
            "SELECT COALESCE(MAX(ordem), -1) + 1 FROM tbl_produto_imagem WHERE id_produto = %s AND id != %s",
            (id_produto, id_img),
        )
        ordem = int(cur.fetchone()[0] or 0)
        principal = ordem == 0
        cur.execute(
            """
            UPDATE tbl_produto_imagem
            SET caminho = %s, ordem = %s, principal = %s, origem = 'manual_upload'
            WHERE id = %s
            RETURNING id, caminho, ordem, principal, origem
            """,
            (caminho_db, ordem, principal, id_img),
        )
        row = cur.fetchone()
        _sincronizar_imagem_principal(cur, id_produto)
        conn.commit()
        img = _imagem_dict_row(row)
        img["tamanho_bytes"] = tamanho
        return jsonify(success=True, message="Imagem enviada.", imagem=img)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/imagens/ordenar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_imagens_ordenar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    ids = body.get("ids") or []
    if not id_produto or not isinstance(ids, list) or not ids:
        return jsonify(success=False, message="Informe produto e ordem das imagens."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        ids_int = [int(x) for x in ids if x not in (None, "")]
        if not ids_int:
            return jsonify(success=False, message="Ordem inválida."), 400
        cur.execute(
            "SELECT id FROM tbl_produto_imagem WHERE id_produto = %s AND id_variante IS NULL",
            (id_produto,),
        )
        existentes = {r[0] for r in cur.fetchall()}
        if set(ids_int) != existentes:
            return jsonify(success=False, message="Lista de imagens incompleta ou inválida."), 400
        for ordem, id_img in enumerate(ids_int):
            cur.execute(
                """
                UPDATE tbl_produto_imagem
                SET ordem = %s, principal = %s
                WHERE id = %s AND id_produto = %s
                """,
                (ordem, ordem == 0, id_img, id_produto),
            )
        _sincronizar_imagem_principal(cur, id_produto)
        conn.commit()
        return jsonify(success=True, message="Ordem atualizada.")
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/imagens/atributo")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_imagens_atributo():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    id_imagem = int(body.get("id_imagem") or 0)
    nome_atributo = (body.get("nome_atributo") or "").strip()
    valor = (body.get("valor") or "").strip()
    if not id_produto or not id_imagem or not nome_atributo or not valor:
        return jsonify(success=False, message="Informe produto, atributo, valor e imagem."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        salvar_regra_atributo_imagem(
            cur,
            id_produto=id_produto,
            nome_atributo=nome_atributo,
            valor=valor,
            id_imagem=id_imagem,
        )
        conn.commit()
        return jsonify(
            success=True,
            message="Imagem associada ao atributo.",
            regras=listar_regras_atributo_imagem(cur, id_produto),
        )
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/imagens/remover")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_imagens_remover():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    id_imagem = body.get("id_imagem")
    id_imagem = int(id_imagem) if id_imagem not in (None, "") else None
    if not id_produto:
        return jsonify(success=False, message="Produto inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        if id_imagem:
            cur.execute(
                "SELECT caminho FROM tbl_produto_imagem WHERE id = %s AND id_produto = %s",
                (id_imagem, id_produto),
            )
            row = cur.fetchone()
            if not row:
                return jsonify(success=False, message="Imagem não encontrada."), 404
            if not _caminho_eh_url(row[0]):
                _remover_imagem_disco(row[0])
            cur.execute(
                "DELETE FROM tbl_produto_imagem WHERE id = %s AND id_produto = %s",
                (id_imagem, id_produto),
            )
            cur.execute(
                """
                UPDATE tbl_produto_variante
                SET id_imagem_principal = NULL, atualizado_em = %s
                WHERE id_imagem_principal = %s
                """,
                (agora_utc(), id_imagem),
            )
        elif _normalizar_bool(body.get("limpar_principal")):
            cur.execute("SELECT imagem_url FROM tbl_produto WHERE id = %s", (id_produto,))
            row = cur.fetchone()
            if row and row[0] and not _caminho_eh_url(row[0]):
                _remover_imagem_disco(row[0])
            cur.execute(
                "UPDATE tbl_produto SET imagem_url = NULL, atualizado_em = %s WHERE id = %s",
                (agora_utc(), id_produto),
            )
            conn.commit()
            return jsonify(success=True, message="Imagem removida.")
        else:
            return jsonify(success=False, message="Imagem inválida."), 400
        _sincronizar_imagem_principal(cur, id_produto)
        conn.commit()
        return jsonify(success=True, message="Imagem removida.")
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/imagem/upload")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_imagem_upload():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp

    id_produto = int(request.form.get("id_produto") or 0)
    arquivo = request.files.get("arquivo")
    if not id_produto or not arquivo or not arquivo.filename:
        return jsonify(success=False, message="Informe o produto e o arquivo."), 400

    ext = _extensao_imagem(arquivo.filename)
    if not ext:
        return jsonify(success=False, message="Use PNG, JPG ou WEBP."), 400

    stream = arquivo.stream
    stream.seek(0, os.SEEK_END)
    tamanho = stream.tell()
    stream.seek(0)
    if tamanho <= 0:
        return jsonify(success=False, message="Arquivo vazio."), 400
    if tamanho > MAX_BYTES_IMAGEM:
        return jsonify(success=False, message="Imagem deve ter no máximo 2 MB."), 400

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT imagem_url FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Produto não encontrado."), 404

        if row[0] and str(row[0]).startswith("imge/produtos/"):
            _remover_imagem_disco(row[0])

        pasta = _pasta_imagens_tenant(int(id_tenant))
        for f in pasta.glob(f"{id_produto}.*"):
            try:
                f.unlink()
            except OSError:
                pass

        destino = pasta / f"{id_produto}{ext}"
        arquivo.save(str(destino))

        caminho_db = _caminho_db_imagem(int(id_tenant), id_produto, ext)
        cur.execute(
            "UPDATE tbl_produto SET imagem_url = %s, atualizado_em = %s WHERE id = %s AND id_tenant = %s",
            (caminho_db, agora_utc(), id_produto, id_tenant),
        )
        conn.commit()
        return jsonify(
            success=True,
            message="Imagem enviada.",
            imagem_url=_imagem_url_resposta(caminho_db),
            imagem_caminho=caminho_db,
        )
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/importar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_importar_pagina():
    from flask import redirect

    return redirect("/fornecedor/importacao")


@fn_catalogo_bp.get("/catalogos/importar/modelo")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_importar_modelo():
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(COLUNAS_CSV)
    w.writerow(
        [
            "SKU-001",
            "Produto exemplo",
            "Descrição opcional",
            "99.90",
            "89.90",
            "10",
            "Geral",
            "UN",
            "sim",
            "sim",
        ]
    )
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=modelo_catalogo_dropnexo.csv"},
    )


@fn_catalogo_bp.post("/catalogos/importar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_importar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp

    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify(success=False, message="Selecione um arquivo CSV."), 400
    if not arquivo.filename.lower().endswith(".csv"):
        return jsonify(success=False, message="Envie um arquivo .csv"), 400

    raw = arquivo.read()
    if not raw:
        return jsonify(success=False, message="Arquivo vazio."), 400
    if len(raw) > 2 * 1024 * 1024:
        return jsonify(success=False, message="CSV deve ter no máximo 2 MB."), 400

    texto = raw.decode("utf-8-sig", errors="replace")
    delim = ";" if ";" in texto.splitlines()[0] else ","
    reader = csv.DictReader(io.StringIO(texto), delimiter=delim)
    if not reader.fieldnames:
        return jsonify(success=False, message="Cabeçalho do CSV inválido."), 400

    mapa = {}
    for col in reader.fieldnames:
        chave = (col or "").strip().lower()
        if chave:
            mapa[chave] = col

    id_tenant = session.get("id_tenant")
    inseridos = 0
    atualizados = 0
    erros: list[dict] = []

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        for num, row in enumerate(reader, start=2):
            if num - 2 >= MAX_LINHAS_CSV:
                erros.append({"linha": num, "erro": f"Máximo de {MAX_LINHAS_CSV} linhas por importação."})
                break

            def cel(*nomes):
                for n in nomes:
                    c = mapa.get(n)
                    if c is not None:
                        return (row.get(c) or "").strip()
                return ""

            nome = cel("nome")
            if not nome:
                if any((row.get(mapa[k]) or "").strip() for k in mapa if k != "nome"):
                    erros.append({"linha": num, "erro": "Nome obrigatório."})
                continue

            sku = cel("sku") or None
            preco = _parse_decimal(cel("preco"))
            promo_raw = cel("preco_promocional")
            preco_promocional = _parse_decimal(promo_raw) if promo_raw else None
            quantidade = max(0, int(_parse_decimal(cel("quantidade"), "0")))
            id_categoria = _resolver_categoria(cur, id_tenant, cel("categoria"))
            unidade = (cel("unidade") or "UN").strip()[:20] or "UN"
            publicado = _normalizar_bool(cel("publicado"), False)
            ativo = _normalizar_bool(cel("ativo"), True)
            descricao = cel("descricao")

            try:
                prod_id = None
                if sku:
                    cur.execute(
                        "SELECT id FROM tbl_produto WHERE id_tenant = %s AND sku = %s",
                        (id_tenant, sku),
                    )
                    found = cur.fetchone()
                    if found:
                        prod_id = found[0]
                        cur.execute(
                            """
                            UPDATE tbl_produto SET
                                nome=%s, descricao=%s, preco=%s, preco_promocional=%s,
                                unidade=%s, id_categoria=%s, ativo=%s, publicado=%s, atualizado_em=%s
                            WHERE id=%s AND id_tenant=%s
                            """,
                            (
                                nome,
                                descricao,
                                preco,
                                preco_promocional,
                                unidade,
                                id_categoria,
                                ativo,
                                publicado,
                                agora_utc(),
                                prod_id,
                                id_tenant,
                            ),
                        )
                        atualizados += 1
                    else:
                        cur.execute(
                            """
                            INSERT INTO tbl_produto (
                                id_tenant, sku, nome, descricao, preco, preco_promocional,
                                unidade, id_categoria, ativo, publicado, atualizado_em
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            RETURNING id
                            """,
                            (
                                id_tenant,
                                sku,
                                nome,
                                descricao,
                                preco,
                                preco_promocional,
                                unidade,
                                id_categoria,
                                ativo,
                                publicado,
                                agora_utc(),
                            ),
                        )
                        prod_id = cur.fetchone()[0]
                        inseridos += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO tbl_produto (
                            id_tenant, nome, descricao, preco, preco_promocional,
                            unidade, id_categoria, ativo, publicado, atualizado_em
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id
                        """,
                        (
                            id_tenant,
                            nome,
                            descricao,
                            preco,
                            preco_promocional,
                            unidade,
                            id_categoria,
                            ativo,
                            publicado,
                            agora_utc(),
                        ),
                    )
                    prod_id = cur.fetchone()[0]
                    inseridos += 1

                cur.execute(
                    """
                    INSERT INTO tbl_produto_estoque (id_produto, quantidade, atualizado_em)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id_produto) DO UPDATE SET
                        quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
                    """,
                    (prod_id, quantidade, agora_utc()),
                )
            except Exception as ex:
                erros.append({"linha": num, "erro": str(ex)})

        conn.commit()
        return jsonify(
            success=True,
            message="Importação concluída.",
            inseridos=inseridos,
            atualizados=atualizados,
            erros=erros[:50],
            total_erros=len(erros),
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/categoria/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def catalogos_categoria_salvar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    nome = (request.get_json(silent=True) or {}).get("nome", "").strip()
    if not nome:
        return jsonify(success=False, message="Informe o nome da categoria."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tbl_categoria (id_tenant, nome)
            VALUES (%s, %s)
            ON CONFLICT (id_tenant, nome) DO UPDATE SET ativo = TRUE
            RETURNING id, nome
            """,
            (id_tenant, nome),
        )
        row = cur.fetchone()
        conn.commit()
        return jsonify(success=True, id=row[0], nome=row[1])
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()

# --- variantes ---


import json
import re

from flask import jsonify, render_template, request, session

from global_utils import (
    Var_ConectarBanco,
    agora_utc,
    exigir_permissao,
    login_obrigatorio,
    usuario_tem_permissao,
)



def _parse_decimal(valor, padrao="0"):
    from decimal import Decimal, InvalidOperation

    if valor is None or valor == "":
        return Decimal(padrao)
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal(padrao)


def _exigir_catalogo_escrita():
    return exigir_catalogo_escrita()


@fn_catalogo_bp.get("/catalogos/categorias/arvore")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def categorias_arvore():
    from srotas_negocio import montar_arvore_categorias as categorias_arvore

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(success=True, categorias=categorias_arvore(cur, id_tenant))
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/variantes/lista")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def variantes_lista():
    id_produto = int(request.args.get("id_produto") or 0)
    id_tenant = session.get("id_tenant")
    if not id_produto:
        return jsonify(success=False, message="id_produto obrigatório."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404

        if session.get("eh_desenvolvedor") or usuario_tem_permissao("catalogos.editar"):
            if sincronizar_variantes_se_necessario(cur, id_produto, id_tenant):
                conn.commit()

        cur.execute(
            f"""
            {SQL_VARIANTE_LISTA}
            WHERE v.id_produto = %s
            ORDER BY v.ordem, v.nome_exibicao
            """,
            (id_produto,),
        )
        variantes = [variante_dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT id, nome, valores, ordem FROM tbl_produto_atributo
            WHERE id_produto = %s ORDER BY ordem, nome
            """,
            (id_produto,),
        )
        atributos = [
            {
                "id": r[0],
                "nome": r[1],
                "valores": r[2] if isinstance(r[2], list) else (json.loads(r[2]) if r[2] else []),
                "ordem": r[3],
            }
            for r in cur.fetchall()
        ]
        return jsonify(success=True, variantes=variantes, atributos=atributos)
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/variantes/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def variantes_salvar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    id_tenant = session.get("id_tenant")
    nome = (body.get("nome_exibicao") or "").strip() or "Padrão"
    if not id_produto:
        return jsonify(success=False, message="id_produto obrigatório."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT formato FROM tbl_produto WHERE id = %s AND id_tenant = %s", (id_produto, id_tenant))
        row_p = cur.fetchone()
        if not row_p:
            return jsonify(success=False, message="Produto não encontrado."), 404

        sku = (body.get("sku") or "").strip() or None
        preco = _parse_decimal(body.get("preco"))
        promo = body.get("preco_promocional")
        preco_promo = _parse_decimal(promo) if promo not in (None, "") else None
        preco_custo = body.get("preco_custo")
        pc = _parse_decimal(preco_custo) if preco_custo not in (None, "") else None
        atributos = body.get("atributos")
        if atributos is None:
            atributos = {}
        quantidade = max(0, int(body.get("quantidade") or 0))
        ativo = str(body.get("ativo", "true")).lower() in ("1", "true", "t", "yes", "sim")
        vid = body.get("id")

        peso_liq = body.get("peso_liquido_kg")
        peso_liq = _parse_decimal(peso_liq) if peso_liq not in (None, "") else None
        peso_br = body.get("peso_bruto_kg")
        peso_br = _parse_decimal(peso_br) if peso_br not in (None, "") else None
        alt = body.get("altura_cm")
        alt = _parse_decimal(alt) if alt not in (None, "") else None
        larg = body.get("largura_cm")
        larg = _parse_decimal(larg) if larg not in (None, "") else None
        prof = body.get("profundidade_cm")
        prof = _parse_decimal(prof) if prof not in (None, "") else None
        gtin = (body.get("gtin") or "").strip() or None
        ncm = (body.get("ncm") or "").strip() or None
        herda_pai = str(body.get("herda_pai", "true")).lower() in ("1", "true", "t", "yes", "sim")
        id_imagem_principal = body.get("id_imagem_principal")
        if id_imagem_principal in (None, "", 0, "0"):
            id_imagem_principal = None
        else:
            id_imagem_principal = int(id_imagem_principal)

        if herda_pai:
            id_imagem_principal = None
            imagem_url = None
        elif id_imagem_principal:
            if not validar_id_imagem_produto(cur, id_imagem_principal, id_produto):
                return jsonify(success=False, message="Imagem inválida para este produto."), 400
            imagem_url = None
        else:
            imagem_url = (body.get("imagem_url") or body.get("imagem_caminho") or "").strip() or None

        if sku:
            exigir_sku_unico_tenant(
                cur,
                id_tenant,
                sku,
                ignorar_id_produto=id_produto,
                ignorar_id_variante=int(vid) if vid else None,
            )

        if vid:
            if not atributos:
                cur.execute("SELECT atributos FROM tbl_produto_variante WHERE id = %s", (vid,))
                row_atr = cur.fetchone()
                if row_atr and row_atr[0]:
                    atributos = (
                        row_atr[0]
                        if isinstance(row_atr[0], dict)
                        else (json.loads(row_atr[0]) if row_atr[0] else {})
                    )
            cur.execute(
                """
                UPDATE tbl_produto_variante SET
                    sku=%s, nome_exibicao=%s, preco=%s, preco_promocional=%s, preco_custo=%s,
                    atributos=%s, imagem_url=%s, id_imagem_principal=%s, ativo=%s, ordem=%s, herda_pai=%s,
                    peso_liquido_kg=%s, peso_bruto_kg=%s, altura_cm=%s, largura_cm=%s,
                    profundidade_cm=%s, gtin=%s, ncm=%s, atualizado_em=%s
                WHERE id=%s AND id_produto=%s
                RETURNING id
                """,
                (
                    sku,
                    nome,
                    preco,
                    preco_promo,
                    pc,
                    json.dumps(atributos),
                    imagem_url,
                    id_imagem_principal,
                    ativo,
                    int(body.get("ordem") or 0),
                    herda_pai,
                    peso_liq,
                    peso_br,
                    alt,
                    larg,
                    prof,
                    gtin,
                    ncm,
                    agora_utc(),
                    vid,
                    id_produto,
                ),
            )
            if not cur.fetchone():
                return jsonify(success=False, message="Variante não encontrada."), 404
            variant_id = int(vid)
            sincronizar_cache_variante(cur, variant_id)
        else:
            cur.execute(
                """
                INSERT INTO tbl_produto_variante (
                    id_produto, sku, nome_exibicao, preco, preco_promocional, preco_custo,
                    atributos, imagem_url, id_imagem_principal, ativo, ordem, herda_pai,
                    peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm, profundidade_cm,
                    gtin, ncm, atualizado_em
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    id_produto,
                    sku,
                    nome,
                    preco,
                    preco_promo,
                    pc,
                    json.dumps(atributos),
                    imagem_url,
                    id_imagem_principal,
                    ativo,
                    int(body.get("ordem") or 0),
                    herda_pai,
                    peso_liq,
                    peso_br,
                    alt,
                    larg,
                    prof,
                    gtin,
                    ncm,
                    agora_utc(),
                ),
            )
            variant_id = cur.fetchone()[0]
            sincronizar_cache_variante(cur, variant_id)
            if row_p[0] == "E":
                pass
            else:
                cur.execute(
                    "UPDATE tbl_produto SET formato = 'E', id_variante_padrao = COALESCE(id_variante_padrao, %s) WHERE id = %s",
                    (variant_id, id_produto),
                )

        cur.execute(
            """
            INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
            VALUES (%s, %s, %s)
            ON CONFLICT (id_variante) DO UPDATE SET quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
            """,
            (variant_id, quantidade, agora_utc()),
        )
        garantir_variante_padrao(cur, id_produto, id_tenant)
        sync_pai_de_variante_padrao(cur, id_produto)
        conn.commit()
        return jsonify(success=True, message="Variante salva.", id=variant_id)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 409
    except Exception as e:
        conn.rollback()
        err = str(e)
        if "uq_variante_produto_sku" in err:
            return jsonify(success=False, message="SKU já usado neste produto."), 409
        return jsonify(success=False, message=err), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/variantes/delete")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def variantes_delete():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    vid = int(body.get("id") or 0)
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT v.id, v.id_produto, p.id_variante_padrao
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto AND p.id_tenant = %s
            WHERE v.id = %s
            """,
            (id_tenant, vid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Variante não encontrada."), 404
        cur.execute("SELECT COUNT(*) FROM tbl_produto_variante WHERE id_produto = %s", (row[1],))
        if int(cur.fetchone()[0]) <= 1:
            return jsonify(success=False, message="O produto precisa de ao menos uma variante."), 400
        cur.execute("DELETE FROM tbl_produto_variante WHERE id = %s", (vid,))
        if row[0] == row[2]:
            cur.execute(
                """
                UPDATE tbl_produto SET id_variante_padrao = (
                    SELECT id FROM tbl_produto_variante WHERE id_produto = %s ORDER BY ordem, id LIMIT 1
                ) WHERE id = %s
                """,
                (row[1], row[1]),
            )
        sync_pai_de_variante_padrao(cur, row[1])
        conn.commit()
        return jsonify(success=True, message="Variante excluída.")
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/atributos/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def atributos_salvar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    nome = (body.get("nome") or "").strip()
    valores = body.get("valores") or []
    if not id_produto or not nome:
        return jsonify(success=False, message="Produto e nome do atributo são obrigatórios."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_produto WHERE id = %s AND id_tenant = %s", (id_produto, id_tenant))
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        aid = salvar_atributo_produto(cur, id_produto, nome, valores, int(body.get("ordem") or 0))
        criadas = gerar_variantes_produto(cur, id_produto, id_tenant)
        conn.commit()
        msg = (
            f"Atributo salvo. {criadas} variação(ões) gerada(s)."
            if criadas
            else "Atributo salvo. Nenhuma variação gerada (é necessário mais de uma combinação)."
        )
        return jsonify(success=True, id=aid, message=msg, criadas=criadas)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/atributos/excluir")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def atributos_excluir():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    nome = (body.get("nome") or "").strip()
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM tbl_produto WHERE id = %s AND id_tenant = %s",
            (id_produto, id_tenant),
        )
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        cur.execute(
            "DELETE FROM tbl_produto_atributo WHERE id_produto = %s AND nome = %s",
            (id_produto, nome),
        )
        criadas = gerar_variantes_produto(cur, id_produto, id_tenant)
        conn.commit()
        if criadas:
            msg = f"Atributo removido. {criadas} variação(ões) recriada(s) com os atributos restantes."
        else:
            msg = "Atributo removido. Todas as variações foram excluídas (não há combinação suficiente)."
        return jsonify(success=True, message=msg, criadas=criadas)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/variantes/adicionar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def variantes_adicionar():
    """Salva um atributo e gera/atualiza SKUs automaticamente."""
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    nome = (body.get("nome") or "").strip()
    raw_vals = body.get("valores") or []
    if isinstance(raw_vals, str):
        raw_vals = [s.strip() for s in re.split(r"[,;\n]+", raw_vals) if s.strip()]
    valores = [str(v).strip() for v in raw_vals if str(v).strip()]
    if not id_produto or not nome or not valores:
        return jsonify(success=False, message="Informe produto, nome do atributo e opções."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_produto WHERE id = %s AND id_tenant = %s", (id_produto, id_tenant))
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        salvar_atributo_produto(cur, id_produto, nome, valores, int(body.get("ordem") or 0))
        criadas = gerar_variantes_produto(cur, id_produto, id_tenant)
        conn.commit()
        if criadas:
            msg = f"Variações recriadas. {criadas} SKU(s) gerado(s) com os atributos atuais."
        else:
            msg = (
                "Atributo salvo, mas nenhuma variação foi gerada. "
                "Cadastre mais de uma opção ou mais de um atributo para gerar SKUs distintos."
            )
        return jsonify(success=True, message=msg, criadas=criadas)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/variantes/presets")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def variantes_presets_lista():
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome, descricao, atributos, ativo
            FROM tbl_variacao_preset
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY nome
            """,
            (id_tenant,),
        )
        presets = []
        for r in cur.fetchall():
            atr = r[3] if isinstance(r[3], list) else (json.loads(r[3]) if r[3] else [])
            presets.append(
                {
                    "id": r[0],
                    "nome": r[1],
                    "descricao": r[2] or "",
                    "atributos": atr,
                    "ativo": bool(r[4]),
                }
            )
        return jsonify(success=True, presets=presets)
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/variantes/aplicar-preset")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def variantes_aplicar_preset():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    id_preset = int(body.get("id_preset") or 0)
    if not id_produto or not id_preset:
        return jsonify(success=False, message="Informe produto e modelo."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_produto WHERE id = %s AND id_tenant = %s", (id_produto, id_tenant))
        if not cur.fetchone():
            return jsonify(success=False, message="Produto não encontrado."), 404
        cur.execute(
            "SELECT nome, atributos FROM tbl_variacao_preset WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
            (id_preset, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Modelo não encontrado."), 404
        atributos = row[1] if isinstance(row[1], list) else (json.loads(row[1]) if row[1] else [])
        if not atributos:
            return jsonify(success=False, message="Modelo sem atributos."), 400
        for i, item in enumerate(atributos):
            nome = (item.get("nome") or "").strip()
            vals = item.get("valores") or []
            if isinstance(vals, str):
                vals = [s.strip() for s in vals.split(",") if s.strip()]
            vals = [str(v).strip() for v in vals if str(v).strip()]
            if nome and vals:
                salvar_atributo_produto(cur, id_produto, nome, vals, i)
        criadas = gerar_variantes_produto(cur, id_produto, id_tenant)
        conn.commit()
        return jsonify(
            success=True,
            message=f'Modelo "{row[0]}" aplicado. {criadas} SKU(s) criado(s).',
            criadas=criadas,
        )
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.post("/catalogos/variantes/gerar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def variantes_gerar():
    if (resp := _exigir_catalogo_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_produto = int(body.get("id_produto") or 0)
    id_tenant = session.get("id_tenant")
    if not id_produto:
        return jsonify(success=False, message="id_produto obrigatório."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        criadas = gerar_variantes_produto(cur, id_produto, id_tenant)
        conn.commit()
        return jsonify(
            success=True,
            message=f"{criadas} variante(s) criada(s).",
            criadas=criadas,
        )
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_catalogo_bp.get("/catalogos/variante/editar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.editar")
def variante_editar():
    return render_template("frm_catalogo_variante_apoio.html")


@fn_catalogo_bp.post("/catalogos/variante/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def variante_apoio():
    body = request.get_json(silent=True) or {}
    vid = int(body.get("id") or body.get("id_variante") or 0)
    id_tenant = session.get("id_tenant")
    if not vid:
        return jsonify(success=False, message="ID da variante obrigatório."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            {SQL_VARIANTE_LISTA}
            INNER JOIN tbl_produto p ON p.id = v.id_produto AND p.id_tenant = %s
            WHERE v.id = %s
            """,
            (id_tenant, vid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Variante não encontrada."), 404
        variante = variante_dict(row)
        cur.execute(
            """
            SELECT id, sku, nome, descricao, preco, preco_promocional, preco_custo,
                   gtin, ncm, peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm,
                   profundidade_cm, imagem_url, referencia, formato
            FROM tbl_produto WHERE id = %s
            """,
            (variante["id_produto"],),
        )
        pai = produto_pai_dict(cur.fetchone())
        return jsonify(success=True, dados=variante, pai=pai)
    finally:
        conn.close()
