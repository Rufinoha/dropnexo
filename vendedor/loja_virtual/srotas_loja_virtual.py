from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from global_utils import Var_ConectarBanco, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_VENDEDOR

_MOD = Path(__file__).resolve().parent

vd_loja_virtual_bp = Blueprint(
    "vd_loja_virtual",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/vendedor/loja_virtual",
)

PRIORIDADES_VALIDAS = {
    "dominio": "Domínio próprio",
    "vitrine": "Vitrine e categorias",
    "checkout": "Carrinho e checkout",
    "marca": "Identidade da marca",
    "pedidos": "Pedidos integrados",
    "mobile": "Loja no celular",
}

_TABELA_OK: bool | None = None


def init_app(app):
    app.register_blueprint(vd_loja_virtual_bp)


def _exigir_vendedor_tenant():
    if session.get("tenant_tipo_negocio") in ("vendedor", "hibrido") or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é vendedor."), 403


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _id_usuario() -> int | None:
    uid = session.get("id_usuario")
    return int(uid) if uid else None


def _garantir_tabela(cur) -> None:
    global _TABELA_OK
    if _TABELA_OK is True:
        return
    try:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema IN (current_schema(), 'public')
              AND table_name = 'tbl_loja_virtual_interesse'
            LIMIT 1
            """
        )
        if cur.fetchone():
            _TABELA_OK = True
            return
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_loja_virtual_interesse (
              id SERIAL PRIMARY KEY,
              id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
              id_usuario INTEGER REFERENCES tbl_usuario(id) ON DELETE SET NULL,
              prioridades JSONB NOT NULL DEFAULT '[]'::jsonb,
              criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT uq_loja_virtual_interesse_tenant UNIQUE (id_tenant)
            )
            """
        )
        _TABELA_OK = True
    except Exception as e:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        raise RuntimeError(
            "Tabela de interesse da Loja Virtual indisponível. "
            "Aplique o SQL 097_loja_virtual_interesse.sql no banco."
        ) from e


def _parse_prioridades(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        key = str(item or "").strip().lower()
        if key in PRIORIDADES_VALIDAS and key not in out:
            out.append(key)
        if len(out) >= 3:
            break
    return out


def _status_interesse(cur, id_tenant: int) -> dict:
    _garantir_tabela(cur)
    cur.execute("SELECT COUNT(*)::int FROM tbl_loja_virtual_interesse")
    total = int(cur.fetchone()[0] or 0)
    cur.execute(
        """
        SELECT prioridades, criado_em
        FROM tbl_loja_virtual_interesse
        WHERE id_tenant = %s
        LIMIT 1
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {"inscrito": False, "prioridades": [], "total_interessados": total, "criado_em": ""}
    prios = row[0]
    if isinstance(prios, str):
        try:
            prios = json.loads(prios)
        except Exception:
            prios = []
    if not isinstance(prios, list):
        prios = []
    return {
        "inscrito": True,
        "prioridades": [p for p in prios if p in PRIORIDADES_VALIDAS],
        "prioridades_labels": [PRIORIDADES_VALIDAS[p] for p in prios if p in PRIORIDADES_VALIDAS],
        "total_interessados": total,
        "criado_em": row[1].isoformat() if row[1] else "",
    }


@vd_loja_virtual_bp.get("/vendedor/loja-virtual")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_loja_virtual.ver")
def pagina():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    return render_template("frm_vd_loja_virtual.html", nav_ativo="vd_loja_virtual")


@vd_loja_virtual_bp.get("/vendedor/loja-virtual/interesse")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_loja_virtual.ver")
def interesse_status():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        st = _status_interesse(cur, id_tenant)
        conn.commit()
        return jsonify(success=True, **st, opcoes=PRIORIDADES_VALIDAS)
    except RuntimeError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=f"Falha ao carregar interesse: {e}"), 500
    finally:
        conn.close()


@vd_loja_virtual_bp.post("/vendedor/loja-virtual/interesse")
@login_obrigatorio()
@exigir_modulo(MODULO_VENDEDOR)
@exigir_permissao(codigo="vd_loja_virtual.ver")
def interesse_salvar():
    if (r := _exigir_vendedor_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    prioridades = _parse_prioridades(body.get("prioridades"))
    if not prioridades:
        return jsonify(
            success=False,
            message="Escolha pelo menos 1 prioridade (até 3) para entrar na lista.",
        ), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        _garantir_tabela(cur)
        cur.execute(
            """
            INSERT INTO tbl_loja_virtual_interesse (id_tenant, id_usuario, prioridades, atualizado_em)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (id_tenant) DO UPDATE SET
              id_usuario = EXCLUDED.id_usuario,
              prioridades = EXCLUDED.prioridades,
              atualizado_em = NOW()
            """,
            (id_tenant, _id_usuario(), json.dumps(prioridades)),
        )
        st = _status_interesse(cur, id_tenant)
        conn.commit()
        return jsonify(
            success=True,
            message="Você entrou na lista de prioridade da Loja Virtual.",
            **st,
        )
    except RuntimeError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=f"Falha ao salvar interesse: {e}"), 500
    finally:
        conn.close()
