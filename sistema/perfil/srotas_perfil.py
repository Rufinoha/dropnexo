from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path

import bcrypt
import requests
from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for

from global_utils import (
    PERFIL_LABEL,
    Var_ConectarBanco,
    agora_utc,
    login_obrigatorio,
    usuario_tem_permissao,
    valida_email,
    validar_politica_senha,
)


_MOD_DIR = Path(__file__).resolve().parent
_RAIZ_PROJETO = _MOD_DIR.parents[1]

perfil_bp = Blueprint(
    "perfil",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/sistema/perfil",
)


def init_app(app):
    app.register_blueprint(perfil_bp)


# Foto de perfil: static/imge/imguser/{id}/ (1 arquivo) — padrão userpadrao.png

EXTENSOES_FOTO = frozenset({".png", ".jpg", ".jpeg", ".webp"})
MIME_POR_EXT_FOTO = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
MAX_BYTES_FOTO = 2 * 1024 * 1024
FOTO_PADRAO_STATIC = "imge/imguser/userpadrao.png"


def _raiz_projeto() -> Path:
    return _RAIZ_PROJETO


def _dir_imguser() -> Path:
    d = _raiz_projeto() / "static" / "imge" / "imguser"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pasta_foto_usuario(id_usuario: int) -> Path:
    return _dir_imguser() / str(id_usuario)


def _caminho_foto_padrao_abs() -> Path:
    return _raiz_projeto() / "static" / FOTO_PADRAO_STATIC.replace("/", os.sep)


def _extensao_foto_permitida(nome: str) -> str | None:
    ext = Path(nome or "").suffix.lower()
    if ext in EXTENSOES_FOTO:
        return ext
    return None


def _nome_arquivo_seguro(nome_original: str) -> str | None:
    base = Path(nome_original or "").name.strip()
    if not base or base in (".", ".."):
        return None
    seguro = "".join(c for c in base if c.isalnum() or c in "._-")
    if not seguro or seguro in (".", ".."):
        return None
    if not _extensao_foto_permitida(seguro):
        return None
    return seguro


def _caminho_db_foto(id_usuario: int, nome_arquivo: str) -> str:
    """Caminho gravado em tbl_usuario.foto_caminho (relativo à raiz do projeto)."""
    return f"static{os.sep}imge{os.sep}imguser{os.sep}{id_usuario}{os.sep}{nome_arquivo}"


def _caminho_absoluto_de_db(caminho_db: str) -> Path:
    rel = (caminho_db or "").replace("\\", "/").strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("Caminho inválido.")
    if not rel.lower().startswith("static/imge/imguser/"):
        raise ValueError("Caminho fora da pasta permitida.")
    return _raiz_projeto() / rel.replace("/", os.sep)


def _url_publica_foto(caminho_db: str | None) -> str:
    if not caminho_db:
        return url_for("static", filename=FOTO_PADRAO_STATIC, _external=False)
    rel = caminho_db.replace("\\", "/").strip()
    if rel.lower().startswith("static/"):
        rel = rel[7:]
    return url_for("static", filename=rel, _external=False)


def _validar_arquivo_foto(nome: str, tamanho: int) -> str | None:
    if tamanho <= 0:
        return "Arquivo vazio."
    if tamanho > MAX_BYTES_FOTO:
        return "A foto deve ter no máximo 2 MB."
    if not _extensao_foto_permitida(nome):
        return "Use PNG, JPG ou WEBP."
    if not _nome_arquivo_seguro(nome):
        return "Nome de arquivo inválido."
    return None


def _limpar_pasta_foto_usuario(id_usuario: int) -> None:
    pasta = _pasta_foto_usuario(id_usuario)
    if not pasta.is_dir():
        return
    for f in pasta.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass


def _remover_foto_customizada_disco(caminho_db: str | None) -> None:
    if not caminho_db:
        return
    try:
        p = _caminho_absoluto_de_db(caminho_db)
        if p.is_file():
            p.unlink()
    except (ValueError, OSError):
        pass
    try:
        id_part = Path(caminho_db.replace("\\", "/")).parts
        if len(id_part) >= 2 and id_part[-2].isdigit():
            _limpar_pasta_foto_usuario(int(id_part[-2]))
    except (ValueError, OSError):
        pass


