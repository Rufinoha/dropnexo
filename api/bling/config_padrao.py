# api/bling/config_padrao.py — defaults ao conectar Bling pela primeira vez
from __future__ import annotations

from global_utils import agora_utc

DEFAULTS_CONEXAO = {
    "fornecedor": {
        "fonte_principal": "bling",
        "modo_imagem": "link",
        "produtos_modo": "importar",
        "estoque_modo": "atualizar",
        "pedidos_modo": "exportar",
    },
    "vendedor": {
        "fonte_principal": "bling",
        "modo_imagem": "link",
        "produtos_modo": "exportar",
        "estoque_modo": "importar",
        "pedidos_modo": "atualizar",
    },
}


def aplicar_defaults_conexao(cur, id_tenant: int, contexto: str) -> None:
    """Aplica configuração padronizada do módulo ativo (fornecedor ou vendedor)."""
    ctx = contexto if contexto in DEFAULTS_CONEXAO else "fornecedor"
    cfg = DEFAULTS_CONEXAO[ctx]
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_config (
            id_tenant, contexto, fonte_principal, modo_imagem,
            produtos_modo, estoque_modo, pedidos_modo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, contexto) DO UPDATE SET
            fonte_principal = EXCLUDED.fonte_principal,
            modo_imagem = EXCLUDED.modo_imagem,
            produtos_modo = EXCLUDED.produtos_modo,
            estoque_modo = EXCLUDED.estoque_modo,
            pedidos_modo = EXCLUDED.pedidos_modo,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            ctx,
            cfg["fonte_principal"],
            cfg["modo_imagem"],
            cfg["produtos_modo"],
            cfg["estoque_modo"],
            cfg["pedidos_modo"],
            agora,
        ),
    )


def garantir_config_contexto(cur, id_tenant: int, contexto: str) -> None:
    """Cria linha de config do módulo ativo se ainda não existir (sem sobrescrever)."""
    ctx = contexto if contexto in DEFAULTS_CONEXAO else "fornecedor"
    cur.execute(
        "SELECT 1 FROM tbl_integracao_bling_config WHERE id_tenant = %s AND contexto = %s",
        (id_tenant, ctx),
    )
    if cur.fetchone():
        return
    cfg = DEFAULTS_CONEXAO[ctx]
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_config (
            id_tenant, contexto, fonte_principal, modo_imagem,
            produtos_modo, estoque_modo, pedidos_modo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_tenant,
            ctx,
            cfg["fonte_principal"],
            cfg["modo_imagem"],
            cfg["produtos_modo"],
            cfg["estoque_modo"],
            cfg["pedidos_modo"],
            agora,
        ),
    )
