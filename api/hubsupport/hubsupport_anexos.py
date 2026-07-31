# api/hubsupport/hubsupport_anexos.py — espelho local + HS (padrão BARACAT)
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import requests

from api.hubsupport.hubsupport_client import HubSupportClient, HubSupportError

logger = logging.getLogger(__name__)

PREFIX = "dropnexo"
ANEXO_URL_PREFIX = "/api/demandas/anexo"


def uuid_de_external_id(external_id: str) -> str:
    m = re.match(rf"^{re.escape(PREFIX)}:chamado:(.+)$", external_id or "")
    return m.group(1) if m else (external_id or "")


def external_id_chamado(chamado_uuid: str | None = None) -> str:
    uid = (chamado_uuid or str(uuid.uuid4())).strip()
    return f"{PREFIX}:chamado:{uid}"


def _extrair_lista_api(raw, *keys: str) -> list:
    preferidas = keys or (
        "itens", "items", "anexos", "attachments", "arquivos", "files", "data",
    )
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    for key in preferidas:
        val = raw.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            nested = _extrair_lista_api(val, *preferidas)
            if nested:
                return nested
    return []


def _nome_de_dict(obj: dict | None) -> str:
    if not isinstance(obj, dict):
        return ""
    for key in ("nome", "name", "display_name", "nome_completo"):
        val = obj.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _normalizar_anexo(item: dict) -> dict:
    if not isinstance(item, dict):
        return {}
    url = (
        item.get("url")
        or item.get("download_url")
        or item.get("public_url")
        or item.get("file_url")
        or item.get("link")
        or item.get("href")
        or ""
    )
    nome = (
        item.get("nome")
        or item.get("nome_original")
        or item.get("filename")
        or item.get("name")
        or item.get("arquivo")
        or ""
    )
    if not nome and url:
        nome = str(url).rsplit("/", 1)[-1].split("?")[0] or "Anexo"
    if not nome and not url:
        return {}
    out = {
        "id": item.get("id") or item.get("anexo_id") or "",
        "nome": str(nome).strip() or "Anexo",
        "url": str(url).strip(),
    }
    ct = item.get("content_type") or item.get("tipo_mime") or item.get("mime_type")
    if ct:
        out["content_type"] = str(ct)
    enviado_por = item.get("enviado_por") or item.get("nome_autor") or item.get("autor") or ""
    if isinstance(enviado_por, dict):
        enviado_por = _nome_de_dict(enviado_por)
    if enviado_por and str(enviado_por).strip():
        out["enviado_por"] = str(enviado_por).strip()
    enviado_em = item.get("enviado_em") or item.get("criado_em") or item.get("created_at") or ""
    if enviado_em:
        out["enviado_em"] = enviado_em.isoformat() if hasattr(enviado_em, "isoformat") else str(enviado_em).strip()
    return out


def _lista_anexos_raw(src) -> list:
    return _extrair_lista_api(
        src, "itens", "items", "anexos", "attachments", "arquivos", "files", "anexo", "data"
    )


def normalizar_anexos_lista(raw) -> list:
    out = []
    for item in _lista_anexos_raw(raw):
        norm = _normalizar_anexo(item)
        if norm:
            out.append(norm)
    return out


def _anexo_de_resposta_upload(resp, nome_fallback: str) -> dict:
    nome = (nome_fallback or "Anexo").strip() or "Anexo"
    if isinstance(resp, dict):
        data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
        if isinstance(data, dict):
            candidatos = []
            if isinstance(data.get("anexo"), dict):
                candidatos.append(data["anexo"])
            candidatos.append(data)
            for key in ("anexos", "attachments", "arquivos", "files", "itens", "items"):
                val = data.get(key)
                if isinstance(val, list) and val:
                    candidatos.extend([x for x in val if isinstance(x, dict)])
                    break
            for cand in candidatos:
                norm = _normalizar_anexo(cand)
                if norm:
                    if not norm.get("nome") or norm["nome"] == "Anexo":
                        norm["nome"] = nome
                    return norm
    return {"id": "", "nome": nome, "url": ""}


