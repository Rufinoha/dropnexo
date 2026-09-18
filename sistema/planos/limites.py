# sistema/planos/limites.py — limites e flags comerciais por plano
from __future__ import annotations

from typing import Any

from flask import session

from global_utils import plano_slug_banco

# Banco: starter | professional | scale | enterprise


_MB = 1024 * 1024
_GB = 1024 * _MB


def _base(
    *,
    slug_comercial: str,
    nome: str,
    gratuito: bool,
    pedidos_mes: int,
    conexoes: int | None,
    produtos: int,
    usuarios: int | None,
    integracao: bool,
    importacao_planilha: bool,
    email_pedidos: bool,
    armazenamento_bytes: int,
    depositos: int | None = None,
) -> dict[str, Any]:
    return {
        "slug_comercial": slug_comercial,
        "nome": nome,
        "gratuito": gratuito,
        "pedidos_mes": pedidos_mes,
        "conexoes": conexoes,
        "produtos": produtos,
        "usuarios": usuarios,
        "integracao": integracao,
        "importacao_planilha": importacao_planilha,
        "email_pedidos": email_pedidos,
        "armazenamento_bytes": int(armazenamento_bytes),
        "depositos": depositos,
    }


_POR_TIPO_BANCO = {
    "vendedor": {
        "starter": lambda: _base(
            slug_comercial="explorar",
            nome="Explorar",
            gratuito=True,
            pedidos_mes=25,
            conexoes=1,
            produtos=50,
            usuarios=1,
            integracao=False,
            importacao_planilha=False,
            email_pedidos=False,
            armazenamento_bytes=200 * _MB,
        ),
        "professional": lambda: _base(
            slug_comercial="crescer",
            nome="Crescer",
            gratuito=False,
            pedidos_mes=150,
            conexoes=3,
            produtos=500,
            usuarios=3,
            integracao=True,
            importacao_planilha=True,
            email_pedidos=True,
            armazenamento_bytes=2 * _GB,
        ),
        "scale": lambda: _base(
            slug_comercial="escalar",
            nome="Escalar",
            gratuito=False,
            pedidos_mes=600,
            conexoes=30,
            produtos=2000,
            usuarios=8,
            integracao=True,
            importacao_planilha=True,
            email_pedidos=True,
            armazenamento_bytes=10 * _GB,
        ),
        "enterprise": lambda: _base(
            slug_comercial="pro",
            nome="Pro",
            gratuito=False,
            pedidos_mes=2000,
            conexoes=80,
            produtos=10000,
            usuarios=None,
            integracao=True,
            importacao_planilha=True,
            email_pedidos=True,
            armazenamento_bytes=40 * _GB,
        ),
    },
    "fornecedor": {
        "starter": lambda: _base(
            slug_comercial="explorar",
            nome="Explorar",
            gratuito=True,
            pedidos_mes=40,
            conexoes=5,
            produtos=150,
            usuarios=1,
            integracao=False,
            importacao_planilha=False,
            email_pedidos=False,
            depositos=1,
            armazenamento_bytes=500 * _MB,
        ),
        "professional": lambda: _base(
            slug_comercial="conectar",
            nome="Conectar",
            gratuito=False,
            pedidos_mes=200,
            conexoes=20,
            produtos=800,
            usuarios=2,
            integracao=True,
            importacao_planilha=True,
            email_pedidos=True,
            depositos=2,
            armazenamento_bytes=5 * _GB,
        ),
        "scale": lambda: _base(
            slug_comercial="expandir",
            nome="Expandir",
            gratuito=False,
            pedidos_mes=800,
            conexoes=60,
            produtos=3000,
            usuarios=None,
            integracao=True,
            importacao_planilha=True,
            email_pedidos=True,
            depositos=5,
            armazenamento_bytes=25 * _GB,
        ),
        "enterprise": lambda: _base(
            slug_comercial="hub",
            nome="Hub",
            gratuito=False,
            pedidos_mes=3000,
            conexoes=None,
            produtos=15000,
            usuarios=None,
            integracao=True,
            importacao_planilha=True,
            email_pedidos=True,
            depositos=None,
            armazenamento_bytes=100 * _GB,
        ),
    },
}


def tipo_negocio_sessao() -> str:
    t = (session.get("tenant_tipo_negocio") or session.get("tipo_negocio") or "").strip().lower()
    if t == "hibrido":
        mod = (session.get("modulo_ativo") or "").strip().lower()
        if mod in ("fornecedor", "vendedor"):
            return mod
        return "fornecedor"
    if t == "fornecedor":
        return "fornecedor"
    return "vendedor"


