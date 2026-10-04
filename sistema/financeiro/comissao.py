# sistema/financeiro/comissao.py — comissão do fornecedor sobre a mensalidade paga
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Sao_Paulo")
_PLANOS_SEM_COMISSAO = frozenset({"", "starter"})
_MESES = (
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def hoje_sp() -> date:
    return datetime.now(_TZ).date()


def janela_fechamento(dia: date | None = None) -> bool:
    d = dia or hoje_sp()
    return 1 <= d.day <= 10


def vencimento_fechamento(dia: date | None = None) -> date:
    d = dia or hoje_sp()
    return d.replace(day=20)


def _nome_tenant_sql() -> str:
    return "COALESCE(NULLIF(TRIM(nome_fantasia), ''), NULLIF(TRIM(nome), ''), 'Conta')"


def _dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v if v is not None else 0))
    except Exception:
        return Decimal("0")


def _pct(v: Any) -> Decimal:
    n = _dec(v)
    if n < 0:
        return Decimal("0")
    if n > 100:
        return Decimal("100")
    return n.quantize(Decimal("0.0001"))


def _impostos_limpos(raw: Any) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("nome") or "").strip()[:40]
        if not nome:
            continue
        out.append({"nome": nome, "percentual": float(_pct(item.get("percentual")))})
    return out


