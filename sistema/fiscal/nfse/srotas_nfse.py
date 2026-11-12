"""Rotas da fundação multi-tenant de NFS-e (rascunho e validação)."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, session
from psycopg2 import IntegrityError, ProgrammingError
from lxml import etree

from global_utils import (
    Var_ConectarBanco,
    db_execute,
    formatar_cnpj,
    login_obrigatorio,
    somente_digitos,
    validar_cnpj,
    validar_cpf,
)
from sistema.fiscal.nfse.acesso import garantir_sessao_nfse, tenant_pode_nota_fiscal
from sistema.fiscal.nfse.adapter import AdapterNacional, texto_rejeicao
from sistema.fiscal.nfse.crypto_certificado import (
    criptografar,
    descriptografar,
    ler_pkcs12,
    validar_configuracao_criptografica,
)
from sistema.fiscal.nfse.danfse import gerar_danfse, gerar_danfse_modelo
from sistema.fiscal.nfse.importar_nfse import (
    avancar_cursor,
    chave_cancelamento,
    cnpj_emitente_na_chave,
    documentos_do_lote,
    ler_nfse,
    numero_nfse_da_chave,
    xml_do_arquivo,
)
from sistema.fiscal.nfse.dps import ErroDPS, assinar_dps, construir_cancelamento, construir_dps, validar_xml
from sistema.fiscal.nfse.prazo_cancelamento import motivo_bloqueio_cancelamento

_MOD = Path(__file__).resolve().parent

nfse_bp = Blueprint(
    "nfse",
    __name__,
    url_prefix="/nfse",
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/nfse",
)


def init_app(app):
    app.register_blueprint(nfse_bp)
    try:
        validar_configuracao_criptografica()
    except Exception:
        pass


def _nav_nfse(codigo_sufixo: str = "nfse") -> str:
    from sistema.plataforma.sessao import MODULO_FORNECEDOR, garantir_modulo_sessao

    prefix = "fn" if garantir_modulo_sessao() == MODULO_FORNECEDOR else "vd"
    return f"{prefix}_notas_{codigo_sufixo}"


def _nfse_autorizado(fn):
    @wraps(fn)
    @login_obrigatorio()
    def wrapper(*args, **kwargs):
        from sistema.plataforma.sessao import HUB_FINANCEIRO, definir_hub_sessao

        garantir_sessao_nfse()
        if not session.get("id_tenant") or not tenant_pode_nota_fiscal():
            if request.path.startswith("/nfse/api/"):
                return jsonify({"success": False, "message": "Acesso ao módulo NFS-e não autorizado."}), 403
            return render_template(
                "frm_nf_em_breve.html",
                titulo="NFS-e",
                mensagem="Acesso ao módulo NFS-e não autorizado neste tenant.",
                nav_ativo=_nav_nfse("nfse"),
            ), 403
        # Deep link /nfse/* entra no hub Financeiro automaticamente.
        definir_hub_sessao(HUB_FINANCEIRO)
        return fn(*args, **kwargs)

    return wrapper


def _tenant() -> int:
    return int(session["id_tenant"])


def _dict_rows(cur) -> list[dict]:
    cols = [item[0] for item in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _dict_row(cur) -> dict | None:
    cols = [item[0] for item in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def _json_safe(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (bytes, bytearray, memoryview)):
        try:
            return bytes(valor).decode("utf-8")
        except Exception:
            return bytes(valor).hex()
    if isinstance(valor, dict):
        return {k: _json_safe(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_safe(v) for v in valor]
    return valor


def _json_dumps(valor) -> str:
    return json.dumps(_json_safe(valor), ensure_ascii=False, default=str)


def _aplicar_motivo_nacional(row: dict) -> dict:
    """A rejeição já gravada traz Codigo/Descricao em resposta_metadata."""
    meta = row.get("resposta_metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = None
    if isinstance(meta, dict):
        codigo, mensagem = texto_rejeicao(meta)
        if mensagem != "DPS rejeitada pela API Nacional.":
            row["erro_codigo"] = codigo
            row["erro_mensagem"] = mensagem
    row.pop("resposta_metadata", None)
    return row


def _payload_row(row: dict | None):
    dados = _aplicar_motivo_nacional(dict(row or {}))
    return {k: _json_safe(v) for k, v in dados.items()}


def _anexar_series_nfe(conn, dados: dict) -> dict:
    """Inclui série/próximo número da NF-e (tbl_fiscal_config), padrão 1."""
    out = dict(dados or {})
    out.setdefault("serie_nfe", 1)
    out.setdefault("proximo_numero_nfe", 1)
    try:
        from sistema.fiscal.nfe_servico import ler_config

        cfg = ler_config(conn.cursor(), _tenant())
        out["serie_nfe"] = int(cfg.get("serie") or 1)
        out["proximo_numero_nfe"] = int(cfg.get("proximo_numero") or 1)
    except Exception:
        pass
    return out


def _salvar_series_nfe(conn, dados: dict) -> None:
    """Persiste série/próximo número da NF-e sem alterar certificado."""
    try:
        from sistema.fiscal.nfe_servico import salvar_config

        serie = max(1, int(dados.get("serie_nfe") or 1))
        proximo = max(1, int(dados.get("proximo_numero_nfe") or 1))
        salvar_config(
            conn.cursor(),
            _tenant(),
            {"serie": serie, "proximo_numero": proximo},
            None,
            "",
            editar_regras=True,
        )
    except Exception:
        # NFS-e continua salvando mesmo se o módulo NF-e ainda não tiver tabela.
        pass


def _schema_atual(conn) -> str:
    cur = db_execute(conn, "SELECT current_schema()")
    row = cur.fetchone()
    return (row[0] if row else None) or "public"


def _coluna_existe(conn, tabela: str, coluna: str) -> bool:
    cur = db_execute(
        conn,
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (tabela, coluna),
    )
    return cur.fetchone() is not None


def _adicionar_coluna(conn, tabela: str, coluna: str, tipo: str) -> None:
    if _coluna_existe(conn, tabela, coluna):
        return
    schema = _schema_atual(conn).replace('"', "")
    db_execute(
        conn,
        f'ALTER TABLE "{schema}"."{tabela}" ADD COLUMN IF NOT EXISTS {coluna} {tipo}',
    )
    conn.commit()
    if not _coluna_existe(conn, tabela, coluna):
        raise RuntimeError(
            f'Coluna {tabela}.{coluna} continua ausente após ALTER. '
            f"Rode o SQL de migração no banco (sql/21_nfse_tomador_avulso.sql)."
        )


def _garantir_partes_operacao(conn) -> None:
    for nome, tipo in (
        ("id_destinatario_empresa", "INTEGER NULL"),
        ("id_intermediario_empresa", "INTEGER NULL"),
        ("observacoes", "TEXT NULL"),
    ):
        try:
            _adicionar_coluna(conn, "tbl_nfse_nota", nome, tipo)
        except Exception as exc:
            conn.rollback()
            # Destinatário/intermediário/observações já existiam em instalações antigas;
            # se falhar aqui, o INSERT ainda pode funcionar sem elas só se já existirem.
            if not _coluna_existe(conn, "tbl_nfse_nota", nome):
                raise RuntimeError(
                    f"Não foi possível criar a coluna tbl_nfse_nota.{nome}: {exc}"
                ) from exc
    _garantir_tomador_avulso(conn)


def _garantir_tomador_avulso(conn) -> None:
    """Garante colunas de endereço do tomador avulso; falha com mensagem clara se o ALTER for negado."""
    colunas = (
        ("tomador_logradouro", "VARCHAR(220) NULL"),
        ("tomador_numero", "VARCHAR(20) NULL"),
        ("tomador_complemento", "VARCHAR(120) NULL"),
        ("tomador_bairro", "VARCHAR(120) NULL"),
        ("tomador_cidade", "VARCHAR(120) NULL"),
        ("tomador_uf", "CHAR(2) NULL"),
        ("tomador_cep", "VARCHAR(8) NULL"),
        ("tomador_telefone", "VARCHAR(20) NULL"),
    )
    faltando = [nome for nome, _ in colunas if not _coluna_existe(conn, "tbl_nfse_nota", nome)]
    if not faltando:
        return
    erros = []
    for nome, tipo in colunas:
        if nome not in faltando:
            continue
        try:
            _adicionar_coluna(conn, "tbl_nfse_nota", nome, tipo)
        except Exception as exc:
            conn.rollback()
            erros.append(f"{nome}: {exc}")
    ainda = [nome for nome, _ in colunas if not _coluna_existe(conn, "tbl_nfse_nota", nome)]
    if ainda:
        detalhe = "; ".join(erros) if erros else "ALTER executou sem erro, mas as colunas não apareceram."
        raise RuntimeError(
            "Falta migração do tomador avulso em tbl_nfse_nota "
            f"({', '.join(ainda)}). Execute no PostgreSQL o arquivo "
            "sql/21_nfse_tomador_avulso.sql com um usuário dono da tabela. "
            f"Detalhe: {detalhe}"
        )


def _id_opcional(valor):
    if valor in (None, "", 0, "0"):
        return None
    return int(valor)


def _texto_opcional(valor, limite=None):
    texto = " ".join(str(valor or "").split()).strip()
    if not texto:
        return None
    if limite and len(texto) > limite:
        return texto[:limite]
    return texto


def _resolver_tomador(conn, dados: dict):
    """Retorna (id_tomador|None, razao, documento, endereco_dict) a partir do payload."""
    modo = str(dados.get("tomador_modo") or "").strip().lower()
    id_tomador = _id_opcional(dados.get("id_tomador_empresa"))
    if modo == "cadastrado" or (modo != "avulso" and id_tomador):
        if not id_tomador:
            raise ValueError("Selecione um tomador cadastrado em Clientes.")
        tomador = db_execute(
            conn,
            """
            SELECT id, razao_social, cnpj FROM tbl_empresa
             WHERE id=%s AND id_tenant=%s AND ativo=TRUE
            """,
            (id_tomador, _tenant()),
        ).fetchone()
        if not tomador:
            raise ValueError("Selecione um tomador cadastrado em Clientes.")
        documento = somente_digitos(tomador[2]) or None
        return id_tomador, tomador[1], documento, {
            "logradouro": None,
            "numero": None,
            "complemento": None,
            "bairro": None,
            "cidade": None,
            "uf": None,
            "cep": None,
            "telefone": None,
        }

    razao = _texto_opcional(dados.get("tomador_razao_social"), 220)
    documento = somente_digitos(dados.get("tomador_cnpj_cpf"))
    if not razao:
        raise ValueError("Informe o nome ou razão social do tomador.")
    if len(documento) == 11:
        if not validar_cpf(documento):
            raise ValueError("CPF do tomador inválido.")
    elif len(documento) == 14:
        if not validar_cnpj(documento):
            raise ValueError("CNPJ do tomador inválido.")
    else:
        raise ValueError("Informe um CPF (11) ou CNPJ (14) do tomador.")
    uf = (_texto_opcional(dados.get("tomador_uf"), 2) or "").upper() or None
    if uf and len(uf) != 2:
        raise ValueError("UF do tomador deve ter 2 letras.")
    cep = somente_digitos(dados.get("tomador_cep")) or None
    if cep and len(cep) != 8:
        raise ValueError("CEP do tomador deve ter 8 dígitos.")
    return None, razao, documento, {
        "logradouro": _texto_opcional(dados.get("tomador_logradouro"), 220),
        "numero": _texto_opcional(dados.get("tomador_numero"), 20),
        "complemento": _texto_opcional(dados.get("tomador_complemento"), 120),
        "bairro": _texto_opcional(dados.get("tomador_bairro"), 120),
        "cidade": _texto_opcional(dados.get("tomador_cidade"), 120),
        "uf": uf,
        "cep": cep,
        "telefone": somente_digitos(dados.get("tomador_telefone")) or None,
    }


def _empresa_ativa(conn, id_empresa):
    if not id_empresa:
        return None
    return db_execute(
        conn,
        """
        SELECT id, razao_social, cnpj, telefone
          FROM tbl_empresa
         WHERE id=%s AND id_tenant=%s AND ativo=TRUE
        """,
        (id_empresa, _tenant()),
    ).fetchone()


def _bool(valor) -> bool:
    return valor is True or str(valor or "").strip().lower() in {"1", "true", "on", "sim", "yes"}


def _decimal(valor, campo: str) -> Decimal:
    try:
        numero = Decimal(str(valor if valor not in (None, "") else "0").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"{campo} inválido.") from exc
    if numero < 0:
        raise ValueError(f"{campo} não pode ser negativo.")
    return numero


def _auditar(conn, tipo: str, mensagem: str, id_nota=None, dados=None):
    db_execute(
        conn,
        """
        INSERT INTO tbl_nfse_evento
            (id_tenant, id_nota, id_usuario, tipo_evento, mensagem, dados_json)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            _tenant(),
            id_nota,
            session.get("id_usuario"),
            tipo,
            mensagem,
            json.dumps(dados or {}, ensure_ascii=False),
        ),
    )


