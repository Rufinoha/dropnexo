# sistema/planos/fornecedor_acompanhamento.py — fase e histórico de contato
from __future__ import annotations

from typing import Any

FASES = (
    "cadastrado",
    "boas_vindas",
    "cadastrando",
    "lembrete",
    "ativo",
    "eh_vendedor",
    "sem_resposta",
    "desistiu",
)

FASE_ROTULO = {
    "cadastrado": "Cadastrado",
    "boas_vindas": "Boas-vindas",
    "cadastrando": "Cadastrando",
    "lembrete": "Lembrete",
    "ativo": "Ativo",
    "eh_vendedor": "É vendedor",
    "sem_resposta": "Sem resposta",
    "desistiu": "Desistiu",
}

CANAIS = ("whatsapp", "email", "telefone", "outro")
DIRECOES = ("enviado", "recebido")


def _tem_coluna_tenant(cur, coluna: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema IN (current_schema(), 'public')
          AND table_name = 'tbl_tenant'
          AND column_name = %s
        LIMIT 1
        """,
        (coluna,),
    )
    return bool(cur.fetchone())


def _tem_tabela_contato(cur) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema IN (current_schema(), 'public')
          AND table_name = 'tbl_fornecedor_contato'
        LIMIT 1
        """
    )
    return bool(cur.fetchone())


def fase_ok(fase: str | None) -> bool:
    if fase is None or fase == "":
        return True
    return fase in FASES


def validar_fase(fase: str | None) -> str | None:
    if fase is None or str(fase).strip() == "":
        return None
    f = str(fase).strip().lower()
    if f not in FASES:
        raise ValueError(f"Fase inválida: {fase}")
    return f