def _dir_anexos_chamado(external_id: str) -> str:
    from flask import current_app

    uid = uuid_de_external_id(external_id) or "sem-uuid"
    uid = re.sub(r"[^a-zA-Z0-9._-]", "", uid)[:80] or "sem-uuid"
    base = getattr(current_app, "static_folder", None) or "static"
    return os.path.join(base, "anexos", "demandas", uid)


def guardar_anexo_local(
    external_id: str,
    nome: str,
    conteudo: bytes,
    content_type: str | None = None,
    *,
    enviado_por: str | None = None,
    enviado_em: str | None = None,
) -> dict:
    from urllib.parse import quote
    from werkzeug.utils import secure_filename

    if not conteudo:
        raise HubSupportError("Arquivo de anexo vazio.")

    pasta = _dir_anexos_chamado(external_id)
    os.makedirs(pasta, exist_ok=True)

    base = secure_filename(nome or "") or "anexo.bin"
    stored = f"{uuid.uuid4().hex[:12]}_{base}"
    full = os.path.join(pasta, stored)
    with open(full, "wb") as fh:
        fh.write(conteudo)

    ref = quote(external_id, safe="")
    meta = {
        "id": stored,
        "nome": (nome or base).strip() or base,
        "url": f"{ANEXO_URL_PREFIX}/{ref}/{quote(stored, safe='')}",
        "content_type": (content_type or "application/octet-stream"),
        "fonte": "local",
        "enviado_em": (enviado_em or datetime.now(timezone.utc).isoformat()),
    }
    if enviado_por and str(enviado_por).strip():
        meta["enviado_por"] = str(enviado_por).strip()

    try:
        with open(full + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "nome": meta["nome"],
                    "enviado_por": meta.get("enviado_por") or "",
                    "enviado_em": meta.get("enviado_em") or "",
                    "content_type": meta.get("content_type") or "",
                },
                fh,
                ensure_ascii=False,
            )
    except OSError:
        logger.exception("Falha ao gravar meta do anexo local")

    return meta