_MESES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
_MESES_CURTO = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")


def _reais(valor) -> float:
    return float(Decimal(str(valor or 0)).quantize(Decimal("0.01")))


def _dia_faturamento_sql() -> str:
    return "COALESCE((n.dt_autorizacao AT TIME ZONE 'America/Sao_Paulo')::date, n.competencia)"


def _mesmo_dia_ano_anterior(hoje: date) -> date:
    try:
        return date(hoje.year - 1, hoje.month, hoje.day)
    except ValueError:
        return date(hoje.year - 1, hoje.month, 28)


def _meses_fechados(hoje: date, quantidade: int = 3) -> list[tuple[int, int]]:
    """Meses anteriores ao mês corrente, do mais antigo ao mais recente."""
    ano, mes = hoje.year, hoje.month - 1
    if mes == 0:
        mes, ano = 12, ano - 1
    achados: list[tuple[int, int]] = []
    for _ in range(quantidade):
        achados.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return list(reversed(achados))


def _meses_de_distancia(origem: tuple[int, int], destino: tuple[int, int]) -> int:
    return (destino[0] - origem[0]) * 12 + (destino[1] - origem[1])


@nfse_bp.route("/")
@_nfse_autorizado
def dashboard():
    return render_template(
        "frm_nfse_dashboard.html",
        nome=session.get("nome"),
        email=session.get("email"),
        menu_ativo="nfse-dashboard",
        nav_ativo=_nav_nfse("nfse"),
        nfse_aba="dashboard",
    )


@nfse_bp.route("/api/dashboard")
@_nfse_autorizado
def api_dashboard():
    hoje = date.today()
    try:
        ano = int(request.args.get("ano") or hoje.year)
    except (TypeError, ValueError):
        ano = hoje.year
    if ano < 2000 or ano > hoje.year + 1:
        ano = hoje.year
    dia = _dia_faturamento_sql()
    conn = Var_ConectarBanco()
    try:
        anos_cur = db_execute(
            conn,
            f"""
            SELECT DISTINCT EXTRACT(YEAR FROM {dia})::int
              FROM tbl_nfse_nota n
             WHERE n.id_tenant = %s AND n.status = 'autorizada'
             ORDER BY 1
            """,
            (_tenant(),),
        )
        anos = [int(r[0]) for r in anos_cur.fetchall() if r[0]]
        if ano not in anos:
            anos.append(ano)
        anos = sorted(set(anos))
        meses_cur = db_execute(
            conn,
            f"""
            SELECT EXTRACT(MONTH FROM {dia})::int,
                   COUNT(*)::int,
                   COALESCE(SUM(n.valor_servico), 0)
              FROM tbl_nfse_nota n
             WHERE n.id_tenant = %s
               AND n.status = 'autorizada'
               AND EXTRACT(YEAR FROM {dia}) = %s
             GROUP BY 1
            """,
            (_tenant(), ano),
        )
        por_mes = {int(r[0]): {"qtd": int(r[1]), "total": _reais(r[2])} for r in meses_cur.fetchall()}
        clientes_cur = db_execute(
            conn,
            f"""
            SELECT COALESCE(NULLIF(TRIM(n.tomador_razao_social), ''), 'Sem tomador'),
                   COUNT(*)::int,
                   COALESCE(SUM(n.valor_servico), 0)
              FROM tbl_nfse_nota n
             WHERE n.id_tenant = %s
               AND n.status = 'autorizada'
               AND EXTRACT(YEAR FROM {dia}) = %s
             GROUP BY 1
             ORDER BY 3 DESC, 2 DESC, 1
             LIMIT 5
            """,
            (_tenant(), ano),
        )
        clientes = [
            {"nome": r[0], "qtd": int(r[1]), "total": _reais(r[2])}
            for r in clientes_cur.fetchall()
        ]
        inicio_anterior = date(hoje.year - 1, 1, 1)
        fim_anterior = _mesmo_dia_ano_anterior(hoje)
        serie_cur = db_execute(
            conn,
            f"""
            SELECT EXTRACT(YEAR FROM {dia})::int,
                   EXTRACT(MONTH FROM {dia})::int,
                   COALESCE(SUM(n.valor_servico), 0)
              FROM tbl_nfse_nota n
             WHERE n.id_tenant = %s
               AND n.status = 'autorizada'
               AND {dia} >= %s
             GROUP BY 1, 2
            """,
            (_tenant(), inicio_anterior),
        )
        serie = {
            (int(r[0]), int(r[1])): _reais(r[2])
            for r in serie_cur.fetchall()
            if r[0] and r[1]
        }
        ytd_cur = db_execute(
            conn,
            f"""
            SELECT
              COALESCE(SUM(n.valor_servico) FILTER (
                WHERE {dia} >= %s AND {dia} <= %s
              ), 0),
              COALESCE(SUM(n.valor_servico) FILTER (
                WHERE {dia} >= %s AND {dia} <= %s
              ), 0)
              FROM tbl_nfse_nota n
             WHERE n.id_tenant = %s AND n.status = 'autorizada'
            """,
            (date(hoje.year, 1, 1), hoje, inicio_anterior, fim_anterior, _tenant()),
        )
        ytd_row = ytd_cur.fetchone() or (0, 0)
    finally:
        conn.close()

    fechados = _meses_fechados(hoje, 3)
    meses_ritmo = [
        {
            "ano": ano_m,
            "mes": mes_m,
            "nome": _MESES[mes_m - 1],
            "total": serie.get((ano_m, mes_m), 0.0),
        }
        for ano_m, mes_m in fechados
    ]
    ritmo = _reais(sum(Decimal(str(m["total"])) for m in meses_ritmo) / Decimal(len(meses_ritmo) or 1))
    variacao_recente = None
    if len(meses_ritmo) >= 2 and meses_ritmo[-2]["total"] > 0:
        anterior_mes = Decimal(str(meses_ritmo[-2]["total"]))
        ultimo_mes = Decimal(str(meses_ritmo[-1]["total"]))
        variacao_recente = float(((ultimo_mes - anterior_mes) / anterior_mes).quantize(Decimal("0.0001")))
    ytd_atual = _reais(ytd_row[0])
    ytd_anterior = _reais(ytd_row[1])
    variacao_anual = None
    if ytd_anterior > 0:
        variacao_anual = float(
            ((Decimal(str(ytd_atual)) - Decimal(str(ytd_anterior))) / Decimal(str(ytd_anterior))).quantize(Decimal("0.0001"))
        )

    meses = []
    total_ano = Decimal("0")
    qtd_ano = 0
    for i in range(1, 13):
        item = por_mes.get(i, {"qtd": 0, "total": 0.0})
        total_ano += Decimal(str(item["total"]))
        qtd_ano += item["qtd"]
        meses.append({
            "mes": i,
            "label": _MESES_CURTO[i - 1],
            "nome": _MESES[i - 1],
            "qtd": item["qtd"],
            "total": item["total"],
        })
    total_ano_f = _reais(total_ano)
    if ano == hoje.year:
        mes_foco = hoje.month
    else:
        mes_foco = max(range(1, 13), key=lambda m: (meses[m - 1]["total"], m))
    foco = meses[mes_foco - 1]
    ticket = _reais(total_ano / qtd_ano) if qtd_ano else 0.0
    return jsonify({
        "success": True,
        "ano": ano,
        "anos": anos,
        "hoje_ano": hoje.year,
        "hoje_mes": hoje.month,
        "mes_foco": mes_foco,
        "mes_foco_nome": _MESES[mes_foco - 1],
        "total_ano": total_ano_f,
        "total_mes": foco["total"],
        "qtd_ano": qtd_ano,
        "qtd_mes": foco["qtd"],
        "ticket": ticket,
        "meses": meses,
        "clientes": clientes,
        "projecao": {
            "ano_meta": 2027,
            "ritmo_mensal": ritmo,
            "meses_ritmo": meses_ritmo,
            "variacao_recente": variacao_recente,
            "ano_atual": hoje.year,
            "ano_anterior": hoje.year - 1,
            "ytd_atual": ytd_atual,
            "ytd_anterior": ytd_anterior,
            "variacao_anual": variacao_anual,
        },
    })


@nfse_bp.route("/notas")
@_nfse_autorizado
def notas():
    return render_template(
        "frm_nfse_notas.html",
        nome=session.get("nome"),
        email=session.get("email"),
        menu_ativo="nfse-notas",
        nav_ativo=_nav_nfse("nfse"),
        nfse_aba="notas",
    )


@nfse_bp.route("/notas/incluir")
@_nfse_autorizado
def notas_incluir():
    return render_template("frm_nfse_nota_apoio.html")


@nfse_bp.route("/notas/editar")
@_nfse_autorizado
def notas_editar():
    return render_template("frm_nfse_nota_apoio.html")


@nfse_bp.route("/parametros")
@_nfse_autorizado
def parametros():
    from sistema.fiscal.nfse.tenant_fiscal import carregar_empresa_fiscal

    empresa = {}
    conn = Var_ConectarBanco()
    try:
        empresa = _anexar_series_nfe(conn, carregar_empresa_fiscal(conn, _tenant()) or {})
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        empresa = {"serie_dps": "1", "proximo_numero_dps": 1, "serie_nfe": 1, "proximo_numero_nfe": 1}
    finally:
        conn.close()

    cnpj_dig = somente_digitos(empresa.get("cnpj") or "")
    if len(cnpj_dig) == 14:
        cnpj_fmt = f"{cnpj_dig[:2]}.{cnpj_dig[2:5]}.{cnpj_dig[5:8]}/{cnpj_dig[8:12]}-{cnpj_dig[12:]}"
    else:
        cnpj_fmt = cnpj_dig
    empresa = dict(empresa)
    empresa["cnpj_formatado"] = cnpj_fmt
    empresa.setdefault("serie_dps", "1")
    empresa.setdefault("proximo_numero_dps", 1)
    empresa.setdefault("serie_nfe", 1)
    empresa.setdefault("proximo_numero_nfe", 1)

    return render_template(
        "frm_nfse_parametros.html",
        nome=session.get("nome"),
        email=session.get("email"),
        menu_ativo="nfse-parametros",
        nav_ativo=_nav_nfse("param"),
        nfse_aba="parametros",
        empresa=empresa,
    )