def limites_plano(
    *,
    plano: str | None = None,
    tipo_negocio: str | None = None,
) -> dict[str, Any]:
    """Retorna limites/flags do plano do tenant (sessão ou parâmetros)."""
    slug = plano_slug_banco(plano if plano is not None else session.get("tenant_plano"))
    tipo = (tipo_negocio or tipo_negocio_sessao()).strip().lower()
    if tipo not in ("vendedor", "fornecedor"):
        tipo = "vendedor"
    factory = _POR_TIPO_BANCO[tipo].get(slug) or _POR_TIPO_BANCO[tipo]["starter"]
    lim = dict(factory())
    lim["plano_banco"] = slug
    lim["tipo_negocio"] = tipo
    return lim


def mensagem_upgrade_integracao() -> str:
    return (
        "No plano gratuito não é possível usar integrações com ERP e Marketplace. "
        "Se já havia conexão, ela permanece salva — mas o acesso e as atualizações ficam pausados. "
        "Assine um plano pago em Meu plano ou regularize em Financeiro."
    )


def mensagem_upgrade_importacao() -> str:
    return (
        "No plano gratuito não é possível importar planilha de produtos. "
        "Faça upgrade em Meu plano para liberar este recurso."
    )


def mensagem_limite_conexoes(*, tipo: str, limite: int) -> str:
    if tipo == "fornecedor":
        return (
            f"Seu plano permite até {limite} vendedor(es) aprovado(s). "
            "Você continua vendo todas as solicitações; para aprovar mais, veja Meu plano."
        )
    return (
        f"Seu plano permite até {limite} fornecedor(es). "
        "Para conectar mais, veja os planos em Meu plano."
    )


def mensagem_limite_pedidos_mes(*, limite: int, usado: int, papel: str = "vendedor") -> str:
    lado = "sua conta" if papel == "vendedor" else "a conta do fornecedor"
    return (
        f"Limite de {limite} pedido(s)/mês atingido ({usado} usados neste mês) em {lado}. "
        "Faça upgrade em Meu plano para continuar."
    )


def mensagem_limite_produtos(*, limite: int, usado: int, papel: str = "vendedor") -> str:
    rotulo = "produtos" if papel == "vendedor" else "produtos/SKUs"
    return (
        f"Seu plano permite até {limite} {rotulo} ({usado} em uso). "
        "Remova itens ou faça upgrade em Meu plano."
    )


def formatar_bytes(n: int | float | None) -> str:
    try:
        b = float(n or 0)
    except (TypeError, ValueError):
        b = 0.0
    if b >= _GB:
        return f"{b / _GB:.2f} GB".replace(".", ",")
    if b >= _MB:
        return f"{b / _MB:.1f} MB".replace(".", ",")
    if b >= 1024:
        return f"{b / 1024:.0f} KB"
    return f"{int(b)} B"


def mensagem_limite_armazenamento(*, limite: int, usado: int) -> str:
    return (
        f"Espaço do plano esgotado ({formatar_bytes(usado)} de {formatar_bytes(limite)}). "
        "Remova arquivos ou faça upgrade em Meu plano."
    )


def _tipo_limites_tenant(tipo_negocio: str | None, papel: str) -> str:
    t = (tipo_negocio or "").strip().lower()
    if t in ("vendedor", "fornecedor"):
        return t
    return papel if papel in ("vendedor", "fornecedor") else "vendedor"


