# sistema/financeiro/comissao.py — comissão do fornecedor sobre a mensalidade paga
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Sao_Paulo")
_PLANOS_SEM_COMISSAO = frozenset({"", "starter"})


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


def painel_comissoes(cur, id_tenant: int) -> dict:
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
    cur.execute(
        """
        SELECT id, valor_centavos, vencimento_em, status, criado_em, nf_nome, pix_chave, pago_em
        FROM tbl_comissao_fechamento
        WHERE id_tenant_fornecedor = %s
        ORDER BY id DESC
        LIMIT 36
        """,
        (id_tenant,),
    )
    faturados = [
        {
            "id": int(r[0]),
            "valor_centavos": int(r[1] or 0),
            "vencimento_em": r[2].isoformat() if r[2] else "",
            "status": r[3],
            "criado_em": r[4].isoformat() if r[4] else "",
            "nf_nome": r[5] or "",
            "pix_chave": r[6] or "",
            "pago_em": r[7].isoformat() if r[7] else "",
        }
        for r in cur.fetchall()
    ]
    cur.execute(
        """
        SELECT f.id, f.referencia, f.plano_slug, f.valor_centavos, f.vencimento_em, f.status,
               COALESCE(NULLIF(TRIM(tv.nome_fantasia), ''), NULLIF(TRIM(tv.nome), ''), 'Vendedor'),
               CASE WHEN prim.id_tenant_fornecedor = %s THEN '' ELSE
                 COALESCE(NULLIF(TRIM(tf.nome_fantasia), ''), NULLIF(TRIM(tf.nome), ''), '')
               END
        FROM tbl_fatura f
        JOIN LATERAL (
          SELECT v.id_tenant_fornecedor
          FROM tbl_vinculo_vendedor_fornecedor v
          WHERE v.id_tenant_vendedor = f.id_tenant AND v.status = 'ativo'
          ORDER BY COALESCE(v.respondido_em, v.solicitado_em), v.id
          LIMIT 1
        ) prim ON TRUE
        JOIN tbl_tenant tv ON tv.id = f.id_tenant
        LEFT JOIN tbl_tenant tf ON tf.id = prim.id_tenant_fornecedor
        WHERE f.status IN ('pendente', 'vencido')
          AND f.vencimento_em IS NOT NULL
          AND f.vencimento_em::date < (NOW() AT TIME ZONE 'America/Sao_Paulo')::date
          AND COALESCE(f.plano_slug, '') NOT IN ('', 'starter')
          AND (
            prim.id_tenant_fornecedor = %s
            OR prim.id_tenant_fornecedor IN (
              SELECT id_tenant_indicado FROM tbl_comissao_indicacao WHERE id_tenant_pai = %s
            )
          )
        ORDER BY f.vencimento_em
        """,
        (id_tenant, id_tenant, id_tenant),
    )
    inadimplentes = [
        {
            "id": int(r[0]),
            "referencia": r[1] or "",
            "plano": r[2] or "",
            "valor_centavos": int(r[3] or 0),
            "vencimento_em": r[4].isoformat() if r[4] else "",
            "status": r[5],
            "vendedor": r[6],
            "via": r[7] or "",
        }
        for r in cur.fetchall()
    ]
    return {
        "ativo": bool(cfg and cfg["ativo"]),
        "pai_nome": _nome(cur, pai) if pai else "",
        "janela_aberta": janela_fechamento(),
        "hoje": hoje_sp().isoformat(),
        "vencimento_se_fechar": vencimento_fechamento().isoformat(),
        "pix_ok": pix["ok"],
        "pix_tipo": pix["tipo"],
        "pix_chave": pix["chave"],
        "total_aberto_centavos": total_aberto,
        "abertos": abertos,
        "faturados": faturados,
        "inadimplentes": inadimplentes,
    }


def fechar_comissoes(
    cur, id_tenant: int, *, nf_nome: str, nf_caminho: str, ids: list[int]
) -> dict:
    if not janela_fechamento():
        raise ValueError("O fechamento fica disponível do dia 1 ao dia 10.")
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
    return {"id": fid, "valor_centavos": total, "vencimento_em": venc.isoformat(), "qtd": len(ids)}


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