@nfse_bp.route("/api/notas")
@_nfse_autorizado
def api_notas():
    conn = Var_ConectarBanco()
    try:
        pagina = max(1, int(request.args.get("pagina", 1)))
        limite = 20
        status = (request.args.get("status") or "").strip()
        termo = (request.args.get("termo") or "").strip()
        where = ["n.id_tenant = %s"]
        params: list = [_tenant()]
        if status:
            where.append("n.status = %s")
            params.append(status)
        if termo:
            where.append(
                "(n.tomador_razao_social ILIKE %s OR coalesce(n.numero_nfse, '') ILIKE %s "
                "OR coalesce(n.chave_nfse, '') ILIKE %s OR cast(n.numero_dps as text) ILIKE %s)"
            )
            params.extend([f"%{termo}%"] * 4)
        where_sql = " AND ".join(where)
        total = db_execute(
            conn, f"SELECT COUNT(*) FROM tbl_nfse_nota n WHERE {where_sql}", tuple(params)
        ).fetchone()[0]
        cur = db_execute(
            conn,
            f"""
            SELECT n.id, n.numero_dps, n.serie_dps, n.numero_nfse, n.chave_nfse,
                   n.tomador_razao_social AS cliente, n.competencia, n.valor_servico,
                   n.status, n.erro_codigo, n.erro_mensagem, n.resposta_metadata,
                   n.dt_criacao, n.dt_autorizacao
              FROM tbl_nfse_nota n
             WHERE {where_sql}
             ORDER BY n.id DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params + [limite, (pagina - 1) * limite]),
        )
        return jsonify(
            {
                "success": True,
                "dados": [_payload_row(r) for r in _dict_rows(cur)],
                "pagina": pagina,
                "total_paginas": max(1, (total + limite - 1) // limite),
                "total": total,
            }
        )
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify(
            {
                "success": False,
                "message": "Não foi possível listar as notas.",
                "detalhe": str(exc)[:400],
            }
        ), 500
    finally:
        conn.close()


@nfse_bp.route("/api/notas/<int:id_nota>")
@_nfse_autorizado
def api_nota(id_nota):
    conn = Var_ConectarBanco()
    try:
        _garantir_partes_operacao(conn)
        cur = db_execute(
            conn,
            """
            SELECT id, id_perfil, id_tomador_empresa, id_destinatario_empresa,
                   id_intermediario_empresa, numero_dps, serie_dps,
                   numero_nfse, chave_nfse, competencia, valor_servico, status,
                   tomador_razao_social, tomador_cnpj_cpf,
                   tomador_logradouro, tomador_numero, tomador_complemento,
                   tomador_bairro, tomador_cidade, tomador_uf, tomador_cep,
                   tomador_telefone, codigo_servico,
                   codigo_tributacao_nacional, codigo_nbs, descricao_servico,
                   incidencia_municipio_ibge, iss_retido, aliquota_iss,
                   retencoes_json, ibs_cbs_json, observacoes, erro_codigo, erro_mensagem,
                   resposta_metadata,
                   id_dps, dt_criacao, dt_atualizacao, dt_autorizacao,
                   dt_inicio_processamento, dt_ultima_tentativa
              FROM tbl_nfse_nota
             WHERE id = %s AND id_tenant = %s
            """,
            (id_nota, _tenant()),
        )
        row = _dict_row(cur)
        if not row:
            return jsonify({"success": False, "message": "Rascunho não encontrado."}), 404
        return jsonify({"success": True, "dados": _payload_row(row)})
    finally:
        conn.close()


@nfse_bp.route("/api/tomadores")
@_nfse_autorizado
def api_tomadores():
    conn = Var_ConectarBanco()
    try:
        filtro = (request.args.get("filtro") or "").strip()
        cur = db_execute(
            conn,
            """
            SELECT id, razao_social, coalesce(nome_fantasia, '') AS nome_fantasia,
                   cnpj, cidade, uf
              FROM tbl_empresa
             WHERE id_tenant = %s AND ativo = TRUE
               AND (razao_social ILIKE %s OR coalesce(nome_fantasia, '') ILIKE %s
                    OR coalesce(cnpj, '') ILIKE %s)
             ORDER BY razao_social
             LIMIT 30
            """,
            (_tenant(), f"%{filtro}%", f"%{filtro}%", f"%{filtro}%"),
        )
        dados = _dict_rows(cur)
        for item in dados:
            item["cnpj"] = formatar_cnpj(item["cnpj"])
        return jsonify({"success": True, "dados": dados})
    finally:
        conn.close()


@nfse_bp.route("/api/perfis")
@_nfse_autorizado
def api_perfis():
    conn = Var_ConectarBanco()
    try:
        somente_ativos = request.args.get("ativos") == "1"
        cur = db_execute(
            conn,
            """
            SELECT * FROM tbl_nfse_perfil_nota
             WHERE id_tenant = %s AND (%s = FALSE OR ativo = TRUE)
             ORDER BY nome
            """,
            (_tenant(), somente_ativos),
        )
        return jsonify({"success": True, "dados": [_payload_row(r) for r in _dict_rows(cur)]})
    finally:
        conn.close()


@nfse_bp.route("/api/perfis/salvar", methods=["POST"])
@_nfse_autorizado
def api_perfil_salvar():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    codigo = (dados.get("codigo_servico") or "").strip()
    tributacao = (dados.get("codigo_tributacao_nacional") or "").strip()
    descricao = (dados.get("descricao_servico") or "").strip()
    if not all((nome, tributacao, descricao)):
        return jsonify({"success": False, "message": "Nome, tributação nacional e descrição são obrigatórios."}), 400
    try:
        ibs_cbs = dados.get("ibs_cbs_json") or {}
        if isinstance(ibs_cbs, str):
            ibs_cbs = json.loads(ibs_cbs)
        if not isinstance(ibs_cbs, dict):
            raise ValueError
    except (ValueError, json.JSONDecodeError):
        return jsonify({"success": False, "message": "Extensão IBS/CBS deve ser um objeto JSON."}), 400

    conn = Var_ConectarBanco()
    try:
        valores = [
            nome,
            _bool(dados.get("ativo", True)),
            codigo,
            tributacao,
            (dados.get("codigo_nbs") or "").strip() or None,
            descricao,
            None,
            None,
            _bool(dados.get("iss_retido")),
            _decimal(dados.get("aliquota_iss"), "Alíquota ISS"),
            _bool(dados.get("pis_retido")),
            _decimal(dados.get("aliquota_pis"), "Alíquota PIS"),
            _bool(dados.get("cofins_retido")),
            _decimal(dados.get("aliquota_cofins"), "Alíquota COFINS"),
            _bool(dados.get("inss_retido")),
            _decimal(dados.get("aliquota_inss"), "Alíquota INSS"),
            _bool(dados.get("ir_retido")),
            _decimal(dados.get("aliquota_ir"), "Alíquota IR"),
            _bool(dados.get("csll_retido")),
            _decimal(dados.get("aliquota_csll"), "Alíquota CSLL"),
            json.dumps(ibs_cbs),
        ]
        id_perfil = dados.get("id")
        if id_perfil:
            cur = db_execute(
                conn,
                """
                UPDATE tbl_nfse_perfil_nota SET
                    nome=%s, ativo=%s, codigo_servico=%s, codigo_tributacao_nacional=%s,
                    codigo_nbs=%s, descricao_servico=%s, incidencia_municipio_ibge=%s,
                    incidencia_municipio_nome=%s, iss_retido=%s, aliquota_iss=%s,
                    pis_retido=%s, aliquota_pis=%s, cofins_retido=%s, aliquota_cofins=%s,
                    inss_retido=%s, aliquota_inss=%s, ir_retido=%s, aliquota_ir=%s,
                    csll_retido=%s, aliquota_csll=%s, ibs_cbs_json=%s::jsonb,
                    dt_atualizacao=NOW()
                 WHERE id=%s AND id_tenant=%s RETURNING id
                """,
                tuple(valores + [int(id_perfil), _tenant()]),
            )
        else:
            cur = db_execute(
                conn,
                """
                INSERT INTO tbl_nfse_perfil_nota (
                    nome, ativo, codigo_servico, codigo_tributacao_nacional, codigo_nbs,
                    descricao_servico, incidencia_municipio_ibge, incidencia_municipio_nome,
                    iss_retido, aliquota_iss, pis_retido, aliquota_pis, cofins_retido,
                    aliquota_cofins, inss_retido, aliquota_inss, ir_retido, aliquota_ir,
                    csll_retido, aliquota_csll, ibs_cbs_json, id_tenant
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s
                ) RETURNING id
                """,
                tuple(valores + [_tenant()]),
            )
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Perfil não encontrado neste tenant."}), 404
        _auditar(conn, "perfil_salvo", "Perfil de nota salvo.", dados={"id_perfil": row[0]})
        conn.commit()
        return jsonify({"success": True, "id": row[0], "message": "Perfil salvo."})
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    finally:
        conn.close()


@nfse_bp.route("/api/config")
@_nfse_autorizado
def api_config():
    from sistema.fiscal.nfse.tenant_fiscal import carregar_empresa_fiscal

    conn = Var_ConectarBanco()
    try:
        dados = _anexar_series_nfe(conn, carregar_empresa_fiscal(conn, _tenant()))
        try:
            crypto_fallback = validar_configuracao_criptografica()
        except Exception:
            crypto_fallback = True
        return jsonify(
            {
                "success": True,
                "dados": _payload_row(dados),
                "dev_crypto_fallback": crypto_fallback,
            }
        )
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify(
            {
                "success": False,
                "message": f"Falha ao ler empresa do tenant: {e}",
                "dados": {},
            }
        ), 500
    finally:
        conn.close()


@nfse_bp.route("/api/consulta-cnpj", methods=["GET", "POST"])
@_nfse_autorizado
def api_consulta_cnpj():
    """Consulta pública de CNPJ para tomador avulso / Completar da Receita."""
    from core.dominio import consultar_cnpj

    body = request.get_json(silent=True) or {}
    cnpj = somente_digitos(body.get("cnpj") or request.args.get("cnpj") or "")
    if len(cnpj) != 14:
        return jsonify(success=False, erro="Informe um CNPJ com 14 dígitos.", message="Informe um CNPJ com 14 dígitos."), 400
    try:
        dados = consultar_cnpj(cnpj)
    except ValueError as exc:
        msg = str(exc) or "Não foi possível consultar o CNPJ."
        return jsonify(success=False, erro=msg, message=msg), 400
    except Exception as exc:
        msg = str(exc) or "Consulta de CNPJ indisponível."
        return jsonify(success=False, erro=msg, message=msg), 502
    # Resposta plana (compat H74) + flags success para requestJSON.
    out = dict(dados)
    out["success"] = True
    out["message"] = "CNPJ consultado."
    return jsonify(out)


@nfse_bp.route("/api/consulta-cep", methods=["GET"])
@_nfse_autorizado
def api_consulta_cep():
    """Consulta ViaCEP para endereço do tomador avulso."""
    import requests

    cep = somente_digitos(request.args.get("cep") or "")
    if len(cep) != 8:
        return jsonify(success=False, erro="CEP inválido.", message="CEP inválido."), 400
    try:
        r = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=8)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        msg = str(exc) or "Falha ao consultar CEP."
        return jsonify(success=False, erro=msg, message=msg), 502
    if data.get("erro"):
        return jsonify(success=False, erro="CEP não encontrado.", message="CEP não encontrado."), 404
    return jsonify(
        success=True,
        cep=cep,
        logradouro=data.get("logradouro") or "",
        complemento=data.get("complemento") or "",
        bairro=data.get("bairro") or "",
        municipio=data.get("localidade") or "",
        cidade=data.get("localidade") or "",
        uf=(data.get("uf") or "").upper(),
        ibge=data.get("ibge") or "",
        message="CEP consultado.",
    )


@nfse_bp.route("/api/config/salvar", methods=["POST"])
@_nfse_autorizado
def api_config_salvar():
    from sistema.fiscal.nfse.tenant_fiscal import salvar_empresa_fiscal

    dados = request.get_json(silent=True) or {}
    cnpj = somente_digitos(dados.get("cnpj"))
    uf = (dados.get("uf") or "").strip().upper()
    ibge = somente_digitos(dados.get("municipio_ibge_codigo"))
    if cnpj and not validar_cnpj(cnpj):
        return jsonify({"success": False, "message": "CNPJ do prestador inválido."}), 400
    if uf and len(uf) != 2:
        return jsonify({"success": False, "message": "UF deve ter dois caracteres."}), 400
    if not ibge:
        return jsonify(
            {
                "success": False,
                "message": "Informe o Código IBGE do município (7 dígitos) ou use Completar da Receita.",
            }
        ), 400
    if len(ibge) != 7:
        return jsonify({"success": False, "message": "Código IBGE deve ter 7 dígitos."}), 400
    bruto_percentual = str(dados.get("percentual_tributos_sn") or "").strip()
    percentual_sn = None
    if bruto_percentual:
        percentual_sn = _decimal(bruto_percentual, "Percentual aproximado do Simples")
        if percentual_sn > Decimal("99.99"):
            return jsonify({"success": False, "message": "Percentual aproximado do Simples deve ficar entre 0 e 99,99."}), 400
    dados = dict(dados)
    dados["percentual_tributos_sn"] = percentual_sn
    dados["optante_simples"] = _bool(dados.get("optante_simples"))
    dados["incentivador_cultural"] = _bool(dados.get("incentivador_cultural"))
    conn = Var_ConectarBanco()
    try:
        salvos = salvar_empresa_fiscal(conn, _tenant(), dados)
        _salvar_series_nfe(conn, dados)
        salvos = _anexar_series_nfe(conn, salvos)
        _auditar(conn, "config_salva", "Empresa fiscal e séries NF-e/NFS-e atualizadas.")
        conn.commit()
        return jsonify(
            {
                "success": True,
                "message": "Empresa fiscal e numeração (NF-e/NFS-e) salvas.",
                "dados": _payload_row(salvos),
            }
        )
    except PermissionError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 403
    except ValueError as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@nfse_bp.route("/api/certificados")
@_nfse_autorizado
def api_certificados():
    conn = Var_ConectarBanco()
    try:
        cur = db_execute(
            conn,
            """
            SELECT id, nome_arquivo, serial_certificado, titular, cnpj_certificado,
                   dt_inicio_validade, dt_fim_validade, ativo, dt_criacao
              FROM tbl_nfse_certificado
             WHERE id_tenant = %s
             ORDER BY ativo DESC, dt_fim_validade DESC
            """,
            (_tenant(),),
        )
        return jsonify({"success": True, "dados": [_payload_row(r) for r in _dict_rows(cur)]})
    finally:
        conn.close()


@nfse_bp.route("/api/certificados/upload", methods=["POST"])
@_nfse_autorizado
def api_certificado_upload():
    arquivo = request.files.get("arquivo")
    senha = request.form.get("senha", "")
    if not arquivo or not arquivo.filename.lower().endswith((".pfx", ".p12")):
        return jsonify({"success": False, "message": "Selecione um arquivo PFX ou P12."}), 400
    conteudo = arquivo.read()
    if not conteudo or len(conteudo) > 5 * 1024 * 1024:
        return jsonify({"success": False, "message": "Certificado vazio ou maior que 5 MB."}), 400
    try:
        meta = ler_pkcs12(conteudo, senha)
        validar_configuracao_criptografica()
    except (ValueError, RuntimeError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    conn = Var_ConectarBanco()
    try:
        config = db_execute(
            conn,
            """
            SELECT COALESCE(NULLIF(TRIM(cnpj), ''),
                            CASE WHEN UPPER(COALESCE(tipo_pessoa,''))='J'
                                 THEN NULLIF(TRIM(documento),'') END)
              FROM tbl_tenant WHERE id=%s
            """,
            (_tenant(),),
        ).fetchone()
        cnpj_config = somente_digitos(config[0]) if config else ""
        if meta["cnpj"] and cnpj_config and meta["cnpj"] != cnpj_config:
            return jsonify(
                {"success": False, "message": "O CNPJ identificado no certificado difere do CNPJ do prestador."}
            ), 400
        db_execute(
            conn, "UPDATE tbl_nfse_certificado SET ativo=FALSE WHERE id_tenant=%s", (_tenant(),)
        )
        cur = db_execute(
            conn,
            """
            INSERT INTO tbl_nfse_certificado (
                id_tenant, nome_arquivo, conteudo_encriptado, senha_encriptada,
                serial_certificado, titular, cnpj_certificado,
                dt_inicio_validade, dt_fim_validade, ativo
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id
            """,
            (
                _tenant(),
                arquivo.filename[:255],
                criptografar(conteudo),
                criptografar(senha.encode("utf-8")),
                meta["serial"],
                meta["titular"],
                meta["cnpj"],
                meta["inicio"],
                meta["fim"],
            ),
        )
        id_cert = cur.fetchone()[0]
        _auditar(conn, "certificado_incluido", "Novo certificado A1 incluído.", dados={"id_certificado": id_cert})
        conn.commit()
        return jsonify({"success": True, "id": id_cert, "message": "Certificado validado e armazenado com criptografia."})
    finally:
        conn.close()


@nfse_bp.route("/api/notas/salvar", methods=["POST"])
@_nfse_autorizado
def api_nota_salvar():
    dados = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        _garantir_partes_operacao(conn)
        id_perfil = int(dados.get("id_perfil") or 0)
        id_destinatario = _id_opcional(dados.get("id_destinatario_empresa"))
        id_intermediario = _id_opcional(dados.get("id_intermediario_empresa"))
        perfil_cur = db_execute(
            conn,
            "SELECT * FROM tbl_nfse_perfil_nota WHERE id=%s AND id_tenant=%s AND ativo=TRUE",
            (id_perfil, _tenant()),
        )
        perfil = _dict_row(perfil_cur)
        if not perfil:
            return jsonify({
                "success": False,
                "message": "Selecione um perfil de nota. Se a lista estiver vazia, cadastre o perfil em Parâmetros.",
                "erros": ["perfil"],
            }), 400
        try:
            id_tomador, tomador_razao, tomador_doc, end = _resolver_tomador(conn, dados)
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc), "erros": ["tomador"]}), 400
        if id_destinatario and not _empresa_ativa(conn, id_destinatario):
            return jsonify({"success": False, "message": "Destinatário não encontrado no cadastro de clientes.", "erros": ["destinatario"]}), 400
        if id_intermediario and not _empresa_ativa(conn, id_intermediario):
            return jsonify({"success": False, "message": "Intermediário não encontrado no cadastro de clientes.", "erros": ["intermediario"]}), 400
        competencia = dados.get("competencia")
        try:
            date.fromisoformat(str(competencia))
        except ValueError:
            return jsonify({"success": False, "message": "Competência inválida.", "erros": ["competencia"]}), 400
        try:
            valor = _decimal(dados.get("valor_servico"), "Valor do serviço")
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc), "erros": ["valor"]}), 400
        prestador = db_execute(
            conn,
            "SELECT municipio_ibge_codigo FROM tbl_tenant WHERE id=%s",
            (_tenant(),),
        ).fetchone()
        local_ibge = somente_digitos(prestador[0]) if prestador and prestador[0] else None
        retencoes = {}
        for tributo in ("pis", "cofins", "inss", "ir", "csll"):
            aliquota = perfil.get(f"aliquota_{tributo}")
            retencoes[tributo] = {
                "retido": bool(perfil.get(f"{tributo}_retido")),
                "aliquota": float(aliquota or 0),
            }
        id_nota = int(dados.get("id") or 0)
        id_usuario = session.get("id_usuario")
        if not id_usuario and not id_nota:
            return jsonify({"success": False, "message": "Sessão sem usuário. Faça login novamente.", "erros": ["sessao"]}), 401
        campos_tomador = (
            id_perfil, id_tomador, id_destinatario, id_intermediario, competencia, valor,
            tomador_razao, tomador_doc,
            end["logradouro"], end["numero"], end["complemento"], end["bairro"],
            end["cidade"], end["uf"], end["cep"], end["telefone"],
            perfil["codigo_servico"], perfil["codigo_tributacao_nacional"], perfil["codigo_nbs"],
            perfil["descricao_servico"], local_ibge, perfil["iss_retido"],
            perfil["aliquota_iss"], _json_dumps(retencoes), _json_dumps(perfil.get("ibs_cbs_json") or {}),
            (dados.get("observacoes") or "").strip() or None,
        )
        if id_nota:
            cur = db_execute(
                conn,
                """
                UPDATE tbl_nfse_nota SET
                    id_perfil=%s, id_tomador_empresa=%s,
                    id_destinatario_empresa=%s, id_intermediario_empresa=%s,
                    competencia=%s, valor_servico=%s,
                    tomador_razao_social=%s, tomador_cnpj_cpf=%s,
                    tomador_logradouro=%s, tomador_numero=%s, tomador_complemento=%s,
                    tomador_bairro=%s, tomador_cidade=%s, tomador_uf=%s, tomador_cep=%s,
                    tomador_telefone=%s, codigo_servico=%s,
                    codigo_tributacao_nacional=%s, codigo_nbs=%s, descricao_servico=%s,
                    incidencia_municipio_ibge=%s, iss_retido=%s, aliquota_iss=%s,
                    retencoes_json=%s::jsonb, ibs_cbs_json=%s::jsonb, observacoes=%s,
                    status='rascunho', erro_codigo=NULL, erro_mensagem=NULL, dt_atualizacao=NOW()
                 WHERE id=%s AND id_tenant=%s AND status IN ('rascunho','validado','rejeitada')
                 RETURNING id
                """,
                (*campos_tomador, id_nota, _tenant()),
            )
        else:
            from sistema.fiscal.nfse.tenant_fiscal import (
                carregar_empresa_fiscal,
                garantir_colunas_tenant_fiscal,
            )

            garantir_colunas_tenant_fiscal(conn)
            config = db_execute(
                conn,
                """
                SELECT COALESCE(NULLIF(TRIM(serie_dps), ''), '1'),
                       COALESCE(NULLIF(proximo_numero_dps, 0), 1),
                       UPPER(COALESCE(tipo_pessoa, ''))
                  FROM tbl_tenant
                 WHERE id=%s FOR UPDATE
                """,
                (_tenant(),),
            ).fetchone()
            if not config:
                return jsonify({"success": False, "message": "Tenant não encontrado.", "erros": ["config"]}), 400
            if config[2] != "J":
                return jsonify({
                    "success": False,
                    "message": "Empresa fiscal exige tenant PJ. Atualize o cadastro do tenant.",
                    "erros": ["pj"],
                }), 400
            emp = carregar_empresa_fiscal(conn, _tenant())
            if not somente_digitos(emp.get("cnpj") or "") or not (emp.get("razao_social") or "").strip():
                return jsonify({
                    "success": False,
                    "message": "Complete a Empresa fiscal (CNPJ e razão social) antes de criar a DPS.",
                    "erros": ["config"],
                }), 400
            cur = db_execute(
                conn,
                """
                INSERT INTO tbl_nfse_nota (
                    id_tenant, id_perfil, id_tomador_empresa, id_destinatario_empresa,
                    id_intermediario_empresa, numero_dps, serie_dps,
                    competencia, valor_servico, tomador_razao_social, tomador_cnpj_cpf,
                    tomador_logradouro, tomador_numero, tomador_complemento, tomador_bairro,
                    tomador_cidade, tomador_uf, tomador_cep, tomador_telefone,
                    codigo_servico, codigo_tributacao_nacional, codigo_nbs, descricao_servico,
                    incidencia_municipio_ibge, iss_retido, aliquota_iss, retencoes_json,
                    ibs_cbs_json, observacoes, criado_por
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s
                )
                RETURNING id
                """,
                (
                    _tenant(), id_perfil, id_tomador, id_destinatario, id_intermediario,
                    config[1], config[0], competencia, valor,
                    tomador_razao, tomador_doc,
                    end["logradouro"], end["numero"], end["complemento"], end["bairro"],
                    end["cidade"], end["uf"], end["cep"], end["telefone"],
                    perfil["codigo_servico"],
                    perfil["codigo_tributacao_nacional"], perfil["codigo_nbs"], perfil["descricao_servico"],
                    local_ibge, perfil["iss_retido"], perfil["aliquota_iss"],
                    _json_dumps(retencoes), _json_dumps(perfil.get("ibs_cbs_json") or {}),
                    (dados.get("observacoes") or "").strip() or None, id_usuario,
                ),
            )
            db_execute(
                conn,
                "UPDATE tbl_tenant SET proximo_numero_dps=COALESCE(proximo_numero_dps,1)+1, dt_atualizacao=NOW() WHERE id=%s",
                (_tenant(),),
            )
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Rascunho não encontrado ou não pode mais ser editado."}), 409
        _auditar(conn, "rascunho_salvo", "DPS salva como rascunho.", row[0])
        conn.commit()
        return jsonify({"success": True, "id": row[0], "message": "Rascunho salvo sem transmissão."})
    except (ValueError, TypeError) as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    except RuntimeError as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500
    except (IntegrityError, ProgrammingError) as exc:
        conn.rollback()
        detalhe = getattr(exc, "pgerror", None) or str(exc)
        return jsonify({
            "success": False,
            "message": "Não foi possível gravar o rascunho no banco.",
            "detalhe": detalhe[:400],
        }), 500
    except Exception as exc:
        conn.rollback()
        return jsonify({
            "success": False,
            "message": "Erro inesperado ao salvar o rascunho.",
            "detalhe": str(exc)[:400],
        }), 500
    finally:
        conn.close()


def _validar_nota(conn, id_nota: int) -> list[str]:
    _garantir_partes_operacao(conn)
    cur = db_execute(
        conn,
        """
        SELECT n.*,
               COALESCE(NULLIF(TRIM(t.razao_social), ''), NULLIF(TRIM(t.nome_completo), ''), t.nome) AS prestador_razao,
               COALESCE(NULLIF(TRIM(t.cnpj), ''),
                        CASE WHEN UPPER(COALESCE(t.tipo_pessoa,''))='J'
                             THEN NULLIF(TRIM(t.documento),'') END) AS prestador_cnpj,
               t.inscricao_municipal, t.municipio_ibge_codigo, t.uf,
               COALESCE(NULLIF(TRIM(t.ambiente_nfse), ''), 'homologacao') AS ambiente,
               COALESCE(NULLIF(TRIM(t.regime_tributario), ''), 'simples_nacional') AS regime_tributario,
               COALESCE(t.optante_simples, TRUE) AS optante_simples,
               t.regime_especial_tributacao,
               t.percentual_tributos_sn,
               emp_inter.razao_social AS intermediario_razao_social,
               emp_inter.cnpj AS intermediario_cnpj_cpf,
               emp_inter.telefone AS intermediario_fone
          FROM tbl_nfse_nota n
          LEFT JOIN tbl_tenant t ON t.id=n.id_tenant
          LEFT JOIN tbl_empresa emp_inter
            ON emp_inter.id=n.id_intermediario_empresa AND emp_inter.id_tenant=n.id_tenant
         WHERE n.id=%s AND n.id_tenant=%s
        """,
        (id_nota, _tenant()),
    )
    nota = _dict_row(cur)
    if not nota:
        return ["Rascunho não encontrado."]
    erros = []
    obrigatorios = {
        "Razão social do prestador": nota.get("prestador_razao"),
        "CNPJ do prestador": nota.get("prestador_cnpj"),
        "Município IBGE do prestador": nota.get("municipio_ibge_codigo"),
        "UF do prestador": nota.get("uf"),
        "Tomador": nota.get("tomador_razao_social"),
        "Código de tributação nacional": nota.get("codigo_tributacao_nacional"),
        "Descrição do serviço": nota.get("descricao_servico"),
    }
    erros.extend(f"{campo} não informado." for campo, valor in obrigatorios.items() if not valor)
    if nota.get("prestador_cnpj") and not validar_cnpj(nota["prestador_cnpj"]):
        erros.append("CNPJ do prestador inválido.")
    documento_tomador = somente_digitos(nota.get("tomador_cnpj_cpf"))
    if len(documento_tomador) not in (11, 14):
        erros.append("CPF/CNPJ do tomador deve conter 11 ou 14 dígitos.")
    try:
        if not erros:
            tenant = {
                "razao_social": nota["prestador_razao"],
                "cnpj": nota["prestador_cnpj"],
                "inscricao_municipal": nota["inscricao_municipal"],
                "municipio_ibge_codigo": nota["municipio_ibge_codigo"],
            }
            xml = construir_dps(nota, tenant, nota)
            validar_xml(xml, nota["ambiente"])
    except ErroDPS as exc:
        erros.append(str(exc))
    cert = db_execute(
        conn,
        """
        SELECT id FROM tbl_nfse_certificado
         WHERE id_tenant=%s AND ativo=TRUE AND dt_fim_validade > NOW()
         ORDER BY dt_fim_validade DESC LIMIT 1
        """,
        (_tenant(),),
    ).fetchone()
    if not cert:
        erros.append("Nenhum certificado A1 ativo e válido.")
    return erros


@nfse_bp.route("/api/notas/<int:id_nota>/validar", methods=["POST"])
@_nfse_autorizado
def api_nota_validar(id_nota):
    conn = Var_ConectarBanco()
    try:
        estado = db_execute(
            conn,
            "SELECT status FROM tbl_nfse_nota WHERE id=%s AND id_tenant=%s FOR UPDATE",
            (id_nota, _tenant()),
        ).fetchone()
        if not estado:
            return jsonify({"success": False, "message": "Rascunho não encontrado."}), 404
        if estado[0] not in {"rascunho", "validado", "rejeitada"}:
            return jsonify({
                "success": False,
                "message": f"Validação bloqueada para nota em estado {estado[0]}.",
            }), 409
        erros = _validar_nota(conn, id_nota)
        if erros:
            db_execute(
                conn,
                """
                UPDATE tbl_nfse_nota SET status='rascunho', erro_codigo='VALIDACAO',
                       erro_mensagem=%s, dt_atualizacao=NOW()
                 WHERE id=%s AND id_tenant=%s
                   AND status IN ('rascunho','validado','rejeitada')
                """,
                ("\n".join(erros), id_nota, _tenant()),
            )
            _auditar(conn, "validacao_falhou", "Rascunho contém pendências.", id_nota, {"erros": erros})
            conn.commit()
            return jsonify({"success": False, "message": "Há pendências de validação.", "erros": erros}), 400
        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota SET status='validado', erro_codigo=NULL, erro_mensagem=NULL,
                   dt_atualizacao=NOW() WHERE id=%s AND id_tenant=%s
                   AND status IN ('rascunho','validado','rejeitada')
            """,
            (id_nota, _tenant()),
        )
        _auditar(conn, "validacao_ok", "Rascunho validado localmente; não transmitido.", id_nota)
        conn.commit()
        return jsonify({"success": True, "message": "Rascunho validado localmente. Nenhum dado foi transmitido."})
    finally:
        conn.close()


def _payload_nfse_hub(nota: dict) -> dict:
    competencia = nota.get("competencia")
    if hasattr(competencia, "isoformat"):
        competencia = competencia.isoformat()
    else:
        competencia = str(competencia or "")[:10]
    aliquota = nota.get("aliquota_iss") or 0
    if isinstance(aliquota, Decimal):
        aliquota = float(aliquota)
    perc_sn = nota.get("percentual_tributos_sn")
    if isinstance(perc_sn, Decimal):
        perc_sn = float(perc_sn)
    payload = {
        "cnpj_emitente": somente_digitos(nota.get("prestador_cnpj")),
        "serie": str(nota.get("serie_dps") or "1"),
        "numero": int(nota.get("numero_dps") or 0),
        "competencia": competencia,
        "tomador_cnpj_cpf": somente_digitos(nota.get("tomador_cnpj_cpf")),
        "tomador_razao_social": (nota.get("tomador_razao_social") or "").strip(),
        "descricao_servico": (nota.get("descricao_servico") or "").strip(),
        "codigo_tributacao_nacional": somente_digitos(nota.get("codigo_tributacao_nacional")),
        "codigo_servico": somente_digitos(nota.get("codigo_servico")),
        "codigo_nbs": somente_digitos(nota.get("codigo_nbs")),
        "valor_servico": str(nota.get("valor_servico") or ""),
        "iss_retido": bool(nota.get("iss_retido")),
        "aliquota_iss": aliquota,
        "observacoes": (nota.get("observacoes") or "").strip() or None,
        "optante_simples": bool(nota.get("optante_simples", True)),
        "regime_tributario_nfse": str(nota.get("regime_tributario") or "simples_nacional"),
        "regime_especial_tributacao": str(nota.get("regime_especial_tributacao") or "0"),
        "percentual_tributos_sn": perc_sn,
    }
    if nota.get("intermediario_cnpj_cpf"):
        payload["intermediario_cnpj_cpf"] = somente_digitos(nota.get("intermediario_cnpj_cpf"))
        payload["intermediario_razao_social"] = (nota.get("intermediario_razao_social") or "").strip()
        payload["intermediario_fone"] = (nota.get("intermediario_fone") or "").strip() or None
    return _json_safe(payload)


def _emitir_nfse_via_hub(conn, nota: dict, id_nota: int):
    """Transmite a DPS pelo hub H74 (/v2/nfse). Assinatura e Sefin ficam no hub."""
    from api.fiscal.focus_nfe import FocusNfeError, baixar, request_json, token_configurado

    if not token_configurado(escopo="nfse"):
        return None

    ambiente = (nota.get("ambiente") or "homologacao").strip().lower()
    if ambiente != "producao":
        ambiente = "homologacao"
    ref = f"dn-nfse-{int(id_nota)}"[:60]
    payload = _payload_nfse_hub(nota)

    def _falha(mensagem: str, *, code: str = "HUB_NFSE", http: int = 422, incerto: bool = False):
        novo_status = "processando" if incerto else "rejeitada"
        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota SET status=%s, erro_codigo=%s, erro_mensagem=%s,
                   dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s AND status='processando'
            """,
            (novo_status, code, (mensagem or "")[:500], id_nota, _tenant()),
        )
        _auditar(
            conn,
            "emissao_incerta" if incerto else "emissao_rejeitada",
            mensagem,
            id_nota,
            {"via": "hub", "code": code},
        )
        conn.commit()
        return jsonify({
            "success": False,
            "code": code,
            "message": mensagem or "Falha na transmissão via hub.",
            "resultado_incerto": incerto,
            "ref": ref,
        }), http

    try:
        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota
               SET status='processando', id_dps=%s,
                   erro_codigo=NULL, erro_mensagem=NULL,
                   dt_inicio_processamento=NOW(), dt_ultima_tentativa=NOW(),
                   dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s
            """,
            (ref, id_nota, _tenant()),
        )
        _auditar(conn, "emissao_iniciada", f"Emissão via hub H74 (ref={ref}).", id_nota)
        conn.commit()

        try:
            status_http, body = request_json(
                ambiente,
                "POST",
                "/v2/nfse",
                params={"ref": ref},
                json_body=payload,
                timeout=120,
                escopo="nfse",
            )
        except FocusNfeError as exc:
            return _falha(
                str(exc),
                code="HUB_NFSE",
                http=(503 if getattr(exc, "status", 0) >= 500 else 422),
            )

        if not isinstance(body, dict):
            body = {}
        status_hub = str(body.get("status") or "").strip().lower()
        chave = str(body.get("chave_nfse") or "").strip() or None
        numero = str(body.get("numero") or body.get("numero_nfse") or "").strip() or None
        mensagem = str(
            body.get("mensagem_sefaz") or body.get("mensagem") or body.get("message") or ""
        ).strip()
        metadata = _json_dumps({"via": "hub", "ref": ref, "http_status": status_http, **body})

        if status_hub == "autorizado" or (status_http in (200, 201) and chave):
            xml_blob = None
            try:
                xml_blob = baixar(ambiente, f"/v2/nfse/{ref}.xml", escopo="nfse")
            except FocusNfeError:
                xml_blob = None
            db_execute(
                conn,
                """
                UPDATE tbl_nfse_nota SET status='autorizada', numero_nfse=%s, chave_nfse=%s,
                       xml_nfse_encriptado=%s, resposta_metadata=%s::jsonb,
                       erro_codigo=NULL, erro_mensagem=NULL, dt_autorizacao=NOW(),
                       dt_atualizacao=NOW()
                 WHERE id=%s AND id_tenant=%s AND status='processando'
                """,
                (
                    numero, chave,
                    criptografar(xml_blob) if xml_blob else None,
                    metadata, id_nota, _tenant(),
                ),
            )
            _auditar(conn, "nfse_autorizada", "NFS-e autorizada via hub H74.", id_nota)
            conn.commit()
            return jsonify({
                "success": True,
                "message": mensagem or "NFS-e autorizada.",
                "numero_nfse": numero,
                "chave_nfse": chave,
                "ref": ref,
            }), 201

        if status_hub in {"processando_autorizacao", "processando"}:
            db_execute(
                conn,
                """
                UPDATE tbl_nfse_nota SET status='processando', erro_codigo=NULL,
                       erro_mensagem=%s, resposta_metadata=%s::jsonb, dt_atualizacao=NOW()
                 WHERE id=%s AND id_tenant=%s AND status='processando'
                """,
                (mensagem[:500] or None, metadata, id_nota, _tenant()),
            )
            _auditar(conn, "emissao_incerta", mensagem or "Processando no hub.", id_nota, {"via": "hub"})
            conn.commit()
            return jsonify({
                "success": False,
                "code": "PROCESSANDO",
                "message": mensagem or "Hub ainda processando a autorização.",
                "resultado_incerto": True,
                "ref": ref,
            }), 503

        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota SET status='rejeitada', erro_codigo=%s, erro_mensagem=%s,
                   resposta_metadata=%s::jsonb, dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s AND status='processando'
            """,
            (
                status_hub or "erro_autorizacao",
                mensagem[:500] or "Rejeitada pelo hub.",
                metadata, id_nota, _tenant(),
            ),
        )
        _auditar(conn, "emissao_rejeitada", mensagem or status_hub, id_nota, {"via": "hub"})
        conn.commit()
        return jsonify({
            "success": False,
            "code": status_hub or "erro_autorizacao",
            "message": mensagem or "Emissão rejeitada pelo hub.",
            "resultado_incerto": False,
            "ref": ref,
        }), 422
    except Exception as exc:
        try:
            return _falha(f"Erro interno na emissão via hub: {exc}", code="HUB_INTERNO", http=500)
        except Exception:
            return jsonify({
                "success": False,
                "code": "HUB_INTERNO",
                "message": f"Erro interno na emissão via hub: {exc}",
                "resultado_incerto": False,
            }), 500


@nfse_bp.route("/api/notas/<int:id_nota>/emitir", methods=["POST"])
@_nfse_autorizado
def api_nota_emitir(id_nota):
    conn = Var_ConectarBanco()
    try:
        _garantir_partes_operacao(conn)
        cur = db_execute(
            conn,
            """
            SELECT n.*,
                   COALESCE(NULLIF(TRIM(t.razao_social), ''), NULLIF(TRIM(t.nome_completo), ''), t.nome) AS prestador_razao,
                   COALESCE(NULLIF(TRIM(t.cnpj), ''),
                            CASE WHEN UPPER(COALESCE(t.tipo_pessoa,''))='J'
                                 THEN NULLIF(TRIM(t.documento),'') END) AS prestador_cnpj,
                   t.inscricao_municipal, t.municipio_ibge_codigo,
                   COALESCE(NULLIF(TRIM(t.ambiente_nfse), ''), 'homologacao') AS ambiente,
                   COALESCE(NULLIF(TRIM(t.regime_tributario), ''), 'simples_nacional') AS regime_tributario,
                   COALESCE(t.optante_simples, TRUE) AS optante_simples,
                   t.regime_especial_tributacao, t.percentual_tributos_sn,
                   emp_inter.razao_social AS intermediario_razao_social,
                   emp_inter.cnpj AS intermediario_cnpj_cpf,
                   emp_inter.telefone AS intermediario_fone,
                   cert.conteudo_encriptado, cert.senha_encriptada
              FROM tbl_nfse_nota n
              JOIN tbl_tenant t ON t.id=n.id_tenant
              LEFT JOIN tbl_empresa emp_inter
                ON emp_inter.id=n.id_intermediario_empresa AND emp_inter.id_tenant=n.id_tenant
              LEFT JOIN LATERAL (
                  SELECT conteudo_encriptado, senha_encriptada
                    FROM tbl_nfse_certificado
                   WHERE id_tenant=n.id_tenant AND ativo=TRUE AND dt_fim_validade > NOW()
                   ORDER BY dt_fim_validade DESC LIMIT 1
              ) cert ON TRUE
             WHERE n.id=%s AND n.id_tenant=%s
             FOR UPDATE OF n
            """,
            (id_nota, _tenant()),
        )
        nota = _dict_row(cur)
        if not nota:
            return jsonify({"success": False, "message": "Rascunho não encontrado."}), 404
        if nota["status"] != "validado":
            return jsonify({
                "success": False,
                "message": (
                    "A emissão exige nota salva e validada."
                    if nota["status"] in ("rascunho", "rejeitada")
                    else f"Emissão bloqueada para nota em estado {nota['status']}."
                ),
            }), 409

        from api.fiscal.focus_nfe import token_configurado as _hub_nfse_ok

        if _hub_nfse_ok(escopo="nfse"):
            return _emitir_nfse_via_hub(conn, nota, id_nota)

        if not nota.get("conteudo_encriptado"):
            return jsonify({
                "success": False,
                "message": (
                    "Configure o Hub H74 (token NFS-e) em Configurações → Hub H74 "
                    "ou mantenha um certificado A1 local ativo."
                ),
            }), 400

        try:
            adapter = AdapterNacional(nota["ambiente"])
            tenant = {
                "razao_social": nota["prestador_razao"],
                "cnpj": nota["prestador_cnpj"],
                "inscricao_municipal": nota["inscricao_municipal"],
                "municipio_ibge_codigo": nota["municipio_ibge_codigo"],
            }
            xml = construir_dps(nota, tenant, nota)
            validar_xml(xml, nota["ambiente"])
            pfx = descriptografar(nota["conteudo_encriptado"])
            senha = descriptografar(nota["senha_encriptada"]).decode("utf-8")
            xml_assinado = assinar_dps(xml, pfx, senha)
            validar_xml(xml_assinado, nota["ambiente"])
        except PermissionError as exc:
            return jsonify({"success": False, "code": "PRODUCAO_BLOQUEADA", "message": str(exc)}), 403
        except (ErroDPS, ValueError, RuntimeError, UnicodeDecodeError) as exc:
            return jsonify({"success": False, "code": "PREPARACAO_DPS", "message": str(exc)}), 400

        id_dps = etree.fromstring(xml_assinado).find(
            "{http://www.sped.fazenda.gov.br/nfse}infDPS"
        ).get("Id")
        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota
               SET status='processando', id_dps=%s, xml_dps_encriptado=%s,
                   erro_codigo=NULL, erro_mensagem=NULL,
                   dt_inicio_processamento=NOW(), dt_ultima_tentativa=NOW(),
                   dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s
            """,
            (id_dps, criptografar(xml_assinado), id_nota, _tenant()),
        )
        _auditar(conn, "emissao_iniciada", "DPS marcada como processando antes da transmissão.", id_nota)
        conn.commit()

        resultado = adapter.emitir(xml_assinado, pfx, senha)
        metadata = json.dumps(resultado.metadados or {}, ensure_ascii=False)
        if resultado.sucesso:
            db_execute(
                conn,
                """
                UPDATE tbl_nfse_nota SET status='autorizada', numero_nfse=%s, chave_nfse=%s,
                       xml_nfse_encriptado=%s, resposta_metadata=%s::jsonb,
                       erro_codigo=NULL, erro_mensagem=NULL, dt_autorizacao=NOW(),
                       dt_atualizacao=NOW()
                 WHERE id=%s AND id_tenant=%s AND status='processando'
                """,
                (
                    resultado.numero_nfse, resultado.chave_nfse,
                    criptografar(resultado.xml_nfse), metadata, id_nota, _tenant(),
                ),
            )
            _auditar(conn, "nfse_autorizada", "NFS-e autorizada pela API Nacional.", id_nota)
            conn.commit()
            return jsonify({
                "success": True, "message": resultado.mensagem,
                "numero_nfse": resultado.numero_nfse, "chave_nfse": resultado.chave_nfse,
            }), 201

        novo_status = "processando" if resultado.incerto else "rejeitada"
        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota SET status=%s, erro_codigo=%s, erro_mensagem=%s,
                   resposta_metadata=%s::jsonb, dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s AND status='processando'
            """,
            (novo_status, resultado.codigo, resultado.mensagem, metadata, id_nota, _tenant()),
        )
        _auditar(
            conn, "emissao_incerta" if resultado.incerto else "emissao_rejeitada",
            resultado.mensagem, id_nota,
            {"codigo": resultado.codigo, "http_status": resultado.http_status},
        )
        conn.commit()
        return jsonify({
            "success": False, "code": resultado.codigo, "message": resultado.mensagem,
            "resultado_incerto": resultado.incerto,
        }), (503 if resultado.incerto else 422)
    finally:
        conn.close()


@nfse_bp.route("/api/notas/<int:id_nota>/liberar-emissao", methods=["POST"])
@_nfse_autorizado
def api_nota_liberar_emissao(id_nota):
    """Destrava nota em processando sem chave — permite validar/emitir de novo."""
    conn = Var_ConectarBanco()
    try:
        cur = db_execute(
            conn,
            """
            SELECT status, chave_nfse, numero_nfse
              FROM tbl_nfse_nota
             WHERE id=%s AND id_tenant=%s
             FOR UPDATE
            """,
            (id_nota, _tenant()),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Nota não encontrada."}), 404
        status, chave, numero = row[0], (row[1] or "").strip(), (row[2] or "").strip()
        if status != "processando":
            return jsonify({
                "success": False,
                "message": f"Só é possível liberar notas em processamento (atual: {status}).",
            }), 409
        if chave or numero:
            return jsonify({
                "success": False,
                "message": (
                    "Esta DPS já tem chave/número. Use Sincronizar ou Informe a chave do portal — "
                    "não reemita para evitar duplicidade."
                ),
            }), 409
        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota
               SET status='validado', erro_codigo=NULL,
                   erro_mensagem='Emissão liberada manualmente (sem chave na Sefin).',
                   dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s AND status='processando'
            """,
            (id_nota, _tenant()),
        )
        _auditar(
            conn,
            "emissao_liberada",
            "Nota destravada para nova emissão (processando sem chave).",
            id_nota,
        )
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Nota liberada. Pode emitir de novo.",
            "status": "validado",
        })
    except Exception as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500
    finally:
        conn.close()


