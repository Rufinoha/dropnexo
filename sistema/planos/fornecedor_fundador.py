# sistema/planos/fornecedor_fundador.py — programa Fornecedor Fundador (10 vagas, vitalicio)
from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)

VAGAS_MAX = 10
PLANO_HUB = "enterprise"
CUPONS_MIGRAVELS = ("TROVAVITALICIO", "FORNFUND")
EMAIL_ESPERA = "hazael@h74.com.br"
SLUG_VITRINE = "fundador"


def garantir_colunas_fundador(cur) -> None:
    """Idempotente: cria colunas/tabela se a migracao 061 ainda nao rodou."""
    cur.execute(
        """
        ALTER TABLE tbl_tenant
          ADD COLUMN IF NOT EXISTS eh_fornecedor_fundador BOOLEAN NOT NULL DEFAULT FALSE,
          ADD COLUMN IF NOT EXISTS fornecedor_fundador_ativo BOOLEAN NOT NULL DEFAULT FALSE,
          ADD COLUMN IF NOT EXISTS sistema_erp TEXT,
          ADD COLUMN IF NOT EXISTS fornecedor_fundador_em TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS fornecedor_fundador_obs TEXT
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_fornecedor_fundador_espera (
          id              SERIAL PRIMARY KEY,
          nome            TEXT NOT NULL,
          whatsapp        TEXT NOT NULL,
          email           TEXT,
          empresa         TEXT,
          segmento        TEXT NOT NULL,
          comentarios     TEXT,
          criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _tem_coluna(cur, coluna: str) -> bool:
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


def colunas_ok(cur) -> bool:
    return _tem_coluna(cur, "eh_fornecedor_fundador")


def contar_fundadores_ativos(cur) -> int:
    if not colunas_ok(cur):
        return 0
    cur.execute(
        """
        SELECT COUNT(*)::int
        FROM tbl_tenant
        WHERE eh_fornecedor_fundador = TRUE
          AND fornecedor_fundador_ativo = TRUE
          AND tipo_negocio IN ('fornecedor', 'hibrido')
        """
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def vagas_restantes(cur) -> int:
    return max(0, VAGAS_MAX - contar_fundadores_ativos(cur))


def programa_aberto(cur) -> bool:
    return vagas_restantes(cur) > 0


def status_programa(cur) -> dict[str, Any]:
    try:
        garantir_colunas_fundador(cur)
    except Exception:
        _log.exception("garantir_colunas_fundador")
    usados = contar_fundadores_ativos(cur)
    resto = max(0, VAGAS_MAX - usados)
    return {
        "vagas_max": VAGAS_MAX,
        "vagas_usadas": usados,
        "vagas_restantes": resto,
        "aberto": resto > 0,
        "plano_hub": PLANO_HUB,
        "slug_vitrine": SLUG_VITRINE,
    }


def eh_fundador_ativo(cur, id_tenant: int) -> bool:
    if not id_tenant or not colunas_ok(cur):
        return False
    cur.execute(
        """
        SELECT eh_fornecedor_fundador, fornecedor_fundador_ativo
        FROM tbl_tenant WHERE id = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        return False
    return bool(row[0]) and bool(row[1])


def dados_fundador_tenant(cur, id_tenant: int) -> dict[str, Any] | None:
    if not colunas_ok(cur):
        return None
    cur.execute(
        """
        SELECT eh_fornecedor_fundador, fornecedor_fundador_ativo, sistema_erp,
               fornecedor_fundador_em, fornecedor_fundador_obs, plano, ativo
        FROM tbl_tenant WHERE id = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "eh_fornecedor_fundador": bool(row[0]),
        "fornecedor_fundador_ativo": bool(row[1]),
        "sistema_erp": (row[2] or "") if row[2] is not None else "",
        "fornecedor_fundador_em": row[3].isoformat() if row[3] else None,
        "fornecedor_fundador_obs": row[4] or "",
        "plano": row[5],
        "ativo": bool(row[6]),
    }


def _aplicar_plano_hub(cur, id_tenant: int) -> None:
    cur.execute(
        "UPDATE tbl_tenant SET plano = %s WHERE id = %s",
        (PLANO_HUB, int(id_tenant)),
    )
    cur.execute(
        """
        INSERT INTO tbl_tenant_cobranca (id_tenant, plano_slug, atualizado_em)
        VALUES (%s, %s, NOW())
        ON CONFLICT (id_tenant) DO UPDATE
          SET plano_slug = EXCLUDED.plano_slug,
              plano_slug_pendente = NULL,
              atualizado_em = NOW()
        """,
        (int(id_tenant), PLANO_HUB),
    )


def atribuir_fundador(
    cur,
    id_tenant: int,
    *,
    forcar: bool = False,
    sistema_erp: str | None = None,
    obs: str | None = None,
) -> dict[str, Any]:
    """Marca tenant como Fundador ativo (limites = Hub). Reserva vaga se houver."""
    garantir_colunas_fundador(cur)
    tid = int(id_tenant)
    cur.execute(
        """
        SELECT tipo_negocio, eh_fornecedor_fundador, fornecedor_fundador_ativo
        FROM tbl_tenant WHERE id = %s FOR UPDATE
        """,
        (tid,),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "message": "Tenant nao encontrado."}
    tipo = (row[0] or "").strip().lower()
    if tipo not in ("fornecedor", "hibrido"):
        return {"ok": False, "message": "So fornecedor/hibrido pode ser Fundador."}

    ja_eh, ja_ativo = bool(row[1]), bool(row[2])
    if ja_eh and ja_ativo:
        if sistema_erp is not None:
            cur.execute(
                "UPDATE tbl_tenant SET sistema_erp = %s WHERE id = %s",
                ((sistema_erp or "").strip() or None, tid),
            )
        _aplicar_plano_hub(cur, tid)
        return {"ok": True, "message": "Ja e Fornecedor Fundador ativo.", "ja_era": True}

    if not forcar and not programa_aberto(cur):
        return {
            "ok": False,
            "message": "Programa Fornecedor Fundador esgotou as 10 vagas.",
            "vagas_restantes": 0,
        }

    erp = (sistema_erp or "").strip() or None
    nota = (obs or "").strip() or None
    cur.execute(
        """
        UPDATE tbl_tenant SET
          eh_fornecedor_fundador = TRUE,
          fornecedor_fundador_ativo = TRUE,
          fornecedor_fundador_em = COALESCE(fornecedor_fundador_em, NOW()),
          sistema_erp = COALESCE(%s, sistema_erp),
          fornecedor_fundador_obs = COALESCE(%s, fornecedor_fundador_obs),
          plano = %s
        WHERE id = %s
        """,
        (erp, nota, PLANO_HUB, tid),
    )
    _aplicar_plano_hub(cur, tid)
    return {
        "ok": True,
        "message": "Fornecedor Fundador ativado.",
        "vagas_restantes": vagas_restantes(cur),
    }


def desativar_fundador(cur, id_tenant: int, *, obs: str | None = None) -> dict[str, Any]:
    """Desativa beneficio (libera vaga). Rebaixa plano para Explorar/starter."""
    garantir_colunas_fundador(cur)
    tid = int(id_tenant)
    nota = (obs or "").strip()
    cur.execute(
        """
        UPDATE tbl_tenant SET
          fornecedor_fundador_ativo = FALSE,
          plano = 'starter',
          fornecedor_fundador_obs = CASE
            WHEN %s <> '' THEN TRIM(BOTH FROM COALESCE(fornecedor_fundador_obs, '') || E'\n' || %s)
            ELSE fornecedor_fundador_obs
          END
        WHERE id = %s AND eh_fornecedor_fundador = TRUE
        RETURNING id
        """,
        (nota, nota, tid),
    )
    if not cur.fetchone():
        return {"ok": False, "message": "Tenant nao e Fornecedor Fundador."}
    cur.execute(
        """
        UPDATE tbl_tenant_cobranca
        SET plano_slug = 'starter', plano_slug_pendente = NULL, atualizado_em = NOW()
        WHERE id_tenant = %s
        """,
        (tid,),
    )
    return {
        "ok": True,
        "message": "Fundador desativado; vaga liberada.",
        "vagas_restantes": vagas_restantes(cur),
    }


def tentar_reservar_no_cadastro(
    cur,
    id_tenant: int,
    *,
    sistema_erp: str | None = None,
) -> dict[str, Any]:
    """Chamado no cadastro de fornecedor: reserva vaga se ainda houver."""
    if not programa_aberto(cur):
        if sistema_erp:
            garantir_colunas_fundador(cur)
            cur.execute(
                "UPDATE tbl_tenant SET sistema_erp = %s WHERE id = %s",
                ((sistema_erp or "").strip() or None, int(id_tenant)),
            )
        return {
            "ok": False,
            "reservado": False,
            "message": "Vagas esgotadas — conta no plano Explorar.",
            "vagas_restantes": 0,
        }
    res = atribuir_fundador(cur, id_tenant, sistema_erp=sistema_erp, obs="Reserva no cadastro")
    res["reservado"] = bool(res.get("ok"))
    return res


def migrar_cupons_fundador(cur) -> dict[str, Any]:
    """Migra tenants que usaram TROVAVITALICIO ou FORNFUND para Fundador (forcado)."""
    garantir_colunas_fundador(cur)
    codigos = [c.upper() for c in CUPONS_MIGRAVELS]
    cur.execute("SELECT to_regclass(%s)", ("tbl_cupom_uso",))
    if not cur.fetchone()[0]:
        return {"ok": True, "migrados": [], "ignorados": [], "message": "tbl_cupom_uso ausente."}

    cur.execute(
        """
        SELECT DISTINCT u.id_tenant
        FROM tbl_cupom_uso u
        JOIN tbl_tenant t ON t.id = u.id_tenant
        WHERE upper(u.codigo) = ANY(%s)
          AND t.tipo_negocio IN ('fornecedor', 'hibrido')
        ORDER BY 1
        """,
        (codigos,),
    )
    ids = [int(r[0]) for r in cur.fetchall()]
    migrados: list[int] = []
    ignorados: list[dict] = []
    for tid in ids:
        res = atribuir_fundador(
            cur,
            tid,
            forcar=True,
            obs=f"Migracao automatica cupons {', '.join(codigos)}",
        )
        if res.get("ok"):
            migrados.append(tid)
        else:
            ignorados.append({"id_tenant": tid, "message": res.get("message")})
    return {
        "ok": True,
        "migrados": migrados,
        "ignorados": ignorados,
        "total": len(migrados),
        "vagas_usadas": contar_fundadores_ativos(cur),
        "vagas_restantes": vagas_restantes(cur),
    }


def listar_fundadores(cur) -> list[dict[str, Any]]:
    garantir_colunas_fundador(cur)
    cur.execute(
        """
        SELECT t.id, t.nome, t.slug, t.documento, t.ativo, t.plano,
               t.fornecedor_fundador_ativo, t.sistema_erp, t.fornecedor_fundador_em,
               t.fornecedor_fundador_obs, t.criado_em,
               (SELECT COUNT(*)::int FROM tbl_produto p
                WHERE p.id_tenant = t.id AND COALESCE(p.publicado, FALSE) = TRUE) AS produtos_pub,
               (SELECT COUNT(*)::int FROM tbl_produto p WHERE p.id_tenant = t.id) AS produtos_total,
               (SELECT u.email FROM tbl_usuario_tenant ut
                JOIN tbl_usuario u ON u.id = ut.id_usuario
                JOIN tbl_perfil pf ON pf.id = ut.id_perfil AND pf.codigo = 'dono'
                WHERE ut.id_tenant = t.id AND ut.ativo = TRUE
                ORDER BY ut.id LIMIT 1) AS email_dono,
               (SELECT u.whatsapp FROM tbl_usuario_tenant ut
                JOIN tbl_usuario u ON u.id = ut.id_usuario
                JOIN tbl_perfil pf ON pf.id = ut.id_perfil AND pf.codigo = 'dono'
                WHERE ut.id_tenant = t.id AND ut.ativo = TRUE
                ORDER BY ut.id LIMIT 1) AS whatsapp_dono
        FROM tbl_tenant t
        WHERE t.eh_fornecedor_fundador = TRUE
          AND t.tipo_negocio IN ('fornecedor', 'hibrido')
        ORDER BY t.fornecedor_fundador_ativo DESC, t.fornecedor_fundador_em NULLS LAST, t.id
        """
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": r[0],
                "nome": r[1],
                "slug": r[2],
                "documento": r[3] or "",
                "ativo": bool(r[4]),
                "plano": r[5],
                "fornecedor_fundador_ativo": bool(r[6]),
                "sistema_erp": r[7] or "",
                "fornecedor_fundador_em": r[8].isoformat() if r[8] else None,
                "fornecedor_fundador_obs": r[9] or "",
                "criado_em": r[10].isoformat() if r[10] else None,
                "produtos_publicados": int(r[11] or 0),
                "produtos_total": int(r[12] or 0),
                "email": r[13] or "",
                "whatsapp": r[14] or "",
            }
        )
    return out


def registrar_espera(
    cur,
    *,
    nome: str,
    whatsapp: str,
    segmento: str,
    email: str | None = None,
    empresa: str | None = None,
    comentarios: str | None = None,
) -> int:
    garantir_colunas_fundador(cur)
    cur.execute(
        """
        INSERT INTO tbl_fornecedor_fundador_espera
          (nome, whatsapp, email, empresa, segmento, comentarios)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            nome.strip(),
            whatsapp.strip(),
            (email or "").strip() or None,
            (empresa or "").strip() or None,
            segmento.strip(),
            (comentarios or "").strip() or None,
        ),
    )
    return int(cur.fetchone()[0])


