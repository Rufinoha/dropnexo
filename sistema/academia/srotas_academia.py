# Academia DropNexo — vídeos de ajuda globais (sem id_tenant; mesmo catálogo para todos)

import os
import json
import shutil
import mimetypes
import secrets
from datetime import datetime
from pathlib import Path

from psycopg2 import ProgrammingError

from flask import (
    Blueprint,
    request,
    jsonify,
    abort,
    Response,
    stream_with_context,
    current_app,
    session,
    render_template,
)

from global_utils import (
    Var_ConectarBanco,
    login_obrigatorio,
)

_MOD_DIR = Path(__file__).resolve().parent
_ACADEMIA_TEMPLATES_DIR = str(_MOD_DIR / "templates")
# Partes pequenas para passar do client_max_body_size padrão do Nginx (~1m)
_ACADEMIA_CHUNK_SIZE = 512 * 1024


def _academia_tmp_dir(upload_id: str) -> str:
    base = current_app.config.get("ACADEMIA_STORAGE_DIR") or os.path.join(
        current_app.root_path, "storage", "academia"
    )
    return os.path.join(base, "_tmp", str(upload_id))


def _pode_gerenciar_academia() -> bool:
    """Gestão de vídeos: somente desenvolvedor da plataforma."""
    return bool(session.get("eh_desenvolvedor"))


def _bloquear_se_sem_gestao_academia():
    if _pode_gerenciar_academia():
        return None
    msg = "Acesso restrito: apenas desenvolvedores podem gerenciar a Academia."
    wants_json = (
        request.is_json
        or request.method != "GET"
        or "application/json" in (request.headers.get("Accept") or "")
        or request.path.endswith("/dados")
        or request.path.endswith("/apoio")
        or request.path.endswith("/salvar")
        or request.path.endswith("/deletar")
        or "/academia/upload/" in request.path
    )
    if wants_json:
        return jsonify({"success": False, "message": msg}), 403
    return msg, 403


academia_bp = Blueprint(
    "academia",
    __name__,
    root_path=str(_MOD_DIR),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/academia",
)


def init_app(app):
    app.register_blueprint(academia_bp)


@academia_bp.get("/academia")
@login_obrigatorio()
def academia():
    return render_template(
        "frm_academia.html",
        pode_gerenciar=_pode_gerenciar_academia(),
        nav_codigo="hdr_academia",
    )


@academia_bp.get("/academia/player")
@login_obrigatorio()
def academia_player():
    """Player em modal (iframe)."""
    idv = request.args.get("id", type=int) or 0
    return render_template("frm_academia_player.html", id_video=idv)


@academia_bp.get("/academia/incluir")
@login_obrigatorio()
def incluir():
    bloqueio = _bloquear_se_sem_gestao_academia()
    if bloqueio:
        return bloqueio
    return render_template("frm_academia_apoio.html")


@academia_bp.get("/academia/editar")
@login_obrigatorio()
def editar():
    bloqueio = _bloquear_se_sem_gestao_academia()
    if bloqueio:
        return bloqueio
    return render_template("frm_academia_apoio.html")