def _mensagem_importacao(importadas, canceladas, reconciliadas, ja_existiam, terceiros, interrompida) -> str:
    partes = []
    if importadas:
        partes.append(f"{importadas} nota(s) importada(s)")
    if reconciliadas:
        partes.append(f"{reconciliadas} em processamento reconciliada(s) com a Sefin")
    if canceladas:
        partes.append(f"{canceladas} cancelamento(s) atualizado(s)")
    if ja_existiam:
        partes.append(f"{ja_existiam} já estavam no painel")
    if terceiros:
        partes.append(f"{terceiros} de outros prestadores ficaram de fora")
    texto = ". ".join(partes) + "." if partes else "Nenhuma nota nova deste CNPJ na Sefin."
    if interrompida:
        texto += " A busca parou antes do fim. Clique de novo para continuar."
    return texto


def _quando_autorizacao(nota: dict):
    if not nota.get("autorizada_em"):
        return None
    try:
        return datetime.fromisoformat(nota["autorizada_em"])
    except ValueError:
        return None


def _localizar_nota_importacao(conn, nota: dict):
    """Localiza rascunho/processando local pela chave, Id DPS ou série+número."""
    if nota.get("chave"):
        row = db_execute(
            conn,
            "SELECT id, status FROM tbl_nfse_nota WHERE id_tenant=%s AND chave_nfse=%s",
            (_tenant(), nota["chave"]),
        ).fetchone()
        if row:
            return row
    if nota.get("id_dps"):
        row = db_execute(
            conn,
            "SELECT id, status FROM tbl_nfse_nota WHERE id_tenant=%s AND id_dps=%s",
            (_tenant(), nota["id_dps"]),
        ).fetchone()
        if row:
            return row
    numero = int(nota["numero_dps"]) if str(nota.get("numero_dps") or "").isdigit() else None
    serie = (nota.get("serie_dps") or "").strip()
    if numero is not None and serie:
        row = db_execute(
            conn,
            """
            SELECT id, status FROM tbl_nfse_nota
             WHERE id_tenant=%s AND serie_dps=%s AND numero_dps=%s
             ORDER BY id DESC LIMIT 1
            """,
            (_tenant(), serie, numero),
        ).fetchone()
        if row:
            return row
    return None


