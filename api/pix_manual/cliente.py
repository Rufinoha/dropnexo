# api/pix_manual/cliente.py — configuração PIX manual do fornecedor
from __future__ import annotations

from global_utils import agora_utc

TIPOS_CHAVE = ("cpf", "cnpj", "email", "telefone", "aleatoria")

_TABELA_OK: bool | None = None


def _tem_tabela(cur) -> bool:
    global _TABELA_OK
    if _TABELA_OK is not None:
        return _TABELA_OK
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'tbl_integracao_pix_manual'
        LIMIT 1
        """
    )
    _TABELA_OK = cur.fetchone() is not None
    return _TABELA_OK


def carregar_config_pix_manual(cur, id_tenant: int) -> dict:
    if not _tem_tabela(cur):
        return {"ativo": False, "configurado": False}
    cur.execute(
        """
        SELECT ativo, tipo_chave, chave_pix, nome_beneficiario, cidade_beneficiario, atualizado_em
        FROM tbl_integracao_pix_manual WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "ativo": False,
            "configurado": False,
            "tipo_chave": "aleatoria",
            "chave_pix": "",
            "nome_beneficiario": "",
            "cidade_beneficiario": "",
        }
    return {
        "ativo": bool(row[0]),
        "configurado": bool((row[2] or "").strip()),
        "tipo_chave": row[1] or "aleatoria",
        "chave_pix": row[2] or "",
        "nome_beneficiario": row[3] or "",
        "cidade_beneficiario": row[4] or "",
        "atualizado_em": row[5].isoformat() if row[5] else None,
    }


def pix_manual_ativo(cur, id_tenant: int) -> bool:
    cfg = carregar_config_pix_manual(cur, id_tenant)
    return bool(cfg.get("ativo") and cfg.get("configurado"))


def salvar_config_pix_manual(
    cur,
    id_tenant: int,
    *,
    ativo: bool,
    tipo_chave: str,
    chave_pix: str,
    nome_beneficiario: str,
    cidade_beneficiario: str,
) -> None:
    if not _tem_tabela(cur):
        raise ValueError("Execute a migração SQL 064_pix_manual.sql.")
    tipo = (tipo_chave or "aleatoria").strip().lower()
    if tipo not in TIPOS_CHAVE:
        raise ValueError("Tipo de chave PIX inválido.")
    chave = (chave_pix or "").strip()
    nome = (nome_beneficiario or "").strip()[:25]
    cidade = (cidade_beneficiario or "").strip()[:15]
    if ativo and not chave:
        raise ValueError("Informe a chave PIX.")
    if ativo and not nome:
        raise ValueError("Informe o nome do beneficiário (como no banco).")
    if ativo and not cidade:
        raise ValueError("Informe a cidade do beneficiário.")

    cur.execute(
        """
        INSERT INTO tbl_integracao_pix_manual (
            id_tenant, ativo, tipo_chave, chave_pix, nome_beneficiario, cidade_beneficiario, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            ativo = EXCLUDED.ativo,
            tipo_chave = EXCLUDED.tipo_chave,
            chave_pix = EXCLUDED.chave_pix,
            nome_beneficiario = EXCLUDED.nome_beneficiario,
            cidade_beneficiario = EXCLUDED.cidade_beneficiario,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, ativo, tipo, chave, nome, cidade, agora_utc()),
    )


def desativar_pix_manual(cur, id_tenant: int) -> None:
    if not _tem_tabela(cur):
        return
    cur.execute(
        """
        UPDATE tbl_integracao_pix_manual SET ativo = FALSE, atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), id_tenant),
    )
