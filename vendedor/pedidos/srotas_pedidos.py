from __future__ import annotations

from pathlib import Path
import time

from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for

from core.pedidos.servico import listar_meios_fornecedor
from api.pix_manual.pix_manual import iniciar_pix_manual, marcar_comprovante_enviado

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from core.pedidos.servico import (
    buscar_produtos_pedido,
    cancelar_pedido,
    combobox_produtos_pedido,
    confirmar_grupo,
    confirmar_pedido,
    excluir_anexo_pedido,
    listar_anexos_pedido,
    listar_fornecedores_pedido,
    listar_pedidos_vendedor,
    obter_contexto_pedido_vendedor,
    obter_grupo_pedido,
    obter_pedido,
    registrar_anexo_pedido,
    salvar_rascunho,
    taxas_fornecedores_vendedor,
)
from api.mercadopago.mercadopago import iniciar_pagamento, meios_pagamento_pedido, sincronizar_pagamento_pedido
from api.melhor_envio.melhor_envio import (
    contratar_etiqueta_pedido,
    cotar_frete_pedido,
    definir_modo_frete_manual,
    definir_modo_frete_melhor_envio,
    escolher_frete_pedido,
    salvar_frete_manual,
    status_melhor_envio_vendedor,
)
from sistema.plataforma.sessao import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent
_RAIZ = _MOD.parent.parent
MAX_BYTES_ANEXO = 5 * 1024 * 1024
_EXT_ANEXO = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".xml"}
vd_pedidos_bp = Blueprint(
    "vd_pedidos",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/pedidos",
)


def init_app(app):
    app.register_blueprint(vd_pedidos_bp)


def _id_vendedor() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _id_usuario() -> int | None:
    uid = session.get("id_usuario")
    return int(uid) if uid else None