def _reconciliar_nota_local(conn, id_local: int, status_atual: str, nota: dict) -> str:
    """Atualiza nota local com o resultado já existente na Sefin (evita duplicar DPS)."""
    quando = _quando_autorizacao(nota)
    meta = json.dumps({"origem": "adn", "nsu": nota.get("nsu"), "reconciliada": True}, ensure_ascii=False)
    if nota.get("cancelada"):
        if status_atual in ("autorizada", "processando"):
            db_execute(
                conn,
                """
                UPDATE tbl_nfse_nota SET
                    status='cancelada', chave_nfse=COALESCE(chave_nfse, %s),
                    numero_nfse=COALESCE(numero_nfse, %s),
                    xml_nfse_encriptado=COALESCE(xml_nfse_encriptado, %s),
                    resposta_metadata=%s::jsonb, dt_atualizacao=NOW()
                 WHERE id=%s AND id_tenant=%s
                """,
                (
                    nota["chave"], nota.get("numero_nfse") or None,
                    criptografar(nota["xml"]) if nota.get("xml") else None,
                    meta, id_local, _tenant(),
                ),
            )
            return "cancelada"
        return "existente"
    if status_atual in ("autorizada", "cancelada"):
        return "existente"
    db_execute(
        conn,
        """
        UPDATE tbl_nfse_nota SET
            status='autorizada',
            numero_nfse=%s,
            chave_nfse=%s,
            id_dps=COALESCE(NULLIF(id_dps, ''), %s),
            xml_nfse_encriptado=%s,
            resposta_metadata=%s::jsonb,
            erro_codigo=NULL,
            erro_mensagem=NULL,
            dt_autorizacao=COALESCE(%s, NOW()),
            dt_atualizacao=NOW()
         WHERE id=%s AND id_tenant=%s
           AND status IN ('processando','rejeitada','validado','rascunho')
        """,
        (
            nota.get("numero_nfse") or None,
            nota["chave"],
            nota.get("id_dps") or None,
            criptografar(nota["xml"]) if nota.get("xml") else None,
            meta,
            quando,
            id_local,
            _tenant(),
        ),
    )
    return "reconciliada"


