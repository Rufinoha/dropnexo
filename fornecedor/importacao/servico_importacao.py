# fornecedor/importacao/servico_importacao.py — motor de lotes e tradução de erros de importação
from __future__ import annotations

# ── erro_traducao ─────────────────────────────────────

import re
from typing import Any


def _msg_low(mensagem: str) -> str:
    return (mensagem or "").strip().lower()


def traduzir_mensagem_erro(
    campo: str | None,
    mensagem: str,
    payload: dict | None = None,
    origem: str | None = None,
) -> str:
    """Converte exceção técnica em texto para o usuário."""
    campo_u = (campo or "").strip().upper()
    msg = (mensagem or "").strip()
    msg_low = _msg_low(msg)
    pl = payload or {}
    origem = (origem or pl.get("origem") or "").strip().lower()

    if campo_u == "__HEADER__":
        return "Coluna obrigatória não encontrada no arquivo."

    if campo_u == "__CONFIG__":
        if "competência" in msg_low or "competencia" in msg_low:
            return "Layout incompleto para este tipo de importação."
        return "Layout inválido."

    if campo_u == "__DB__" or "violates" in msg_low or "null value in column" in msg_low:
        return _traduzir_erro_banco(msg, msg_low)

    # Integração Bling / Python interno
    if "nonetype" in msg_low and "not subscriptable" in msg_low:
        return (
            "Não foi possível gravar o produto: o vínculo com o catálogo local está inconsistente "
            "(registro mapeado ausente ou inválido). Tente reimportar; se persistir, remova o vínculo "
            "antigo na integração Bling."
        )

    if "sku obrigatório" in msg_low or "sku obrigatorio" in msg_low:
        return "SKU obrigatório: o produto no Bling não possui código (SKU)."

    if "produto pai não encontrado" in msg_low or "produto pai nao encontrado" in msg_low:
        return "Produto pai não encontrado na API do Bling."

    if "nenhuma variação importada" in msg_low or "nenhuma variacao importada" in msg_low:
        return "Grupo de variações rejeitado: todas as variações precisam ser válidas (regra tudo ou nada)."

    if "imagem excede" in msg_low:
        return "Imagem maior que 3 MB — reduza ou altere o modo de importação de imagens."

    if "timeout" in msg_low or "timed out" in msg_low:
        return "Tempo esgotado ao comunicar com o Bling. Tente novamente em instantes."

    if "401" in msg or "403" in msg or "unauthorized" in msg_low:
        return "Falha de autenticação com o Bling. Reconecte a integração."

    if "429" in msg or "rate limit" in msg_low:
        return "Limite de requisições do Bling atingido. Aguarde e tente novamente."

    if origem == "bling" and msg_low.startswith("valueerror"):
        return msg.split(":", 1)[-1].strip() or "Dados inválidos retornados pelo Bling."

    # Validações de negócio comuns (CSV / layout)
    if "campo obrigatório" in msg_low or "campo obrigatorio" in msg_low:
        return "Campo obrigatório não preenchido."

    if "nome obrigatório" in msg_low or "nome obrigatorio" in msg_low:
        return "Nome do produto é obrigatório."

    if "máximo de" in msg_low and "linhas" in msg_low:
        return msg

    if "valor inválido" in msg_low or "valor invalido" in msg_low:
        return "Valor inválido na linha importada."

    if "duplicate key" in msg_low or "unique constraint" in msg_low or "já existe" in msg_low:
        return "Registro duplicado (SKU ou identificador já existente)."

    return msg or "Erro de importação."


def _traduzir_erro_banco(msg: str, msg_low: str) -> str:
    if (
        "null value in column" in msg_low
        or "not-null constraint" in msg_low
        or "violates not-null constraint" in msg_low
    ):
        return "Campo obrigatório não preenchido."

    if "duplicate key" in msg_low or "unique constraint" in msg_low:
        return "Valor já existe no banco (duplicado)."

    if "violates foreign key constraint" in msg_low:
        return "Referência inválida: valor relacionado não encontrado."

    if "invalid input syntax for type numeric" in msg_low:
        return "Número inválido."

    if "invalid input syntax for type integer" in msg_low:
        return "Número inteiro inválido."

    if "invalid input syntax for type date" in msg_low:
        return "Data inválida."

    if "value too long for type" in msg_low:
        return "Texto maior que o tamanho permitido."

    if "tuple index out of range" in msg_low:
        return "Estrutura de gravação incompatível (quantidade de campos)."

    return msg or "Falha ao gravar registro no banco."