@academia_bp.post("/academia/dados")
@login_obrigatorio()
def dados():
    if not request.is_json:
        return jsonify({"success": False, "message": "Requisição inválida."}), 400

    payload = request.get_json(silent=True) or {}
    categoria = (payload.get("categoria") or "").strip()
    q = (payload.get("q") or "").strip()

    where = ["ativo = true"]
    params = []

    if categoria and categoria != "__TODOS__":
        where.append("categoria = %s")
        params.append(categoria)

    if q:
        like = f"%{q}%"
        where.append("(titulo ILIKE %s OR descricao ILIKE %s OR categoria ILIKE %s)")
        params.extend([like, like, like])

    sql_cats = """
        SELECT DISTINCT categoria
        FROM tbl_academia_video
        WHERE ativo = true AND categoria IS NOT NULL AND categoria <> ''
        ORDER BY categoria ASC
    """

    sql_mv = """
        SELECT id, categoria, titulo, descricao, duracao_txt, views
        FROM tbl_academia_video
        WHERE ativo = true
        ORDER BY views DESC, id DESC
        LIMIT 4
    """

    sql_list = f"""
        SELECT id, categoria, titulo, descricao, duracao_txt, ordem, views
        FROM tbl_academia_video
        WHERE {" AND ".join(where)}
        ORDER BY categoria ASC, ordem ASC, id DESC
        LIMIT 200
    """

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()

        cur.execute(sql_cats)
        categorias = [r[0] for r in cur.fetchall()]

        cur.execute(sql_mv)
        mais_vistos = [{
            "id": r[0],
            "categoria": r[1],
            "titulo": r[2],
            "descricao": r[3],
            "duracao_txt": r[4],
            "views": int(r[5] or 0),
        } for r in cur.fetchall()]

        cur.execute(sql_list, params)
        itens = [{
            "id": r[0],
            "categoria": r[1],
            "titulo": r[2],
            "descricao": r[3],
            "duracao_txt": r[4],
            "ordem": int(r[5] or 0),
            "views": int(r[6] or 0),
        } for r in cur.fetchall()]

        return jsonify({
            "success": True,
            "categorias": categorias,
            "mais_vistos": mais_vistos,
            "itens": itens,
        }), 200

    except ProgrammingError as e:
        err = str(e).lower()
        if "tbl_academia_video" in err and ("does not exist" in err or "não existe" in err or "nao existe" in err):
            return jsonify({
                "success": True,
                "categorias": [],
                "mais_vistos": [],
                "itens": [],
                "aviso": "Tabela de vídeos da academia não encontrada. Contate o administrador.",
            }), 200
        return jsonify({"success": False, "message": f"Falha ao carregar dados. {e}"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Falha ao carregar dados. {e}"}), 500

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


@academia_bp.post("/academia/apoio")
@login_obrigatorio()
def apoio():
    bloqueio = _bloquear_se_sem_gestao_academia()
    if bloqueio:
        return bloqueio
    if not request.is_json:
        return jsonify({"success": False, "message": "Requisição inválida."}), 400

    payload = request.get_json(silent=True) or {}
    try:
        idv = int(payload.get("id") or 0)
    except (TypeError, ValueError):
        idv = 0

    if not (idv > 0):
        return jsonify({"success": True, "item": None}), 200

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, categoria, titulo, descricao, duracao_txt, ativo, ordem, nome_original, views
            FROM tbl_academia_video
            WHERE id = %s
            """,
            (idv,),
        )
        r = cur.fetchone()

        if not r:
            return jsonify({"success": False, "message": "Registro não encontrado."}), 404

        item = {
            "id": r[0],
            "categoria": r[1],
            "titulo": r[2],
            "descricao": r[3],
            "duracao_txt": r[4],
            "ativo": bool(r[5]),
            "ordem": int(r[6] or 0),
            "nome_original": r[7],
            "views": int(r[8] or 0),
        }

        return jsonify({"success": True, "item": item}), 200

    except Exception as e:
        return jsonify({"success": False, "message": f"Falha ao carregar apoio. {e}"}), 500

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


@academia_bp.post("/academia/upload/iniciar")
@login_obrigatorio()
def upload_iniciar():
    """Inicia upload fragmentado (bypass de limite 413 do proxy)."""
    bloqueio = _bloquear_se_sem_gestao_academia()
    if bloqueio:
        return bloqueio
    if not request.is_json:
        return jsonify({"success": False, "message": "Requisição inválida."}), 400

    payload = request.get_json(silent=True) or {}
    nome = (payload.get("nome") or "video.mp4").strip() or "video.mp4"
    try:
        tamanho = int(payload.get("tamanho") or 0)
        total_chunks = int(payload.get("total_chunks") or 0)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Metadados de upload inválidos."}), 400

    if tamanho <= 0 or total_chunks <= 0:
        return jsonify({"success": False, "message": "Informe tamanho e total de partes."}), 400
    if tamanho > 2 * 1024 * 1024 * 1024:
        return jsonify({"success": False, "message": "Arquivo acima de 2 GB não é suportado."}), 400

    upload_id = secrets.token_hex(16)
    tmp = _academia_tmp_dir(upload_id)
    os.makedirs(tmp, exist_ok=True)
    meta = {
        "id_usuario": int(session.get("id_usuario") or 0),
        "nome_original": nome,
        "tamanho": tamanho,
        "total_chunks": total_chunks,
        "recebidos": [],
    }
    with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)

    return jsonify(
        {
            "success": True,
            "upload_id": upload_id,
            "chunk_size": _ACADEMIA_CHUNK_SIZE,
        }
    )


@academia_bp.post("/academia/upload/chunk")
@login_obrigatorio()
def upload_chunk():
    bloqueio = _bloquear_se_sem_gestao_academia()
    if bloqueio:
        return bloqueio

    upload_id = (request.form.get("upload_id") or "").strip()
    try:
        index = int(request.form.get("index"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Índice da parte inválido."}), 400

    parte = request.files.get("chunk")
    if not upload_id or not parte:
        return jsonify({"success": False, "message": "Parte do arquivo ausente."}), 400

    tmp = _academia_tmp_dir(upload_id)
    meta_path = os.path.join(tmp, "meta.json")
    if not os.path.isfile(meta_path):
        return jsonify({"success": False, "message": "Upload não iniciado ou expirado."}), 404

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if int(meta.get("id_usuario") or 0) != int(session.get("id_usuario") or 0):
        return jsonify({"success": False, "message": "Upload não pertence a esta sessão."}), 403

    if index < 0 or index >= int(meta.get("total_chunks") or 0):
        return jsonify({"success": False, "message": "Índice fora do intervalo."}), 400

    dest = os.path.join(tmp, f"part_{index:06d}")
    parte.save(dest)

    recebidos = set(meta.get("recebidos") or [])
    recebidos.add(index)
    meta["recebidos"] = sorted(recebidos)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)

    return jsonify(
        {
            "success": True,
            "recebidos": len(meta["recebidos"]),
            "total_chunks": meta["total_chunks"],
        }
    )


def _montar_upload_tmp(upload_id: str) -> tuple[str, str, int]:
    """Concatena partes e devolve (abs_path_final_tmp, nome_original, tamanho)."""
    tmp = _academia_tmp_dir(upload_id)
    meta_path = os.path.join(tmp, "meta.json")
    if not os.path.isfile(meta_path):
        raise ValueError("Upload não encontrado.")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if int(meta.get("id_usuario") or 0) != int(session.get("id_usuario") or 0):
        raise PermissionError("Upload não pertence a esta sessão.")

    total = int(meta.get("total_chunks") or 0)
    recebidos = set(meta.get("recebidos") or [])
    if len(recebidos) < total or any(i not in recebidos for i in range(total)):
        raise ValueError("Upload incompleto: faltam partes do arquivo.")

    assembled = os.path.join(tmp, "assembled.mp4")
    with open(assembled, "wb") as out:
        for i in range(total):
            part = os.path.join(tmp, f"part_{i:06d}")
            with open(part, "rb") as inp:
                while True:
                    buf = inp.read(1024 * 1024)
                    if not buf:
                        break
                    out.write(buf)

    tamanho = os.path.getsize(assembled)
    esperado = int(meta.get("tamanho") or 0)
    if esperado and abs(tamanho - esperado) > 64:
        raise ValueError("Tamanho montado diverge do arquivo original.")

    return assembled, (meta.get("nome_original") or "video.mp4"), tamanho


def _limpar_upload_tmp(upload_id: str) -> None:
    tmp = _academia_tmp_dir(upload_id)
    if not os.path.isdir(tmp):
        return
    for nome in os.listdir(tmp):
        try:
            os.remove(os.path.join(tmp, nome))
        except OSError:
            pass
    try:
        os.rmdir(tmp)
    except OSError:
        pass


@academia_bp.post("/academia/salvar")
@login_obrigatorio()
def salvar():
    bloqueio = _bloquear_se_sem_gestao_academia()
    if bloqueio:
        return bloqueio
    try:
        idv = int(request.form.get("id") or 0)
    except (TypeError, ValueError):
        idv = 0

    categoria = (request.form.get("categoria") or "").strip()
    titulo = (request.form.get("titulo") or "").strip()
    descricao = (request.form.get("descricao") or "").strip()
    duracao_txt = (request.form.get("duracao_txt") or "").strip() or None
    upload_id = (request.form.get("upload_id") or "").strip()

    try:
        ordem = int(request.form.get("ordem") or 0)
    except (TypeError, ValueError):
        ordem = 0

    ativo_raw = str(request.form.get("ativo") or "1").strip()
    ativo = ativo_raw in ("1", "true", "True", "SIM", "sim")

    if not categoria:
        return jsonify({"success": False, "message": "Informe a categoria."}), 400
    if not titulo:
        return jsonify({"success": False, "message": "Informe o título."}), 400
    if not descricao:
        return jsonify({"success": False, "message": "Informe a descrição."}), 400

    file = request.files.get("arquivo")
    tem_arquivo = bool(file) or bool(upload_id)

    if not (idv > 0) and not tem_arquivo:
        return jsonify({"success": False, "message": "Selecione um arquivo MP4."}), 400

    if file:
        mime = (file.mimetype or "").lower()
        if mime != "video/mp4":
            return jsonify({"success": False, "message": "O arquivo deve ser MP4 (video/mp4)."}), 400

    id_usuario = session.get("id_usuario")

    conn = None
    cur = None
    assembled_path = None
    nome_original = None
    tamanho_montado = None
    try:
        if upload_id:
            assembled_path, nome_original, tamanho_montado = _montar_upload_tmp(upload_id)

        conn = Var_ConectarBanco()
        cur = conn.cursor()

        if not (idv > 0):
            cur.execute(
                """
                INSERT INTO tbl_academia_video
                  (categoria, titulo, descricao, duracao_txt, ativo, ordem, views, id_usuario_upload, data_upload)
                VALUES
                  (%s, %s, %s, %s, %s, %s, 0, %s, NOW())
                RETURNING id
                """,
                (categoria, titulo, descricao, duracao_txt, ativo, ordem, id_usuario),
            )
            idv = cur.fetchone()[0]
        else:
            cur.execute(
                """
                UPDATE tbl_academia_video
                SET categoria=%s, titulo=%s, descricao=%s, duracao_txt=%s, ativo=%s, ordem=%s
                WHERE id=%s
                """,
                (categoria, titulo, descricao, duracao_txt, ativo, ordem, idv),
            )

        if file or assembled_path:
            base = current_app.config.get("ACADEMIA_STORAGE_DIR") or os.path.join(
                current_app.root_path, "storage", "academia"
            )
            os.makedirs(base, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_arm = f"{ts}_vid{idv}_{secrets.token_hex(4)}.mp4"
            abs_path = os.path.join(base, nome_arm)

            if assembled_path:
                shutil.move(assembled_path, abs_path)
                tamanho = tamanho_montado or os.path.getsize(abs_path)
                nome_arq = nome_original or "video.mp4"
            else:
                file.save(abs_path)
                tamanho = os.path.getsize(abs_path)
                nome_arq = file.filename

            caminho_rel = os.path.relpath(abs_path, current_app.root_path).replace("\\", "/")

            cur.execute(
                """
                UPDATE tbl_academia_video
                SET nome_original=%s,
                    nome_armazenado=%s,
                    caminho_relativo=%s,
                    tipo_mime=%s,
                    tamanho_bytes=%s
                WHERE id=%s
                """,
                (nome_arq, nome_arm, caminho_rel, "video/mp4", tamanho, idv),
            )

        conn.commit()
        if upload_id:
            _limpar_upload_tmp(upload_id)
        return jsonify({"success": True, "id": idv}), 200

    except PermissionError as e:
        return jsonify({"success": False, "message": str(e)}), 403
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return jsonify({"success": False, "message": f"Falha ao salvar. {e}"}), 500

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
        if upload_id and assembled_path and os.path.isfile(assembled_path):
            try:
                os.remove(assembled_path)
            except OSError:
                pass


@academia_bp.post("/academia/deletar")
@login_obrigatorio()
def deletar():
    bloqueio = _bloquear_se_sem_gestao_academia()
    if bloqueio:
        return bloqueio
    if not request.is_json:
        return jsonify({"success": False, "message": "Requisição inválida."}), 400

    payload = request.get_json(silent=True) or {}
    try:
        idv = int(payload.get("id") or 0)
    except (TypeError, ValueError):
        idv = 0

    if not (idv > 0):
        return jsonify({"success": False, "message": "ID inválido."}), 400

    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()
        cur.execute("UPDATE tbl_academia_video SET ativo = false WHERE id = %s", (idv,))
        conn.commit()
        return jsonify({"success": True}), 200

    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return jsonify({"success": False, "message": f"Falha ao excluir. {e}"}), 500

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


@academia_bp.get("/academia/stream/<int:id_video>")
@login_obrigatorio()
def stream(id_video: int):
    conn = None
    cur = None
    try:
        conn = Var_ConectarBanco()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT caminho_relativo, tipo_mime
            FROM tbl_academia_video
            WHERE id = %s AND ativo = true
            """,
            (id_video,),
        )
        r = cur.fetchone()

        if not r:
            abort(404)

        caminho_rel = r[0]
        mime = r[1] or "video/mp4"

        abs_path = os.path.join(current_app.root_path, caminho_rel)
        if not os.path.exists(abs_path):
            abort(404)

        file_size = os.path.getsize(abs_path)
        mime = mime or mimetypes.guess_type(abs_path)[0] or "video/mp4"

        range_header = request.headers.get("Range")

        def inc_views_se_primeiro(start_zero: bool):
            if not start_zero:
                return
            try:
                cur.execute(
                    "UPDATE tbl_academia_video SET views = views + 1 WHERE id = %s",
                    (id_video,),
                )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass

        if not range_header:
            inc_views_se_primeiro(True)

            def generate():
                with open(abs_path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk

            return Response(
                stream_with_context(generate()),
                mimetype=mime,
                headers={
                    "Content-Length": str(file_size),
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-store",
                },
            )

        try:
            _, bytes_range = range_header.strip().split("=")
            start_str, end_str = bytes_range.split("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except (ValueError, AttributeError):
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        length = end - start + 1

        inc_views_se_primeiro(start == 0)

        def generate_range():
            with open(abs_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return Response(
            stream_with_context(generate_range()),
            status=206,
            mimetype=mime,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Cache-Control": "no-store",
            },
        )

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