def _gravar_nota_importada(conn, nota: dict, cnpj_tenant: str, serie_config: str, usuario: int) -> str:
    if nota["cnpj_prestador"] and nota["cnpj_prestador"] != cnpj_tenant:
        return "terceiro"
    if cnpj_emitente_na_chave(nota["chave"]) not in ("", cnpj_tenant):
        return "terceiro"
    if not nota["chave"] or not nota["serie_dps"] or not nota["competencia"]:
        return "invalida"
    existente = _localizar_nota_importacao(conn, nota)
    if existente:
        return _reconciliar_nota_local(conn, existente[0], existente[1], nota)
    tomador = db_execute(
        conn,
        """
        SELECT id FROM tbl_empresa
         WHERE id_tenant=%s AND regexp_replace(coalesce(cnpj, ''), '\\D', '', 'g')=%s
         LIMIT 1
        """,
        (_tenant(), nota["tomador_doc"]),
    ).fetchone() if nota["tomador_doc"] else None
    numero = int(nota["numero_dps"]) if str(nota["numero_dps"]).isdigit() else None
    quando = _quando_autorizacao(nota)
    db_execute(conn, "SAVEPOINT nfse_imp")
    try:
        db_execute(
            conn,
            """
            INSERT INTO tbl_nfse_nota (
                id_tenant, id_tomador_empresa, numero_dps, serie_dps, numero_nfse, chave_nfse,
                competencia, valor_servico, status, tomador_razao_social, tomador_cnpj_cpf,
                codigo_servico, codigo_tributacao_nacional, codigo_nbs, descricao_servico,
                incidencia_municipio_ibge, iss_retido, aliquota_iss, criado_por, dt_autorizacao,
                id_dps, xml_nfse_encriptado, resposta_metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
            )
            """,
            (
                _tenant(), tomador[0] if tomador else None, numero, nota["serie_dps"],
                nota["numero_nfse"] or None, nota["chave"], nota["competencia"], nota["valor"],
                "cancelada" if nota["cancelada"] else "autorizada",
                nota["tomador"][:220], nota["tomador_doc"] or None,
                nota["codigo_servico"], nota["codigo_tributacao"] or "000000", nota["nbs"],
                nota["descricao"], nota["municipio"] or None, nota["iss_retido"], nota["aliquota"],
                usuario, quando, nota["id_dps"] or None, criptografar(nota["xml"]),
                json.dumps({"origem": "adn", "nsu": nota["nsu"]}, ensure_ascii=False),
            ),
        )
        if numero and nota["serie_dps"] == serie_config:
            db_execute(
                conn,
                """
                UPDATE tbl_tenant
                   SET proximo_numero_dps=GREATEST(COALESCE(proximo_numero_dps, 1), %s),
                       dt_atualizacao=NOW()
                 WHERE id=%s
                """,
                (numero + 1, _tenant()),
            )
        db_execute(conn, "RELEASE SAVEPOINT nfse_imp")
    except IntegrityError:
        db_execute(conn, "ROLLBACK TO SAVEPOINT nfse_imp")
        # Corrida: outra gravação criou a mesma DPS — tenta reconciliar.
        de_novo = _localizar_nota_importacao(conn, nota)
        if de_novo:
            return _reconciliar_nota_local(conn, de_novo[0], de_novo[1], nota)
        return "existente"
    return "cancelada" if nota["cancelada"] else "importada"