def obter_dica_erro(
    mensagem_tecnica: str,
    payload: dict | None = None,
    origem: str | None = None,
) -> str:
    """Sugestão prática para o usuário."""
    msg_low = _msg_low(mensagem_tecnica)
    pl = payload or {}
    origem = (origem or pl.get("origem") or "").strip().lower()

    if "nonetype" in msg_low and "not subscriptable" in msg_low:
        return (
            "Verifique se o produto ainda existe no DropNexo. Se foi excluído manualmente, "
            "desvincule-o no Bling ou limpe tbl_integracao_map e importe novamente."
        )

    if "sku obrigatório" in msg_low or "sku obrigatorio" in msg_low:
        return "No Bling, preencha o campo Código (SKU) do produto e reimporte."

    if origem == "bling" and pl.get("id_bling"):
        return f"Abra o produto #{pl.get('id_bling')} no Bling, corrija os dados e execute a importação de novo."

    if pl.get("linha_arquivo"):
        return f"Corrija a linha {pl.get('linha_arquivo')} do arquivo e importe novamente."

    return "Corrija o registro na origem e repita a importação."


def classificar_erro(mensagem_tecnica: str, origem: str | None = None) -> str:
    """Categoria curta para badge na UI."""
    msg_low = _msg_low(mensagem_tecnica)
    origem = (origem or "").lower()

    if origem == "bling":
        return "Integração Bling"
    if origem == "arquivo":
        return "Arquivo CSV"
    if "nonetype" in msg_low:
        return "Vínculo inconsistente"
    if "sku" in msg_low:
        return "Dados incompletos"
    if "violates" in msg_low or "constraint" in msg_low:
        return "Banco de dados"
    return "Importação"


def enriquecer_erro(
    *,
    id: int,
    linha_arquivo: int | None,
    ref_externa: str | None,
    nome: str | None,
    sku: str | None,
    campo: str | None,
    mensagem: str,
    payload: Any,
    corrigido: bool,
    criado_em: str | None,
) -> dict:
    """Normaliza linha de tbl_importacao_erro para a API/UI."""
    pl: dict = {}
    if isinstance(payload, dict):
        pl = payload
    elif isinstance(payload, str) and payload.strip():
        try:
            import json

            pl = json.loads(payload)
        except Exception:
            pl = {"raw": payload}

    tecnica = (pl.get("mensagem_tecnica") or mensagem or "").strip()
    origem = pl.get("origem")
    amigavel = traduzir_mensagem_erro(campo, tecnica, pl, origem)
    # Registros antigos já gravados com mensagem amigável
    if not pl.get("mensagem_tecnica") and mensagem and mensagem != tecnica:
        amigavel = mensagem

    categoria = classificar_erro(tecnica, origem)
    dica = pl.get("dica") or obter_dica_erro(tecnica, pl, origem)

    detalhe = {
        "id": id,
        "linha_arquivo": linha_arquivo,
        "ref_externa": ref_externa,
        "nome": nome,
        "sku": sku,
        "campo": campo,
        "mensagem": amigavel,
        "mensagem_tecnica": tecnica,
        "categoria": categoria,
        "dica": dica,
        "corrigido": corrigido,
        "criado_em": criado_em,
        "payload": pl,
    }
    return detalhe


def montar_payload_erro(
    *,
    mensagem_tecnica: str,
    origem: str,
    campo: str | None = None,
    extra: dict | None = None,
    traceback_txt: str | None = None,
) -> dict:
    pl: dict = {"origem": origem, "mensagem_tecnica": mensagem_tecnica}
    if campo:
        pl["campo_original"] = campo
    if traceback_txt:
        pl["traceback"] = traceback_txt[-3000:]
    if extra:
        pl.update(extra)
    pl["dica"] = obter_dica_erro(mensagem_tecnica, pl, origem)
    pl["categoria"] = classificar_erro(mensagem_tecnica, origem)
    return pl


# ── servico_importacao ────────────────────────────────

import json
from datetime import datetime
from typing import Any

from global_utils import agora_utc

MODULO_CATALOGO = "catalogo_produto"

ORIGEM_MANUAL = "manual"
ORIGEM_ARQUIVO = "arquivo"
ORIGEM_INTEGRACAO = "integracao"

STATUS_PROCESSANDO = "processando"
STATUS_CONCLUIDO = "concluido"
STATUS_ERRO = "erro"
STATUS_CANCELADO = "cancelado"