def listar_anexos_disco(external_id: str) -> list:
    from urllib.parse import quote

    pasta = _dir_anexos_chamado(external_id)
    if not os.path.isdir(pasta):
        return []

    ref = quote(external_id, safe="")
    out = []
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        return []

    for stored in nomes:
        if not stored or stored.startswith(".") or stored.endswith(".meta.json"):
            continue
        full = os.path.join(pasta, stored)
        if not os.path.isfile(full):
            continue
        nome = stored.split("_", 1)[1] if "_" in stored else stored
        item = {
            "id": stored,
            "nome": nome,
            "url": f"{ANEXO_URL_PREFIX}/{ref}/{quote(stored, safe='')}",
            "fonte": "local",
        }
        try:
            mtime = os.path.getmtime(full)
            item["enviado_em"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass
        meta_path = full + ".meta.json"
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
                if isinstance(meta, dict):
                    if meta.get("nome"):
                        item["nome"] = str(meta["nome"]).strip() or item["nome"]
                    if meta.get("enviado_por"):
                        item["enviado_por"] = str(meta["enviado_por"]).strip()
                    if meta.get("enviado_em"):
                        item["enviado_em"] = str(meta["enviado_em"]).strip()
                    if meta.get("content_type"):
                        item["content_type"] = str(meta["content_type"]).strip()
            except (OSError, ValueError, TypeError):
                pass
        out.append(item)
    return out


def resolver_caminho_anexo_local(external_id: str, nome_armazenado: str) -> tuple[str, str]:
    stored = (nome_armazenado or "").strip().replace("\\", "/").split("/")[-1]
    if not stored or not re.match(r"^[A-Za-z0-9._-]+$", stored):
        raise HubSupportError("Nome de anexo inválido.", status_code=400)

    pasta = os.path.abspath(_dir_anexos_chamado(external_id))
    full = os.path.abspath(os.path.join(pasta, stored))
    if not full.startswith(pasta + os.sep):
        raise HubSupportError("Caminho de anexo inválido.", status_code=400)
    if not os.path.isfile(full):
        raise HubSupportError("Anexo não encontrado.", status_code=404)

    nome_exibicao = stored.split("_", 1)[1] if "_" in stored else stored
    return full, nome_exibicao


def mesclar_anexos(*listas: list) -> list:
    por_chave = {}
    ordem = []
    for lista in listas:
        for a in lista or []:
            if not isinstance(a, dict):
                continue
            nome = str(a.get("nome") or "").strip().lower()
            chave = (str(a.get("id") or ""), str(a.get("url") or ""), nome)
            if not any(chave):
                continue
            chave_nome = ("nome", nome) if nome else chave
            existente = por_chave.get(chave_nome) or por_chave.get(chave)
            if existente:
                merged = dict(existente)
                for k, v in a.items():
                    if v in (None, "", [], {}):
                        continue
                    if k not in merged or not merged.get(k):
                        merged[k] = v
                    elif k == "url" and str(v).startswith(ANEXO_URL_PREFIX):
                        merged[k] = v
                    elif k != "url" and v:
                        merged[k] = v
                por_chave[chave_nome] = merged
                if chave_nome not in ordem:
                    ordem.append(chave_nome)
            else:
                por_chave[chave_nome] = dict(a)
                ordem.append(chave_nome)
    return [por_chave[k] for k in ordem if k in por_chave]


def ordenar_anexos_mais_recentes(anexos: list) -> list:
    def chave(a: dict):
        raw = a.get("enviado_em") or a.get("criado_em") or a.get("created_at") or ""
        try:
            if hasattr(raw, "timestamp"):
                return raw
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(
        [a for a in (anexos or []) if isinstance(a, dict)],
        key=chave,
        reverse=True,
    )


def consolidar_anexos_thread(thread: list) -> list:
    out = []
    for m in thread or []:
        if not isinstance(m, dict):
            continue
        for a in m.get("anexos") or []:
            if isinstance(a, dict):
                out.append(a)
    return out


def _nome_anexo_ja_no_disco(external_id: str, nome: str) -> bool:
    alvo = (nome or "").strip().lower()
    if not alvo:
        return False
    for a in listar_anexos_disco(external_id):
        if str(a.get("nome") or "").strip().lower() == alvo:
            return True
    return False


def _bytes_de_item_anexo(client: HubSupportClient, item: dict) -> tuple[bytes, str, str] | None:
    import base64

    if not isinstance(item, dict):
        return None

    nome = str(item.get("nome") or item.get("filename") or item.get("name") or "anexo.bin").strip() or "anexo.bin"
    ct = str(item.get("content_type") or item.get("tipo_mime") or item.get("mime") or "application/octet-stream")

    raw = item.get("conteudo") or item.get("content") or item.get("arquivo") or item.get("file")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw), nome, ct
    if isinstance(raw, str) and raw.strip():
        s = raw.strip()
        if s.startswith("data:") and "," in s:
            try:
                return base64.b64decode(s.split(",", 1)[1]), nome, ct
            except Exception:
                return None

    for key in ("conteudo_base64", "content_base64", "base64", "arquivo_base64", "data_base64"):
        b64 = item.get(key)
        if not b64 or not isinstance(b64, str):
            continue
        try:
            return base64.b64decode(b64.strip()), nome, ct
        except Exception:
            continue

    url = str(
        item.get("url") or item.get("download_url") or item.get("href") or item.get("link") or ""
    ).strip()
    if not url:
        return None

    if url.startswith("/"):
        root = client.base_url.rsplit("/api/", 1)[0] if "/api/" in client.base_url else client.base_url
        url = root.rstrip("/") + url

    try:
        headers = {"Authorization": f"Bearer {client.token}"} if client.token else {}
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code >= 400:
            logger.warning("Falha ao baixar anexo remoto HTTP %s", resp.status_code)
            return None
        return resp.content, nome, ct or (resp.headers.get("Content-Type") or "application/octet-stream")
    except Exception:
        logger.exception("Erro ao baixar anexo remoto")
        return None