def limites_plano_tenant(cur, id_tenant: int, papel: str) -> dict[str, Any]:
    """Limites do tenant pelo banco (não depende da sessão)."""
    cur.execute(
        "SELECT plano, tipo_negocio FROM tbl_tenant WHERE id = %s",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    plano = row[0] if row else None
    tipo_negocio = row[1] if row else None
    return limites_plano(
        plano=plano,
        tipo_negocio=_tipo_limites_tenant(tipo_negocio, papel),
    )


def _inicio_fim_mes_atual_sql() -> tuple[str, str]:
    """Expressões SQL (timestamptz) do mês civil em America/Sao_Paulo."""
    inicio = (
        "(date_trunc('month', (NOW() AT TIME ZONE 'America/Sao_Paulo')) "
        "AT TIME ZONE 'America/Sao_Paulo')"
    )
    fim = (
        "((date_trunc('month', (NOW() AT TIME ZONE 'America/Sao_Paulo')) "
        "+ INTERVAL '1 month') AT TIME ZONE 'America/Sao_Paulo')"
    )
    return inicio, fim


def contar_pedidos_mes(cur, id_tenant: int, papel: str) -> int:
    """Pedidos do mês (exceto rascunho) do vendedor ou fornecedor."""
    from core.pedidos.servico import STATUS_RASCUNHO, col_status_vendedor

    cv = col_status_vendedor(cur)
    col_tenant = "id_tenant_vendedor" if papel == "vendedor" else "id_tenant_fornecedor"
    inicio, fim = _inicio_fim_mes_atual_sql()
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM tbl_pedido
        WHERE {col_tenant} = %s
          AND {cv} IS DISTINCT FROM %s
          AND COALESCE(confirmado_em, criado_em) >= {inicio}
          AND COALESCE(confirmado_em, criado_em) < {fim}
        """,
        (int(id_tenant), STATUS_RASCUNHO),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def contar_produtos(cur, id_tenant: int, papel: str) -> int:
    """Produtos em uso no plano: catálogo do fornecedor ou Meus produtos do vendedor."""
    if papel == "fornecedor":
        cur.execute(
            "SELECT COUNT(*) FROM tbl_produto WHERE id_tenant = %s",
            (int(id_tenant),),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(DISTINCT id_produto)
            FROM tbl_produto_vendedor
            WHERE id_tenant_vendedor = %s
            """,
            (int(id_tenant),),
        )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def produto_ja_no_catalogo_vendedor(cur, id_vendedor: int, id_produto: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND id_produto = %s
        LIMIT 1
        """,
        (int(id_vendedor), int(id_produto)),
    )
    return cur.fetchone() is not None


def verificar_limite_pedidos_mes(
    cur,
    id_tenant: int,
    papel: str,
    *,
    quantidade: int = 1,
) -> tuple[bool, str]:
    """Retorna (ok, mensagem). quantidade = pedidos que serão criados/confirmados agora."""
    qtd = max(1, int(quantidade or 1))
    lim = limites_plano_tenant(cur, id_tenant, papel)
    limite = lim.get("pedidos_mes")
    if limite is None:
        return True, ""
    limite_i = int(limite)
    usado = contar_pedidos_mes(cur, id_tenant, papel)
    if usado + qtd > limite_i:
        return False, mensagem_limite_pedidos_mes(limite=limite_i, usado=usado, papel=papel)
    return True, ""


def exigir_limite_pedidos_mes(
    cur,
    id_tenant: int,
    papel: str,
    *,
    quantidade: int = 1,
) -> None:
    ok, msg = verificar_limite_pedidos_mes(cur, id_tenant, papel, quantidade=quantidade)
    if not ok:
        raise ValueError(msg)


def verificar_limite_produtos(
    cur,
    id_tenant: int,
    papel: str,
    *,
    quantidade: int = 1,
) -> tuple[bool, str]:
    qtd = max(1, int(quantidade or 1))
    lim = limites_plano_tenant(cur, id_tenant, papel)
    limite = lim.get("produtos")
    if limite is None:
        return True, ""
    limite_i = int(limite)
    usado = contar_produtos(cur, id_tenant, papel)
    if usado + qtd > limite_i:
        return False, mensagem_limite_produtos(limite=limite_i, usado=usado, papel=papel)
    return True, ""


def exigir_limite_produtos(
    cur,
    id_tenant: int,
    papel: str,
    *,
    quantidade: int = 1,
) -> None:
    ok, msg = verificar_limite_produtos(cur, id_tenant, papel, quantidade=quantidade)
    if not ok:
        raise ValueError(msg)


def exigir_novo_produto_vendedor(cur, id_vendedor: int, id_produto: int) -> None:
    """Só consome cota se o produto ainda não existir em Meus produtos."""
    if produto_ja_no_catalogo_vendedor(cur, id_vendedor, id_produto):
        return
    exigir_limite_produtos(cur, int(id_vendedor), "vendedor", quantidade=1)


def exigir_novo_produto_catalogo(cur, id_tenant: int) -> None:
    """Trava criação em tbl_produto (catálogo do tenant / sync Bling)."""
    cur.execute(
        "SELECT plano, tipo_negocio FROM tbl_tenant WHERE id = %s",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    plano = row[0] if row else None
    tipo = ((row[1] if row else None) or "fornecedor").strip().lower()
    papel = "vendedor" if tipo == "vendedor" else "fornecedor"
    lim = limites_plano(plano=plano, tipo_negocio=papel)
    limite = lim.get("produtos")
    if limite is None:
        return
    cur.execute(
        "SELECT COUNT(*) FROM tbl_produto WHERE id_tenant = %s",
        (int(id_tenant),),
    )
    usado = int((cur.fetchone() or [0])[0] or 0)
    limite_i = int(limite)
    if usado + 1 > limite_i:
        raise ValueError(mensagem_limite_produtos(limite=limite_i, usado=usado, papel=papel))


def exigir_capacidade_pedido_novo(cur, id_vendedor: int, id_fornecedor: int) -> None:
    """Valida cota mensal do vendedor e do fornecedor para 1 pedido novo."""
    exigir_limite_pedidos_mes(cur, int(id_vendedor), "vendedor", quantidade=1)
    if id_fornecedor:
        exigir_limite_pedidos_mes(cur, int(id_fornecedor), "fornecedor", quantidade=1)


def contar_usuarios_tenant(cur, id_tenant: int) -> int:
    cur.execute(
        """
        SELECT COUNT(*)::int
        FROM tbl_usuario_tenant
        WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    return int(cur.fetchone()[0] or 0)


def contar_conexoes(cur, id_tenant: int, papel: str) -> int:
    tid = int(id_tenant)
    if papel == "fornecedor":
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM tbl_vinculo_vendedor_fornecedor
            WHERE id_tenant_fornecedor = %s AND status IN ('ativo', 'pausado')
            """,
            (tid,),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM tbl_vinculo_vendedor_fornecedor
            WHERE id_tenant_vendedor = %s AND status IN ('ativo', 'pausado', 'aguardando')
            """,
            (tid,),
        )
    return int(cur.fetchone()[0] or 0)