def gerar_numero_lote(cur, id_tenant: int) -> str:
    ano = datetime.now().year
    prefixo = f"IMP-{ano}-"
    cur.execute(
        """
        SELECT numero FROM tbl_importacao_lote
        WHERE id_tenant = %s AND numero LIKE %s
        ORDER BY id DESC LIMIT 1
        """,
        (id_tenant, prefixo + "%"),
    )
    row = cur.fetchone()
    seq = 1
    if row and row[0]:
        try:
            seq = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefixo}{seq:06d}"


def criar_lote(
    cur,
    *,
    id_tenant: int,
    modulo: str,
    origem: str,
    id_usuario: int | None = None,
    provedor: str | None = None,
    id_layout: int | None = None,
    nome_lote: str | None = None,
    nome_arquivo: str | None = None,
    meta: dict | None = None,
) -> tuple[int, str]:
    numero = gerar_numero_lote(cur, id_tenant)
    cur.execute(
        """
        INSERT INTO tbl_importacao_lote (
            id_tenant, numero, modulo, origem, provedor, id_layout,
            nome_lote, nome_arquivo, status, meta, importado_por, importado_em
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s
        ) RETURNING id
        """,
        (
            id_tenant,
            numero,
            modulo,
            origem,
            provedor,
            id_layout,
            nome_lote,
            nome_arquivo,
            STATUS_PROCESSANDO,
            json.dumps(meta or {}),
            id_usuario,
            agora_utc(),
        ),
    )
    return int(cur.fetchone()[0]), numero