def _salvar_foto_usuario(
    conn,
    *,
    id_usuario: int,
    arquivo_stream,
    nome_original: str,
    tamanho: int,
) -> tuple[str | None, str | None]:
    err = _validar_arquivo_foto(nome_original, tamanho)
    if err:
        return None, err

    nome_arquivo = _nome_arquivo_seguro(nome_original)
    if not nome_arquivo:
        return None, "Nome de arquivo inválido."

    cur = conn.cursor()
    cur.execute("SELECT foto_caminho FROM tbl_usuario WHERE id = %s", (id_usuario,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return None, "Usuário não encontrado."

    antigo = row[0]
    if antigo:
        _remover_foto_customizada_disco(antigo)
    _limpar_pasta_foto_usuario(id_usuario)

    pasta = _pasta_foto_usuario(id_usuario)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / nome_arquivo
    arquivo_stream.save(str(destino))

    caminho_db = _caminho_db_foto(id_usuario, nome_arquivo)
    cur.execute(
        "UPDATE tbl_usuario SET foto_caminho = %s WHERE id = %s",
        (caminho_db, id_usuario),
    )
    cur.close()

    return caminho_db, None


def _mime_foto(caminho: str) -> str:
    ext = Path(caminho or "").suffix.lower()
    return MIME_POR_EXT_FOTO.get(ext, "application/octet-stream")

def _so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def _valida_uf(uf: str) -> bool:
    ufs = {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
        "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
        "SP", "SE", "TO",
    }
    return (uf or "").strip().upper() in ufs


def _abas_perfil_ctx() -> dict:
    eh_dev = bool(session.get("eh_desenvolvedor"))
    perfil = (session.get("perfil_codigo") or "").lower()
    return {
        "perfil": True,
        "empresa": eh_dev or perfil in ("dono", "admin"),
        "pagamento": eh_dev or perfil in ("dono", "admin", "financeiro"),
        "faturas": eh_dev or perfil in ("dono", "admin", "financeiro"),
        "cancelar": eh_dev or perfil == "dono",
    }


def _exigir_aba(perfil_ok: bool):
    if not perfil_ok:
        return jsonify(success=False, message="Sem permissão para esta aba."), 403
    return None


def _pasta_logo_tenant(id_tenant: int) -> Path:
    d = _raiz_projeto() / "upload" / f"tenant{id_tenant}" / "logotipo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _caminho_db_logo(id_tenant: int, nome_arquivo: str) -> str:
    return f"upload{os.sep}tenant{id_tenant}{os.sep}logotipo{os.sep}{nome_arquivo}"


def _caminho_abs_logo(caminho_db: str | None) -> Path | None:
    if not caminho_db:
        return None
    rel = caminho_db.replace("\\", "/").strip().lstrip("/")
    if ".." in rel.split("/"):
        return None
    if not rel.lower().startswith(("upload/tenant", "static/imge/imgtenant")):
        return None
    return _raiz_projeto() / rel.replace("/", os.sep)


def _url_logo_tenant(caminho_db: str | None) -> str:
    if not caminho_db:
        return ""
    return url_for("perfil.api_minha_empresa_logo_arquivo", _external=False)


def _tenant_row_para_dict(row, inscricoes: list) -> dict:
    return {
        "tipo_pessoa": row[0],
        "documento": row[1],
        "nome_completo": row[2],
        "nome": row[3],
        "razao_social": row[4] or "",
        "nome_fantasia": row[5] or "",
        "inscricao_estadual": row[6] or "",
        "inscricao_municipal": row[7] or "",
        "ie_isento": bool(row[8]),
        "cnae_principal": row[9] or "",
        "atividade_principal": row[10] or "",
        "codigo_regime_tributario": row[11] or "",
        "tamanho_empresa": row[12] or "",
        "segmento_comercio": bool(row[13]),
        "segmento_ecommerce": bool(row[14]),
        "segmento_industria": bool(row[15]),
        "segmento_servicos": bool(row[16]),
        "faturamento_ultimo_ano": row[17] or "",
        "quantidade_funcionarios": row[18] or "",
        "cep": row[19] or "",
        "logradouro": row[20] or "",
        "numero": row[21] or "",
        "complemento": row[22] or "",
        "bairro": row[23] or "",
        "cidade": row[24] or "",
        "uf": row[25] or "",
        "pessoas_contato": row[26] or "",
        "telefone_comercial": row[27] or "",
        "celular_comercial": row[28] or "",
        "email_comercial": row[29] or "",
        "site": row[30] or "",
        "logo_url": _url_logo_tenant(row[31]),
        "plano": row[32],
        "inscricoes_st": inscricoes,
    }


def _carregar_tenant_empresa(cur, id_tenant: int) -> dict | None:
    cur.execute(
        """
        SELECT tipo_pessoa, documento, nome_completo, nome,
               razao_social, nome_fantasia, inscricao_estadual, inscricao_municipal,
               ie_isento, cnae_principal, atividade_principal, codigo_regime_tributario,
               tamanho_empresa, segmento_comercio, segmento_ecommerce, segmento_industria,
               segmento_servicos, faturamento_ultimo_ano, quantidade_funcionarios,
               cep, logradouro, numero, complemento, bairro, cidade, uf,
               pessoas_contato, telefone_comercial, celular_comercial, email_comercial,
               site, logo_caminho, plano
        FROM tbl_tenant WHERE id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return None
    cur.execute(
        "SELECT uf, inscricao_estadual FROM tbl_tenant_inscricao_st WHERE id_tenant = %s ORDER BY id",
        (id_tenant,),
    )
    inscricoes = [{"uf": r[0], "inscricao_estadual": r[1]} for r in cur.fetchall()]
    return _tenant_row_para_dict(row, inscricoes)


def _garantir_cobranca_tenant(cur, id_tenant: int):
    cur.execute("SELECT 1 FROM tbl_tenant_cobranca WHERE id_tenant = %s", (id_tenant,))
    if cur.fetchone():
        return
    cur.execute("SELECT plano, email_comercial FROM tbl_tenant WHERE id = %s", (id_tenant,))
    row = cur.fetchone()
    plano = row[0] if row else "starter"
    email = row[1] if row else None
    cur.execute(
        """
        INSERT INTO tbl_tenant_cobranca (id_tenant, plano_slug, email_cobranca, inicio_cobranca)
        VALUES (%s, %s, %s, CURRENT_DATE)
        """,
        (id_tenant, plano, email),
    )


@perfil_bp.get("/meu-perfil")
@login_obrigatorio
def meu_perfil():
    abas = _abas_perfil_ctx()
    aba = (request.args.get("aba") or "perfil").strip().lower()
    if aba not in abas or not abas.get(aba):
        aba = "perfil"
    return render_template("frm_meu_perfil.html", abas=abas, aba_inicial=aba)


@perfil_bp.get("/api/meu-perfil")
@login_obrigatorio
def api_meu_perfil_dados():
    id_usuario = session["id_usuario"]
    id_tenant = session["id_tenant"]

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id, u.nome, u.email, u.whatsapp, u.foto_caminho,
                   pf.codigo, pf.nome, ut.ultimo_acesso_em,
                   t.nome, t.plano, u.eh_desenvolvedor
            FROM tbl_usuario u
            INNER JOIN tbl_usuario_tenant ut ON ut.id_usuario = u.id
            INNER JOIN tbl_perfil pf ON pf.id = ut.id_perfil
            INNER JOIN tbl_tenant t ON t.id = ut.id_tenant
            WHERE u.id = %s AND ut.id_tenant = %s AND ut.ativo = TRUE
            LIMIT 1
            """,
            (id_usuario, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Perfil não encontrado."), 404

        tem_foto_custom = bool(row[4])
        foto_url = _url_publica_foto(row[4] if tem_foto_custom else None)

        perfil_codigo = (row[5] or "visualizador").lower()
        return jsonify(
            success=True,
            perfil={
                "id_usuario": row[0],
                "nome": row[1],
                "email": row[2],
                "whatsapp": row[3] or "",
                "foto_url": foto_url,
                "foto_url_padrao": url_for("static", filename=FOTO_PADRAO_STATIC, _external=False),
                "tem_foto": tem_foto_custom,
                "papel": perfil_codigo,
                "papel_label": PERFIL_LABEL.get(perfil_codigo, row[6] or perfil_codigo),
                "perfil_codigo": perfil_codigo,
                "perfil_nome": row[6],
                "eh_desenvolvedor": bool(row[10]),
                "ultimo_acesso_em": row[7].isoformat() if row[7] else None,
                "tenant_nome": row[8],
                "tenant_plano": row[9],
            },
            politica_senha={
                "min8": "Mínimo de 8 caracteres",
                "maiuscula": "1 letra maiúscula",
                "minuscula": "1 letra minúscula",
                "numero": "1 número",
                "especial": "1 caractere especial",
            },
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@perfil_bp.put("/api/meu-perfil")
@login_obrigatorio
def api_meu_perfil_salvar():
    id_usuario = session["id_usuario"]
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    whatsapp = (dados.get("whatsapp") or "").strip() or None

    if len(nome) < 2:
        return jsonify(success=False, message="Informe o nome."), 400

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_usuario SET nome = %s, whatsapp = %s
            WHERE id = %s
            """,
            (nome, whatsapp, id_usuario),
        )
        conn.commit()
        session["nome"] = nome
        return jsonify(success=True, message="Dados salvos.", nome=nome)
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify(success=False, message=str(e)), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@perfil_bp.post("/api/meu-perfil/trocar-senha")
@login_obrigatorio
def api_meu_perfil_trocar_senha():
    id_usuario = session["id_usuario"]
    dados = request.get_json(silent=True) or {}
    senha_atual = dados.get("senha_atual") or ""
    senha_nova = dados.get("senha_nova") or ""
    confirmar = dados.get("confirmar") or ""

    if not senha_atual:
        return jsonify(success=False, message="Informe a senha atual."), 400

    ok_senha, msg_senha = validar_politica_senha(senha_nova, confirmar)
    if not ok_senha:
        return jsonify(success=False, message=msg_senha), 400

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute("SELECT senha_hash FROM tbl_usuario WHERE id = %s", (id_usuario,))
        row = cur.fetchone()
        if not row or not row[0]:
            return jsonify(success=False, message="Conta sem senha definida."), 400

        try:
            ok_atual = bcrypt.checkpw(senha_atual.encode("utf-8"), row[0].encode("utf-8"))
        except Exception:
            ok_atual = False
        if not ok_atual:
            return jsonify(success=False, message="Senha atual incorreta."), 400

        senha_hash = bcrypt.hashpw(senha_nova.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
        cur.execute(
            "UPDATE tbl_usuario SET senha_hash = %s WHERE id = %s",
            (senha_hash, id_usuario),
        )
        conn.commit()
        return jsonify(success=True, message="Senha alterada com sucesso.")
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify(success=False, message=str(e)), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@perfil_bp.post("/api/meu-perfil/foto")
@login_obrigatorio
def api_meu_perfil_foto_upload():
    id_usuario = session["id_usuario"]
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify(success=False, message="Selecione uma imagem."), 400

    conn = None
    try:
        arquivo.seek(0, os.SEEK_END)
        tamanho = arquivo.tell()
        arquivo.seek(0)

        conn = Var_ConectarBanco()
        rel, err = _salvar_foto_usuario(
            conn,
            id_usuario=id_usuario,
            arquivo_stream=arquivo,
            nome_original=arquivo.filename,
            tamanho=tamanho,
        )
        if err:
            return jsonify(success=False, message=err), 400
        conn.commit()
        return jsonify(
            success=True,
            message="Foto atualizada.",
            foto_url=_url_publica_foto(rel) + "?t=" + str(int(agora_utc().timestamp())),
            tem_foto=True,
        )
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify(success=False, message=str(e)), 500
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@perfil_bp.delete("/api/meu-perfil/foto")
@login_obrigatorio
def api_meu_perfil_foto_remover():
    id_usuario = session["id_usuario"]
    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute("SELECT foto_caminho FROM tbl_usuario WHERE id = %s", (id_usuario,))
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Usuário não encontrado."), 404
        antigo = row[0]
        cur.execute("UPDATE tbl_usuario SET foto_caminho = NULL WHERE id = %s", (id_usuario,))
        conn.commit()
        _remover_foto_customizada_disco(antigo)
        return jsonify(
            success=True,
            message="Foto removida.",
            foto_url=_url_publica_foto(None),
            tem_foto=False,
        )
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify(success=False, message=str(e)), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@perfil_bp.get("/api/meu-perfil/foto")
@login_obrigatorio
def api_meu_perfil_foto_arquivo():
    id_usuario = session["id_usuario"]
    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute("SELECT foto_caminho FROM tbl_usuario WHERE id = %s", (id_usuario,))
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Usuário não encontrado."), 404

        if row[0]:
            try:
                caminho = _caminho_absoluto_de_db(row[0])
            except ValueError:
                caminho = None
            if caminho and caminho.is_file():
                return send_file(caminho, mimetype=_mime_foto(row[0]), max_age=300)

        padrao = _caminho_foto_padrao_abs()
        if padrao.is_file():
            return send_file(padrao, mimetype=_mime_foto(padrao.name), max_age=3600)
        return jsonify(success=False, message="Imagem padrão não encontrada."), 404
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


# ── Minha empresa ─────────────────────────────────────────────────────

@perfil_bp.get("/api/minha-empresa")
@login_obrigatorio
def api_minha_empresa_dados():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["empresa"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = _carregar_tenant_empresa(cur, id_tenant)
        if not dados:
            return jsonify(success=False, message="Empresa não encontrada."), 404
        return jsonify(success=True, dados=dados)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@perfil_bp.put("/api/minha-empresa")
@login_obrigatorio
def api_minha_empresa_salvar():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["empresa"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    dados = request.get_json(silent=True) or {}

    nome = (dados.get("nome") or "").strip()
    nome_completo = (dados.get("nome_completo") or "").strip()
    nome_fantasia = nome or (dados.get("nome_fantasia") or "").strip() or None
    if len(nome) < 2 or len(nome_completo) < 2:
        return jsonify(success=False, message="Informe o apelido e a razão social."), 400

    cep = _so_digitos(dados.get("cep") or "")
    uf = (dados.get("uf") or "").strip().upper()
    if cep and len(cep) != 8:
        return jsonify(success=False, message="CEP inválido."), 400
    if uf and not _valida_uf(uf):
        return jsonify(success=False, message="UF inválida."), 400

    email_com = (dados.get("email_comercial") or "").strip()
    if email_com and not valida_email(email_com):
        return jsonify(success=False, message="E-mail comercial inválido."), 400

    inscricoes = dados.get("inscricoes_st") or []
    if not isinstance(inscricoes, list):
        inscricoes = []

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_tenant SET
                nome = %s, nome_completo = %s, razao_social = %s, nome_fantasia = %s,
                inscricao_estadual = %s, inscricao_municipal = %s, ie_isento = %s,
                cnae_principal = %s, atividade_principal = %s, codigo_regime_tributario = %s,
                tamanho_empresa = %s,
                segmento_comercio = %s, segmento_ecommerce = %s,
                segmento_industria = %s, segmento_servicos = %s,
                faturamento_ultimo_ano = %s, quantidade_funcionarios = %s,
                cep = %s, logradouro = %s, numero = %s, complemento = %s,
                bairro = %s, cidade = %s, uf = %s,
                pessoas_contato = %s, telefone_comercial = %s, celular_comercial = %s,
                email_comercial = %s, site = %s
            WHERE id = %s
            """,
            (
                nome,
                nome_completo,
                (dados.get("razao_social") or "").strip() or None,
                nome_fantasia,
                (dados.get("inscricao_estadual") or "").strip() or None,
                (dados.get("inscricao_municipal") or "").strip() or None,
                bool(dados.get("ie_isento")),
                (dados.get("cnae_principal") or "").strip() or None,
                (dados.get("atividade_principal") or "").strip() or None,
                (dados.get("codigo_regime_tributario") or "").strip() or None,
                (dados.get("tamanho_empresa") or "").strip() or None,
                bool(dados.get("segmento_comercio")),
                bool(dados.get("segmento_ecommerce")),
                bool(dados.get("segmento_industria")),
                bool(dados.get("segmento_servicos")),
                (dados.get("faturamento_ultimo_ano") or "").strip() or None,
                (dados.get("quantidade_funcionarios") or "").strip() or None,
                cep or None,
                (dados.get("logradouro") or "").strip() or None,
                (dados.get("numero") or "").strip() or None,
                (dados.get("complemento") or "").strip() or None,
                (dados.get("bairro") or "").strip() or None,
                (dados.get("cidade") or "").strip() or None,
                uf or None,
                (dados.get("pessoas_contato") or "").strip() or None,
                _so_digitos(dados.get("telefone_comercial") or "") or None,
                _so_digitos(dados.get("celular_comercial") or "") or None,
                email_com or None,
                (dados.get("site") or "").strip() or None,
                id_tenant,
            ),
        )
        cur.execute("DELETE FROM tbl_tenant_inscricao_st WHERE id_tenant = %s", (id_tenant,))
        for ins in inscricoes:
            if not isinstance(ins, dict):
                continue
            iuf = (ins.get("uf") or "").strip().upper()
            ie = (ins.get("inscricao_estadual") or "").strip()
            if iuf and ie and _valida_uf(iuf):
                cur.execute(
                    "INSERT INTO tbl_tenant_inscricao_st (id_tenant, uf, inscricao_estadual) VALUES (%s,%s,%s)",
                    (id_tenant, iuf, ie),
                )
        conn.commit()
        session["tenant_nome"] = nome
        return jsonify(success=True, message="Dados da empresa salvos.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@perfil_bp.get("/api/minha-empresa/logo/arquivo")
@login_obrigatorio
def api_minha_empresa_logo_arquivo():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["empresa"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT logo_caminho FROM tbl_tenant WHERE id = %s", (id_tenant,))
        row = cur.fetchone()
        if not row or not row[0]:
            return jsonify(success=False, message="Sem logotipo."), 404
        caminho = _caminho_abs_logo(row[0])
        if not caminho or not caminho.is_file():
            return jsonify(success=False, message="Arquivo não encontrado."), 404
        return send_file(caminho, mimetype=_mime_foto(caminho.name), max_age=300)
    finally:
        conn.close()


@perfil_bp.get("/api/minha-empresa/cep/<cep>")
@login_obrigatorio
def api_minha_empresa_cep(cep: str):
    bloqueio = _exigir_aba(_abas_perfil_ctx()["empresa"])
    if bloqueio:
        return bloqueio
    cep_limpo = _so_digitos(cep)
    if len(cep_limpo) != 8:
        return jsonify(success=False, message="CEP inválido."), 400
    try:
        r = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=8)
        r.raise_for_status()
        data = r.json()
        if data.get("erro"):
            return jsonify(success=False, message="CEP não encontrado."), 404
        return jsonify(
            success=True,
            endereco={
                "logradouro": data.get("logradouro") or "",
                "bairro": data.get("bairro") or "",
                "cidade": data.get("localidade") or "",
                "uf": data.get("uf") or "",
            },
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 502


@perfil_bp.post("/api/minha-empresa/logo")
@login_obrigatorio
def api_minha_empresa_logo():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["empresa"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify(success=False, message="Selecione uma imagem."), 400
    arquivo.seek(0, os.SEEK_END)
    tamanho = arquivo.tell()
    arquivo.seek(0)
    err = _validar_arquivo_foto(arquivo.filename, tamanho)
    if err:
        return jsonify(success=False, message=err), 400
    nome_arquivo = _nome_arquivo_seguro(arquivo.filename)
    if not nome_arquivo:
        return jsonify(success=False, message="Nome de arquivo inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT logo_caminho FROM tbl_tenant WHERE id = %s", (id_tenant,))
        row = cur.fetchone()
        antigo = _caminho_abs_logo(row[0] if row else None)
        if antigo and antigo.is_file():
            try:
                antigo.unlink()
            except OSError:
                pass
        pasta = _pasta_logo_tenant(id_tenant)
        for f in pasta.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    pass
        destino = pasta / nome_arquivo
        arquivo.save(str(destino))
        caminho_db = _caminho_db_logo(id_tenant, nome_arquivo)
        cur.execute("UPDATE tbl_tenant SET logo_caminho = %s WHERE id = %s", (caminho_db, id_tenant))
        conn.commit()
        ts = int(agora_utc().timestamp())
        return jsonify(
            success=True,
            message="Logotipo atualizado.",
            logo_url=_url_logo_tenant(caminho_db) + "?t=" + str(ts),
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


# ── Cobrança e faturas ────────────────────────────────────────────────

@perfil_bp.get("/api/cobranca/config")
@login_obrigatorio
def api_cobranca_config():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["pagamento"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        _garantir_cobranca_tenant(cur, id_tenant)
        conn.commit()
        cur.execute(
            """
            SELECT tc.forma_pagamento, tc.dia_vencimento, tc.email_cobranca, tc.inicio_cobranca,
                   tc.plano_slug, p.nome, p.valor_centavos, p.periodicidade
            FROM tbl_tenant_cobranca tc
            JOIN tbl_plano p ON p.slug = tc.plano_slug
            WHERE tc.id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Cobrança não configurada."), 404
        from api.efi.cliente import efi_disponivel

        return jsonify(
            success=True,
            config={
                "forma_pagamento": row[0],
                "dia_vencimento": row[1],
                "email_cobranca": row[2] or "",
                "inicio_cobranca": row[3].isoformat() if row[3] else None,
                "plano_slug": row[4],
                "plano_nome": row[5],
                "valor_centavos": row[6],
                "periodicidade": row[7],
                "efi_configurado": efi_disponivel(),
            },
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@perfil_bp.put("/api/cobranca/config")
@login_obrigatorio
def api_cobranca_config_salvar():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["pagamento"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    dados = request.get_json(silent=True) or {}
    forma = (dados.get("forma_pagamento") or "boleto").strip().lower()
    if forma not in ("boleto", "pix", "cartao"):
        return jsonify(success=False, message="Forma de pagamento inválida."), 400
    try:
        dia = int(dados.get("dia_vencimento") or 15)
    except (TypeError, ValueError):
        dia = 15
    if dia < 1 or dia > 28:
        return jsonify(success=False, message="Dia de vencimento deve ser entre 1 e 28."), 400
    email = (dados.get("email_cobranca") or "").strip()
    if email and not valida_email(email):
        return jsonify(success=False, message="E-mail de cobrança inválido."), 400

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        _garantir_cobranca_tenant(cur, id_tenant)
        cur.execute(
            """
            UPDATE tbl_tenant_cobranca
            SET forma_pagamento = %s, dia_vencimento = %s, email_cobranca = %s, atualizado_em = NOW()
            WHERE id_tenant = %s
            """,
            (forma, dia, email or None, id_tenant),
        )
        conn.commit()
        return jsonify(success=True, message="Forma de pagamento salva.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@perfil_bp.get("/api/faturas")
@login_obrigatorio
def api_faturas_listar():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["faturas"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    pagina = max(1, int(request.args.get("page") or 1))
    por_pagina = 20
    offset = (pagina - 1) * por_pagina

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tbl_fatura WHERE id_tenant = %s", (id_tenant,))
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT id, referencia, valor_centavos, status, link_boleto, vencimento_em, pago_em, efi_charge_id
            FROM tbl_fatura WHERE id_tenant = %s
            ORDER BY referencia DESC
            LIMIT %s OFFSET %s
            """,
            (id_tenant, por_pagina, offset),
        )
        itens = []
        for r in cur.fetchall():
            valor_fmt = f"R$ {r[2] / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            itens.append(
                {
                    "id": r[0],
                    "referencia": r[1],
                    "valor_centavos": r[2],
                    "valor_formatado": valor_fmt,
                    "status": r[3],
                    "link_boleto": r[4],
                    "vencimento_em": r[5].isoformat() if r[5] else None,
                    "pago_em": r[6].isoformat() if r[6] else None,
                    "efi_charge_id": r[7],
                }
            )
        return jsonify(
            success=True,
            faturas=itens,
            total=total,
            pagina=pagina,
            total_paginas=max(1, (total + por_pagina - 1) // por_pagina),
        )
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


def _proximo_vencimento(dia: int) -> date:
    hoje = date.today()
    try:
        venc = hoje.replace(day=dia)
    except ValueError:
        venc = hoje.replace(day=28)
    if venc <= hoje:
        if hoje.month == 12:
            venc = date(hoje.year + 1, 1, min(dia, 28))
        else:
            try:
                venc = date(hoje.year, hoje.month + 1, dia)
            except ValueError:
                venc = date(hoje.year, hoje.month + 1, 28)
    return venc


@perfil_bp.post("/api/faturas/gerar")
@login_obrigatorio
def api_faturas_gerar():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["faturas"])
    if bloqueio:
        return bloqueio
    if not session.get("eh_desenvolvedor") and (session.get("perfil_codigo") or "").lower() != "dono":
        return jsonify(success=False, message="Somente o dono da conta pode gerar cobrança manual."), 403

    id_tenant = session["id_tenant"]
    hoje = date.today()
    referencia = hoje.strftime("%Y-%m")

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_fatura WHERE id_tenant = %s AND referencia = %s", (id_tenant, referencia))
        if cur.fetchone():
            return jsonify(success=False, message="Já existe fatura para este mês."), 409

        _garantir_cobranca_tenant(cur, id_tenant)
        cur.execute(
            """
            SELECT tc.dia_vencimento, tc.email_cobranca, tc.forma_pagamento, p.valor_centavos, p.nome,
                   t.nome_completo, t.documento, t.nome
            FROM tbl_tenant_cobranca tc
            JOIN tbl_plano p ON p.slug = tc.plano_slug
            JOIN tbl_tenant t ON t.id = tc.id_tenant
            WHERE tc.id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify(success=False, message="Configure a cobrança antes."), 400

        dia_venc, email_cob, forma, valor, plano_nome, nome_cli, doc, nome_t = row
        if valor <= 0:
            return jsonify(success=False, message="Plano atual não gera cobrança."), 400
        if forma != "boleto":
            return jsonify(success=False, message="Somente boleto disponível nesta fase."), 400

        from api.efi.cliente import criar_cobranca_boleto, efi_disponivel

        if not efi_disponivel():
            return jsonify(success=False, message="Efi não configurado no .env."), 503

        venc = _proximo_vencimento(int(dia_venc or 15))
        cob = criar_cobranca_boleto(
            nome_cliente=nome_cli or nome_t,
            documento=doc,
            email=email_cob or session.get("email") or "",
            valor_centavos=valor,
            descricao=f"DropNexo — {plano_nome}",
            vencimento=venc,
        )
        cur.execute(
            """
            INSERT INTO tbl_fatura (
                id_tenant, referencia, valor_centavos, status, efi_charge_id,
                link_boleto, codigo_barras, vencimento_em
            ) VALUES (%s,%s,%s,'pendente',%s,%s,%s,%s)
            RETURNING id
            """,
            (
                id_tenant,
                referencia,
                valor,
                cob.get("charge_id"),
                cob.get("link_boleto"),
                cob.get("codigo_barras"),
                venc,
            ),
        )
        fid = cur.fetchone()[0]
        conn.commit()
        return jsonify(success=True, message="Fatura gerada.", id=fid, link_boleto=cob.get("link_boleto"))
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


# ── Cancelar conta ────────────────────────────────────────────────────

@perfil_bp.post("/api/cancelar-conta/iniciar")
@login_obrigatorio
def api_cancelar_conta_iniciar():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["cancelar"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    id_usuario = session["id_usuario"]
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tbl_cancelamento_conta (id_tenant, id_usuario, etapa)
            VALUES (%s, %s, 1)
            ON CONFLICT (id_tenant) DO UPDATE SET etapa = 1, solicitado_em = NOW()
            """,
            (id_tenant, id_usuario),
        )
        conn.commit()
        return jsonify(success=True, etapa=1)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@perfil_bp.post("/api/cancelar-conta/confirmar")
@login_obrigatorio
def api_cancelar_conta_confirmar():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["cancelar"])
    if bloqueio:
        return bloqueio
    dados = request.get_json(silent=True) or {}
    motivo = (dados.get("motivo") or "").strip()
    if len(motivo) < 5:
        return jsonify(success=False, message="Informe o motivo do cancelamento."), 400
    id_tenant = session["id_tenant"]
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_cancelamento_conta SET etapa = 2, motivo = %s
            WHERE id_tenant = %s
            """,
            (motivo, id_tenant),
        )
        conn.commit()
        return jsonify(success=True, etapa=2)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@perfil_bp.get("/api/cancelar-conta/exportar")
@login_obrigatorio
def api_cancelar_conta_exportar():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["cancelar"])
    if bloqueio:
        return bloqueio
    id_tenant = session["id_tenant"]
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute("SELECT nome, slug, plano, documento FROM tbl_tenant WHERE id = %s", (id_tenant,))
        tenant = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM tbl_usuario_tenant WHERE id_tenant = %s", (id_tenant,))
        qtd_usuarios = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM tbl_produto WHERE id_tenant = %s", (id_tenant,))
        qtd_produtos = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT referencia, valor_centavos, status FROM tbl_fatura WHERE id_tenant = %s", (id_tenant,))
        faturas = [{"referencia": r[0], "valor_centavos": r[1], "status": r[2]} for r in cur.fetchall()]
        payload = {
            "tenant": {
                "nome": tenant[0] if tenant else "",
                "slug": tenant[1] if tenant else "",
                "plano": tenant[2] if tenant else "",
                "documento": tenant[3] if tenant else "",
            },
            "resumo": {"usuarios": qtd_usuarios, "produtos": qtd_produtos, "faturas": len(faturas)},
            "faturas": faturas,
            "exportado_em": datetime.utcnow().isoformat() + "Z",
        }
        return jsonify(success=True, dados=payload)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@perfil_bp.post("/api/cancelar-conta/concluir")
@login_obrigatorio
def api_cancelar_conta_concluir():
    bloqueio = _exigir_aba(_abas_perfil_ctx()["cancelar"])
    if bloqueio:
        return bloqueio
    dados = request.get_json(silent=True) or {}
    if not dados.get("confirmar"):
        return jsonify(success=False, message="Confirme que deseja cancelar a conta."), 400
    id_tenant = session["id_tenant"]
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT etapa FROM tbl_cancelamento_conta WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or int(row[0]) < 2:
            return jsonify(success=False, message="Conclua as etapas anteriores."), 400
        cur.execute("UPDATE tbl_tenant SET ativo = FALSE WHERE id = %s", (id_tenant,))
        cur.execute(
            "UPDATE tbl_usuario_tenant SET ativo = FALSE WHERE id_tenant = %s",
            (id_tenant,),
        )
        cur.execute(
            """
            UPDATE tbl_cancelamento_conta SET etapa = 3, concluido_em = NOW()
            WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
        conn.commit()
        session.clear()
        return jsonify(success=True, message="Conta cancelada.", redirect=url_for("auth.pagina_login"))
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()

