# vendedor/fornecedores/srotas_fornecedores.py — vínculos com fornecedores e desconexão
from __future__ import annotations

# ── servico_desvincular_fornecedor ────────────────────

"""Desconexão de fornecedor pelo vendedor e tratamento dos produtos da vitrine."""


import json
from typing import Literal

from global_utils import agora_utc
from fornecedor.catalogo.srotas_catalogo import exigir_sku_unico_tenant, resolver_sku_unico_tenant
from fornecedor.catalogo.catalogo import garantir_linhas_estoque_depositos, sincronizar_total_variante

AcaoProdutos = Literal["excluir", "converter"]


def contar_produtos_vitrine(cur, id_vendedor: int, id_fornecedor: int) -> int:
    cur.execute(
        """
        SELECT COUNT(DISTINCT id_produto)::int
        FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _resolver_categoria_vendedor(cur, id_vendedor: int, id_categoria_forn: int | None) -> int | None:
    if not id_categoria_forn:
        return None
    cur.execute(
        "SELECT nome FROM tbl_categoria WHERE id = %s",
        (id_categoria_forn,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    nome = str(row[0]).strip()
    cur.execute(
        """
        INSERT INTO tbl_categoria (id_tenant, nome)
        VALUES (%s, %s)
        ON CONFLICT (id_tenant, nome) DO UPDATE SET ativo = TRUE
        RETURNING id
        """,
        (id_vendedor, nome),
    )
    cat = cur.fetchone()
    return int(cat[0]) if cat else None


def _sku_unico_clone(cur, id_vendedor: int, sku_base: str | None, id_produto_novo: int) -> str | None:
    sku = (sku_base or "").strip()
    if not sku:
        return None
    candidatos = [sku, f"{sku}-DV", f"{sku}-DV{id_produto_novo}"]
    for cand in candidatos:
        try:
            exigir_sku_unico_tenant(cur, id_vendedor, cand, ignorar_id_produto=id_produto_novo)
            return cand
        except ValueError:
            continue
    return f"DV{id_produto_novo}"


def _copiar_imagens_produto(cur, id_produto_origem: int, id_produto_destino: int) -> dict[int, int]:
    """Copia galeria do pai; retorna mapa id_imagem_antiga -> id_imagem_nova."""
    cur.execute(
        """
        SELECT id, caminho, ordem, principal, COALESCE(origem, 'manual_upload')
        FROM tbl_produto_imagem
        WHERE id_produto = %s AND id_variante IS NULL
        ORDER BY ordem, id
        """,
        (id_produto_origem,),
    )
    mapa: dict[int, int] = {}
    for img_id, caminho, ordem, principal, origem in cur.fetchall():
        cur.execute(
            """
            INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal, origem)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (id_produto_destino, caminho, ordem, principal, origem),
        )
        novo_id = cur.fetchone()[0]
        mapa[int(img_id)] = int(novo_id)
    return mapa


def _copiar_atributos_produto(cur, id_produto_origem: int, id_produto_destino: int) -> None:
    cur.execute(
        "SELECT nome, valores, ordem FROM tbl_produto_atributo WHERE id_produto = %s ORDER BY ordem, nome",
        (id_produto_origem,),
    )
    for nome, valores, ordem in cur.fetchall():
        cur.execute(
            """
            INSERT INTO tbl_produto_atributo (id_produto, nome, valores, ordem)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_produto, nome) DO UPDATE SET valores = EXCLUDED.valores, ordem = EXCLUDED.ordem
            """,
            (id_produto_destino, nome, valores, ordem),
        )


