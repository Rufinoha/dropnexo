# armazem/fornecedores — cadastro local de fornecedores do armazém
from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for

from global_utils import Var_ConectarBanco, agora_utc, exigir_modulo, exigir_permissao, login_obrigatorio
from sistema.plataforma.sessao import MODULO_ARMAZEM

_MOD = Path(__file__).resolve().parent
_RAIZ = _MOD.parent.parent

az_fornecedores_bp = Blueprint(
    "az_fornecedores",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/armazem/fornecedores",
)

_EXT_LOGO = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_LOGO_BYTES = 2 * 1024 * 1024


def init_app(app):
    app.register_blueprint(az_fornecedores_bp)


def _id_tenant() -> int | None:
    tid = session.get("id_tenant")
    return int(tid) if tid else None


def _exigir_armazem_tenant():
    if session.get("tenant_tipo_negocio") in ("armazem",) or session.get("eh_desenvolvedor"):
        return None
    return jsonify(success=False, message="Conta não é armazém."), 403


def _so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def garantir_tabela_fornecedor_armazem(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_armazem_fornecedor (
            id BIGSERIAL PRIMARY KEY,
            id_tenant_armazem BIGINT NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
            nome VARCHAR(200) NOT NULL,
            nome_fantasia VARCHAR(200),
            documento VARCHAR(20),
            email VARCHAR(200),
            telefone VARCHAR(30),
            whatsapp VARCHAR(30),
            observacoes TEXT,
            logo_caminho VARCHAR(500),
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        ALTER TABLE tbl_armazem_fornecedor
          ADD COLUMN IF NOT EXISTS logo_caminho VARCHAR(500)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_armazem_fornecedor_tenant
          ON tbl_armazem_fornecedor (id_tenant_armazem)
        """
    )


def _logo_url(fid: int, caminho: str | None) -> str:
    if not caminho:
        return ""
    return url_for("az_fornecedores.logo_arquivo", id_fornecedor=fid)


def _row_dict(row) -> dict:
    fid = row[0]
    caminho = row[9] if len(row) > 9 else None
    return {
        "id": fid,
        "nome": row[1] or "",
        "nome_fantasia": row[2] or "",
        "documento": row[3] or "",
        "email": row[4] or "",
        "telefone": row[5] or "",
        "whatsapp": row[6] or "",
        "observacoes": row[7] or "",
        "ativo": bool(row[8]),
        "logo_caminho": caminho or "",
        "logo_url": _logo_url(fid, caminho),
    }


_COLS = """
    id, nome, nome_fantasia, documento, email, telefone, whatsapp, observacoes, ativo, logo_caminho
"""


def _pasta_logo(id_tenant: int, id_fornecedor: int) -> Path:
    d = _RAIZ / "upload" / f"tenant{id_tenant}" / "armazem_fornecedor" / str(id_fornecedor)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _caminho_db_logo(id_tenant: int, id_fornecedor: int, nome_arquivo: str) -> str:
    return f"upload/tenant{id_tenant}/armazem_fornecedor/{id_fornecedor}/{nome_arquivo}"


def _caminho_abs(caminho_db: str | None) -> Path | None:
    if not caminho_db:
        return None
    rel = caminho_db.replace("\\", "/").strip().lstrip("/")
    if ".." in rel.split("/"):
        return None
    if not rel.lower().startswith("upload/tenant"):
        return None
    return _RAIZ / rel.replace("/", os.sep)


def _nome_seguro(nome: str) -> str | None:
    base = Path(nome or "").name.strip()
    if not base or base in (".", ".."):
        return None
    seguro = "".join(c for c in base if c.isalnum() or c in "._-")
    if not seguro or Path(seguro).suffix.lower() not in _EXT_LOGO:
        return None
    return seguro


@az_fornecedores_bp.get("/armazem/fornecedores")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.ver")
def pagina():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    return render_template("frm_az_fornecedores.html", nav_ativo="az_fornecedores")


@az_fornecedores_bp.get("/armazem/fornecedores/dados")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.ver")
def dados():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    busca = (request.args.get("busca") or "").strip()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        conn.commit()
        params: list = [id_tenant]
        where = "id_tenant_armazem = %s AND ativo = TRUE"
        if busca:
            where += " AND (nome ILIKE %s OR nome_fantasia ILIKE %s OR documento ILIKE %s)"
            like = f"%{busca}%"
            params.extend([like, like, like])
        cur.execute(
            f"""
            SELECT {_COLS}
            FROM tbl_armazem_fornecedor
            WHERE {where}
            ORDER BY COALESCE(NULLIF(nome_fantasia, ''), nome)
            """,
            params,
        )
        return jsonify(success=True, dados=[_row_dict(r) for r in cur.fetchall()])
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify(success=False, message=f"Erro ao listar fornecedores: {e}"), 500
    finally:
        conn.close()


@az_fornecedores_bp.post("/armazem/fornecedores/apoio")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.editar")
def apoio():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    fid = body.get("id")
    if not fid:
        return jsonify(success=True, dados=None)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        cur.execute(
            f"""
            SELECT {_COLS}
            FROM tbl_armazem_fornecedor
            WHERE id = %s AND id_tenant_armazem = %s
            """,
            (int(fid), id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        return jsonify(success=True, dados=_row_dict(row))
    finally:
        conn.close()


@az_fornecedores_bp.post("/armazem/fornecedores/salvar")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.editar")
def salvar():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if len(nome) < 2:
        return jsonify(success=False, message="Informe o nome do fornecedor."), 400
    fantasia = (body.get("nome_fantasia") or "").strip() or None
    documento = _so_digitos(body.get("documento") or "") or None
    email = (body.get("email") or "").strip() or None
    telefone = _so_digitos(body.get("telefone") or "") or None
    whatsapp = _so_digitos(body.get("whatsapp") or "") or None
    obs = (body.get("observacoes") or "").strip() or None
    ativo = bool(body.get("ativo", True))
    agora = agora_utc()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        fid = body.get("id")
        if fid:
            cur.execute(
                """
                UPDATE tbl_armazem_fornecedor SET
                    nome=%s, nome_fantasia=%s, documento=%s, email=%s,
                    telefone=%s, whatsapp=%s, observacoes=%s, ativo=%s, atualizado_em=%s
                WHERE id=%s AND id_tenant_armazem=%s
                RETURNING id, logo_caminho
                """,
                (
                    nome,
                    fantasia,
                    documento,
                    email,
                    telefone,
                    whatsapp,
                    obs,
                    ativo,
                    agora,
                    int(fid),
                    id_tenant,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_armazem_fornecedor (
                    id_tenant_armazem, nome, nome_fantasia, documento, email,
                    telefone, whatsapp, observacoes, ativo, atualizado_em
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, logo_caminho
                """,
                (
                    id_tenant,
                    nome,
                    fantasia,
                    documento,
                    email,
                    telefone,
                    whatsapp,
                    obs,
                    ativo,
                    agora,
                ),
            )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        conn.commit()
        return jsonify(
            success=True,
            id=row[0],
            logo_url=_logo_url(int(row[0]), row[1]),
            message="Fornecedor salvo.",
        )
    finally:
        conn.close()


@az_fornecedores_bp.post("/armazem/fornecedores/<int:id_fornecedor>/logo")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.editar")
def logo_upload(id_fornecedor: int):
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    if not id_tenant:
        return jsonify(success=False, message="Sessão inválida."), 403
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify(success=False, message="Selecione uma imagem."), 400
    arquivo.seek(0, os.SEEK_END)
    tamanho = arquivo.tell()
    arquivo.seek(0)
    if tamanho <= 0:
        return jsonify(success=False, message="Arquivo vazio."), 400
    if tamanho > _MAX_LOGO_BYTES:
        return jsonify(success=False, message="O logotipo deve ter no máximo 2 MB."), 400
    nome_arquivo = _nome_seguro(arquivo.filename)
    if not nome_arquivo:
        return jsonify(success=False, message="Use PNG, JPG ou WEBP."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        cur.execute(
            """
            SELECT logo_caminho FROM tbl_armazem_fornecedor
            WHERE id = %s AND id_tenant_armazem = %s
            """,
            (id_fornecedor, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        antigo = _caminho_abs(row[0])
        if antigo and antigo.is_file():
            try:
                antigo.unlink()
            except OSError:
                pass
        pasta = _pasta_logo(id_tenant, id_fornecedor)
        for f in pasta.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    pass
        destino = pasta / nome_arquivo
        arquivo.save(str(destino))
        caminho_db = _caminho_db_logo(id_tenant, id_fornecedor, nome_arquivo)
        cur.execute(
            """
            UPDATE tbl_armazem_fornecedor
            SET logo_caminho = %s, atualizado_em = %s
            WHERE id = %s AND id_tenant_armazem = %s
            """,
            (caminho_db, agora_utc(), id_fornecedor, id_tenant),
        )
        conn.commit()
        ts = int(agora_utc().timestamp())
        return jsonify(
            success=True,
            message="Logotipo atualizado.",
            logo_url=_logo_url(id_fornecedor, caminho_db) + f"?t={ts}",
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@az_fornecedores_bp.get("/armazem/fornecedores/<int:id_fornecedor>/logo")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.ver")
def logo_arquivo(id_fornecedor: int):
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT logo_caminho FROM tbl_armazem_fornecedor
            WHERE id = %s AND id_tenant_armazem = %s AND ativo = TRUE
            """,
            (id_fornecedor, id_tenant),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return jsonify(success=False, message="Sem logotipo."), 404
        caminho = _caminho_abs(row[0])
        if not caminho or not caminho.is_file():
            return jsonify(success=False, message="Arquivo não encontrado."), 404
        mime, _ = mimetypes.guess_type(str(caminho))
        return send_file(caminho, mimetype=mime or "image/png", max_age=3600)
    finally:
        conn.close()


@az_fornecedores_bp.post("/armazem/fornecedores/excluir")
@login_obrigatorio()
@exigir_modulo(MODULO_ARMAZEM)
@exigir_permissao(codigo="az_fornecedores.editar")
def excluir():
    if (r := _exigir_armazem_tenant()) is not None:
        return r
    id_tenant = _id_tenant()
    body = request.get_json(silent=True) or {}
    try:
        fid = int(body.get("id"))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Fornecedor inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabela_fornecedor_armazem(cur)
        cur.execute(
            """
            UPDATE tbl_armazem_fornecedor
            SET ativo = FALSE, atualizado_em = %s
            WHERE id = %s AND id_tenant_armazem = %s
            """,
            (agora_utc(), fid, id_tenant),
        )
        if cur.rowcount == 0:
            return jsonify(success=False, message="Fornecedor não encontrado."), 404
        conn.commit()
        return jsonify(success=True, message="Fornecedor removido.")
    finally:
        conn.close()