def contar_depositos(cur, id_tenant: int) -> int:
    try:
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND COALESCE(ativo, TRUE) = TRUE
            """,
            (int(id_tenant),),
        )
        return int(cur.fetchone()[0] or 0)
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return 0


def uso_cotas_tenant(cur, id_tenant: int, tipo_negocio: str | None = None) -> list[dict[str, Any]]:
    """Resumo de uso para a tela Meu plano (por papel disponível)."""
    from sistema.planos.armazenamento import uso_armazenamento_vs_plano

    cur.execute("SELECT tipo_negocio FROM tbl_tenant WHERE id = %s", (int(id_tenant),))
    row = cur.fetchone()
    tipo = (tipo_negocio or (row[0] if row else None) or "vendedor").strip().lower()
    papeis: list[str] = []
    if tipo in ("vendedor", "hibrido"):
        papeis.append("vendedor")
    if tipo in ("fornecedor", "hibrido"):
        papeis.append("fornecedor")
    if not papeis:
        papeis = ["vendedor"]

    out: list[dict[str, Any]] = []
    for papel in papeis:
        lim = limites_plano_tenant(cur, id_tenant, papel)
        ped_lim = lim.get("pedidos_mes")
        prod_lim = lim.get("produtos")
        conn_lim = lim.get("conexoes")
        usu_lim = lim.get("usuarios")
        dep_lim = lim.get("depositos")
        ped_uso = contar_pedidos_mes(cur, id_tenant, papel)
        prod_uso = contar_produtos(cur, id_tenant, papel)
        conn_uso = contar_conexoes(cur, id_tenant, papel)
        usu_uso = contar_usuarios_tenant(cur, id_tenant)
        arm = uso_armazenamento_vs_plano(cur, id_tenant, papel)

        bloco: dict[str, Any] = {
            "papel": papel,
            "papel_rotulo": "Vendedor" if papel == "vendedor" else "Fornecedor",
            "plano_nome": lim.get("nome") or "",
            "pedidos": {
                "usado": ped_uso,
                "limite": ped_lim,
                "rotulo": "Pedidos neste mês",
            },
            "produtos": {
                "usado": prod_uso,
                "limite": prod_lim,
                "rotulo": "Produtos" if papel == "vendedor" else "Produtos / SKUs",
            },
            "conexoes": {
                "usado": conn_uso,
                "limite": conn_lim,
                "rotulo": "Fornecedores" if papel == "vendedor" else "Vendedores aprovados",
            },
            "usuarios": {
                "usado": usu_uso,
                "limite": usu_lim,
                "rotulo": "Usuários da equipe",
            },
            "armazenamento": {
                "usado": arm.get("usado_bytes") or 0,
                "limite": arm.get("limite_bytes"),
                "rotulo": "Espaço em disco",
                "rotulo_usado": arm.get("rotulo_total") or formatar_bytes(0),
                "rotulo_limite": arm.get("rotulo_limite") or "—",
                "percentual": arm.get("percentual") or 0,
                "itens": arm.get("itens") or [],
                "formatado": True,
            },
        }
        if papel == "fornecedor":
            bloco["depositos"] = {
                "usado": contar_depositos(cur, id_tenant),
                "limite": dep_lim,
                "rotulo": "Depósitos",
            }
        out.append(bloco)
    return out
