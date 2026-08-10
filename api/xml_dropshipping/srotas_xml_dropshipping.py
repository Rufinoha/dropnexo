# api/xml_dropshipping/srotas_xml_dropshipping.py — rotas da integração XML Dropshipping
from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from api.xml_dropshipping.xml_dropshipping import (
    ORIGEM_DEFAULTS,
    carregar_config,
    desconectar,
    listar_mapeamento_categorias,
    salvar_conexao,
    salvar_mapeamento_categorias,
    sincronizar_feed_tenant,
    xml_conectado,
)
from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import garantir_modulo_sessao

_log = logging.getLogger(__name__)
_MOD = Path(__file__).resolve().parent

xml_bp = Blueprint(
    "xml_dropshipping",
    __name__,
    root_path=str(_MOD),
    static_folder="static",
    static_url_path="/static/api/xml_dropshipping",
)


def init_app(app):
    app.register_blueprint(xml_bp)


def _pode_integracoes() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
    )


@xml_bp.get("/api/integracoes/xml-dropshipping/status")
@login_obrigatorio()
def api_status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cfg = carregar_config(cur, int(id_tenant))
        return jsonify(success=True, **cfg, defaults=ORIGEM_DEFAULTS)
    finally:
        conn.close()


@xml_bp.post("/api/integracoes/xml-dropshipping/conectar")
@login_obrigatorio()
def api_conectar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = salvar_conexao(cur, int(id_tenant), body)
        # Primeira sync em background leve (síncrona na v1 — feed ~1MB)
        sync = sincronizar_feed_tenant(cur, int(id_tenant), conn=conn)
        conn.commit()
        return jsonify(
            success=True,
            message=(
                f"Conectado. Feed com {res.get('produtos_no_feed')} produto(s). "
                f"{sync.get('mensagem')}"
            ),
            **res,
            sync=sync,
        )
    except Exception as e:
        conn.rollback()
        _log.exception("XML Dropshipping conectar")
        return jsonify(success=False, message=str(e)[:400]), 400
    finally:
        conn.close()


@xml_bp.post("/api/integracoes/xml-dropshipping/desconectar")
@login_obrigatorio()
def api_desconectar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        desconectar(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, message="XML Dropshipping desconectado.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@xml_bp.post("/api/integracoes/xml-dropshipping/salvar-origem")
@login_obrigatorio()
def api_salvar_origem():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not xml_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Conecte o feed antes."), 400
        from api.xml_dropshipping.xml_dropshipping import _garantir_acervo, carregar_config
        from global_utils import agora_utc

        cur.execute(
            """
            UPDATE tbl_integracao_xml_dropshipping SET
                origem_nome = %s, origem_documento = %s, origem_cep = %s,
                origem_logradouro = %s, origem_numero = %s, origem_complemento = %s,
                origem_bairro = %s, origem_cidade = %s, origem_uf = %s,
                origem_telefone = %s, atualizado_em = %s
            WHERE id_tenant = %s
            """,
            (
                (body.get("origem_nome") or ORIGEM_DEFAULTS["origem_nome"])[:160],
                (body.get("origem_documento") or "")[:20],
                (body.get("origem_cep") or "")[:12],
                (body.get("origem_logradouro") or "")[:160],
                (body.get("origem_numero") or "")[:30],
                (body.get("origem_complemento") or "")[:80],
                (body.get("origem_bairro") or "")[:80],
                (body.get("origem_cidade") or "Bauru")[:80],
                (body.get("origem_uf") or "SP")[:2],
                (body.get("origem_telefone") or ORIGEM_DEFAULTS["origem_telefone"])[:40],
                agora_utc(),
                int(id_tenant),
            ),
        )
        cfg = carregar_config(cur, int(id_tenant))
        _garantir_acervo(cur, int(id_tenant), cfg)
        conn.commit()
        return jsonify(success=True, message="Endereço de origem salvo.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@xml_bp.post("/api/integracoes/xml-dropshipping/sincronizar")
@login_obrigatorio()
def api_sincronizar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        res = sincronizar_feed_tenant(cur, int(id_tenant), conn=conn)
        conn.commit()
        return jsonify(success=True, **res)
    except Exception as e:
        conn.rollback()
        _log.exception("XML Dropshipping sync manual")
        try:
            cur = conn.cursor()
            from global_utils import agora_utc

            cur.execute(
                """
                UPDATE tbl_integracao_xml_dropshipping
                SET ultimo_erro = %s, atualizado_em = %s
                WHERE id_tenant = %s
                """,
                (str(e)[:500], agora_utc(), int(id_tenant)),
            )
            conn.commit()
        except Exception:
            pass
        return jsonify(success=False, message=str(e)[:400]), 400
    finally:
        conn.close()


@xml_bp.get("/api/integracoes/xml-dropshipping/categorias/mapeamento")
@login_obrigatorio()
def api_categorias_map_listar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        itens = listar_mapeamento_categorias(cur, int(id_tenant))
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@xml_bp.post("/api/integracoes/xml-dropshipping/categorias/mapeamento")
@login_obrigatorio()
def api_categorias_map_salvar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    body = request.get_json(silent=True) or {}
    itens = body.get("itens") or body.get("mapeamentos") or []
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        n = salvar_mapeamento_categorias(cur, int(id_tenant), itens)
        conn.commit()
        return jsonify(success=True, salvos=n, message=f"{n} mapeamento(s) salvos.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()