def definir_fase(
    cur,
    id_tenant: int,
    fase: str | None,
    *,
    autor: str = "",
    motivo: str | None = None,
    registrar_historico: bool = True,
) -> dict[str, Any]:
    """Atualiza fornecedor_fase. Opcionalmente grava linha no histórico."""
    if not _tem_coluna_tenant(cur, "fornecedor_fase"):
        raise ValueError("Migração de fase ainda não aplicada (sql/23).")
    fase_n = validar_fase(fase)
    tid = int(id_tenant)
    cur.execute(
        """
        UPDATE tbl_tenant
           SET fornecedor_fase = %s,
               fornecedor_fase_em = CASE
                 WHEN %s IS NULL THEN NULL
                 ELSE NOW()
               END
         WHERE id = %s
           AND tipo_negocio IN ('fornecedor', 'hibrido')
        RETURNING id, fornecedor_fase, fornecedor_fase_em
        """,
        (fase_n, fase_n, tid),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Fornecedor não encontrado.")
    if registrar_historico and _tem_tabela_contato(cur):
        resumo = (motivo or "").strip() or (
            f"Fase alterada para {FASE_ROTULO.get(fase_n or '', fase_n or '—')}."
        )
        registrar_contato(
            cur,
            tid,
            canal="outro",
            direcao="enviado",
            resumo=resumo[:500],
            fase_apos=fase_n,
            autor=autor or "Sistema",
            aplicar_fase=False,
        )
    return {
        "id": int(row[0]),
        "fase": row[1],
        "fase_em": row[2].isoformat() if row[2] else None,
    }


def registrar_contato(
    cur,
    id_tenant: int,
    *,
    canal: str,
    direcao: str,
    resumo: str,
    fase_apos: str | None = None,
    autor: str = "",
    aplicar_fase: bool = True,
) -> dict[str, Any]:
    if not _tem_tabela_contato(cur):
        raise ValueError("Migração de contato ainda não aplicada (sql/23).")
    canal_n = (canal or "").strip().lower()
    direcao_n = (direcao or "").strip().lower()
    if canal_n not in CANAIS:
        raise ValueError("Canal inválido.")
    if direcao_n not in DIRECOES:
        raise ValueError("Direção inválida.")
    texto = (resumo or "").strip()
    if not texto:
        raise ValueError("Informe um resumo do contato.")
    if len(texto) > 500:
        raise ValueError("Resumo com no máximo 500 caracteres.")
    fase_n = validar_fase(fase_apos)
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT 1 FROM tbl_tenant
         WHERE id = %s AND tipo_negocio IN ('fornecedor', 'hibrido')
        """,
        (tid,),
    )
    if not cur.fetchone():
        raise ValueError("Fornecedor não encontrado.")

    if aplicar_fase and fase_n is not None and _tem_coluna_tenant(cur, "fornecedor_fase"):
        cur.execute(
            """
            UPDATE tbl_tenant
               SET fornecedor_fase = %s, fornecedor_fase_em = NOW()
             WHERE id = %s
            """,
            (fase_n, tid),
        )

    cur.execute(
        """
        INSERT INTO tbl_fornecedor_contato
          (id_tenant, canal, direcao, resumo, fase_apos, autor)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, criado_em, canal, direcao, resumo, fase_apos, autor
        """,
        (tid, canal_n, direcao_n, texto, fase_n, (autor or "").strip()[:120]),
    )
    row = cur.fetchone()
    return {
        "id": int(row[0]),
        "criado_em": row[1].isoformat() if row[1] else None,
        "canal": row[2],
        "direcao": row[3],
        "resumo": row[4],
        "fase_apos": row[5],
        "autor": row[6] or "",
    }


def listar_contatos(cur, id_tenant: int, *, limite: int = 100) -> list[dict[str, Any]]:
    if not _tem_tabela_contato(cur):
        return []
    lim = max(1, min(int(limite or 100), 500))
    cur.execute(
        """
        SELECT id, criado_em, canal, direcao, resumo, fase_apos, autor
          FROM tbl_fornecedor_contato
         WHERE id_tenant = %s
         ORDER BY criado_em DESC, id DESC
         LIMIT %s
        """,
        (int(id_tenant), lim),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": int(r[0]),
                "criado_em": r[1].isoformat() if r[1] else None,
                "canal": r[2],
                "direcao": r[3],
                "resumo": r[4] or "",
                "fase_apos": r[5],
                "fase_apos_rotulo": FASE_ROTULO.get(r[5] or "", r[5] or ""),
                "autor": r[6] or "",
            }
        )
    return out


def ultimo_contato(cur, id_tenant: int) -> dict[str, Any] | None:
    itens = listar_contatos(cur, id_tenant, limite=1)
    return itens[0] if itens else None


def enriquecer_fundadores_com_acompanhamento(cur, itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anexa fase / último contato aos itens de listar_fundadores()."""
    if not itens:
        return itens
    tem_fase = _tem_coluna_tenant(cur, "fornecedor_fase")
    tem_contato = _tem_tabela_contato(cur)
    if not tem_fase and not tem_contato:
        for it in itens:
            it.setdefault("fase", None)
            it.setdefault("fase_em", None)
            it.setdefault("fase_rotulo", "")
            it.setdefault("ultimo_contato", None)
        return itens

    ids = [int(i["id"]) for i in itens if i.get("id")]
    fase_map: dict[int, tuple[str | None, Any]] = {}
    if tem_fase and ids:
        cur.execute(
            """
            SELECT id, fornecedor_fase, fornecedor_fase_em
              FROM tbl_tenant
             WHERE id = ANY(%s)
            """,
            (ids,),
        )
        for r in cur.fetchall():
            fase_map[int(r[0])] = (r[1], r[2])

    contato_map: dict[int, dict[str, Any]] = {}
    if tem_contato and ids:
        cur.execute(
            """
            SELECT DISTINCT ON (id_tenant)
                   id_tenant, id, criado_em, canal, direcao, resumo, fase_apos, autor
              FROM tbl_fornecedor_contato
             WHERE id_tenant = ANY(%s)
             ORDER BY id_tenant, criado_em DESC, id DESC
            """,
            (ids,),
        )
        for r in cur.fetchall():
            contato_map[int(r[0])] = {
                "id": int(r[1]),
                "criado_em": r[2].isoformat() if r[2] else None,
                "canal": r[3],
                "direcao": r[4],
                "resumo": r[5] or "",
                "fase_apos": r[6],
                "autor": r[7] or "",
            }

    for it in itens:
        tid = int(it["id"])
        fase, fase_em = fase_map.get(tid, (None, None))
        it["fase"] = fase
        it["fase_em"] = fase_em.isoformat() if fase_em else None
        it["fase_rotulo"] = FASE_ROTULO.get(fase or "", "") if fase else ""
        it["ultimo_contato"] = contato_map.get(tid)
    return itens