def _clonar_produto_para_vendedor(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    id_produto_origem: int,
) -> dict[int, int]:
    """Clona produto integrado para o tenant do vendedor. Retorna mapa variante_antiga -> variante_nova."""
    cur.execute(
        """
        SELECT nome_vitrine, descricao_vitrine, imagem_url_vitrine
        FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_produto = %s
        ORDER BY id
        LIMIT 1
        """,
        (id_vendedor, id_produto_origem),
    )
    vit = cur.fetchone()
    nome_vit = (vit[0] or "").strip() if vit and vit[0] else None
    desc_vit = (vit[1] or "").strip() if vit and vit[1] else None
    img_vit = (vit[2] or "").strip() if vit and vit[2] else None

    cur.execute(
        """
        SELECT nome, descricao, sku, preco, preco_promocional, unidade, id_categoria, imagem_url,
               ativo, publicado, formato, tipo, preco_custo, gtin, ncm, referencia, condicao,
               peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm, profundidade_cm,
               prazo_envio_dias, moq, marca, grupo, valor_atacado, valor_dropshipping,
               reposicao_estoque, dimensao_caixa_cm, peso_gramas, id_deposito_expedicao,
               cest, origem_fiscal, frete_gratis, volumes, producao, valor_drop, valor_drop_manual
        FROM tbl_produto
        WHERE id = %s AND id_tenant = %s
        """,
        (id_produto_origem, id_fornecedor),
    )
    p = cur.fetchone()
    if not p:
        return {}

    id_categoria = _resolver_categoria_vendedor(cur, id_vendedor, p[6])
    nome = nome_vit or p[0]
    descricao = desc_vit if desc_vit is not None else (p[1] or "")
    imagem_url = img_vit or p[7]

    cur.execute(
        """
        INSERT INTO tbl_produto (
            id_tenant, nome, descricao, sku, preco, preco_promocional, unidade, id_categoria,
            imagem_url, ativo, publicado, formato, tipo, preco_custo, gtin, ncm, referencia,
            condicao, peso_liquido_kg, peso_bruto_kg, altura_cm, largura_cm, profundidade_cm,
            prazo_envio_dias, moq, marca, grupo, valor_atacado, valor_dropshipping,
            reposicao_estoque, dimensao_caixa_cm, peso_gramas, id_deposito_expedicao,
            cest, origem_fiscal, frete_gratis, volumes, producao, valor_drop, valor_drop_manual,
            origem, atualizado_em
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual',%s
        )
        RETURNING id
        """,
        (
            id_vendedor,
            nome,
            descricao,
            p[2],
            p[3],
            p[4],
            p[5] or "UN",
            id_categoria,
            imagem_url,
            True,
            False,
            p[10] or "S",
            p[11] or "P",
            p[12],
            p[13],
            p[14],
            p[15],
            p[16],
            p[17],
            p[18],
            p[19],
            p[20],
            p[21],
            p[22],
            p[23] or 1,
            p[24],
            p[25],
            p[26],
            p[27],
            bool(p[28]),
            p[29],
            p[30],
            None,
            p[32],
            p[33],
            bool(p[34]),
            p[35],
            p[36],
            p[37],
            bool(p[38]),
            agora_utc(),
        ),
    )
    id_produto_novo = int(cur.fetchone()[0])
    sku_novo = _sku_unico_clone(cur, id_vendedor, p[2], id_produto_novo)
    if sku_novo:
        cur.execute("UPDATE tbl_produto SET sku = %s WHERE id = %s", (sku_novo, id_produto_novo))

    mapa_imagens = _copiar_imagens_produto(cur, id_produto_origem, id_produto_novo)
    _copiar_atributos_produto(cur, id_produto_origem, id_produto_novo)

    cur.execute(
        """
        SELECT pv.id_variante, pv.preco_venda, pv.preco_fornecedor, pv.ativo, pv.estoque_vitrine,
               pv.nome_vitrine, pv.descricao_vitrine, pv.imagem_url_vitrine
        FROM tbl_produto_vendedor pv
        WHERE pv.id_tenant_vendedor = %s AND pv.id_produto = %s AND pv.id_tenant_fornecedor = %s
        ORDER BY pv.id
        """,
        (id_vendedor, id_produto_origem, id_fornecedor),
    )
    pv_rows = cur.fetchall()
    if not pv_rows:
        return {}

    cur.execute(
        "SELECT nome FROM tbl_produto_atributo WHERE id_produto = %s ORDER BY ordem, nome",
        (id_produto_origem,),
    )
    nomes_attr = [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
    skus_reservados: set[str] = set()

    mapa_variantes: dict[int, int] = {}
    primeiro_vid: int | None = None
    ordem = 0

    for pv_row in pv_rows:
        id_var_origem = int(pv_row[0])
        cur.execute(
            """
            SELECT v.sku, v.nome_exibicao, v.preco, v.preco_promocional, v.preco_custo, v.atributos,
                   v.imagem_url, v.ativo, v.herda_pai, v.peso_liquido_kg, v.peso_bruto_kg,
                   v.altura_cm, v.largura_cm, v.profundidade_cm, v.gtin, v.ncm, v.descricao,
                   v.valor_drop, COALESCE(v.valor_drop_manual, FALSE), v.id_imagem_principal, v.ordem
            FROM tbl_produto_variante v
            WHERE v.id = %s AND v.id_produto = %s
            """,
            (id_var_origem, id_produto_origem),
        )
        v = cur.fetchone()
        if not v:
            continue

        preco_venda = float(pv_row[1] or v[2] or 0)
        preco_custo = float(pv_row[2] or v[4] or 0) if pv_row[2] or v[4] else None
        ativo = bool(pv_row[3])
        estoque = int(pv_row[4] or 0)
        nome_var = (pv_row[5] or "").strip() or v[1]
        desc_var = (pv_row[6] or "").strip() if pv_row[6] else (v[16] or "")
        img_var = (pv_row[7] or "").strip() or v[6]

        atributos = v[5] if isinstance(v[5], dict) else (json.loads(v[5]) if v[5] else {})
        sku_var = (v[0] or "").strip()
        if sku_var:
            try:
                sku_var = resolver_sku_unico_tenant(
                    cur,
                    id_vendedor,
                    sku_novo or sku_var,
                    nomes_attr,
                    atributos,
                    id_produto_novo,
                    skus_reservados,
                )
            except ValueError:
                sku_var = f"DV{id_produto_novo}-{id_var_origem}"
            skus_reservados.add(sku_var)

        id_img_principal = None
        if v[19] and int(v[19]) in mapa_imagens:
            id_img_principal = mapa_imagens[int(v[19])]

        ordem += 1
        cur.execute(
            """
            INSERT INTO tbl_produto_variante (
                id_produto, sku, nome_exibicao, preco, preco_promocional, preco_custo,
                atributos, imagem_url, ativo, ordem, herda_pai, peso_liquido_kg, peso_bruto_kg,
                altura_cm, largura_cm, profundidade_cm, gtin, ncm, descricao,
                valor_drop, valor_drop_manual, id_imagem_principal, atualizado_em
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            RETURNING id
            """,
            (
                id_produto_novo,
                sku_var or None,
                nome_var,
                preco_venda,
                v[3],
                preco_custo,
                json.dumps(atributos, ensure_ascii=False),
                img_var,
                ativo,
                ordem,
                bool(v[8]),
                v[9],
                v[10],
                v[11],
                v[12],
                v[13],
                v[14],
                v[15],
                desc_var,
                v[17],
                bool(v[18]),
                id_img_principal,
                agora_utc(),
            ),
        )
        id_var_nova = int(cur.fetchone()[0])
        mapa_variantes[id_var_origem] = id_var_nova
        if primeiro_vid is None:
            primeiro_vid = id_var_nova

        cur.execute(
            """
            INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
            VALUES (%s, %s, %s)
            ON CONFLICT (id_variante) DO UPDATE SET quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_var_nova, max(0, estoque), agora_utc()),
        )
        garantir_linhas_estoque_depositos(cur, id_vendedor, id_var_nova)
        sincronizar_total_variante(cur, id_var_nova)

    formato = "E" if len(mapa_variantes) > 1 else "S"
    cur.execute(
        """
        UPDATE tbl_produto
        SET formato = %s, id_variante_padrao = %s, atualizado_em = %s
        WHERE id = %s
        """,
        (formato, primeiro_vid, agora_utc(), id_produto_novo),
    )

    if formato == "S" and primeiro_vid:
        cur.execute(
            "SELECT preco, imagem_url FROM tbl_produto_variante WHERE id = %s",
            (primeiro_vid,),
        )
        var_pai = cur.fetchone()
        if var_pai:
            cur.execute(
                """
                UPDATE tbl_produto
                SET preco = %s, imagem_url = COALESCE(NULLIF(imagem_url, ''), %s), atualizado_em = %s
                WHERE id = %s
                """,
                (var_pai[0], var_pai[1], agora_utc(), id_produto_novo),
            )

    return mapa_variantes


def _remover_referencias_variantes(cur, id_vendedor: int, ids_variantes: list[int]) -> None:
    if not ids_variantes:
        return
    cur.execute(
        """
        DELETE FROM tbl_kit_vendedor_item i
        USING tbl_kit_vendedor k
        WHERE i.id_kit = k.id AND k.id_tenant = %s AND i.id_variante = ANY(%s)
        """,
        (id_vendedor, ids_variantes),
    )
    cur.execute(
        "DELETE FROM tbl_produto_favorito WHERE id_tenant = %s AND id_variante = ANY(%s)",
        (id_vendedor, ids_variantes),
    )


def _atualizar_referencias_variantes(cur, id_vendedor: int, mapa: dict[int, int]) -> None:
    if not mapa:
        return
    for id_antigo, id_novo in mapa.items():
        cur.execute(
            """
            UPDATE tbl_kit_vendedor_item i
            SET id_variante = %s
            FROM tbl_kit_vendedor k
            WHERE i.id_kit = k.id AND k.id_tenant = %s AND i.id_variante = %s
            """,
            (id_novo, id_vendedor, id_antigo),
        )
        cur.execute(
            """
            UPDATE tbl_produto_favorito
            SET id_variante = %s, id_produto = (
                SELECT id_produto FROM tbl_produto_variante WHERE id = %s
            )
            WHERE id_tenant = %s AND id_variante = %s
            """,
            (id_novo, id_novo, id_vendedor, id_antigo),
        )


def _excluir_produtos_vitrine(cur, id_vendedor: int, id_fornecedor: int) -> int:
    cur.execute(
        """
        SELECT id_variante FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    ids_variantes = [int(r[0]) for r in cur.fetchall()]
    _remover_referencias_variantes(cur, id_vendedor, ids_variantes)
    cur.execute(
        """
        DELETE FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    return cur.rowcount


def _converter_produtos_vitrine(cur, id_vendedor: int, id_fornecedor: int) -> tuple[int, int]:
    cur.execute(
        """
        SELECT DISTINCT id_produto
        FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        ORDER BY id_produto
        """,
        (id_vendedor, id_fornecedor),
    )
    produtos = [int(r[0]) for r in cur.fetchall()]
    mapa_global: dict[int, int] = {}
    convertidos = 0
    for id_produto in produtos:
        mapa = _clonar_produto_para_vendedor(cur, id_vendedor, id_fornecedor, id_produto)
        if mapa:
            mapa_global.update(mapa)
            convertidos += 1

    _atualizar_referencias_variantes(cur, id_vendedor, mapa_global)
    cur.execute(
        """
        DELETE FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    return convertidos, len(mapa_global)


def desconectar_fornecedor(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    acao_produtos: AcaoProdutos = "excluir",
) -> dict:
    if id_vendedor == id_fornecedor:
        raise ValueError("Operação inválida.")

    cur.execute(
        """
        SELECT id, status FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        """,
        (id_vendedor, id_fornecedor),
    )
    vinc = cur.fetchone()
    if not vinc or vinc[1] != "ativo":
        raise ValueError("Vínculo com este fornecedor não está ativo.")

    qtd_vitrine = contar_produtos_vitrine(cur, id_vendedor, id_fornecedor)
    produtos_removidos = 0
    produtos_convertidos = 0
    variantes_convertidas = 0

    if qtd_vitrine > 0:
        if acao_produtos == "converter":
            produtos_convertidos, variantes_convertidas = _converter_produtos_vitrine(
                cur, id_vendedor, id_fornecedor
            )
        else:
            produtos_removidos = _excluir_produtos_vitrine(cur, id_vendedor, id_fornecedor)
    else:
        cur.execute(
            """
            DELETE FROM tbl_produto_vendedor
            WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
            """,
            (id_vendedor, id_fornecedor),
        )

    cur.execute(
        """
        UPDATE tbl_vinculo_vendedor_fornecedor
        SET status = 'inativo', inativado_em = NOW()
        WHERE id = %s AND id_tenant_fornecedor = %s
        """,
        (vinc[0], id_fornecedor),
    )

    return {
        "qtd_produtos_vitrine": qtd_vitrine,
        "produtos_removidos": produtos_removidos,
        "produtos_convertidos": produtos_convertidos,
        "variantes_convertidas": variantes_convertidas,
    }


# ── srotas_fornecedores ───────────────────────────────

import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from fornecedor.parametros.requisitos import (
    carregar_contato_responsavel_fornecedor,
    carregar_requisitos,
    carregar_requisitos_raw,
    requisitos_tem_conteudo,
    sql_fornecedor_elegivel_rede_vendedor,
)
from fornecedor.parametros.precificacao import (
    buscar_regra_fornecedor,
    calcular_preco_sugerido_revenda,
    pct_margem_revenda_efetiva,
)
from vendedor.precificacao.srotas_precificacao import precificar_na_integracao
from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, login_obrigatorio, exigir_permissao, url_imagem_produto
from core.dominio import montar_snapshot_vendedor
from sistema.plataforma.sessao import MODULO_VENDEDOR

_MOD_DIR = Path(__file__).resolve().parent

vd_fornecedores_bp = Blueprint(
    "vd_fornecedores",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/fornecedores",
)



def _id_tenant_sessao() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _where_rede(id_tenant: int, busca: str, id_fornecedor: str, id_categoria: str) -> tuple[str, list]:
    where = [
        "p.id_tenant <> %s",
        "p.publicado = TRUE",
        "p.ativo = TRUE",
        "v.ativo = TRUE",
        "t.ativo = TRUE",
        "t.tipo_negocio IN ('fornecedor', 'hibrido')",
    ]
    params: list = [id_tenant]

    if busca:
        where.append(
            "(p.nome ILIKE %s OR v.sku ILIKE %s OR v.nome_exibicao ILIKE %s OR t.nome ILIKE %s)"
        )
        like = f"%{busca}%"
        params.extend([like, like, like, like])
    if id_fornecedor:
        where.append("p.id_tenant = %s")
        params.append(int(id_fornecedor))
    if id_categoria:
        where.append("p.id_categoria = %s")
        params.append(int(id_categoria))

    return " AND ".join(where), params


def _parse_atributos_variante(raw) -> dict[str, str]:
    if isinstance(raw, dict):
        data = raw
    elif raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
    else:
        return {}
    out: dict[str, str] = {}
    for chave, valor in data.items():
        nome = str(chave or "").strip()
        val = str(valor or "").strip()
        if nome and val:
            out[nome] = val
    return out


def _ordem_atributos_produto(cur, id_produto: int) -> list[str]:
    cur.execute(
        "SELECT nome FROM tbl_produto_atributo WHERE id_produto = %s ORDER BY ordem, nome",
        (id_produto,),
    )
    return [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]


def _agrupar_atributos_resumo(
    variantes: list[dict],
    ordem_nomes: list[str] | None = None,
) -> list[dict]:
    ordem: list[str] = []
    mapa: dict[str, list[str]] = {}
    for var in variantes:
        for nome, valor in (var.get("atributos") or {}).items():
            if nome not in mapa:
                ordem.append(nome)
                mapa[nome] = []
            if valor not in mapa[nome]:
                mapa[nome].append(valor)
    if ordem_nomes:
        por_nome = {n.lower(): n for n in ordem}
        ordenados: list[str] = []
        vistos: set[str] = set()
        for nome in ordem_nomes:
            chave = (nome or "").strip()
            if not chave:
                continue
            real = por_nome.get(chave.lower())
            if real and real not in vistos:
                ordenados.append(real)
                vistos.add(real)
        for nome in ordem:
            if nome not in vistos:
                ordenados.append(nome)
        ordem = ordenados
    return [{"nome": nome, "valores": mapa[nome]} for nome in ordem if mapa.get(nome)]


@vd_fornecedores_bp.get("/fornecedores")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def pagina():
    return render_template("frm_fornecedores.html", nav_ativo="fornecedores")


@vd_fornecedores_bp.get("/fornecedores/combos")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def combos():
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.id, t.nome, COUNT(p.id)::int
            FROM tbl_tenant t
            INNER JOIN tbl_produto p ON p.id_tenant = t.id
                AND p.publicado = TRUE AND p.ativo = TRUE
            WHERE t.id <> %s
              AND t.ativo = TRUE
              AND t.tipo_negocio IN ('fornecedor', 'hibrido')
            GROUP BY t.id, t.nome
            ORDER BY t.nome
            """,
            (id_tenant,),
        )
        fornecedores = [{"id": r[0], "nome": r[1], "qtd_produtos": r[2]} for r in cur.fetchall()]
        return jsonify(success=True, fornecedores=fornecedores)
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/categorias")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def categorias():
    id_tenant = _id_tenant_sessao()
    id_fornecedor = (request.args.get("id_fornecedor") or "").strip()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    if not id_fornecedor:
        return jsonify(success=True, categorias=[])

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT c.id, c.nome
            FROM tbl_categoria c
            INNER JOIN tbl_produto p ON p.id_categoria = c.id
                AND p.id_tenant = c.id_tenant
                AND p.publicado = TRUE AND p.ativo = TRUE
            WHERE c.id_tenant = %s AND c.ativo = TRUE
            ORDER BY c.nome
            """,
            (int(id_fornecedor),),
        )
        cats = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(success=True, categorias=cats)
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/dados")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def dados():
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = max(1, min(int(request.args.get("porPagina", 20)), 100))
    busca = (request.args.get("busca") or "").strip()
    id_fornecedor = (request.args.get("id_fornecedor") or "").strip()
    id_categoria = (request.args.get("id_categoria") or "").strip()
    offset = (pagina - 1) * por_pagina

    where_sql, params = _where_rede(id_tenant, busca, id_fornecedor, id_categoria)

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            WHERE {where_sql}
            """,
            params,
        )
        total = int(cur.fetchone()[0] or 0)
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

        cur.execute(
            f"""
            SELECT v.id, v.sku, v.nome_exibicao, p.nome, v.preco, v.preco_promocional,
                   COALESCE(v.imagem_url, p.imagem_url), p.unidade,
                   c.nome AS categoria, COALESCE(e.quantidade, 0),
                   t.id AS id_fornecedor, t.nome AS fornecedor_nome, t.slug AS fornecedor_slug,
                   t.cidade, t.uf, p.formato, p.id AS id_produto
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE {where_sql}
            ORDER BY t.nome, p.nome, v.nome_exibicao
            LIMIT %s OFFSET %s
            """,
            params + [por_pagina, offset],
        )
        dados = [
            {
                "id": r[0],
                "id_variante": r[0],
                "id_produto": r[16],
                "sku": r[1] or "",
                "nome": f"{r[3]} — {r[2]}" if r[2] and r[2] != r[3] else (r[3] or r[2]),
                "preco": float(r[4] or 0),
                "preco_promocional": float(r[5]) if r[5] is not None else None,
                "imagem_url": url_imagem_produto(r[6]),
                "unidade": r[7] or "UN",
                "categoria": r[8] or "",
                "estoque": int(r[9] or 0),
                "id_fornecedor": r[10],
                "fornecedor_nome": r[11],
                "fornecedor_slug": r[12],
                "fornecedor_cidade": r[13] or "",
                "fornecedor_uf": r[14] or "",
                "formato": r[15],
            }
            for r in cur.fetchall()
        ]
        return jsonify(
            success=True,
            dados=dados,
            total=total,
            total_paginas=total_paginas,
            pagina=pagina,
        )
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/variante/<int:id_variante>")
@login_obrigatorio()
@exigir_permissao(codigo="fornecedores.ver")
def variante_detalhe(id_variante: int):
    id_tenant = _id_tenant_sessao()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT v.id, v.sku, v.nome_exibicao, p.nome, p.descricao, v.preco, v.preco_promocional,
                   COALESCE(v.imagem_url, p.imagem_url), p.unidade, c.nome,
                   COALESCE(e.quantidade, 0), t.id, t.nome, t.slug, t.cidade, t.uf, p.formato, p.id
            FROM tbl_produto_variante v
            INNER JOIN tbl_produto p ON p.id = v.id_produto
            INNER JOIN tbl_tenant t ON t.id = p.id_tenant
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE v.id = %s AND p.id_tenant <> %s
              AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
              AND t.ativo = TRUE AND t.tipo_negocio IN ('fornecedor', 'hibrido')
            """,
            (id_variante, id_tenant),
        )
        r = cur.fetchone()
        if not r:
            return jsonify(success=False, message="Produto não encontrado na rede."), 404

        return jsonify(
            success=True,
            produto={
                "id": r[0],
                "id_variante": r[0],
                "id_produto": r[17],
                "sku": r[1] or "",
                "nome": f"{r[3]} — {r[2]}" if r[2] and r[2] != r[3] else (r[3] or r[2]),
                "descricao": r[4] or "",
                "preco": float(r[5] or 0),
                "preco_promocional": float(r[6]) if r[6] is not None else None,
                "imagem_url": url_imagem_produto(r[7]),
                "unidade": r[8] or "UN",
                "categoria": r[9] or "",
                "estoque": int(r[10] or 0),
                "id_fornecedor": r[11],
                "fornecedor_nome": r[12],
                "fornecedor_slug": r[13],
                "fornecedor_cidade": r[14] or "",
                "fornecedor_uf": r[15] or "",
                "formato": r[16] or "S",
            },
        )
    finally:
        conn.close()

def _parse_ids_segmentos(raw: str) -> list[int]:
    ids: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


@vd_fornecedores_bp.get("/fornecedores/segmentos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def segmentos_rede():
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        elegivel = sql_fornecedor_elegivel_rede_vendedor("t")
        cur.execute(
            f"""
            SELECT s.id, s.nome, COUNT(DISTINCT fs.id_tenant)::int
            FROM tbl_segmento s
            INNER JOIN tbl_fornecedor_segmento fs ON fs.id_segmento = s.id
            INNER JOIN tbl_tenant t ON t.id = fs.id_tenant
                AND t.id <> %s
                AND t.ativo = TRUE
                AND t.tipo_negocio IN ('fornecedor', 'hibrido')
                AND {elegivel}
            WHERE s.ativo = TRUE
              AND s.id_tenant IS NULL
            GROUP BY s.id, s.nome, s.ordem
            ORDER BY s.ordem NULLS LAST, s.nome
            """,
            (id_vendedor,),
        )
        segmentos = [{"id": r[0], "nome": r[1], "qtd_fornecedores": r[2]} for r in cur.fetchall()]
        return jsonify(success=True, segmentos=segmentos)
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/rede")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def rede():
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403
    busca = (request.args.get("busca") or "").strip()
    ids_segmentos = _parse_ids_segmentos(request.args.get("segmentos") or "")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        elegivel = sql_fornecedor_elegivel_rede_vendedor("t")
        where = [
            "t.id <> %s",
            "t.ativo = TRUE",
            "t.tipo_negocio IN ('fornecedor', 'hibrido')",
            elegivel,
        ]
        params: list = [id_vendedor]
        if busca:
            where.append(
                "(COALESCE(t.nome_fantasia, t.nome) ILIKE %s OR t.cidade ILIKE %s OR t.razao_social ILIKE %s)"
            )
            like = f"%{busca}%"
            params.extend([like, like, like])
        if ids_segmentos:
            where.append(
                """EXISTS (
                    SELECT 1 FROM tbl_fornecedor_segmento fs
                    WHERE fs.id_tenant = t.id AND fs.id_segmento = ANY(%s)
                )"""
            )
            params.append(ids_segmentos)
        cur.execute(
            f"""
            SELECT t.id, COALESCE(t.nome_fantasia, t.nome), t.cidade, t.uf,
                   t.telefone_comercial, t.email_comercial,
                   v.id AS id_vinculo, COALESCE(v.status, 'nenhum'),
                   (SELECT COUNT(*)::int FROM tbl_produto p
                    WHERE p.id_tenant = t.id AND p.ativo = TRUE),
                   (SELECT COUNT(DISTINCT pv.id_produto)::int
                    FROM tbl_produto_vendedor pv
                    WHERE pv.id_tenant_vendedor = %s AND pv.id_tenant_fornecedor = t.id),
                   v.mensagem_resposta
            FROM tbl_tenant t
            LEFT JOIN tbl_vinculo_vendedor_fornecedor v
                ON v.id_tenant_fornecedor = t.id AND v.id_tenant_vendedor = %s
            WHERE {' AND '.join(where)}
            ORDER BY t.nome
            LIMIT 120
            """,
            [id_vendedor, id_vendedor] + params,
        )
        cards = []
        for row in cur.fetchall():
            tid = row[0]
            cur.execute(
                """
                SELECT s.id, s.nome
                FROM tbl_fornecedor_segmento fs
                JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
                WHERE fs.id_tenant = %s
                ORDER BY s.nome
                LIMIT 8
                """,
                (tid,),
            )
            seg_rows = cur.fetchall()
            segmentos = [r[1] for r in seg_rows]
            ids_seg = [r[0] for r in seg_rows]
            st = row[7] or "nenhum"
            cards.append(
                {
                    "id": tid,
                    "nome": row[1],
                    "cidade": row[2] or "",
                    "uf": row[3] or "",
                    "telefone": row[4] or "",
                    "email": row[5] or "",
                    "segmentos": segmentos,
                    "ids_segmentos": ids_seg,
                    "qtd_produtos": int(row[8] or 0),
                    "qtd_produtos_vitrine": int(row[9] or 0),
                    "status_vinculo": st,
                    "id_vinculo": row[6],
                    "motivo_recusa": row[10] or "" if st == "recusado" else "",
                }
            )
        return jsonify(success=True, fornecedores=cards)
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/loja")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def pagina_loja():
    return render_template("frm_fornecedor_loja.html")

@vd_fornecedores_bp.get("/fornecedores/solicitar-vinculo/apoio")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def pagina_solicitar_vinculo_apoio():
    return render_template("frm_solicitar_vinculo.html")


@vd_fornecedores_bp.get("/fornecedores/<int:id_fornecedor>/requisitos-vinculo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def requisitos_vinculo(id_fornecedor: int):
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(t.nome_fantasia, t.nome)
            FROM tbl_tenant t
            WHERE t.id = %s AND t.ativo = TRUE
              AND t.tipo_negocio IN ('fornecedor', 'hibrido')
            """,
            (id_fornecedor,),
        )
        forn = cur.fetchone()
        if not forn:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        req, tem_registro = carregar_requisitos_raw(cur, id_fornecedor)
        cur.execute("SELECT tipo_pessoa FROM tbl_tenant WHERE id = %s", (id_vendedor,))
        tp = cur.fetchone()
        vendedor_pj = tp and tp[0] == "J"
        contato = None
        if tem_registro and req.get("mostrar_contato_vendedor"):
            contato = carregar_contato_responsavel_fornecedor(cur, id_fornecedor)
        return jsonify(
            success=True,
            fornecedor_nome=forn[0],
            requisitos=req,
            tem_requisitos=requisitos_tem_conteudo(req),
            requisitos_salvos=tem_registro,
            vendedor_eh_pj=vendedor_pj,
            contato_fornecedor=contato,
        )
    finally:
        conn.close()


@vd_fornecedores_bp.post("/fornecedores/solicitar-vinculo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def solicitar_vinculo():
    id_vendedor = session.get("id_tenant")
    id_usuario = session.get("id_usuario")
    body = request.get_json(silent=True) or {}
    try:
        id_forn = int(body.get("id_fornecedor"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Fornecedor inválido."), 400
    if id_forn == id_vendedor:
        return jsonify(success=False, message="Operação inválida."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        req = carregar_requisitos(cur, id_forn)
        if requisitos_tem_conteudo(req):
            if not body.get("aceite_requisitos"):
                return jsonify(success=False, message="Aceite os requisitos do fornecedor para continuar."), 400
        if not body.get("aceite_compartilhamento_dados"):
            return jsonify(
                success=False,
                message="Autorize o acesso aos seus dados cadastrais para o fornecedor validar a solicitação.",
            ), 400
        if not body.get("aceite_declaracao_apto"):
            return jsonify(success=False, message="Confirme que está apto a cumprir as condições informadas."), 400
        if req.get("exige_cnpj"):
            cur.execute("SELECT tipo_pessoa FROM tbl_tenant WHERE id = %s", (id_vendedor,))
            tp = cur.fetchone()
            if not tp or tp[0] != "J":
                return jsonify(
                    success=False,
                    message="Este fornecedor exige CNPJ. Atualize os dados da empresa em Minha conta.",
                ), 400

        snap = montar_snapshot_vendedor(cur, id_vendedor, id_usuario)
        agora = agora_utc().isoformat()
        if requisitos_tem_conteudo(req):
            snap["aceite_requisitos"] = True
            snap["aceite_requisitos_em"] = agora
            snap["requisitos_aceitos"] = req
        snap["aceite_compartilhamento_dados"] = True
        snap["aceite_compartilhamento_em"] = agora
        snap["aceite_declaracao_apto"] = True
        snap["aceite_declaracao_em"] = agora

        cur.execute(
            """
            SELECT status FROM tbl_vinculo_vendedor_fornecedor
            WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
            """,
            (id_vendedor, id_forn),
        )
        row = cur.fetchone()
        if row:
            st = row[0]
            if st == "ativo":
                return jsonify(success=False, message="Você já está conectado a este fornecedor."), 409
            if st == "aguardando":
                return jsonify(success=False, message="Solicitação já enviada. Aguarde aprovação."), 409
            cur.execute(
                """
                UPDATE tbl_vinculo_vendedor_fornecedor
                SET status = 'aguardando', solicitado_em = NOW(), respondido_em = NULL,
                    mensagem_resposta = NULL,
                    snapshot_vendedor = %s::jsonb,
                    mensagem_solicitacao = %s
                WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
                """,
                (
                    json.dumps(snap, ensure_ascii=False),
                    (body.get("mensagem") or "").strip() or None,
                    id_vendedor,
                    id_forn,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_vinculo_vendedor_fornecedor
                    (id_tenant_vendedor, id_tenant_fornecedor, status, snapshot_vendedor, mensagem_solicitacao)
                VALUES (%s, %s, 'aguardando', %s::jsonb, %s)
                """,
                (
                    id_vendedor,
                    id_forn,
                    json.dumps(snap, ensure_ascii=False),
                    (body.get("mensagem") or "").strip() or None,
                ),
            )
        conn.commit()
        return jsonify(success=True, message="Solicitação enviada. Aguardando aprovação do fornecedor.")
    finally:
        conn.close()


@vd_fornecedores_bp.post("/fornecedores/desconectar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def desconectar():
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    try:
        id_forn = int(body.get("id_fornecedor"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Fornecedor inválido."), 400
    acao = (body.get("acao_produtos") or "excluir").strip().lower()
    if acao not in ("excluir", "converter"):
        return jsonify(success=False, message="Ação inválida para os produtos."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        resultado = desconectar_fornecedor(cur, int(id_vendedor), id_forn, acao_produtos=acao)
        conn.commit()
        if acao == "converter" and resultado["produtos_convertidos"]:
            msg = (
                f"Fornecedor desconectado. {resultado['produtos_convertidos']} produto(s) "
                "passaram a ser seus (cadastro completo)."
            )
        elif resultado["qtd_produtos_vitrine"]:
            msg = (
                f"Fornecedor desconectado. {resultado['qtd_produtos_vitrine']} produto(s) "
                "foram removidos de Meus produtos."
            )
        else:
            msg = "Fornecedor desconectado com sucesso."
        return jsonify(success=True, message=msg, **resultado)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/<int:id_fornecedor>/loja/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def loja_dados(id_fornecedor: int):
    id_vendedor = session.get("id_tenant")
    if not id_vendedor:
        return jsonify(success=False, message="Sessão inválida."), 403
    busca = (request.args.get("busca") or "").strip()
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = min(60, max(12, int(request.args.get("porPagina", 24))))
    offset = (pagina - 1) * por_pagina

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(t.nome_fantasia, t.nome), t.cidade, t.uf,
                   COALESCE(v.status, 'nenhum')
            FROM tbl_tenant t
            LEFT JOIN tbl_vinculo_vendedor_fornecedor v
                ON v.id_tenant_fornecedor = t.id AND v.id_tenant_vendedor = %s
            WHERE t.id = %s AND t.ativo = TRUE
              AND t.tipo_negocio IN ('fornecedor', 'hibrido')
            """,
            (id_vendedor, id_fornecedor),
        )
        forn = cur.fetchone()
        if not forn:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404

        where_prod = [
            "p.id_tenant = %s",
            "p.publicado = TRUE",
            "p.ativo = TRUE",
        ]
        params_prod: list = [id_fornecedor]
        if busca:
            where_prod.append("(p.nome ILIKE %s OR p.descricao ILIKE %s)")
            like = f"%{busca}%"
            params_prod.extend([like, like])

        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM tbl_produto p
            WHERE {' AND '.join(where_prod)}
            """,
            params_prod,
        )
        total = int(cur.fetchone()[0] or 0)
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

        cur.execute(
            f"""
            SELECT p.id, p.nome, LEFT(COALESCE(p.descricao, ''), 220),
                   p.imagem_url, c.id_segmento, p.id_categoria, p.formato
            FROM tbl_produto p
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria AND c.id_tenant = p.id_tenant
            WHERE {' AND '.join(where_prod)}
            ORDER BY p.nome
            LIMIT %s OFFSET %s
            """,
            params_prod + [por_pagina, offset],
        )
        produtos = []
        status_vinculo = forn[3] or "nenhum"
        for row in cur.fetchall():
            id_produto = row[0]
            cur.execute(
                """
                SELECT v.id, v.nome_exibicao, v.atributos,
                       COALESCE(NULLIF(v.valor_drop, 0), NULLIF(p.valor_drop, 0), v.preco) AS preco_drop,
                       COALESCE(v.imagem_url, p.imagem_url),
                       COALESCE(e.quantidade, 0),
                       pv.id IS NOT NULL AS ativado
                FROM tbl_produto_variante v
                JOIN tbl_produto p ON p.id = v.id_produto
                LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
                LEFT JOIN tbl_produto_vendedor pv
                    ON pv.id_variante = v.id AND pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
                WHERE p.id = %s AND v.ativo = TRUE
                ORDER BY v.nome_exibicao NULLS LAST, v.id
                """,
                (id_vendedor, id_produto),
            )
            variantes = []
            precos_drop: list[float] = []
            for vr in cur.fetchall():
                preco_drop = float(vr[3] or 0)
                precos_drop.append(preco_drop)
                atributos = _parse_atributos_variante(vr[2])
                variantes.append(
                    {
                        "id_variante": vr[0],
                        "grade": (vr[1] or "").strip() or "Único",
                        "atributos": atributos,
                        "preco_fornecedor": preco_drop,
                        "estoque": int(vr[5] or 0),
                        "ativado": bool(vr[6]),
                    }
                )
            if not variantes:
                continue

            preco_forn = min(precos_drop) if precos_drop else 0.0
            regra_fn = buscar_regra_fornecedor(cur, id_fornecedor, row[5])
            pct_revenda = pct_margem_revenda_efetiva(regra_fn)
            preco_sug = calcular_preco_sugerido_revenda(preco_forn, pct_revenda)
            lucro = round(preco_sug - preco_forn, 2)
            margem = pct_revenda
            img_url = url_imagem_produto(row[3])
            if not img_url:
                cur.execute(
                    """
                    SELECT COALESCE(v.imagem_url, p.imagem_url)
                    FROM tbl_produto_variante v
                    JOIN tbl_produto p ON p.id = v.id_produto
                    WHERE p.id = %s AND v.ativo = TRUE
                      AND COALESCE(v.imagem_url, p.imagem_url) IS NOT NULL
                    LIMIT 1
                    """,
                    (id_produto,),
                )
                img_row = cur.fetchone()
                if img_row:
                    img_url = url_imagem_produto(img_row[0])

            todos_ativados = all(v["ativado"] for v in variantes)
            algum_ativado = any(v["ativado"] for v in variantes)
            atributos_resumo = _agrupar_atributos_resumo(
                variantes,
                _ordem_atributos_produto(cur, id_produto),
            )
            tem_variacoes = (row[6] or "S") == "E" or len(variantes) > 1

            produtos.append(
                {
                    "id_produto": id_produto,
                    "nome": row[1],
                    "descricao": (row[2] or "").strip(),
                    "imagem_url": img_url,
                    "formato": row[6] or "S",
                    "variantes": variantes,
                    "atributos_resumo": atributos_resumo,
                    "tem_variacoes": tem_variacoes,
                    "grades": [v["grade"] for v in variantes[:12]],
                    "preco_fornecedor": preco_forn,
                    "preco_sugerido": preco_sug,
                    "lucro_estimado": lucro,
                    "margem_pct": margem,
                    "estoque_total": sum(v["estoque"] for v in variantes),
                    "ativado": todos_ativados,
                    "parcialmente_ativado": algum_ativado and not todos_ativados,
                }
            )

        return jsonify(
            success=True,
            fornecedor={
                "id": id_fornecedor,
                "nome": forn[0],
                "cidade": forn[1] or "",
                "uf": forn[2] or "",
                "status_vinculo": status_vinculo,
            },
            produtos=produtos,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
        )
    finally:
        conn.close()


@vd_fornecedores_bp.post("/fornecedores/loja/ativar-produto")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def loja_ativar_produto():
    id_vendedor = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    try:
        id_produto = int(body.get("id_produto"))
        id_fornecedor = int(body.get("id_fornecedor"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Produto inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status FROM tbl_vinculo_vendedor_fornecedor
            WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
            """,
            (id_vendedor, id_fornecedor),
        )
        vinc = cur.fetchone()
        if not vinc or vinc[0] != "ativo":
            return jsonify(
                success=False,
                message="Vínculo com o fornecedor não está ativo. Solicite aprovação primeiro.",
            ),
            403

        cur.execute(
            """
            SELECT v.id, p.id, p.id_tenant,
                   COALESCE(NULLIF(v.valor_drop, 0), NULLIF(p.valor_drop, 0), v.preco),
                   c.id_segmento, p.id_categoria
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
            WHERE p.id = %s AND p.id_tenant = %s
              AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
            """,
            (id_produto, id_fornecedor),
        )
        rows = cur.fetchall()
        if not rows:
            return jsonify(success=False, message="Produto não encontrado."), 404

        from vendedor.meus_produtos.servico_meus_produtos import espelhar_depositos_fornecedor

        espelhar_depositos_fornecedor(cur, int(id_vendedor), id_fornecedor, id_produto=id_produto)

        ativados = 0
        for row in rows:
            preco_forn = float(row[3] or 0)
            preco_venda = precificar_na_integracao(
                cur, int(id_vendedor), id_fornecedor, row[5], preco_forn
            )
            cur.execute(
                """
                INSERT INTO tbl_produto_vendedor
                    (id_tenant_vendedor, id_tenant_fornecedor, id_variante, id_produto,
                     preco_fornecedor, preco_venda, ativo, estoque_vitrine)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, 0)
                ON CONFLICT (id_tenant_vendedor, id_variante) DO UPDATE SET
                    ativo = TRUE, preco_fornecedor = EXCLUDED.preco_fornecedor,
                    preco_venda = CASE WHEN tbl_produto_vendedor.preco_manual THEN tbl_produto_vendedor.preco_venda
                                  ELSE EXCLUDED.preco_venda END,
                    atualizado_em = NOW()
                """,
                (id_vendedor, row[2], row[0], row[1], preco_forn, preco_venda),
            )
            ativados += 1
        conn.commit()
        return jsonify(
            success=True,
            message=f"Produto integrado em Meus produtos ({ativados} variação(ões)).",
            ativados=ativados,
        )
    finally:
        conn.close()


@vd_fornecedores_bp.get("/fornecedores/<int:id_fornecedor>/catalogo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="fornecedores.ver")
def catalogo_fornecedor(id_fornecedor: int):
    id_vendedor = session.get("id_tenant")
    pagina = max(1, int(request.args.get("pagina", 1)))
    por_pagina = min(48, max(12, int(request.args.get("porPagina", 24))))
    offset = (pagina - 1) * por_pagina
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE p.id_tenant = %s AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
            """,
            (id_fornecedor,),
        )
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT v.id, p.nome, v.nome_exibicao, v.preco,
                   COALESCE(v.imagem_url, p.imagem_url), COALESCE(e.quantidade, 0)
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
            WHERE p.id_tenant = %s AND p.publicado = TRUE AND p.ativo = TRUE AND v.ativo = TRUE
            ORDER BY p.nome
            LIMIT %s OFFSET %s
            """,
            (id_fornecedor, por_pagina, offset),
        )
        produtos = [
            {
                "id_variante": r[0],
                "nome": f"{r[1]} — {r[2]}" if r[2] and r[2] != r[1] else r[1],
                "preco": float(r[3] or 0),
                "imagem_url": url_imagem_produto(r[4]),
                "estoque": int(r[5] or 0),
            }
            for r in cur.fetchall()
        ]
        return jsonify(
            success=True,
            produtos=produtos,
            total=total,
            pagina=pagina,
            total_paginas=max(1, (total + por_pagina - 1) // por_pagina),
        )
    finally:
        conn.close()


def init_app(app):
    app.register_blueprint(vd_fornecedores_bp)
