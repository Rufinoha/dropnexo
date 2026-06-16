# fornecedor/importacao/srotas_importacao.py — painel de importação
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from api.bling.sync_produtos import importar_produtos
from fornecedor.importacao.servico_importacao import (
    MODULO_CATALOGO,
    ORIGEM_ARQUIVO,
    ORIGEM_INTEGRACAO,
    STATUS_CONCLUIDO,
    STATUS_ERRO,
    campos_base_layout,
    criar_lote,
    definir_layout_padrao,
    excluir_layout_importacao,
    excluir_lote,
    finalizar_lote,
    garantir_layout_padrao_csv,
    listar_erros_lote,
    listar_layouts,
    listar_layouts_admin,
    listar_lotes,
    obter_layout_detalhe,
    obter_lote,
    obter_cards_importacao,
    registrar_erro_lote,
    rotulo_origem,
    salvar_layout_importacao,
    ultimo_lote,
)
from global_utils import (
    Var_ConectarBanco,
    agora_utc,
    exigir_permissao,
    login_obrigatorio,
    usuario_tem_permissao,
)

_MOD = Path(__file__).resolve().parent

fn_importacao_bp = Blueprint(
    "fn_importacao",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/fornecedor/importacao",
)


def init_app(app):
    app.register_blueprint(fn_importacao_bp)


def _pode_importar():
    return session.get("eh_desenvolvedor") or usuario_tem_permissao("fn_importacao.editar") or usuario_tem_permissao(
        "catalogos.editar"
    )


def _exigir_escrita():
    if _pode_importar():
        return None
    return jsonify(success=False, message="Sem permissão para importar."), 403


def _bling_conectado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return bool(row and row[0] == "conectado")


def _bling_config_fornecedor(cur, id_tenant: int) -> dict:
    """Config Bling do fornecedor (opcoes de estoque, últimas syncs)."""
    padrao = {
        "estoque_baixa_pedido": False,
        "estoque_importar_bling": False,
        "estoque_polling_minutos": 30,
    }
    try:
        cur.execute(
            """
            SELECT estoque_modo, pedidos_modo, ultima_sync_estoque, ultima_sync_produtos, opcoes
            FROM tbl_integracao_bling_config
            WHERE id_tenant = %s AND contexto = 'fornecedor'
            """,
            (id_tenant,),
        )
    except Exception:
        cur.execute(
            """
            SELECT estoque_modo, pedidos_modo, ultima_sync_estoque, ultima_sync_produtos
            FROM tbl_integracao_bling_config
            WHERE id_tenant = %s AND contexto = 'fornecedor'
            """,
            (id_tenant,),
        )
    row = cur.fetchone()
    if not row:
        return {**padrao, "estoque_modo": "importar", "pedidos_modo": "importar"}

    opcoes_raw = row[4] if len(row) > 4 else {}
    if isinstance(opcoes_raw, str):
        try:
            opcoes_raw = json.loads(opcoes_raw)
        except json.JSONDecodeError:
            opcoes_raw = {}
    if not isinstance(opcoes_raw, dict):
        opcoes_raw = {}

    def sync_iso(val):
        return val.isoformat() if val else None

    return {
        "estoque_modo": row[0] or "importar",
        "pedidos_modo": row[1] or "importar",
        "ultima_sync_estoque": sync_iso(row[2]),
        "ultima_sync_produtos": sync_iso(row[3]),
        "estoque_baixa_pedido": bool(opcoes_raw.get("estoque_baixa_pedido", padrao["estoque_baixa_pedido"])),
        "estoque_importar_bling": bool(opcoes_raw.get("estoque_importar_bling", padrao["estoque_importar_bling"])),
        "estoque_polling_minutos": int(opcoes_raw.get("estoque_polling_minutos") or padrao["estoque_polling_minutos"]),
    }