def plano_fundador_vitrine() -> dict[str, Any]:
    """Card comercial unico enquanto o programa estiver aberto."""
    return {
        "slug": SLUG_VITRINE,
        "nome": "Fornecedor Fundador",
        "preco_mensal": 0,
        "destaque": "Vitalicio · 10 vagas · acesso Hub completo",
        "featured": True,
        "tag": "Programa fundador",
        "cta_gratis": True,
        "fundador": True,
        "limites": [
            {"valor": "3.000", "rotulo": "pedidos/mes"},
            {"valor": "Ilimitados", "rotulo": "vendedores aprovados"},
            {"valor": "15.000", "rotulo": "produtos"},
            {"valor": "Ilimitados", "rotulo": "usuarios"},
            {"valor": "Ilimitados", "rotulo": "depositos"},
            {"valor": "100 GB", "rotulo": "espaco"},
        ],
        "recursos": [
            {"label": "Acesso completo do plano Hub", "on": True, "sub": "", "icon": ""},
            {"label": "Vitalicio enquanto Fundador ativo", "on": True, "sub": "", "icon": ""},
            {"label": "Selo exclusivo na rede", "on": True, "sub": "", "icon": ""},
            {"label": "Participacao no desenvolvimento", "on": True, "sub": "", "icon": ""},
            {"label": "Suporte direto com o fundador", "on": True, "sub": "", "icon": ""},
            {"label": "Integracao Bling disponivel", "on": True, "sub": "", "icon": ""},
        ],
    }


def catalogo_fornecedor_com_fundador(cur, planos_normais: list[dict]) -> dict[str, Any]:
    """Retorna planos da vitrine fornecedor + meta do programa."""
    st = status_programa(cur)
    if st["aberto"]:
        return {
            "planos": [plano_fundador_vitrine()],
            "programa": st,
            "modo": "fundador",
            "url_espera": None,
        }
    return {
        "planos": planos_normais,
        "programa": st,
        "modo": "normal",
        "url_espera": "/lista-espera-fundador",
    }