@nfse_bp.route("/api/notas/importar", methods=["POST"])
@_nfse_autorizado
def api_notas_importar():
    """Copia para o painel as NFS-e que este CNPJ já emitiu. Não transmite DPS."""
    conn = Var_ConectarBanco()
    try:
        from sistema.fiscal.nfse.tenant_fiscal import carregar_empresa_fiscal, garantir_colunas_tenant_fiscal

        try:
            garantir_colunas_tenant_fiscal(conn)
        except Exception:
            conn.rollback()
        try:
            emp = carregar_empresa_fiscal(conn, _tenant())
            cur = db_execute(
                conn,
                """
                SELECT cert.conteudo_encriptado, cert.senha_encriptada
                  FROM tbl_tenant t
                  LEFT JOIN LATERAL (
                      SELECT conteudo_encriptado, senha_encriptada
                        FROM tbl_nfse_certificado
                       WHERE id_tenant=t.id AND ativo=TRUE AND dt_fim_validade > NOW()
                       ORDER BY dt_fim_validade DESC LIMIT 1
                  ) cert ON TRUE
                 WHERE t.id=%s
                """,
                (_tenant(),),
            )
        except ProgrammingError:
            conn.rollback()
            return jsonify({
                "success": False,
                "message": "Falta atualizar o banco (colunas fiscais do tenant). Reinicie e tente de novo.",
            }), 400
        cert_row = cur.fetchone()
        if not emp.get("eh_pj"):
            return jsonify({"success": False, "message": "Importação exige tenant PJ com Empresa fiscal."}), 400
        if not cert_row:
            return jsonify({"success": False, "message": "Configure a Empresa fiscal antes de importar."}), 400
        cnpj = somente_digitos(emp.get("cnpj") or "")
        ambiente = emp.get("ambiente") or "homologacao"
        serie_config = emp.get("serie_dps") or "1"
        cursor = int(emp.get("ultimo_nsu_adn") or 0)
        pfx_cifrado, senha_cifrada = cert_row[0], cert_row[1]
        if len(cnpj) != 14:
            return jsonify({"success": False, "message": "CNPJ do prestador não está cadastrado."}), 400
        if not pfx_cifrado:
            return jsonify({"success": False, "message": "Nenhum certificado A1 ativo e válido."}), 400
        try:
            pfx = descriptografar(pfx_cifrado)
            senha = descriptografar(senha_cifrada).decode("utf-8")
            adapter = AdapterNacional(ambiente or "homologacao")
        except (PermissionError, ValueError, RuntimeError, UnicodeDecodeError) as exc:
            return jsonify({"success": False, "message": str(exc)}), 400

        contagem = {
            "importada": 0, "cancelada": 0, "reconciliada": 0,
            "existente": 0, "terceiro": 0, "invalida": 0,
        }
        interrompida = False
        aviso = ""
        cursor_original = int(cursor or 0)
        # Se há DPS em processamento, tenta reabrir NSU para reconciliar.
        # Se o ADN rejeitar o NSU rebobinado, volta ao cursor normal sem abortar tudo.
        qtd_processando = db_execute(
            conn,
            "SELECT COUNT(*) FROM tbl_nfse_nota WHERE id_tenant=%s AND status='processando'",
            (_tenant(),),
        ).fetchone()[0]
        usando_rewind = bool(qtd_processando and cursor_original > 0)
        if usando_rewind:
            cursor = max(0, cursor_original - 300)
        for _ in range(20):
            lote = adapter.consultar_dfe(int(cursor or 0), pfx, senha)
            if not lote.sucesso:
                if usando_rewind:
                    cursor = cursor_original
                    usando_rewind = False
                    continue
                aviso = lote.mensagem
                if lote.http_status:
                    aviso = f"{aviso} (HTTP {lote.http_status})"
                interrompida = True
                break
            usando_rewind = False
            documentos, cursor, avancou = avancar_cursor(int(cursor or 0), documentos_do_lote(lote.metadados or {}))
            if not avancou:
                break
            eventos = []
            for item in documentos:
                xml = xml_do_arquivo(item["arquivo"])
                if item["tipo"] == "EVENTO":
                    eventos.append(xml)
                    continue
                if not xml:
                    contagem["invalida"] += 1
                    continue
                nota = ler_nfse(xml)
                if not nota:
                    continue
                nota["xml"] = xml
                nota["nsu"] = item["nsu"]
                if not nota["chave"]:
                    nota["chave"] = item["chave"]
                resultado = _gravar_nota_importada(conn, nota, cnpj, serie_config or "", session["id_usuario"])
                contagem[resultado] = contagem.get(resultado, 0) + 1
            for xml in eventos:
                chave = chave_cancelamento(xml) if xml else ""
                if len(chave) != 50 or cnpj_emitente_na_chave(chave) != cnpj:
                    continue
                atualizada = db_execute(
                    conn,
                    """
                    UPDATE tbl_nfse_nota SET status='cancelada', dt_atualizacao=NOW()
                     WHERE id_tenant=%s AND chave_nfse=%s AND status='autorizada'
                    """,
                    (_tenant(), chave),
                )
                if atualizada.rowcount:
                    contagem["cancelada"] += 1
            db_execute(
                conn,
                "UPDATE tbl_tenant SET ultimo_nsu_adn=%s, dt_atualizacao=NOW() WHERE id=%s",
                (cursor, _tenant()),
            )
            conn.commit()
        else:
            interrompida = True
        if aviso and not any(contagem[chave] for chave in ("importada", "cancelada", "reconciliada", "existente")):
            conn.rollback()
            return jsonify({"success": False, "message": aviso}), 502
        _auditar(conn, "importacao_adn", "Consulta de NFS-e já emitidas no Ambiente Nacional.", dados={
            "importadas": contagem["importada"],
            "reconciliadas": contagem["reconciliada"],
            "canceladas": contagem["cancelada"],
            "nsu": int(cursor or 0),
        })
        conn.commit()
        texto = _mensagem_importacao(
            contagem["importada"], contagem["cancelada"], contagem["reconciliada"],
            contagem["existente"], contagem["terceiro"], interrompida,
        )
        if aviso:
            texto = f"{texto} {aviso}"
        return jsonify({"success": True, "message": texto})
    finally:
        conn.close()


@nfse_bp.route("/api/danfse-modelo")
@_nfse_autorizado
def api_danfse_modelo():
    pdf = gerar_danfse_modelo()
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": 'inline; filename="DANFSe-modelo.pdf"'},
    )