def _salvar_bling_estoque_config(cur, id_tenant: int, body: dict) -> None:
    baixa = bool(body.get("estoque_baixa_pedido"))
    importar = bool(body.get("estoque_importar_bling"))
    try:
        polling = int(body.get("estoque_polling_minutos") or 30)
    except (TypeError, ValueError):
        polling = 30
    if polling not in (15, 30, 60):
        polling = 30

    opcoes = {
        "estoque_baixa_pedido": baixa,
        "estoque_importar_bling": importar,
        "estoque_polling_minutos": polling,
    }
    pedidos_modo = "exportar" if baixa else "importar"
    estoque_modo = "importar" if importar else "exportar" if baixa else "importar"
    agora = agora_utc()

    try:
        cur.execute(
            """
            INSERT INTO tbl_integracao_bling_config (
                id_tenant, contexto, pedidos_modo, estoque_modo, opcoes, atualizado_em
            ) VALUES (%s, 'fornecedor', %s, %s, %s::jsonb, %s)
            ON CONFLICT (id_tenant, contexto) DO UPDATE SET
                pedidos_modo = EXCLUDED.pedidos_modo,
                estoque_modo = EXCLUDED.estoque_modo,
                opcoes = EXCLUDED.opcoes,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, pedidos_modo, estoque_modo, json.dumps(opcoes), agora),
        )
    except Exception:
        cur.execute(
            """
            INSERT INTO tbl_integracao_bling_config (
                id_tenant, contexto, pedidos_modo, estoque_modo, atualizado_em
            ) VALUES (%s, 'fornecedor', %s, %s, %s)
            ON CONFLICT (id_tenant, contexto) DO UPDATE SET
                pedidos_modo = EXCLUDED.pedidos_modo,
                estoque_modo = EXCLUDED.estoque_modo,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, pedidos_modo, estoque_modo, agora),
        )


@fn_importacao_bp.get("/fornecedor/importacao")
@login_obrigatorio()
def importacao_pagina():
    return redirect(url_for("fn_catalogo.pagina"))