def materializar_anexos_remotos(
    conn,
    external_id: str,
    anexos: list | None,
    *,
    client: HubSupportClient | None = None,
    log_fn=None,
) -> list:
    client = client or HubSupportClient(conn=conn)
    metas = []
    for item in anexos or []:
        if not isinstance(item, dict):
            continue
        norm = _normalizar_anexo(item)
        nome = norm.get("nome") or item.get("nome") or "anexo.bin"
        if _nome_anexo_ja_no_disco(external_id, str(nome)):
            for local in listar_anexos_disco(external_id):
                if str(local.get("nome") or "").lower() == str(nome).lower():
                    metas.append(local)
                    break
            continue

        got = _bytes_de_item_anexo(client, item)
        if not got:
            if norm.get("nome"):
                metas.append(norm)
            continue
        conteudo, nome_ok, ct = got
        if not conteudo:
            continue
        meta = guardar_anexo_local(
            external_id,
            nome_ok,
            conteudo,
            ct,
            enviado_por=norm.get("enviado_por") or item.get("enviado_por"),
            enviado_em=norm.get("enviado_em") or item.get("criado_em") or item.get("enviado_em"),
        )
        if norm.get("id"):
            meta["hubsupport_id"] = norm.get("id")
        metas.append(meta)
        if log_fn:
            log_fn(conn, "anexo_materializar", True, f"{nome_ok} ({len(conteudo)} bytes)")
    return metas


def resgatar_anexos_hubsupport(conn, external_id: str, *, hubsupport_id: str | int | None = None, log_fn=None) -> dict:
    external_id = (external_id or "").strip()
    if not external_id.startswith(f"{PREFIX}:chamado:"):
        external_id = external_id_chamado(external_id)

    client = HubSupportClient(conn=conn)
    ref = hubsupport_id or external_id
    if hubsupport_id is None:
        cur = conn.cursor()
        cur.execute(
            "SELECT hubsupport_id FROM tbl_hubsupport_chamado WHERE external_id = %s LIMIT 1",
            (external_id,),
        )
        row = cur.fetchone()
        if row and row[0]:
            ref = row[0]

    try:
        raw = client.listar_anexos(ref)
        lista = normalizar_anexos_lista(raw)
        if not lista and isinstance(raw, (dict, list)):
            lista = _lista_anexos_raw(raw)
        metas = materializar_anexos_remotos(conn, external_id, lista, client=client, log_fn=log_fn)
        if log_fn:
            log_fn(conn, "resgatar_anexos", True, f"ref={ref} n={len(metas)}")
        return {"ok": True, "external_id": external_id, "quantidade": len(metas), "anexos": metas}
    except HubSupportError as e:
        if log_fn:
            log_fn(conn, "resgatar_anexos", False, str(e), e.status_code)
        return {
            "ok": False,
            "external_id": external_id,
            "quantidade": 0,
            "anexos": [],
            "erro": str(e),
            "status_code": e.status_code,
        }


def enviar_anexos_chamado(
    client: HubSupportClient,
    external_id: str,
    anexos: list | None,
    *,
    enviado_por: str | None = None,
) -> list:
    """Persiste local + envia ao HubSupport. Retorna metadados para a thread."""
    metas = []
    if not anexos:
        return metas

    agora = datetime.now(timezone.utc).isoformat()
    for an in anexos:
        if not isinstance(an, dict):
            continue
        nome = (an.get("nome") or "anexo").strip()
        conteudo = an.get("conteudo")
        if not conteudo:
            continue

        meta = guardar_anexo_local(
            external_id,
            nome,
            conteudo,
            an.get("content_type"),
            enviado_por=enviado_por,
            enviado_em=agora,
        )
        try:
            resp_an = client.enviar_anexo(external_id, nome, conteudo, an.get("content_type"))
            remoto = _anexo_de_resposta_upload(resp_an, nome)
            if remoto.get("id"):
                meta["hubsupport_id"] = remoto.get("id")
        except HubSupportError as e:
            raise HubSupportError(f"Falha ao enviar anexo «{nome}» ao HubSupport: {e}") from e

        metas.append(meta)
    return metas