@nfse_bp.route("/api/notas/<int:id_nota>/reconciliar", methods=["POST"])
@_nfse_autorizado
def api_nota_reconciliar(id_nota):
    """Atualiza a nota com a chave do portal e tenta baixar o XML completo na Sefin."""
    dados = request.get_json(silent=True) or {}
    chave = somente_digitos(dados.get("chave_nfse") or dados.get("chave") or "")
    numero_informado = str(dados.get("numero_nfse") or "").strip() or None
    if len(chave) != 50:
        return jsonify({
            "success": False,
            "message": "Informe a chave de acesso completa da NFS-e (50 dígitos), copiada do portal.",
        }), 400
    conn = Var_ConectarBanco()
    try:
        cur = db_execute(
            conn,
            """
            SELECT n.id, n.status, n.numero_dps, n.serie_dps, n.id_dps, n.numero_nfse,
                   n.xml_nfse_encriptado,
                   COALESCE(NULLIF(TRIM(t.cnpj), ''),
                            CASE WHEN UPPER(COALESCE(t.tipo_pessoa,''))='J'
                                 THEN NULLIF(TRIM(t.documento),'') END) AS prestador_cnpj,
                   COALESCE(NULLIF(TRIM(t.ambiente_nfse), ''), 'homologacao') AS ambiente,
                   cert.conteudo_encriptado, cert.senha_encriptada
              FROM tbl_nfse_nota n
              JOIN tbl_tenant t ON t.id=n.id_tenant
              LEFT JOIN LATERAL (
                  SELECT conteudo_encriptado, senha_encriptada
                    FROM tbl_nfse_certificado
                   WHERE id_tenant=n.id_tenant AND ativo=TRUE AND dt_fim_validade > NOW()
                   ORDER BY dt_fim_validade DESC LIMIT 1
              ) cert ON TRUE
             WHERE n.id=%s AND n.id_tenant=%s
             FOR UPDATE OF n
            """,
            (id_nota, _tenant()),
        )
        nota = _dict_row(cur)
        if not nota:
            return jsonify({"success": False, "message": "Nota não encontrada."}), 404
        if nota["status"] not in ("processando", "rejeitada", "validado", "autorizada"):
            return jsonify({
                "success": False,
                "message": f"Não é possível reconciliar nota em estado {nota['status']}.",
            }), 409
        cnpj_tenant = somente_digitos(nota.get("prestador_cnpj"))
        cnpj_chave = cnpj_emitente_na_chave(chave)
        if not cnpj_chave or cnpj_chave != cnpj_tenant:
            return jsonify({
                "success": False,
                "message": "A chave informada não pertence ao CNPJ prestador deste painel.",
            }), 400

        numero = numero_informado or numero_nfse_da_chave(chave) or nota.get("numero_nfse")
        xml_bytes = None
        consulta_ok = False
        consulta_msg = ""
        ambiente = nota.get("ambiente") or "homologacao"

        if nota.get("conteudo_encriptado") and nota.get("senha_encriptada"):
            try:
                pfx = descriptografar(nota["conteudo_encriptado"])
                senha = descriptografar(nota["senha_encriptada"]).decode("utf-8")
                adapter = AdapterNacional(ambiente)
                consulta = adapter.consultar_nfse(chave, pfx, senha)
                consulta_msg = consulta.mensagem or ""
                if consulta.sucesso and consulta.xml_nfse:
                    xml_bytes = consulta.xml_nfse
                    consulta_ok = True
                    if consulta.numero_nfse:
                        numero = str(consulta.numero_nfse)
                    if consulta.chave_nfse:
                        chave = somente_digitos(consulta.chave_nfse) or chave
            except Exception as exc:
                consulta_msg = str(exc)

        meta = json.dumps({
            "origem": "reconciliacao_manual",
            "chave": chave,
            "xml_baixado": bool(xml_bytes),
            "consulta_sefin": consulta_msg[:300] if consulta_msg else None,
        }, ensure_ascii=False)

        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota SET
                status='autorizada',
                chave_nfse=%s,
                numero_nfse=COALESCE(%s, numero_nfse),
                xml_nfse_encriptado=COALESCE(%s, xml_nfse_encriptado),
                erro_codigo=NULL,
                erro_mensagem=NULL,
                resposta_metadata=%s::jsonb,
                dt_autorizacao=COALESCE(dt_autorizacao, NOW()),
                dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s
               AND status IN ('processando','rejeitada','validado','autorizada')
            """,
            (
                chave,
                str(numero) if numero else None,
                criptografar(xml_bytes) if xml_bytes else None,
                meta,
                id_nota,
                _tenant(),
            ),
        )
        _auditar(
            conn, "nfse_reconciliada",
            "Nota reconciliada com chave do portal"
            + (" e XML baixado da Sefin." if xml_bytes else " (XML não disponível na consulta)."),
            id_nota,
            {"chave": chave, "numero": numero, "xml": bool(xml_bytes)},
        )
        conn.commit()
        if consulta_ok:
            mensagem = "Nota reconciliada com XML completo baixado da Sefin."
        else:
            mensagem = (
                "Nota reconciliada com a chave"
                + (f" e número {numero}." if numero else ".")
                + " Não foi possível baixar o XML agora"
                + (f": {consulta_msg}" if consulta_msg else ".")
                + " A DANFSe usará os dados locais; tente reconciliar de novo depois."
            )
        return jsonify({
            "success": True,
            "message": mensagem,
            "chave_nfse": chave,
            "numero_nfse": numero,
            "xml_baixado": bool(xml_bytes),
        })
    finally:
        conn.close()


@nfse_bp.route("/api/notas/<int:id_nota>/danfse")
@_nfse_autorizado
def api_nota_danfse(id_nota):
    conn = Var_ConectarBanco()
    try:
        _garantir_partes_operacao(conn)
        cur = db_execute(
            conn,
            """
            SELECT n.*, t.razao_social AS prestador_razao, t.cnpj AS prestador_cnpj,
                   t.municipio_nome AS prestador_municipio,
                   COALESCE(e.endereco, n.tomador_logradouro) AS tomador_logradouro,
                   COALESCE(e.numero, n.tomador_numero) AS tomador_numero,
                   COALESCE(e.complemento, n.tomador_complemento) AS tomador_complemento,
                   COALESCE(e.bairro, n.tomador_bairro) AS tomador_bairro,
                   COALESCE(e.cidade, n.tomador_cidade) AS tomador_cidade,
                   COALESCE(e.uf, n.tomador_uf) AS tomador_uf,
                   COALESCE(e.cep, n.tomador_cep) AS tomador_cep,
                   COALESCE(e.telefone, n.tomador_telefone) AS tomador_telefone,
                   emp_dest.razao_social AS dest_nome, emp_dest.cnpj AS dest_doc,
                   emp_dest.endereco AS dest_logradouro, emp_dest.numero AS dest_numero,
                   emp_dest.complemento AS dest_complemento, emp_dest.bairro AS dest_bairro,
                   emp_dest.cidade AS dest_cidade, emp_dest.uf AS dest_uf,
                   emp_dest.cep AS dest_cep, emp_dest.telefone AS dest_fone,
                   emp_inter.razao_social AS interm_nome, emp_inter.cnpj AS interm_doc,
                   emp_inter.endereco AS interm_logradouro, emp_inter.numero AS interm_numero,
                   emp_inter.complemento AS interm_complemento, emp_inter.bairro AS interm_bairro,
                   emp_inter.cidade AS interm_cidade, emp_inter.uf AS interm_uf,
                   emp_inter.cep AS interm_cep, emp_inter.telefone AS interm_fone,
                   cert.conteudo_encriptado, cert.senha_encriptada
              FROM tbl_nfse_nota n
              JOIN tbl_tenant t ON t.id=n.id_tenant
              LEFT JOIN tbl_empresa e ON e.id=n.id_tomador_empresa AND e.id_tenant=n.id_tenant
              LEFT JOIN tbl_empresa emp_dest
                ON emp_dest.id=n.id_destinatario_empresa AND emp_dest.id_tenant=n.id_tenant
              LEFT JOIN tbl_empresa emp_inter
                ON emp_inter.id=n.id_intermediario_empresa AND emp_inter.id_tenant=n.id_tenant
              LEFT JOIN LATERAL (
                  SELECT conteudo_encriptado, senha_encriptada
                    FROM tbl_nfse_certificado
                   WHERE id_tenant=n.id_tenant AND ativo=TRUE AND dt_fim_validade > NOW()
                   ORDER BY dt_fim_validade DESC LIMIT 1
              ) cert ON TRUE
             WHERE n.id=%s AND n.id_tenant=%s
            """,
            (id_nota, _tenant()),
        )
        nota = _dict_row(cur)
        if not nota or nota["status"] not in ("autorizada", "cancelada"):
            return jsonify({"success": False, "message": "DANFSe disponível somente para NFS-e autorizada ou cancelada."}), 404
        xml = descriptografar(nota["xml_nfse_encriptado"]) if nota.get("xml_nfse_encriptado") else None
        pdf = None
        if nota.get("chave_nfse") and nota.get("conteudo_encriptado"):
            pdf = AdapterNacional(nota.get("ambiente") or "producao").baixar_danfse(
                nota["chave_nfse"],
                descriptografar(nota["conteudo_encriptado"]),
                descriptografar(nota["senha_encriptada"]).decode("utf-8"),
            )
        if not pdf:
            pdf = gerar_danfse(xml, nota)
        nome = f"DANFSe-{nota.get('numero_nfse') or id_nota}.pdf"
        return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})
    finally:
        conn.close()


@nfse_bp.route("/api/notas/<int:id_nota>/cancelar", methods=["POST"])
@_nfse_autorizado
def api_nota_cancelar(id_nota):
    dados = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = db_execute(
            conn,
            """
            SELECT n.id, n.status, n.chave_nfse, n.dt_autorizacao, n.resposta_metadata,
                   COALESCE(NULLIF(TRIM(t.ambiente_nfse), ''), 'homologacao') AS ambiente,
                   COALESCE(NULLIF(TRIM(t.cnpj), ''),
                            CASE WHEN UPPER(COALESCE(t.tipo_pessoa,''))='J'
                                 THEN NULLIF(TRIM(t.documento),'') END) AS cnpj,
                   cert.conteudo_encriptado, cert.senha_encriptada
              FROM tbl_nfse_nota n
              JOIN tbl_tenant t ON t.id=n.id_tenant
              LEFT JOIN LATERAL (
                  SELECT conteudo_encriptado, senha_encriptada
                    FROM tbl_nfse_certificado
                   WHERE id_tenant=n.id_tenant AND ativo=TRUE AND dt_fim_validade > NOW()
                   ORDER BY dt_fim_validade DESC LIMIT 1
              ) cert ON TRUE
             WHERE n.id=%s AND n.id_tenant=%s
             FOR UPDATE OF n
            """,
            (id_nota, _tenant()),
        )
        nota = _dict_row(cur)
        if not nota:
            return jsonify({"success": False, "message": "Nota não encontrada."}), 404
        if nota["status"] != "autorizada":
            return jsonify({"success": False, "message": "Só uma NFS-e autorizada pode ser cancelada."}), 409
        bloqueio = motivo_bloqueio_cancelamento(nota.get("dt_autorizacao"))
        if bloqueio:
            return jsonify({"success": False, "code": "prazo_cancelamento", "message": bloqueio}), 409
        if not nota.get("chave_nfse") or not nota.get("conteudo_encriptado"):
            return jsonify({"success": False, "message": "Chave ou certificado ausente para o cancelamento."}), 400
        try:
            xml = construir_cancelamento(
                nota["chave_nfse"], nota["cnpj"], nota["ambiente"],
                str(dados.get("codigo") or "1"), dados.get("motivo") or "",
            )
            validar_xml(xml, nota["ambiente"], "pedRegEvento_v1.01.xsd")
            pfx = descriptografar(nota["conteudo_encriptado"])
            senha = descriptografar(nota["senha_encriptada"]).decode("utf-8")
            xml_assinado = assinar_dps(xml, pfx, senha, tag="infPedReg")
            validar_xml(xml_assinado, nota["ambiente"], "pedRegEvento_v1.01.xsd")
        except (ErroDPS, ValueError, RuntimeError, UnicodeDecodeError) as exc:
            return jsonify({"success": False, "message": str(exc)}), 400

        resultado = AdapterNacional(nota["ambiente"]).cancelar(nota["chave_nfse"], xml_assinado, pfx, senha)
        if not resultado.sucesso:
            _auditar(conn, "cancelamento_rejeitado", resultado.mensagem, id_nota, {"codigo": resultado.codigo})
            conn.commit()
            return jsonify({"success": False, "code": resultado.codigo, "message": resultado.mensagem}), 422

        meta = nota.get("resposta_metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        meta["cancelamento"] = {"codigo": str(dados.get("codigo") or "1"), "motivo": dados.get("motivo")}
        db_execute(
            conn,
            """
            UPDATE tbl_nfse_nota
               SET status='cancelada', resposta_metadata=%s::jsonb, dt_atualizacao=NOW()
             WHERE id=%s AND id_tenant=%s AND status='autorizada'
            """,
            (json.dumps(meta, ensure_ascii=False), id_nota, _tenant()),
        )
        _auditar(conn, "nfse_cancelada", "NFS-e cancelada na Sefin Nacional.", id_nota)
        conn.commit()
        return jsonify({"success": True, "message": "NFS-e cancelada."})
    finally:
        conn.close()