@fn_importacao_bp.get("/fornecedor/importacao/cards")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_cards():
    id_tenant = int(session.get("id_tenant"))
    id_lote = request.args.get("id_lote", type=int)
    origem = (request.args.get("origem") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = obter_cards_importacao(cur, id_tenant, id_lote, origem=origem)
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@fn_importacao_bp.get("/fornecedor/importacao/erro")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_erro_pagina():
    return render_template("frm_importacao_erro.html")


@fn_importacao_bp.get("/fornecedor/importacao/dados")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_dados():
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        bling = _bling_conectado(cur, int(id_tenant))
        bling_config = _bling_config_fornecedor(cur, int(id_tenant)) if bling else None
        layouts = listar_layouts(cur, int(id_tenant))
        ultimo = ultimo_lote(cur, int(id_tenant))
        ultimo_bling = ultimo_lote(cur, int(id_tenant), origem=ORIGEM_INTEGRACAO) if bling else None
        conn.commit()
        return jsonify(
            success=True,
            modulo=MODULO_CATALOGO,
            bling_conectado=bling,
            bling_config=bling_config,
            integracoes=[{"id": "bling", "nome": "Bling", "conectado": bling}] if bling else [],
            layouts=layouts,
            ultimo_lote=ultimo,
            ultimo_lote_bling=ultimo_bling,
            pode_editar=_pode_importar(),
        )
    finally:
        conn.close()


@fn_importacao_bp.get("/fornecedor/importacao/lotes")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_lotes():
    id_tenant = session.get("id_tenant")
    data_de = (request.args.get("de") or "").strip() or None
    data_ate = (request.args.get("ate") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        lotes = listar_lotes(cur, int(id_tenant), data_de=data_de, data_ate=data_ate)
        for l in lotes:
            l["origem_rotulo"] = rotulo_origem(l.get("origem") or "")
        return jsonify(success=True, dados=lotes)
    finally:
        conn.close()


@fn_importacao_bp.get("/fornecedor/importacao/lote/<int:id_lote>")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_lote_detalhe(id_lote: int):
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        lote = obter_lote(cur, int(id_tenant), id_lote)
        if not lote:
            return jsonify(success=False, message="Lote não encontrado."), 404
        lote["origem_rotulo"] = rotulo_origem(lote.get("origem") or "")
        erros = listar_erros_lote(cur, int(id_tenant), id_lote)
        return jsonify(success=True, lote=lote, erros=erros)
    finally:
        conn.close()


@fn_importacao_bp.delete("/fornecedor/importacao/lote/<int:id_lote>")
@login_obrigatorio()
@exigir_permissao(codigo="fn_importacao.editar")
def importacao_lote_excluir(id_lote: int):
    if (resp := _exigir_escrita()) is not None:
        return resp
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        resultado = excluir_lote(cur, int(id_tenant), id_lote)
        conn.commit()
        return jsonify(
            success=True,
            message=f"Lote excluído. {resultado['produtos_removidos']} produto(s) removido(s).",
            dados=resultado,
        )
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_importacao_bp.post("/fornecedor/importacao/bling/estoque")
@login_obrigatorio()
@exigir_permissao(codigo="fn_importacao.editar")
def importacao_bling_estoque():
    if (resp := _exigir_escrita()) is not None:
        return resp

    body = request.get_json(silent=True) or {}
    id_tenant = int(session.get("id_tenant"))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not _bling_conectado(cur, id_tenant):
            return jsonify(success=False, message="Conecte o Bling antes de configurar estoque."), 400
        _salvar_bling_estoque_config(cur, id_tenant, body)
        conn.commit()
        config = _bling_config_fornecedor(cur, id_tenant)
        return jsonify(success=True, message="Configuração de estoque salva.", bling_config=config)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_importacao_bp.post("/fornecedor/importacao/arquivo")
@login_obrigatorio()
@exigir_permissao(codigo="fn_importacao.editar")
def importacao_arquivo():
    if (resp := _exigir_escrita()) is not None:
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

    id_tenant = int(session.get("id_tenant"))
    id_usuario = session.get("id_usuario")
    filename = arquivo.filename

    from fornecedor.catalogo.srotas_catalogo import (  # noqa: WPS433 — reutiliza parser
        MAX_LINHAS_CSV,
        _normalizar_bool,
        _parse_decimal,
        _resolver_categoria,
    )

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

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        id_layout = garantir_layout_padrao_csv(cur, id_tenant)
        id_lote, numero = criar_lote(
            cur,
            id_tenant=id_tenant,
            modulo=MODULO_CATALOGO,
            origem=ORIGEM_ARQUIVO,
            id_usuario=int(id_usuario) if id_usuario else None,
            id_layout=id_layout,
            nome_arquivo=filename,
            meta={"layout": "csv_padrao"},
        )

        inseridos = 0
        atualizados = 0
        rejeitadas = 0
        total_linhas = 0

        for num, row in enumerate(reader, start=2):
            if num - 2 >= MAX_LINHAS_CSV:
                registrar_erro_lote(
                    cur,
                    id_tenant=id_tenant,
                    id_lote=id_lote,
                    modulo=MODULO_CATALOGO,
                    linha_arquivo=num,
                    mensagem=f"Máximo de {MAX_LINHAS_CSV} linhas por importação.",
                )
                rejeitadas += 1
                break
            total_linhas += 1

            def cel(*nomes):
                for n in nomes:
                    c = mapa.get(n)
                    if c is not None:
                        return (row.get(c) or "").strip()
                return ""

            nome = cel("nome")
            if not nome:
                if any((row.get(mapa[k]) or "").strip() for k in mapa if k != "nome"):
                    registrar_erro_lote(
                        cur,
                        id_tenant=id_tenant,
                        id_lote=id_lote,
                        modulo=MODULO_CATALOGO,
                        linha_arquivo=num,
                        mensagem="Nome obrigatório.",
                    )
                    rejeitadas += 1
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
                criando = True
                if sku:
                    cur.execute(
                        "SELECT id FROM tbl_produto WHERE id_tenant = %s AND sku = %s",
                        (id_tenant, sku),
                    )
                    found = cur.fetchone()
                    if found:
                        prod_id = found[0]
                        criando = False
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
                                unidade, id_categoria, ativo, publicado, origem,
                                id_importacao_lote, atualizado_em
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                                ORIGEM_ARQUIVO,
                                id_lote,
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
                            unidade, id_categoria, ativo, publicado, origem,
                            id_importacao_lote, atualizado_em
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                            ORIGEM_ARQUIVO,
                            id_lote,
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
                if criando and prod_id:
                    pass  # origem/lote já definidos no INSERT
            except Exception as ex:
                rejeitadas += 1
                registrar_erro_lote(
                    cur,
                    id_tenant=id_tenant,
                    id_lote=id_lote,
                    modulo=MODULO_CATALOGO,
                    linha_arquivo=num,
                    nome_registro=nome,
                    sku_registro=sku or "",
                    mensagem=str(ex),
                )

        status = STATUS_ERRO if inseridos + atualizados == 0 else STATUS_CONCLUIDO
        finalizar_lote(
            cur,
            id_lote,
            status=status,
            total_linhas=total_linhas,
            total_importadas=inseridos,
            total_atualizadas=atualizados,
            total_rejeitadas=rejeitadas,
        )
        conn.commit()
        lote = obter_lote(cur, id_tenant, id_lote)
        erros = listar_erros_lote(cur, id_tenant, id_lote)
        return jsonify(
            success=True,
            message=f"Importação {numero} concluída.",
            id_lote=id_lote,
            numero=numero,
            inseridos=inseridos,
            atualizados=atualizados,
            rejeitadas=rejeitadas,
            lote=lote,
            erros=erros,
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_importacao_bp.get("/fornecedor/importacao/layout/incluir")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_layout_incluir():
    return render_template("frm_importacao_layout.html")


@fn_importacao_bp.get("/fornecedor/importacao/layout/editar")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_layout_editar():
    return render_template("frm_importacao_layout.html")


@fn_importacao_bp.get("/fornecedor/importacao/layout/campos_base")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_layout_campos_base():
    modulo = (request.args.get("modulo") or MODULO_CATALOGO).strip()
    dados = campos_base_layout(modulo)
    if not dados:
        return jsonify(success=False, message="Módulo sem campos base configurados."), 400
    return jsonify(success=True, dados=dados)


@fn_importacao_bp.get("/fornecedor/importacao/layout/dados")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_layout_dados():
    id_tenant = int(session.get("id_tenant"))
    modulo = (request.args.get("modulo") or MODULO_CATALOGO).strip()
    nome = (request.args.get("nome") or "").strip() or None
    status = (request.args.get("status") or "").strip() or None
    padrao = (request.args.get("padrao") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = listar_layouts_admin(
            cur, id_tenant, modulo, nome=nome, status=status, padrao=padrao
        )
        conn.commit()
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@fn_importacao_bp.get("/fornecedor/importacao/layout/apoio")
@login_obrigatorio()
@exigir_permissao(codigo="catalogos.ver")
def importacao_layout_apoio():
    id_tenant = int(session.get("id_tenant"))
    modulo = (request.args.get("modulo") or MODULO_CATALOGO).strip()
    id_layout = request.args.get("id", type=int)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_layout:
            layout = obter_layout_detalhe(cur, id_tenant, id_layout, modulo)
            if not layout:
                return jsonify(success=False, message="Layout não encontrado."), 404
            return jsonify(success=True, dados={"layout": layout, "campos": layout.get("campos") or []})
        dados = listar_layouts(cur, id_tenant, modulo)
        return jsonify(success=True, dados=dados)
    finally:
        conn.close()


@fn_importacao_bp.post("/fornecedor/importacao/layout/salvar")
@login_obrigatorio()
@exigir_permissao(codigo="fn_importacao.editar")
def importacao_layout_salvar():
    if (resp := _exigir_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    body.setdefault("modulo", MODULO_CATALOGO)
    id_tenant = int(session.get("id_tenant"))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        id_layout = salvar_layout_importacao(cur, id_tenant, body)
        conn.commit()
        return jsonify(success=True, message="Layout salvo.", id=id_layout)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@fn_importacao_bp.delete("/fornecedor/importacao/layout/<int:id_layout>")
@login_obrigatorio()
@exigir_permissao(codigo="fn_importacao.editar")
def importacao_layout_excluir(id_layout: int):
    if (resp := _exigir_escrita()) is not None:
        return resp
    modulo = (request.args.get("modulo") or MODULO_CATALOGO).strip()
    id_tenant = int(session.get("id_tenant"))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        excluir_layout_importacao(cur, id_tenant, id_layout, modulo)
        conn.commit()
        return jsonify(success=True, message="Layout excluído.")
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@fn_importacao_bp.post("/fornecedor/importacao/layout/padrao")
@login_obrigatorio()
@exigir_permissao(codigo="fn_importacao.editar")
def importacao_layout_padrao():
    if (resp := _exigir_escrita()) is not None:
        return resp
    body = request.get_json(silent=True) or {}
    id_layout = body.get("id")
    modulo = (body.get("modulo") or MODULO_CATALOGO).strip()
    if not id_layout:
        return jsonify(success=False, message="Informe o layout."), 400
    id_tenant = int(session.get("id_tenant"))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        definir_layout_padrao(cur, id_tenant, int(id_layout), modulo)
        conn.commit()
        return jsonify(success=True, message="Layout definido como padrão.")
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@fn_importacao_bp.post("/fornecedor/importacao/integracao/bling")
@login_obrigatorio()
@exigir_permissao(codigo="fn_importacao.editar")
def importacao_bling():
    if (resp := _exigir_escrita()) is not None:
        return resp

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    raw_ids = body.get("ids_categorias_bling")
    ids_categorias_bling: list[str] | None = None
    if isinstance(raw_ids, list):
        ids_categorias_bling = [str(c).strip() for c in raw_ids if str(c or "").strip()]
    incluir_sub = body.get("incluir_subcategorias", True)
    if isinstance(incluir_sub, str):
        incluir_sub = incluir_sub.lower() in ("1", "true", "sim", "yes")

    id_tenant = int(session.get("id_tenant"))
    id_usuario = session.get("id_usuario")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not _bling_conectado(cur, id_tenant):
            return jsonify(success=False, message="Conecte o Bling antes de sincronizar."), 400

        id_lote, numero = criar_lote(
            cur,
            id_tenant=id_tenant,
            modulo=MODULO_CATALOGO,
            origem=ORIGEM_INTEGRACAO,
            id_usuario=int(id_usuario) if id_usuario else None,
            provedor="bling",
            nome_lote=f"Bling — {contexto}",
            meta={"contexto": contexto},
        )
        conn.commit()

        resultado = importar_produtos(
            cur,
            id_tenant,
            contexto,
            ids_categorias_bling=ids_categorias_bling,
            incluir_subcategorias=bool(incluir_sub),
            id_importacao_lote=id_lote,
            id_usuario=int(id_usuario) if id_usuario else None,
        )
        conn.commit()

        status = resultado.get("status") or "ok"
        total_falhas = int(resultado.get("total_falhas") or 0)
        if status == "erro":
            msg = f"Importação {numero}: nenhum produto importado. {total_falhas} com falha."
        elif status == "aviso":
            msg = f"Importação {numero} concluída com {total_falhas} falha(s)."
        else:
            msg = f"Importação {numero} concluída com sucesso."

        lote = obter_lote(cur, id_tenant, id_lote)
        erros = listar_erros_lote(cur, id_tenant, id_lote)
        return jsonify(success=True, message=msg, dados=resultado, lote=lote, erros=erros, numero=numero)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        msg = str(e)
        if "transaction is aborted" in msg.lower():
            msg = (
                "Falha no banco durante a importação. "
                "Verifique se a migration 027_importacao_lote.sql foi aplicada."
            )
        return jsonify(success=False, message=msg), 500
    finally:
        conn.close()