@vd_pedidos_bp.get("/vendedor/pedidos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos():
    return render_template("frm_vd_pedidos.html", nav_ativo="vd_pedidos")


def _taxas_fornecedores_map(cur, id_vendedor: int) -> dict:
    return {str(k): v for k, v in taxas_fornecedores_vendedor(cur, id_vendedor).items()}


def _extensao_anexo(nome: str) -> str:
    import os

    ext = os.path.splitext(nome or "")[1].lower()
    return ext if ext in _EXT_ANEXO else ""


def _pasta_anexos_tenant(id_tenant: int) -> Path:
    pasta = _RAIZ / "upload" / f"tenant{id_tenant}" / "pedidos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


@vd_pedidos_bp.get("/vendedor/pedidos/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_dados():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    status = (request.args.get("status") or "").strip() or None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(
            success=True,
            pedidos=listar_pedidos_vendedor(cur, id_v, status),
            fornecedores=listar_fornecedores_pedido(cur, id_v),
            taxas_fornecedor=_taxas_fornecedores_map(cur, id_v),
        )
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/produtos/combobox")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_produtos_combobox():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(sucesso=False, mensagem="Sessão inválida."), 403
    termo = (request.args.get("filtro") or "").strip()
    try:
        limite = min(40, max(1, int(request.args.get("limitar") or 20)))
    except (TypeError, ValueError):
        limite = 20
    id_forn = request.args.get("id_fornecedor")
    id_forn_i = int(id_forn) if id_forn and str(id_forn).isdigit() else None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = combobox_produtos_pedido(cur, id_v, termo, limite=limite, id_fornecedor=id_forn_i)
        return jsonify(sucesso=True, dados=dados)
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/produtos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_produtos():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    termo = request.args.get("q") or ""
    id_forn = request.args.get("id_fornecedor")
    id_forn_i = int(id_forn) if id_forn else None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        return jsonify(
            success=True,
            produtos=buscar_produtos_pedido(cur, id_v, termo, id_forn_i),
        )
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_detalhe(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        ped = obter_pedido(cur, id_pedido, id_vendedor=id_v)
        if not ped:
            return jsonify(success=False, message="Pedido não encontrado."), 404
        return jsonify(success=True, pedido=ped)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Erro ao obter pedido %s", id_pedido)
        return jsonify(success=False, message="Erro ao carregar pedido."), 500
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>/contexto")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_contexto(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        grupo = obter_contexto_pedido_vendedor(cur, id_v, id_pedido)
        if not grupo:
            return jsonify(success=False, message="Pedido não encontrado."), 404
        for ped in grupo.get("pedidos") or []:
            ped["anexos"] = listar_anexos_pedido(cur, ped["id"], id_vendedor=id_v)
        return jsonify(success=True, grupo=grupo)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Erro ao obter contexto pedido %s", id_pedido)
        return jsonify(success=False, message="Erro ao carregar pedido."), 500
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/grupo/<int:id_grupo>")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_grupo(id_grupo: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        grupo = obter_grupo_pedido(cur, id_v, id_grupo)
        if not grupo:
            return jsonify(success=False, message="Grupo de pedido não encontrado."), 404
        for ped in grupo.get("pedidos") or []:
            ped["anexos"] = listar_anexos_pedido(cur, ped["id"], id_vendedor=id_v)
        return jsonify(success=True, grupo=grupo)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Erro ao obter grupo %s", id_grupo)
        return jsonify(success=False, message="Erro ao carregar pedido."), 500
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>/anexos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_anexos_lista(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        anexos = listar_anexos_pedido(cur, id_pedido, id_vendedor=id_v)
        return jsonify(success=True, anexos=anexos)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/anexos")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedido_anexos_upload(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    tipo = (request.form.get("tipo") or "").strip().lower()
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify(success=False, message="Selecione um arquivo."), 400
    ext = _extensao_anexo(arquivo.filename)
    if not ext:
        return jsonify(success=False, message="Use PDF, XML, PNG ou JPG."), 400
    stream = arquivo.stream
    stream.seek(0, 2)
    tamanho = stream.tell()
    stream.seek(0)
    if tamanho <= 0:
        return jsonify(success=False, message="Arquivo vazio."), 400
    if tamanho > MAX_BYTES_ANEXO:
        return jsonify(success=False, message="Arquivo deve ter no máximo 5 MB."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        ped = obter_pedido(cur, id_pedido, id_vendedor=id_v)
        if not ped:
            return jsonify(success=False, message="Pedido não encontrado."), 404
        pasta = _pasta_anexos_tenant(id_v)
        nome_safe = Path(arquivo.filename).name
        destino = pasta / f"{id_pedido}_{tipo}_{int(time.time())}{ext}"
        arquivo.save(str(destino))
        caminho_db = f"upload/tenant{id_v}/pedidos/{destino.name}"
        anexo = registrar_anexo_pedido(
            cur,
            id_v,
            id_pedido,
            tipo,
            nome_safe,
            caminho_db,
            tamanho,
            id_usuario=_id_usuario(),
        )
        if tipo == "comprovante_pix":
            marcar_comprovante_enviado(cur, id_pedido, id_vendedor=id_v)
        conn.commit()
        return jsonify(success=True, message="Anexo enviado.", anexo=anexo)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.delete("/vendedor/pedidos/anexos/<int:id_anexo>")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedido_anexo_excluir(id_anexo: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        info = excluir_anexo_pedido(cur, id_v, id_anexo)
        caminho = (info.get("caminho") or "").replace("\\", "/")
        if caminho and ".." not in caminho.split("/"):
            arquivo = _RAIZ.joinpath(*caminho.split("/"))
            if arquivo.is_file():
                try:
                    arquivo.unlink()
                except OSError:
                    pass
        conn.commit()
        return jsonify(success=True, message="Anexo removido.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/anexos/arquivo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_anexo_arquivo():
    import mimetypes
    import os

    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    caminho = (request.args.get("caminho") or "").strip().replace("\\", "/")
    if not caminho or ".." in caminho.split("/"):
        return jsonify(success=False, message="Caminho inválido."), 400
    prefixo = f"upload/tenant{id_v}/pedidos/"
    if not caminho.lower().startswith(prefixo.lower()):
        return jsonify(success=False, message="Arquivo não permitido."), 403
    arquivo = _RAIZ / caminho.replace("/", os.sep)
    if not arquivo.is_file():
        return jsonify(success=False, message="Arquivo não encontrado."), 404
    mime, _ = mimetypes.guess_type(str(arquivo))
    return send_file(arquivo, mimetype=mime or "application/octet-stream", max_age=3600)


@vd_pedidos_bp.post("/vendedor/pedidos/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_salvar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = salvar_rascunho(cur, id_v, body, id_usuario=_id_usuario())
        conn.commit()
        return jsonify(success=True, message="Rascunho salvo.", **res)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/frete/melhor-envio/status")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_frete_me_status():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        st = status_melhor_envio_vendedor(cur, id_v)
        return jsonify(success=True, **st)
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/frete/cotar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_frete_cotar(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = cotar_frete_pedido(cur, id_v, id_pedido)
        conn.commit()
        return jsonify(success=True, **res)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        return jsonify(success=False, message=str(e)), 502
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/frete/escolher")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_frete_escolher(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    try:
        service_id = int(body.get("service_id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Informe service_id da opção de frete."), 400
    opcao_raw = body.get("opcao") if isinstance(body.get("opcao"), dict) else None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = escolher_frete_pedido(cur, id_v, id_pedido, service_id, opcao_raw=opcao_raw)
        conn.commit()
        return jsonify(success=True, message="Frete selecionado.", **res)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        return jsonify(success=False, message=str(e)), 502
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/frete/modo")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_frete_modo(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    modo = (body.get("modo") or "").strip().lower()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if modo == "manual":
            res = definir_modo_frete_manual(
                cur,
                id_v,
                id_pedido,
                valor_frete=body.get("valor_frete"),
                codigo_rastreio=body.get("codigo_rastreio"),
                transportadora=body.get("transportadora"),
            )
        elif modo in ("melhor_envio", "me"):
            res = definir_modo_frete_melhor_envio(cur, id_v, id_pedido)
        else:
            return jsonify(success=False, message="Modo inválido. Use manual ou melhor_envio."), 400
        conn.commit()
        return jsonify(success=True, message="Modo de frete atualizado.", **res)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/frete/manual")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_frete_manual_salvar(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = salvar_frete_manual(
            cur,
            id_v,
            id_pedido,
            valor_frete=body.get("valor_frete"),
            codigo_rastreio=body.get("codigo_rastreio"),
            transportadora=body.get("transportadora"),
        )
        conn.commit()
        return jsonify(success=True, message="Frete manual salvo.", **res)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/frete/contratar-etiqueta")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_frete_contratar_etiqueta(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    forcar = bool(body.get("forcar"))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = contratar_etiqueta_pedido(
            cur,
            id_v,
            id_pedido,
            id_usuario=_id_usuario(),
            forcar=forcar,
        )
        conn.commit()
        if res.get("ignorado"):
            return jsonify(success=True, message=res.get("message") or "Nada a fazer.", **res)
        return jsonify(success=True, message=res.get("message") or "Etiqueta gerada.", **res)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 502
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/ml/etiqueta")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_ml_baixar_etiqueta(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from api.mercado_livre.pedidos_ml import baixar_etiqueta_ml

        res = baixar_etiqueta_ml(
            cur,
            id_v,
            id_pedido,
            _pasta_anexos_tenant(id_v),
            id_usuario=_id_usuario(),
        )
        conn.commit()
        return jsonify(success=True, **res)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/<int:id_pedido>/tiktok/etiqueta")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_tiktok_baixar_etiqueta(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from api.tiktok.pedidos_tiktok import baixar_etiqueta_tiktok

        res = baixar_etiqueta_tiktok(
            cur,
            id_v,
            id_pedido,
            _pasta_anexos_tenant(id_v),
            id_usuario=_id_usuario(),
        )
        conn.commit()
        return jsonify(success=True, **res)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/confirmar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_confirmar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if body.get("id_grupo"):
            ids = confirmar_grupo(cur, id_v, int(body["id_grupo"]), id_usuario=_id_usuario())
            msg = f"{len(ids)} pedido(s) confirmado(s). Estoque reservado. Aguardando pagamento."
        elif body.get("id_pedido"):
            confirmar_pedido(cur, id_v, int(body["id_pedido"]), id_usuario=_id_usuario())
            ids = [int(body["id_pedido"])]
            msg = "Pedido confirmado. Estoque reservado. Aguardando pagamento."
        else:
            return jsonify(success=False, message="Informe id_grupo ou id_pedido."), 400
        conn.commit()
        return jsonify(success=True, message=msg, pedidos_ids=ids)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        conn.rollback()
        import logging
        logging.getLogger(__name__).exception("Erro ao confirmar pedido")
        return jsonify(success=False, message="Erro interno ao confirmar o pedido."), 500
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/cancelar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_cancelar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    try:
        id_pedido = int(body.get("id_pedido"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Pedido inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cancelar_pedido(
            cur,
            id_pedido,
            id_vendedor=id_v,
            id_usuario=_id_usuario(),
            motivo=body.get("motivo"),
        )
        conn.commit()
        return jsonify(success=True, message="Pedido cancelado.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/meios-pagamento/preview")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_meios_preview():
    """Meios de pagamento por fornecedor (preview antes de confirmar o pedido)."""
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    raw = (request.args.get("fornecedores") or "").strip()
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    if not ids:
        return jsonify(success=True, fornecedores=[])

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        mp_icone = url_for("mercadopago.static", filename="imge/icone_mercadopago.png")
        out = []
        for id_f in ids:
            cur.execute(
                "SELECT COALESCE(NULLIF(TRIM(nome_fantasia), ''), nome) FROM tbl_tenant WHERE id = %s",
                (id_f,),
            )
            row = cur.fetchone()
            nome = (row[0] if row else "") or f"Fornecedor #{id_f}"
            integracoes = listar_meios_fornecedor(cur, id_f, icone_mp=mp_icone)
            out.append(
                {
                    "id_fornecedor": id_f,
                    "fornecedor_nome": nome,
                    "integracoes": integracoes,
                }
            )
        return jsonify(success=True, fornecedores=out)
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>/meios-pagamento")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_meios_pagamento(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = meios_pagamento_pedido(cur, id_v, id_pedido)
        return jsonify(success=True, **dados)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@vd_pedidos_bp.post("/vendedor/pedidos/pagar")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.editar")
def pedidos_pagar():
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    try:
        id_pedido = int(body.get("id_pedido"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Pedido inválido."), 400
    meio = (body.get("meio") or "").strip().lower()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if meio == "pix_manual":
            result = iniciar_pix_manual(cur, id_v, id_pedido)
            msg = "PIX manual gerado."
        else:
            result = iniciar_pagamento(
                cur,
                id_v,
                id_pedido,
                meio,
                email_sessao=session.get("email"),
            )
            msg = "Pagamento iniciado."
        conn.commit()
        return jsonify(success=True, message=msg, **result)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        return jsonify(success=False, message=str(e)), 502
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/<int:id_pedido>/pagamento/status")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedido_pagamento_status(id_pedido: int):
    id_v = _id_vendedor()
    if not id_v:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        result = sincronizar_pagamento_pedido(cur, id_v, id_pedido)
        conn.commit()
        return jsonify(success=True, **result)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except RuntimeError as e:
        return jsonify(success=False, message=str(e)), 502
    finally:
        conn.close()


@vd_pedidos_bp.get("/vendedor/pedidos/pagamento/retorno")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_pedidos.ver")
def pedidos_pagamento_retorno():
    from flask import redirect, url_for

    id_v = _id_vendedor()
    st = (request.args.get("status") or "").strip().lower()
    try:
        id_pedido = int(request.args.get("id_pedido") or 0)
    except (TypeError, ValueError):
        id_pedido = 0

    if id_v and id_pedido:
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            sincronizar_pagamento_pedido(cur, id_v, id_pedido)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    q = f"pagamento={st or 'retorno'}"
    if id_pedido:
        q += f"&id_pedido={id_pedido}"
    return redirect(f"/vendedor/pedidos?{q}")