def registrar_erro_lote(
    cur,
    *,
    id_tenant: int,
    id_lote: int,
    modulo: str,
    mensagem: str,
    linha_arquivo: int | None = None,
    ref_externa: str | None = None,
    nome_registro: str | None = None,
    sku_registro: str | None = None,
    campo: str | None = None,
    payload: dict | None = None,
    origem: str | None = None,
) -> None:
    pl = dict(payload or {})
    tecnica = (pl.get("mensagem_tecnica") or mensagem or "").strip()
    if "mensagem_tecnica" not in pl:
        pl["mensagem_tecnica"] = tecnica
    if origem and "origem" not in pl:
        pl["origem"] = origem
    if linha_arquivo is not None and "linha_arquivo" not in pl:
        pl["linha_arquivo"] = linha_arquivo
    if ref_externa and "id_bling" not in pl and origem == "bling":
        pl["id_bling"] = ref_externa

    msg_amigavel = traduzir_mensagem_erro(campo, tecnica, pl, pl.get("origem"))

    cur.execute(
        """
        INSERT INTO tbl_importacao_erro (
            id_tenant, id_importacao_lote, modulo, linha_arquivo, ref_externa,
            nome_registro, sku_registro, campo, mensagem, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            id_tenant,
            id_lote,
            modulo,
            linha_arquivo,
            ref_externa,
            nome_registro,
            sku_registro,
            campo,
            msg_amigavel,
            json.dumps(pl),
        ),
    )


def atualizar_progresso_lote(
    cur,
    id_lote: int,
    *,
    total: int,
    processados: int,
    importados: int,
    atualizados: int,
    rejeitadas: int,
    ignorados: int = 0,
    meta_patch: dict | None = None,
) -> None:
    """Atualiza contadores visíveis durante importação assíncrona (polling)."""
    patch: dict[str, Any] = {
        "processados": processados,
        "ignorados": ignorados,
        "total_jobs": total,
        "fase": "processando",
    }
    if meta_patch:
        patch.update(meta_patch)
    cur.execute(
        """
        UPDATE tbl_importacao_lote SET
            status = %s,
            total_linhas = %s,
            total_importadas = %s,
            total_atualizadas = %s,
            total_rejeitadas = %s,
            meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb
        WHERE id = %s
        """,
        (
            STATUS_PROCESSANDO,
            total,
            importados,
            atualizados,
            rejeitadas,
            json.dumps(patch),
            id_lote,
        ),
    )


def marcar_lote_erro_fatal(cur, id_lote: int, mensagem: str) -> None:
    cur.execute(
        """
        UPDATE tbl_importacao_lote SET
            status = %s,
            meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb,
            finalizado_em = %s
        WHERE id = %s
        """,
        (
            STATUS_ERRO,
            json.dumps({"erro_fatal": mensagem[:900], "fase": "erro"}),
            agora_utc(),
            id_lote,
        ),
    )


def obter_meta_lote(cur, id_tenant: int, id_lote: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT meta FROM tbl_importacao_lote
        WHERE id = %s AND id_tenant = %s
        """,
        (id_lote, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        return {}
    raw = row[0]
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def progresso_importacao_dict(lote: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    total = int(lote.get("total_linhas") or meta.get("total_jobs") or 0)
    processados = int(meta.get("processados") or 0)
    status = (lote.get("status") or STATUS_PROCESSANDO).lower()
    concluido = status in (STATUS_CONCLUIDO, STATUS_ERRO, STATUS_CANCELADO)
    pct = round((processados / total) * 100) if total > 0 else (100 if concluido else 0)
    return {
        "id_lote": lote.get("id"),
        "numero": lote.get("numero"),
        "status": status,
        "fase": meta.get("fase") or ("concluido" if concluido else "processando"),
        "total": total,
        "processados": processados,
        "importados": int(lote.get("total_importadas") or 0),
        "atualizados": int(lote.get("total_atualizadas") or 0),
        "erros": int(lote.get("total_rejeitadas") or 0),
        "ignorados": int(meta.get("ignorados") or 0),
        "percentual": min(pct, 100),
        "concluido": concluido,
        "mensagem": meta.get("mensagem"),
        "erro_fatal": meta.get("erro_fatal"),
        "status_importacao": meta.get("status_importacao"),
    }


def finalizar_lote(
    cur,
    id_lote: int,
    *,
    status: str,
    total_linhas: int = 0,
    total_importadas: int = 0,
    total_atualizadas: int = 0,
    total_rejeitadas: int = 0,
    meta: dict | None = None,
) -> None:
    if meta:
        cur.execute(
            """
            UPDATE tbl_importacao_lote SET
                status = %s, total_linhas = %s, total_importadas = %s,
                total_atualizadas = %s, total_rejeitadas = %s,
                meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb,
                finalizado_em = %s
            WHERE id = %s
            """,
            (
                status,
                total_linhas,
                total_importadas,
                total_atualizadas,
                total_rejeitadas,
                json.dumps(meta),
                agora_utc(),
                id_lote,
            ),
        )
    else:
        cur.execute(
            """
            UPDATE tbl_importacao_lote SET
                status = %s, total_linhas = %s, total_importadas = %s,
                total_atualizadas = %s, total_rejeitadas = %s, finalizado_em = %s
            WHERE id = %s
            """,
            (
                status,
                total_linhas,
                total_importadas,
                total_atualizadas,
                total_rejeitadas,
                agora_utc(),
                id_lote,
            ),
        )


def lote_para_dict(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "numero": row[1],
        "modulo": row[2],
        "origem": row[3],
        "provedor": row[4],
        "nome_lote": row[5],
        "nome_arquivo": row[6],
        "status": row[7],
        "total_linhas": row[8],
        "total_importadas": row[9],
        "total_atualizadas": row[10],
        "total_rejeitadas": row[11],
        "importado_em": row[12].isoformat() if row[12] else None,
        "finalizado_em": row[13].isoformat() if row[13] else None,
        "importado_por": row[14],
        "importado_por_nome": row[15],
    }


_LOTE_COLS = """
    l.id, l.numero, l.modulo, l.origem, l.provedor, l.nome_lote, l.nome_arquivo,
    l.status, l.total_linhas, l.total_importadas, l.total_atualizadas, l.total_rejeitadas,
    l.importado_em, l.finalizado_em, l.importado_por, u.nome
"""


def obter_lote(cur, id_tenant: int, id_lote: int, modulo: str | None = None) -> dict | None:
    sql = f"""
        SELECT {_LOTE_COLS}
        FROM tbl_importacao_lote l
        LEFT JOIN tbl_usuario u ON u.id = l.importado_por
        WHERE l.id = %s AND l.id_tenant = %s
    """
    params: list[Any] = [id_lote, id_tenant]
    if modulo:
        sql += " AND l.modulo = %s"
        params.append(modulo)
    cur.execute(sql, params)
    row = cur.fetchone()
    return lote_para_dict(row) if row else None


def listar_lotes(
    cur,
    id_tenant: int,
    *,
    modulo: str = MODULO_CATALOGO,
    data_de: str | None = None,
    data_ate: str | None = None,
    limite: int = 100,
) -> list[dict]:
    sql = f"""
        SELECT {_LOTE_COLS}
        FROM tbl_importacao_lote l
        LEFT JOIN tbl_usuario u ON u.id = l.importado_por
        WHERE l.id_tenant = %s AND l.modulo = %s
    """
    params: list[Any] = [id_tenant, modulo]
    if data_de:
        sql += " AND l.importado_em::date >= %s::date"
        params.append(data_de)
    if data_ate:
        sql += " AND l.importado_em::date <= %s::date"
        params.append(data_ate)
    sql += " ORDER BY l.importado_em DESC, l.id DESC LIMIT %s"
    params.append(limite)
    cur.execute(sql, params)
    return [lote_para_dict(r) for r in cur.fetchall()]


def listar_erros_lote(cur, id_tenant: int, id_lote: int, limite: int = 500) -> list[dict]:
    cur.execute(
        """
        SELECT id, linha_arquivo, ref_externa, nome_registro, sku_registro,
               campo, mensagem, payload, corrigido, criado_em
        FROM tbl_importacao_erro
        WHERE id_tenant = %s AND id_importacao_lote = %s
        ORDER BY COALESCE(linha_arquivo, 999999), id
        LIMIT %s
        """,
        (id_tenant, id_lote, limite),
    )
    rows = []
    for r in cur.fetchall():
        payload_raw = r[7]
        if isinstance(payload_raw, str):
            try:
                payload_raw = json.loads(payload_raw)
            except Exception:
                payload_raw = {}
        rows.append(
            enriquecer_erro(
                id=r[0],
                linha_arquivo=r[1],
                ref_externa=r[2],
                nome=r[3],
                sku=r[4],
                campo=r[5],
                mensagem=r[6],
                payload=payload_raw or {},
                corrigido=r[8],
                criado_em=r[9].isoformat() if r[9] else None,
            )
        )
    return rows


def ultimo_lote(
    cur,
    id_tenant: int,
    modulo: str = MODULO_CATALOGO,
    origem: str | None = None,
) -> dict | None:
    filtro_origem = "AND l.origem = %s" if origem else ""
    params: list = [id_tenant, modulo]
    if origem:
        params.append(origem)
    cur.execute(
        f"""
        SELECT {_LOTE_COLS}
        FROM tbl_importacao_lote l
        LEFT JOIN tbl_usuario u ON u.id = l.importado_por
        WHERE l.id_tenant = %s AND l.modulo = %s {filtro_origem}
        ORDER BY l.importado_em DESC, l.id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    row = cur.fetchone()
    return lote_para_dict(row) if row else None


def excluir_lote(cur, id_tenant: int, id_lote: int, modulo: str = MODULO_CATALOGO) -> dict[str, int]:
    cur.execute(
        """
        SELECT id FROM tbl_importacao_lote
        WHERE id = %s AND id_tenant = %s AND modulo = %s
        """,
        (id_lote, id_tenant, modulo),
    )
    if not cur.fetchone():
        raise ValueError("Lote de importação não encontrado.")

    cur.execute(
        """
        SELECT COUNT(*) FROM tbl_produto
        WHERE id_tenant = %s AND id_importacao_lote = %s AND origem = 'editado'
        """,
        (id_tenant, id_lote),
    )
    editados = int(cur.fetchone()[0] or 0)
    if editados:
        raise ValueError(
            f"Não é possível excluir: {editados} produto(s) deste lote foram editados manualmente depois."
        )

    cur.execute(
        """
        SELECT id FROM tbl_produto
        WHERE id_tenant = %s AND id_importacao_lote = %s
          AND origem IN ('arquivo', 'integracao')
        """,
        (id_tenant, id_lote),
    )
    ids_produto = [int(r[0]) for r in cur.fetchall()]
    removidos = len(ids_produto)

    if ids_produto:
        cur.execute(
            """
            DELETE FROM tbl_integracao_map
            WHERE id_tenant = %s AND entidade = 'produto' AND id_dropnexo = ANY(%s)
            """,
            (id_tenant, ids_produto),
        )
        cur.execute(
            """
            DELETE FROM tbl_produto
            WHERE id_tenant = %s AND id = ANY(%s)
              AND origem IN ('arquivo', 'integracao')
            """,
            (id_tenant, ids_produto),
        )

    cur.execute(
        "DELETE FROM tbl_importacao_erro WHERE id_tenant = %s AND id_importacao_lote = %s",
        (id_tenant, id_lote),
    )
    cur.execute(
        "DELETE FROM tbl_importacao_lote WHERE id = %s AND id_tenant = %s",
        (id_lote, id_tenant),
    )
    return {"produtos_removidos": removidos}


def garantir_layout_padrao_csv(cur, id_tenant: int) -> int:
    cur.execute(
        """
        SELECT id FROM tbl_importacao_layout
        WHERE id_tenant = %s AND modulo = %s AND padrao = TRUE
        LIMIT 1
        """,
        (id_tenant, MODULO_CATALOGO),
    )
    row = cur.fetchone()
    if row:
        return int(row[0])

    cur.execute(
        """
        INSERT INTO tbl_importacao_layout (
            id_tenant, modulo, nome, descricao, ativo, padrao, tipo_arquivo
        ) VALUES (%s, %s, %s, %s, TRUE, TRUE, 'csv')
        RETURNING id
        """,
        (
            id_tenant,
            MODULO_CATALOGO,
            "Catálogo CSV padrão",
            "sku;nome;descricao;preco;preco_promocional;quantidade;categoria;unidade;publicado;ativo",
        ),
    )
    id_layout = int(cur.fetchone()[0])
    campos = [
        ("sku", "sku", False, 1),
        ("nome", "nome", True, 2),
        ("descricao", "descricao", False, 3),
        ("preco", "preco", False, 4),
        ("preco_promocional", "preco_promocional", False, 5),
        ("quantidade", "quantidade", False, 6),
        ("categoria", "categoria", False, 7),
        ("unidade", "unidade", False, 8),
        ("publicado", "publicado", False, 9),
        ("ativo", "ativo", False, 10),
    ]
    for campo, coluna, obrig, ordem in campos:
        cur.execute(
            """
            INSERT INTO tbl_importacao_layout_campo (
                id_layout, campo_interno, coluna_arquivo, obrigatorio, ordem
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (id_layout, campo, coluna, obrig, ordem),
        )
    return id_layout


def listar_layouts(cur, id_tenant: int, modulo: str = MODULO_CATALOGO) -> list[dict]:
    garantir_layout_padrao_csv(cur, id_tenant)
    cur.execute(
        """
        SELECT id, nome, descricao, ativo, padrao, tipo_arquivo
        FROM tbl_importacao_layout
        WHERE id_tenant = %s AND modulo = %s
        ORDER BY padrao DESC, nome
        """,
        (id_tenant, modulo),
    )
    return [
        {
            "id": r[0],
            "nome": r[1],
            "descricao": r[2],
            "ativo": r[3],
            "padrao": r[4],
            "tipo_arquivo": r[5],
        }
        for r in cur.fetchall()
    ]


MAX_LAYOUTS_POR_MODULO = 3

CAMPOS_BASE_CATALOGO = [
    {"campo_interno": "sku", "obrigatorio": False, "ordem": 1},
    {"campo_interno": "nome", "obrigatorio": True, "ordem": 2},
    {"campo_interno": "descricao", "obrigatorio": False, "ordem": 3},
    {"campo_interno": "preco", "obrigatorio": False, "ordem": 4},
    {"campo_interno": "preco_promocional", "obrigatorio": False, "ordem": 5},
    {"campo_interno": "quantidade", "obrigatorio": False, "ordem": 6},
    {"campo_interno": "categoria", "obrigatorio": False, "ordem": 7},
    {"campo_interno": "unidade", "obrigatorio": False, "ordem": 8},
    {"campo_interno": "publicado", "obrigatorio": False, "ordem": 9},
    {"campo_interno": "ativo", "obrigatorio": False, "ordem": 10},
]


def campos_base_layout(modulo: str = MODULO_CATALOGO) -> list[dict]:
    if modulo == MODULO_CATALOGO:
        return [dict(c) for c in CAMPOS_BASE_CATALOGO]
    return []


def listar_layouts_admin(
    cur,
    id_tenant: int,
    modulo: str = MODULO_CATALOGO,
    *,
    nome: str | None = None,
    status: str | None = None,
    padrao: str | None = None,
) -> list[dict]:
    garantir_layout_padrao_csv(cur, id_tenant)
    filtros = ["id_tenant = %s", "modulo = %s"]
    params: list[Any] = [id_tenant, modulo]
    if nome:
        filtros.append("nome ILIKE %s")
        params.append(f"%{nome}%")
    st = (status or "").strip().lower()
    if st == "ativo":
        filtros.append("ativo = TRUE")
    elif st == "inativo":
        filtros.append("ativo = FALSE")
    pd = (padrao or "").strip().lower()
    if pd in ("sim", "s", "1", "true"):
        filtros.append("padrao = TRUE")
    elif pd in ("nao", "não", "n", "0", "false"):
        filtros.append("padrao = FALSE")
    cur.execute(
        f"""
        SELECT id, nome, descricao, ativo, padrao, tipo_arquivo
        FROM tbl_importacao_layout
        WHERE {" AND ".join(filtros)}
        ORDER BY padrao DESC, nome
        """,
        tuple(params),
    )
    return [
        {
            "id": r[0],
            "nome": r[1],
            "nome_layout": r[1],
            "descricao": r[2],
            "ativo": r[3],
            "padrao": r[4],
            "tipo_arquivo": r[5],
        }
        for r in cur.fetchall()
    ]


def obter_layout_detalhe(cur, id_tenant: int, id_layout: int, modulo: str = MODULO_CATALOGO) -> dict | None:
    cur.execute(
        """
        SELECT id, nome, descricao, ativo, padrao, modulo, tipo_arquivo
        FROM tbl_importacao_layout
        WHERE id = %s AND id_tenant = %s AND modulo = %s
        """,
        (id_layout, id_tenant, modulo),
    )
    row = cur.fetchone()
    if not row:
        return None
    layout = {
        "id": row[0],
        "nome": row[1],
        "nome_layout": row[1],
        "descricao": row[2],
        "ativo": row[3],
        "padrao": row[4],
        "modulo": row[5],
        "tipo_arquivo": row[6],
    }
    cur.execute(
        """
        SELECT id, campo_interno, coluna_arquivo, obrigatorio, ordem
        FROM tbl_importacao_layout_campo
        WHERE id_layout = %s
        ORDER BY ordem, id
        """,
        (id_layout,),
    )
    layout["campos"] = [
        {
            "id": r[0],
            "campo_interno": r[1],
            "coluna_arquivo": r[2],
            "obrigatorio": r[3],
            "ordem": r[4],
        }
        for r in cur.fetchall()
    ]
    return layout


def _contar_layouts(cur, id_tenant: int, modulo: str) -> int:
    cur.execute(
        "SELECT COUNT(*) FROM tbl_importacao_layout WHERE id_tenant = %s AND modulo = %s",
        (id_tenant, modulo),
    )
    return int(cur.fetchone()[0] or 0)


def salvar_layout_importacao(cur, id_tenant: int, payload: dict) -> int:
    modulo = (payload.get("modulo") or MODULO_CATALOGO).strip()
    nome = (payload.get("nome") or payload.get("nome_layout") or "").strip()
    if not nome:
        raise ValueError("Nome do layout é obrigatório.")
    descricao = (payload.get("descricao") or "").strip() or None
    ativo = bool(payload.get("ativo", True))
    padrao = bool(payload.get("padrao", False))
    campos = payload.get("campos") if isinstance(payload.get("campos"), list) else []
    layout_id = payload.get("id")

    if padrao:
        cur.execute(
            "UPDATE tbl_importacao_layout SET padrao = FALSE WHERE id_tenant = %s AND modulo = %s",
            (id_tenant, modulo),
        )

    if layout_id:
        id_layout = int(layout_id)
        cur.execute(
            """
            SELECT id FROM tbl_importacao_layout
            WHERE id = %s AND id_tenant = %s AND modulo = %s
            """,
            (id_layout, id_tenant, modulo),
        )
        if not cur.fetchone():
            raise ValueError("Layout não encontrado.")
        cur.execute(
            """
            UPDATE tbl_importacao_layout
            SET nome = %s, descricao = %s, ativo = %s, padrao = %s
            WHERE id = %s AND id_tenant = %s
            """,
            (nome, descricao, ativo, padrao, id_layout, id_tenant),
        )
        cur.execute("DELETE FROM tbl_importacao_layout_campo WHERE id_layout = %s", (id_layout,))
    else:
        if _contar_layouts(cur, id_tenant, modulo) >= MAX_LAYOUTS_POR_MODULO:
            raise ValueError(f"Máximo de {MAX_LAYOUTS_POR_MODULO} layouts por módulo.")
        cur.execute(
            """
            INSERT INTO tbl_importacao_layout (
                id_tenant, modulo, nome, descricao, ativo, padrao, tipo_arquivo
            ) VALUES (%s, %s, %s, %s, %s, %s, 'csv')
            RETURNING id
            """,
            (id_tenant, modulo, nome, descricao, ativo, padrao),
        )
        id_layout = int(cur.fetchone()[0])

    ordem_auto = 1
    for c in campos:
        campo = (c.get("campo_interno") or "").strip()
        if not campo:
            continue
        coluna = (c.get("coluna_arquivo") or campo).strip()
        obrig = bool(c.get("obrigatorio", False))
        try:
            ordem = int(c.get("ordem") or ordem_auto)
        except (TypeError, ValueError):
            ordem = ordem_auto
        cur.execute(
            """
            INSERT INTO tbl_importacao_layout_campo (
                id_layout, campo_interno, coluna_arquivo, obrigatorio, ordem
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (id_layout, campo, coluna, obrig, ordem),
        )
        ordem_auto += 1

    return id_layout


def excluir_layout_importacao(cur, id_tenant: int, id_layout: int, modulo: str = MODULO_CATALOGO) -> None:
    cur.execute(
        """
        SELECT padrao FROM tbl_importacao_layout
        WHERE id = %s AND id_tenant = %s AND modulo = %s
        """,
        (id_layout, id_tenant, modulo),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Layout não encontrado.")
    cur.execute(
        "SELECT COUNT(*) FROM tbl_importacao_layout WHERE id_tenant = %s AND modulo = %s",
        (id_tenant, modulo),
    )
    total = int(cur.fetchone()[0] or 0)
    if total <= 1:
        raise ValueError("Não é possível excluir o único layout do módulo.")
    cur.execute("DELETE FROM tbl_importacao_layout_campo WHERE id_layout = %s", (id_layout,))
    cur.execute(
        "DELETE FROM tbl_importacao_layout WHERE id = %s AND id_tenant = %s AND modulo = %s",
        (id_layout, id_tenant, modulo),
    )
    if row[0]:
        cur.execute(
            """
            UPDATE tbl_importacao_layout SET padrao = TRUE
            WHERE id = (
                SELECT id FROM tbl_importacao_layout
                WHERE id_tenant = %s AND modulo = %s
                ORDER BY id LIMIT 1
            )
            """,
            (id_tenant, modulo),
        )


def definir_layout_padrao(cur, id_tenant: int, id_layout: int, modulo: str = MODULO_CATALOGO) -> None:
    cur.execute(
        """
        SELECT id FROM tbl_importacao_layout
        WHERE id = %s AND id_tenant = %s AND modulo = %s
        """,
        (id_layout, id_tenant, modulo),
    )
    if not cur.fetchone():
        raise ValueError("Layout não encontrado.")
    cur.execute(
        "UPDATE tbl_importacao_layout SET padrao = FALSE WHERE id_tenant = %s AND modulo = %s",
        (id_tenant, modulo),
    )
    cur.execute(
        "UPDATE tbl_importacao_layout SET padrao = TRUE WHERE id = %s AND id_tenant = %s",
        (id_layout, id_tenant),
    )


def rotulo_origem(origem: str) -> str:
    return {
        ORIGEM_MANUAL: "Manual",
        ORIGEM_ARQUIVO: "Arquivo",
        ORIGEM_INTEGRACAO: "Integração",
    }.get(origem, origem)


def obter_cards_importacao(
    cur,
    id_tenant: int,
    id_lote: int | None = None,
    origem: str | None = None,
) -> dict:
    if id_lote:
        lote = obter_lote(cur, id_tenant, id_lote)
    else:
        lote = ultimo_lote(cur, id_tenant, origem=origem)
    if not lote:
        return {}
    cur.execute(
        """
        SELECT COUNT(*) FROM tbl_importacao_erro
        WHERE id_tenant = %s AND id_importacao_lote = %s
        """,
        (id_tenant, lote["id"]),
    )
    qtd_erros = int(cur.fetchone()[0] or 0)
    rejeitadas = int(lote.get("total_rejeitadas") or 0)
    return {
        "lote": lote["id"],
        "numero": lote.get("numero"),
        "total": int(lote.get("total_linhas") or 0),
        "inseridas": int(lote.get("total_importadas") or 0),
        "atualizadas": int(lote.get("total_atualizadas") or 0),
        "erros": max(rejeitadas, qtd_erros),
        "nome_arquivo": lote.get("nome_arquivo") or lote.get("nome_lote") or lote.get("numero") or "",
        "origem": lote.get("origem"),
        "origem_rotulo": rotulo_origem(lote.get("origem") or ""),
        "importado_em": lote.get("importado_em"),
    }