def calcular_comissao_centavos(
    valor_pago_centavos: int,
    *,
    base: str,
    percentual: Any,
    impostos: list[dict],
) -> int:
    pago = max(0, int(valor_pago_centavos or 0))
    taxa = sum(_dec(i.get("percentual")) for i in impostos)
    if taxa > 100:
        taxa = Decimal("100")
    base_c = Decimal(pago)
    if (base or "") == "liquido":
        base_c = (base_c * (Decimal("100") - taxa) / Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    com = (base_c * _pct(percentual) / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, int(com))


def _config_row(cur, id_tenant: int) -> dict | None:
    cur.execute(
        """
        SELECT ativo, base, percentual_proprio, percentual_indicado, impostos
        FROM tbl_comissao_config WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "ativo": bool(row[0]),
        "base": row[1] if row[1] in ("faturamento", "liquido") else "faturamento",
        "percentual_proprio": float(row[2] or 0),
        "percentual_indicado": float(row[3] or 0),
        "impostos": _impostos_limpos(row[4]),
    }


def pai_da_indicacao(cur, id_tenant: int) -> int | None:
    cur.execute(
        "SELECT id_tenant_pai FROM tbl_comissao_indicacao WHERE id_tenant_indicado = %s",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def comissao_menu_visivel(cur, id_tenant: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_comissao_config WHERE id_tenant = %s AND ativo = TRUE
        UNION
        SELECT 1 FROM tbl_comissao_item
         WHERE id_tenant_beneficiario = %s AND status = 'aberto'
        UNION
        SELECT 1 FROM tbl_comissao_fechamento
         WHERE id_tenant_fornecedor = %s AND status = 'aguardando'
        LIMIT 1
        """,
        (int(id_tenant), int(id_tenant), int(id_tenant)),
    )
    return cur.fetchone() is not None


def registrar_comissao_fatura(cur, id_fatura: int) -> None:
    """Gera o item no pagamento. Plano grátis e valor zero não entram. A mesma fatura conta uma vez."""
    cur.execute(
        """
        SELECT id, id_tenant, valor_centavos, COALESCE(plano_slug, ''), status,
               COALESCE(pago_em, NOW()), COALESCE(referencia, '')
        FROM tbl_fatura WHERE id = %s
        """,
        (int(id_fatura),),
    )
    fat = cur.fetchone()
    if not fat or (fat[4] or "") != "pago":
        return
    valor = int(fat[2] or 0)
    plano = (fat[3] or "").strip().lower()
    if valor <= 0 or plano in _PLANOS_SEM_COMISSAO:
        return
    cur.execute("SELECT 1 FROM tbl_comissao_item WHERE id_fatura = %s", (int(id_fatura),))
    if cur.fetchone():
        return

    id_vendedor = int(fat[1])
    origem_id = _fornecedor_primeiro_vinculo(cur, id_vendedor)
    if not origem_id:
        return
    pai = pai_da_indicacao(cur, origem_id)
    if pai:
        cfg = _config_row(cur, pai)
        if not cfg or not cfg["ativo"]:
            return
        beneficiario = pai
        origem = "indicado"
        percentual = cfg["percentual_indicado"]
    else:
        cfg = _config_row(cur, origem_id)
        if not cfg or not cfg["ativo"]:
            return
        beneficiario = origem_id
        origem = "proprio"
        percentual = cfg["percentual_proprio"]
    if _pct(percentual) <= 0:
        return
    comissao = calcular_comissao_centavos(
        valor,
        base=cfg["base"],
        percentual=percentual,
        impostos=cfg["impostos"],
    )
    cur.execute(
        """
        INSERT INTO tbl_comissao_item (
          id_fatura, id_tenant_vendedor, id_tenant_beneficiario, id_tenant_origem,
          origem, referencia, plano_slug, valor_pago_centavos, base, percentual,
          impostos, valor_comissao_centavos, pago_em, status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,'aberto')
        ON CONFLICT (id_fatura) DO NOTHING
        """,
        (
            int(id_fatura),
            id_vendedor,
            beneficiario,
            origem_id,
            origem,
            fat[6] or "",
            plano,
            valor,
            cfg["base"],
            _pct(percentual),
            json.dumps(cfg["impostos"], ensure_ascii=False),
            comissao,
            fat[5],
        ),
    )


def _fornecedor_primeiro_vinculo(cur, id_vendedor: int) -> int | None:
    """Entre os vínculos ativos, a comissão fica com o fornecedor a que o vendedor se conectou primeiro."""
    cur.execute(
        """
        SELECT id_tenant_fornecedor
        FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND status = 'ativo'
        ORDER BY COALESCE(respondido_em, solicitado_em), id
        LIMIT 1
        """,
        (int(id_vendedor),),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _nome(cur, id_tenant: int) -> str:
    cur.execute(f"SELECT {_nome_tenant_sql()} FROM tbl_tenant WHERE id = %s", (int(id_tenant),))
    row = cur.fetchone()
    return row[0] if row else "Conta"


def dados_config_comissao(cur, id_tenant: int) -> dict:
    cfg = _config_row(cur, id_tenant) or {
        "ativo": False,
        "base": "faturamento",
        "percentual_proprio": 0.0,
        "percentual_indicado": 0.0,
        "impostos": [],
    }
    pai = pai_da_indicacao(cur, id_tenant)
    cur.execute(
        """
        SELECT i.id_tenant_indicado,
               COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), NULLIF(TRIM(t.nome), ''), 'Conta')
        FROM tbl_comissao_indicacao i
        JOIN tbl_tenant t ON t.id = i.id_tenant_indicado
        WHERE i.id_tenant_pai = %s
        ORDER BY 2
        """,
        (int(id_tenant),),
    )
    indicados = [{"id": int(r[0]), "nome": r[1]} for r in cur.fetchall()]
    return {
        **cfg,
        "pai_id": pai,
        "pai_nome": _nome(cur, pai) if pai else "",
        "indicados": indicados,
        "preview": {
            "faturamento": calcular_comissao_centavos(
                10000, base="faturamento", percentual=cfg["percentual_proprio"], impostos=cfg["impostos"]
            ),
            "liquido": calcular_comissao_centavos(
                10000, base="liquido", percentual=cfg["percentual_proprio"], impostos=cfg["impostos"]
            ),
        },
    }


def salvar_config_comissao(cur, id_tenant: int, body: dict) -> None:
    id_tenant = int(id_tenant)
    pai = pai_da_indicacao(cur, id_tenant)
    ativo = bool(body.get("ativo"))
    if pai and ativo:
        raise ValueError(
            f"Este fornecedor está indicado por {_nome(cur, pai)}. "
            "A comissão nova vai para quem indicou."
        )
    base = (body.get("base") or "faturamento").strip().lower()
    if base not in ("faturamento", "liquido"):
        base = "faturamento"
    impostos = _impostos_limpos(body.get("impostos"))
    soma = sum(_dec(i["percentual"]) for i in impostos)
    if soma > 100:
        raise ValueError("A soma dos impostos não pode passar de 100%.")
    proprio = _pct(body.get("percentual_proprio"))
    indicado = _pct(body.get("percentual_indicado"))
    cur.execute(
        """
        INSERT INTO tbl_comissao_config (
          id_tenant, ativo, base, percentual_proprio, percentual_indicado, impostos, atualizado_em
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb, NOW())
        ON CONFLICT (id_tenant) DO UPDATE SET
          ativo = EXCLUDED.ativo,
          base = EXCLUDED.base,
          percentual_proprio = EXCLUDED.percentual_proprio,
          percentual_indicado = EXCLUDED.percentual_indicado,
          impostos = EXCLUDED.impostos,
          atualizado_em = NOW()
        """,
        (id_tenant, ativo and not pai, base, proprio, indicado, json.dumps(impostos, ensure_ascii=False)),
    )

    ids_ind = []
    for x in body.get("indicados") or []:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n > 0 and n != id_tenant and n not in ids_ind:
            ids_ind.append(n)
    if pai and ids_ind:
        raise ValueError("Fornecedor indicado não indica outro.")
    cur.execute(
        "SELECT id_tenant_indicado FROM tbl_comissao_indicacao WHERE id_tenant_pai = %s",
        (id_tenant,),
    )
    atuais = {int(r[0]) for r in cur.fetchall()}
    novos = set(ids_ind)
    for sair in atuais - novos:
        cur.execute(
            "DELETE FROM tbl_comissao_indicacao WHERE id_tenant_pai = %s AND id_tenant_indicado = %s",
            (id_tenant, sair),
        )
    for entrar in novos - atuais:
        cur.execute(
            "SELECT tipo_negocio FROM tbl_tenant WHERE id = %s",
            (entrar,),
        )
        row = cur.fetchone()
        if not row or (row[0] or "") not in ("fornecedor", "hibrido"):
            raise ValueError("Só um fornecedor pode ser indicado.")
        cur.execute(
            "SELECT id_tenant_pai FROM tbl_comissao_indicacao WHERE id_tenant_indicado = %s",
            (entrar,),
        )
        outro = cur.fetchone()
        if outro and int(outro[0]) != id_tenant:
            raise ValueError(f"{_nome(cur, entrar)} já está indicado por outra conta.")
        cur.execute(
            "SELECT 1 FROM tbl_comissao_indicacao WHERE id_tenant_pai = %s",
            (entrar,),
        )
        if cur.fetchone():
            raise ValueError(f"{_nome(cur, entrar)} já indica outros fornecedores.")
        cur.execute(
            """
            INSERT INTO tbl_comissao_indicacao (id_tenant_indicado, id_tenant_pai)
            VALUES (%s, %s)
            ON CONFLICT (id_tenant_indicado) DO UPDATE SET id_tenant_pai = EXCLUDED.id_tenant_pai
            """,
            (entrar, id_tenant),
        )
        cur.execute(
            """
            INSERT INTO tbl_comissao_config (id_tenant, ativo, atualizado_em)
            VALUES (%s, FALSE, NOW())
            ON CONFLICT (id_tenant) DO UPDATE SET ativo = FALSE, atualizado_em = NOW()
            """,
            (entrar,),
        )


def listar_baixas_comissao(cur, status: str) -> dict:
    st = "pago" if (status or "") == "pago" else "aguardando"
    cur.execute(
        """
        SELECT status, COUNT(*)::int
        FROM tbl_comissao_fechamento
        WHERE status IN ('aguardando', 'pago')
        GROUP BY status
        """
    )
    cont = {r[0]: int(r[1]) for r in cur.fetchall()}
    ordem = "f.pago_em DESC NULLS LAST, f.id DESC" if st == "pago" else "f.vencimento_em ASC, f.id ASC"
    cur.execute(
        f"""
        SELECT f.id, f.id_tenant_fornecedor,
               COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), NULLIF(TRIM(t.nome), ''), 'Conta'),
               f.valor_centavos, f.vencimento_em, f.criado_em, f.pago_em,
               f.nf_nome, f.pix_tipo, f.pix_chave, f.status,
               f.comprovante_nome
        FROM tbl_comissao_fechamento f
        JOIN tbl_tenant t ON t.id = f.id_tenant_fornecedor
        WHERE f.status = %s
        ORDER BY {ordem}
        LIMIT 200
        """,
        (st,),
    )
    itens = []
    for r in cur.fetchall():
        itens.append(
            {
                "id": int(r[0]),
                "id_tenant": int(r[1]),
                "fornecedor": r[2] or "",
                "valor_centavos": int(r[3] or 0),
                "vencimento_em": r[4].isoformat() if r[4] else "",
                "criado_em": r[5].isoformat() if r[5] else "",
                "pago_em": r[6].isoformat() if r[6] else "",
                "nf_nome": r[7] or "",
                "pix_tipo": r[8] or "",
                "pix_chave": r[9] or "",
                "status": r[10] or "",
                "comprovante_nome": r[11] or "",
            }
        )
    return {
        "status": st,
        "itens": itens,
        "qtd_aguardando": cont.get("aguardando", 0),
        "qtd_pago": cont.get("pago", 0),
    }


def gravar_comprovante_fechamento(cur, id_fechamento: int, nome: str, caminho: str) -> int:
    cur.execute(
        """
        UPDATE tbl_comissao_fechamento
        SET comprovante_nome = %s, comprovante_caminho = %s
        WHERE id = %s AND status = 'aguardando'
        RETURNING id_tenant_fornecedor
        """,
        ((nome or "comprovante")[:180], caminho, int(id_fechamento)),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Fechamento não encontrado ou já pago.")
    return int(row[0])


def caminho_comprovante_fechamento(cur, id_fechamento: int) -> tuple[str, str] | None:
    cur.execute(
        """
        SELECT comprovante_caminho, comprovante_nome
        FROM tbl_comissao_fechamento
        WHERE id = %s
        """,
        (int(id_fechamento),),
    )
    row = cur.fetchone()
    if not row or not (row[0] or "").strip():
        return None
    return row[0], row[1] or "comprovante"


def dar_baixa_fechamento(cur, id_tenant: int, id_fechamento: int) -> None:
    cur.execute(
        """
        SELECT COALESCE(comprovante_caminho, '')
        FROM tbl_comissao_fechamento
        WHERE id = %s AND id_tenant_fornecedor = %s AND status = 'aguardando'
        """,
        (int(id_fechamento), int(id_tenant)),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Fechamento não encontrado ou já pago.")
    if not str(row[0] or "").strip():
        raise ValueError("Anexe o comprovante de pagamento antes da baixa.")
    cur.execute(
        """
        UPDATE tbl_comissao_fechamento
        SET status = 'pago', pago_em = NOW()
        WHERE id = %s AND id_tenant_fornecedor = %s AND status = 'aguardando'
        """,
        (int(id_fechamento), int(id_tenant)),
    )
    if cur.rowcount == 0:
        raise ValueError("Fechamento não encontrado ou já pago.")


def _pix_fornecedor(cur, id_tenant: int) -> dict:
    from api.pix_manual.pix_manual import carregar_config_pix_manual, pix_manual_ativo

    if not pix_manual_ativo(cur, int(id_tenant)):
        return {"ok": False, "tipo": "", "chave": ""}
    cfg = carregar_config_pix_manual(cur, int(id_tenant))
    chave = (cfg.get("chave_pix") or "").strip()
    if not chave:
        return {"ok": False, "tipo": "", "chave": ""}
    return {"ok": True, "tipo": cfg.get("tipo_chave") or "", "chave": chave}


def _somar_meses(inicio: date, meses: int) -> date:
    meses = int(meses or 0)
    y = inicio.year + (inicio.month - 1 + meses) // 12
    m = (inicio.month - 1 + meses) % 12 + 1
    if m == 12:
        ultimo = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo = date(y, m + 1, 1) - timedelta(days=1)
    return date(y, m, min(inicio.day, ultimo.day))


def _como_data(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _periodo_valido(ano: int | None, mes: int | None) -> tuple[int, int]:
    hoje = hoje_sp()
    try:
        ano_i = int(ano) if ano else hoje.year
    except (TypeError, ValueError):
        ano_i = hoje.year
    try:
        mes_i = int(mes) if mes else hoje.month
    except (TypeError, ValueError):
        mes_i = hoje.month
    if ano_i < 2000 or ano_i > 2100:
        ano_i = hoje.year
    if mes_i < 1 or mes_i > 12:
        mes_i = hoje.month
    return ano_i, mes_i


def _dia_no_mes(ano: int, mes: int, dia: int) -> date:
    dia = max(1, min(28, int(dia or 15)))
    return date(ano, mes, dia)


def _primeiro_vencimento(a_partir: date, dia: int) -> date:
    dia = max(1, min(28, int(dia or 15)))
    cand = date(a_partir.year, a_partir.month, dia)
    if cand < a_partir:
        cand = _somar_meses(cand, 1)
    return cand


def _lote_no_mes(cur, id_tenant: int, dia: date | None = None) -> bool:
    d = (dia or hoje_sp()).replace(day=1)
    prox = _somar_meses(d, 1)
    cur.execute(
        """
        SELECT 1 FROM tbl_comissao_fechamento
        WHERE id_tenant_fornecedor = %s
          AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date >= %s
          AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date < %s
        LIMIT 1
        """,
        (int(id_tenant), d, prox),
    )
    return cur.fetchone() is not None


def _frase_topo(hoje: date, *, lote: bool, janela: bool, pix_ok: bool, tem_aberto: bool) -> str:
    atual = _MESES[hoje.month]
    prox_data = _somar_meses(hoje.replace(day=1), 1)
    prox = _MESES[prox_data.month]
    if lote:
        return f"{atual.capitalize()} já foi faturado. O que ficou em aberto entra em {prox}."
    if janela and not pix_ok:
        return "Conecte o PIX Manual em Integrações para faturar até o dia 10."
    if janela and not tem_aberto:
        return "Nada em aberto para faturar neste período."
    if janela:
        return "Feche até o dia 10. O vencimento deste lote é dia 20."
    return f"O próximo fechamento é de 1 a 10 de {prox}."


def _vendedores_rede(cur, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        WITH rede AS (
          SELECT %s::int AS id_fornecedor
          UNION
          SELECT id_tenant_indicado FROM tbl_comissao_indicacao WHERE id_tenant_pai = %s
        )
        SELECT t.id,
               COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), NULLIF(TRIM(t.nome), ''), 'Vendedor'),
               COALESCE(t.plano, ''),
               COALESCE(t.tipo_negocio, ''),
               COALESCE(tc.dia_vencimento, 15),
               COALESCE(NULLIF(tc.periodicidade, ''), 'mensal'),
               COALESCE(p.valor_centavos, 0),
               prim.id_tenant_fornecedor,
               CASE WHEN prim.id_tenant_fornecedor = %s THEN '' ELSE
                 COALESCE(NULLIF(TRIM(tf.nome_fantasia), ''), NULLIF(TRIM(tf.nome), ''), '')
               END
        FROM tbl_tenant t
        JOIN LATERAL (
          SELECT v.id_tenant_fornecedor
          FROM tbl_vinculo_vendedor_fornecedor v
          WHERE v.id_tenant_vendedor = t.id AND v.status = 'ativo'
          ORDER BY COALESCE(v.respondido_em, v.solicitado_em), v.id
          LIMIT 1
        ) prim ON prim.id_tenant_fornecedor IN (SELECT id_fornecedor FROM rede)
        LEFT JOIN tbl_tenant_cobranca tc ON tc.id_tenant = t.id
        LEFT JOIN tbl_plano p ON p.slug = t.plano
        LEFT JOIN tbl_tenant tf ON tf.id = prim.id_tenant_fornecedor
        WHERE COALESCE(t.ativo, TRUE) = TRUE
          AND COALESCE(t.plano, '') NOT IN ('', 'starter')
          AND COALESCE(p.valor_centavos, 0) > 0
          AND NOT (
            COALESCE(t.eh_fornecedor_fundador, FALSE)
            AND COALESCE(t.fornecedor_fundador_ativo, FALSE)
          )
        ORDER BY 2
        """,
        (int(id_tenant), int(id_tenant), int(id_tenant)),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": int(r[0]),
                "nome": r[1] or "Vendedor",
                "plano": (r[2] or "").strip().lower(),
                "tipo": r[3] or "",
                "dia": int(r[4] or 15),
                "periodo": (r[5] or "mensal").strip().lower(),
                "catalogo": int(r[6] or 0),
                "origem_id": int(r[7]),
                "via": r[8] or "",
            }
        )
    return out


def _ultimas_faturas(cur, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    cur.execute(
        """
        SELECT DISTINCT ON (id_tenant)
          id_tenant, status, valor_centavos, vencimento_em, COALESCE(referencia, ''),
          COALESCE(plano_slug, ''),
          COALESCE(pago_em, criado_em)::date,
          COALESCE(meses_cobertos, 1)
        FROM tbl_fatura
        WHERE id_tenant = ANY(%s)
          AND status IN ('pendente', 'pago', 'vencido')
          AND COALESCE(plano_slug, '') NOT IN ('', 'starter')
        ORDER BY id_tenant, id DESC
        """,
        (ids,),
    )
    out = {}
    for r in cur.fetchall():
        out[int(r[0])] = {
            "status": r[1] or "",
            "valor": int(r[2] or 0),
            "vencimento": _como_data(r[3]),
            "referencia": r[4] or "",
            "plano": (r[5] or "").strip().lower(),
            "base": _como_data(r[6]),
            "meses": max(1, int(r[7] or 1)),
        }
    return out


def _faturas_no_mes(cur, ids: list[int], inicio: date, fim: date) -> dict[int, dict]:
    if not ids:
        return {}
    cur.execute(
        """
        SELECT DISTINCT ON (id_tenant)
          id, id_tenant, COALESCE(referencia, ''), COALESCE(plano_slug, ''),
          valor_centavos, vencimento_em, status
        FROM tbl_fatura
        WHERE id_tenant = ANY(%s)
          AND status IN ('pendente', 'vencido')
          AND vencimento_em IS NOT NULL
          AND vencimento_em::date >= %s
          AND vencimento_em::date <= %s
          AND COALESCE(plano_slug, '') NOT IN ('', 'starter')
        ORDER BY id_tenant, vencimento_em, id
        """,
        (ids, inicio, fim),
    )
    out = {}
    for r in cur.fetchall():
        out[int(r[1])] = {
            "id": int(r[0]),
            "referencia": r[2] or "",
            "plano": (r[3] or "").strip().lower(),
            "valor": int(r[4] or 0),
            "vencimento": _como_data(r[5]),
            "status": r[6] or "",
        }
    return out


def _cobra_no_vencimento(due: date, ultima: dict | None, dia: int, hoje: date) -> bool:
    """A previsão mostra só a próxima cobrança, no mês em que ela vence."""
    if due < hoje:
        return False
    if not ultima:
        primeiro = _primeiro_vencimento(hoje, dia)
    elif ultima["status"] in ("pendente", "vencido"):
        return False
    else:
        base = ultima.get("base")
        if not base:
            return False
        primeiro = _primeiro_vencimento(_somar_meses(base, int(ultima["meses"] or 1)), dia)
    return due == primeiro


def _linhas_ciclo(cur, id_tenant: int, cfg: dict | None, ano: int, mes: int) -> tuple[list[dict], list[dict]]:
    """Previsão do mês (ainda no prazo) e inadimplência do mês (vencimento já passou)."""
    hoje = hoje_sp()
    inicio = date(ano, mes, 1)
    if pai_da_indicacao(cur, id_tenant) or not cfg or not cfg["ativo"]:
        return [], []

    from sistema.financeiro.assinaturas_painel import nome_plano_comercial
    from sistema.financeiro.cupom import PERIODOS, calcular_preco

    vendedores = _vendedores_rede(cur, id_tenant)
    ids = [v["id"] for v in vendedores]
    fim = _somar_meses(inicio, 1) - timedelta(days=1)
    abertas = _faturas_no_mes(cur, ids, inicio, fim)
    ultimas = _ultimas_faturas(cur, ids)
    previsoes = []
    inadimplentes = []
    for v in vendedores:
        origem = "proprio" if v["origem_id"] == int(id_tenant) else "indicado"
        percentual = cfg["percentual_proprio"] if origem == "proprio" else cfg["percentual_indicado"]
        if _pct(percentual) <= 0:
            continue
        aberta = abertas.get(v["id"])
        if aberta and aberta["vencimento"] and aberta["vencimento"] < hoje:
            inadimplentes.append(
                {
                    "id": aberta["id"],
                    "referencia": aberta["referencia"],
                    "plano": nome_plano_comercial(aberta["plano"] or v["plano"], v["tipo"]),
                    "valor_centavos": aberta["valor"],
                    "vencimento_em": aberta["vencimento"].isoformat(),
                    "status": aberta["status"],
                    "vendedor": v["nome"],
                    "via": v["via"],
                }
            )
            continue
        valor = 0
        venc = None
        referencia = ""
        plano_slug = v["plano"]
        if aberta and aberta["vencimento"] and aberta["vencimento"] >= hoje and aberta["valor"] > 0:
            valor = aberta["valor"]
            venc = aberta["vencimento"]
            referencia = aberta["referencia"]
            plano_slug = aberta["plano"] or v["plano"]
        elif not aberta and inicio >= date(hoje.year, hoje.month, 1):
            periodo = v["periodo"] if v["periodo"] in PERIODOS else "mensal"
            due = _dia_no_mes(ano, mes, v["dia"])
            if _cobra_no_vencimento(due, ultimas.get(v["id"]), v["dia"], hoje):
                valor = int(calcular_preco(v["catalogo"], periodo)["valor_final_centavos"] or 0)
                venc = due
        if not venc or valor <= 0:
            continue
        comissao = calcular_comissao_centavos(
            valor, base=cfg["base"], percentual=percentual, impostos=cfg["impostos"]
        )
        if comissao <= 0:
            continue
        previsoes.append(
            {
                "id": int(aberta["id"]) if aberta else 0,
                "referencia": referencia,
                "plano": nome_plano_comercial(plano_slug, v["tipo"]),
                "vendedor": v["nome"],
                "via": v["via"],
                "vencimento_em": venc.isoformat(),
                "valor_pago_centavos": valor,
                "valor_comissao_centavos": comissao,
                "percentual": float(_pct(percentual)),
                "base": cfg["base"],
                "impostos": cfg["impostos"],
                "origem": origem,
                "previsao": True,
            }
        )
    previsoes.sort(key=lambda i: (i["vencimento_em"], i["vendedor"]))
    inadimplentes.sort(key=lambda i: (i["vencimento_em"], i["vendedor"]))
    return previsoes, inadimplentes


def painel_comissoes(
    cur, id_tenant: int, *, ano: int | None = None, mes: int | None = None, ano_faturado: int | None = None
) -> dict:
    id_tenant = int(id_tenant)
    cfg = _config_row(cur, id_tenant)
    pai = pai_da_indicacao(cur, id_tenant)
    pix = _pix_fornecedor(cur, id_tenant)
    cur.execute(
        """
        SELECT i.id, i.referencia, i.plano_slug, i.valor_pago_centavos, i.valor_comissao_centavos,
               i.pago_em, i.origem, i.percentual, i.base, i.impostos,
               COALESCE(NULLIF(TRIM(tv.nome_fantasia), ''), NULLIF(TRIM(tv.nome), ''), 'Vendedor'),
               COALESCE(NULLIF(TRIM(to2.nome_fantasia), ''), NULLIF(TRIM(to2.nome), ''), '')
        FROM tbl_comissao_item i
        JOIN tbl_tenant tv ON tv.id = i.id_tenant_vendedor
        LEFT JOIN tbl_tenant to2 ON to2.id = i.id_tenant_origem AND i.origem = 'indicado'
        WHERE i.id_tenant_beneficiario = %s AND i.status = 'aberto'
        ORDER BY i.pago_em DESC, i.id DESC
        """,
        (id_tenant,),
    )
    abertos = []
    total_aberto = 0
    for r in cur.fetchall():
        total_aberto += int(r[4] or 0)
        abertos.append(
            {
                "id": int(r[0]),
                "referencia": r[1] or "",
                "plano": r[2] or "",
                "valor_pago_centavos": int(r[3] or 0),
                "valor_comissao_centavos": int(r[4] or 0),
                "pago_em": r[5].isoformat() if r[5] else "",
                "origem": r[6],
                "percentual": float(r[7] or 0),
                "base": r[8],
                "impostos": _impostos_limpos(r[9]),
                "vendedor": r[10],
                "via": r[11] or "",
            }
        )
    hoje = hoje_sp()
    ano_i, mes_i = _periodo_valido(ano, mes)
    try:
        ano_fat = int(ano_faturado or 0)
    except (TypeError, ValueError):
        ano_fat = 0
    if ano_fat < 2000 or ano_fat > 2100:
        ano_fat = 0
    inicio_12 = _somar_meses(hoje.replace(day=1), -11)
    if ano_fat:
        filtro_fat = (
            "AND EXTRACT(YEAR FROM (criado_em AT TIME ZONE 'America/Sao_Paulo'))::int = %s",
            (id_tenant, ano_fat),
        )
    else:
        filtro_fat = (
            "AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date >= %s",
            (id_tenant, inicio_12),
        )
    cur.execute(
        f"""
        SELECT id, valor_centavos, vencimento_em, status, criado_em, nf_nome, pago_em
        FROM tbl_comissao_fechamento
        WHERE id_tenant_fornecedor = %s
          {filtro_fat[0]}
        ORDER BY criado_em DESC, id DESC
        """,
        filtro_fat[1],
    )
    faturados = [
        {
            "id": int(r[0]),
            "valor_centavos": int(r[1] or 0),
            "vencimento_em": r[2].isoformat() if r[2] else "",
            "status": r[3],
            "criado_em": r[4].isoformat() if r[4] else "",
            "nf_nome": r[5] or "",
            "pago_em": r[6].isoformat() if r[6] else "",
        }
        for r in cur.fetchall()
    ]
    cur.execute(
        """
        SELECT DISTINCT EXTRACT(YEAR FROM (criado_em AT TIME ZONE 'America/Sao_Paulo'))::int
        FROM tbl_comissao_fechamento
        WHERE id_tenant_fornecedor = %s
        ORDER BY 1 DESC
        """,
        (id_tenant,),
    )
    anos_faturado = [int(r[0]) for r in cur.fetchall() if r[0]]
    if hoje.year not in anos_faturado:
        anos_faturado.append(hoje.year)
        anos_faturado.sort(reverse=True)
    previsoes, inadimplentes = _linhas_ciclo(cur, id_tenant, cfg, ano_i, mes_i)
    lote = _lote_no_mes(cur, id_tenant, hoje)
    janela = janela_fechamento(hoje)
    return {
        "ativo": bool(cfg and cfg["ativo"]),
        "pai_nome": _nome(cur, pai) if pai else "",
        "janela_aberta": janela,
        "lote_no_mes": lote,
        "pode_faturar": bool(janela and pix["ok"] and not lote),
        "frase": _frase_topo(hoje, lote=lote, janela=janela, pix_ok=pix["ok"], tem_aberto=bool(abertos)),
        "hoje": hoje.isoformat(),
        "ano": ano_i,
        "mes": mes_i,
        "ano_faturado": ano_fat,
        "anos_periodo": sorted({hoje.year - 1, hoje.year, hoje.year + 1, ano_i}),
        "anos_faturado": anos_faturado,
        "vencimento_se_fechar": vencimento_fechamento(hoje).isoformat(),
        "pix_ok": pix["ok"],
        "pix_tipo": pix["tipo"],
        "pix_chave": pix["chave"],
        "total_aberto_centavos": total_aberto,
        "previsoes": previsoes,
        "abertos": abertos,
        "faturados": faturados,
        "inadimplentes": inadimplentes,
    }


def fechar_comissoes(
    cur, id_tenant: int, *, nf_nome: str, nf_caminho: str, ids: list[int]
) -> dict:
    hoje = hoje_sp()
    if not janela_fechamento(hoje):
        raise ValueError("O fechamento fica disponível do dia 1 ao dia 10.")
    if _lote_no_mes(cur, int(id_tenant), hoje):
        prox = _MESES[_somar_meses(hoje.replace(day=1), 1).month]
        raise ValueError(
            f"{_MESES[hoje.month].capitalize()} já foi faturado. "
            f"O que ficou em aberto entra em {prox}."
        )
    pix = _pix_fornecedor(cur, int(id_tenant))
    if not pix["ok"]:
        raise ValueError("Conecte o PIX Manual em Integrações antes de faturar.")
    if not (nf_caminho or "").strip():
        raise ValueError("Anexe a nota fiscal do período.")
    escolhidos = sorted({int(i) for i in (ids or []) if int(i) > 0})
    if not escolhidos:
        raise ValueError("Selecione ao menos uma comissão.")
    cur.execute(
        """
        SELECT id, valor_comissao_centavos FROM tbl_comissao_item
        WHERE id_tenant_beneficiario = %s AND status = 'aberto' AND id = ANY(%s)
        ORDER BY id
        """,
        (int(id_tenant), escolhidos),
    )
    rows = cur.fetchall()
    if len(rows) != len(escolhidos):
        raise ValueError("Algum item selecionado não está mais em aberto.")
    total = sum(int(r[1] or 0) for r in rows)
    venc = vencimento_fechamento()
    cur.execute(
        """
        INSERT INTO tbl_comissao_fechamento (
          id_tenant_fornecedor, valor_centavos, vencimento_em, nf_caminho, nf_nome,
          pix_tipo, pix_chave, status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,'aguardando')
        RETURNING id
        """,
        (
            int(id_tenant),
            total,
            venc,
            nf_caminho,
            (nf_nome or "nota.pdf")[:180],
            pix["tipo"],
            pix["chave"],
        ),
    )
    fid = int(cur.fetchone()[0])
    ids = [int(r[0]) for r in rows]
    cur.execute(
        """
        UPDATE tbl_comissao_item
        SET status = 'faturado', id_fechamento = %s
        WHERE id = ANY(%s) AND status = 'aberto'
        """,
        (fid, ids),
    )
    cur.execute(
        """
        SELECT COUNT(*) FROM tbl_comissao_item
        WHERE id_tenant_beneficiario = %s AND status = 'aberto'
        """,
        (int(id_tenant),),
    )
    restante = int(cur.fetchone()[0] or 0)
    return {
        "id": fid,
        "valor_centavos": total,
        "vencimento_em": venc.isoformat(),
        "qtd": len(ids),
        "qtd_restante": restante,
    }


def caminho_nf_fechamento(cur, id_fechamento: int, id_tenant: int) -> tuple[str, str] | None:
    cur.execute(
        """
        SELECT nf_caminho, nf_nome FROM tbl_comissao_fechamento
        WHERE id = %s AND id_tenant_fornecedor = %s
        """,
        (int(id_fechamento), int(id_tenant)),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    return row[0], row[1] or "nota.pdf"


def detalhe_fechamento(cur, id_tenant: int, id_fechamento: int) -> dict | None:
    cur.execute(
        """
        SELECT id, valor_centavos, vencimento_em, status, criado_em, nf_nome, pago_em
        FROM tbl_comissao_fechamento
        WHERE id = %s AND id_tenant_fornecedor = %s
        """,
        (int(id_fechamento), int(id_tenant)),
    )
    cab = cur.fetchone()
    if not cab:
        return None
    cur.execute(
        """
        SELECT i.referencia, i.plano_slug, i.valor_pago_centavos, i.valor_comissao_centavos,
               i.pago_em, i.origem,
               COALESCE(NULLIF(TRIM(tv.nome_fantasia), ''), NULLIF(TRIM(tv.nome), ''), 'Vendedor'),
               COALESCE(NULLIF(TRIM(to2.nome_fantasia), ''), NULLIF(TRIM(to2.nome), ''), '')
        FROM tbl_comissao_item i
        JOIN tbl_tenant tv ON tv.id = i.id_tenant_vendedor
        LEFT JOIN tbl_tenant to2 ON to2.id = i.id_tenant_origem AND i.origem = 'indicado'
        WHERE i.id_fechamento = %s AND i.id_tenant_beneficiario = %s
        ORDER BY tv.nome_fantasia, i.id
        """,
        (int(id_fechamento), int(id_tenant)),
    )
    itens = [
        {
            "referencia": r[0] or "",
            "plano": r[1] or "",
            "valor_pago_centavos": int(r[2] or 0),
            "valor_comissao_centavos": int(r[3] or 0),
            "pago_em": r[4].isoformat() if r[4] else "",
            "origem": r[5] or "",
            "vendedor": r[6] or "",
            "via": r[7] or "",
        }
        for r in cur.fetchall()
    ]
    return {
        "id": int(cab[0]),
        "valor_centavos": int(cab[1] or 0),
        "vencimento_em": cab[2].isoformat() if cab[2] else "",
        "status": cab[3] or "",
        "criado_em": cab[4].isoformat() if cab[4] else "",
        "nf_nome": cab[5] or "",
        "pago_em": cab[6].isoformat() if cab[6] else "",
        "itens": itens,
    }


def buscar_fornecedores_comissao(cur, id_tenant: int, termo: str) -> list[dict]:
    q = f"%{(termo or '').strip()}%"
    cur.execute(
        """
        SELECT t.id,
               COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), NULLIF(TRIM(t.nome), ''), 'Conta')
        FROM tbl_tenant t
        WHERE t.tipo_negocio IN ('fornecedor', 'hibrido')
          AND t.id <> %s
          AND (t.nome ILIKE %s OR t.nome_fantasia ILIKE %s OR t.documento ILIKE %s)
          AND NOT EXISTS (
            SELECT 1 FROM tbl_comissao_indicacao i
            WHERE i.id_tenant_indicado = t.id AND i.id_tenant_pai <> %s
          )
          AND NOT EXISTS (
            SELECT 1 FROM tbl_comissao_indicacao i WHERE i.id_tenant_pai = t.id
          )
        ORDER BY 2
        LIMIT 12
        """,
        (int(id_tenant), q, q, q, int(id_tenant)),
    )
    return [{"id": int(r[0]), "nome": r[1]} for r in cur.fetchall()]
