# api/xml_dropshipping/xml_dropshipping.py — conexão, acervo e sync do feed XML
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from global_utils import agora_utc

_log = logging.getLogger(__name__)

ORIGEM_PRODUTO = "integracao"
PROVEDOR = "xml_dropshipping"
TIMEOUT_FEED = (10, 90)

# Defaults editáveis — origem física do modelo Revenda de Calçados (Bauru/SP)
ORIGEM_DEFAULTS = {
    "origem_nome": "Revenda de Calçados",
    "origem_documento": "",
    "origem_cep": "17013-000",
    "origem_logradouro": "Bauru",
    "origem_numero": "S/N",
    "origem_complemento": "",
    "origem_bairro": "Centro",
    "origem_cidade": "Bauru",
    "origem_uf": "SP",
    "origem_telefone": "(14) 3624-1097",
}


def garantir_tabelas_xml_dropshipping(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_integracao_xml_dropshipping (
            id_tenant INTEGER PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
            status VARCHAR(32) NOT NULL DEFAULT 'desconectado',
            url_xml TEXT,
            url_csv TEXT,
            token TEXT,
            id_tenant_acervo INTEGER REFERENCES tbl_tenant(id) ON DELETE SET NULL,
            id_deposito INTEGER REFERENCES tbl_deposito_expedicao(id) ON DELETE SET NULL,
            origem_nome VARCHAR(160) NOT NULL DEFAULT 'Revenda de Calçados',
            origem_documento VARCHAR(20) NOT NULL DEFAULT '',
            origem_cep VARCHAR(12) NOT NULL DEFAULT '',
            origem_logradouro VARCHAR(160) NOT NULL DEFAULT '',
            origem_numero VARCHAR(30) NOT NULL DEFAULT '',
            origem_complemento VARCHAR(80) NOT NULL DEFAULT '',
            origem_bairro VARCHAR(80) NOT NULL DEFAULT '',
            origem_cidade VARCHAR(80) NOT NULL DEFAULT 'Bauru',
            origem_uf VARCHAR(2) NOT NULL DEFAULT 'SP',
            origem_telefone VARCHAR(40) NOT NULL DEFAULT '(14) 3624-1097',
            sync_auto BOOLEAN NOT NULL DEFAULT TRUE,
            ultima_sync TIMESTAMPTZ,
            ultimo_erro TEXT,
            meta JSONB NOT NULL DEFAULT '{}',
            conectado_em TIMESTAMPTZ,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Cache GLOBAL de categorias do feed (preenchido pelo tenant doador)
    cur.execute("SAVEPOINT sp_xml_cat_cache")
    try:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'tbl_xml_dropshipping_categoria_cache'
              AND column_name = 'id_tenant'
            LIMIT 1
            """
        )
        if cur.fetchone():
            cur.execute("DROP TABLE IF EXISTS tbl_xml_dropshipping_categoria_cache")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_xml_dropshipping_categoria_cache (
                id SERIAL PRIMARY KEY,
                category_key VARCHAR(160) NOT NULL UNIQUE,
                nome VARCHAR(255) NOT NULL,
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("RELEASE SAVEPOINT sp_xml_cat_cache")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT sp_xml_cat_cache")
        _log.warning("garantir cache categorias XML falhou", exc_info=True)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_integracao_xml_categoria_map (
            id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
            category_key VARCHAR(160) NOT NULL,
            id_categoria INTEGER REFERENCES tbl_categoria(id) ON DELETE SET NULL,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id_tenant, category_key)
        )
        """
    )


def _norm_key(nome: str) -> str:
    s = re.sub(r"\s+", " ", (nome or "").strip().lower())
    return s[:160]


def _dec(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def _txt(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return str(el.text).strip()


def montar_url_xml(url_xml: str = "", token: str = "") -> str:
    u = (url_xml or "").strip()
    tok = (token or "").strip()
    if not u and tok:
        return f"https://www.revendadecalcados.com.br/xmldrop?token={tok}"
    if u and tok and "token=" not in u.lower():
        sep = "&" if "?" in u else "?"
        return f"{u}{sep}token={tok}"
    return u


def extrair_token_da_url(url: str) -> str:
    try:
        q = parse_qs(urlparse(url).query)
        vals = q.get("token") or []
        return (vals[0] or "").strip() if vals else ""
    except Exception:
        return ""


def baixar_xml(url: str) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "DropNexo-XMLDropshipping/1.0",
            "Accept": "application/xml,text/xml,*/*",
        },
        method="GET",
    )
    with urlopen(req, timeout=TIMEOUT_FEED[1]) as resp:
        return resp.read()


def parse_produtos_xml(raw: bytes) -> tuple[list[dict], str]:
    root = ET.fromstring(raw)
    msg = _txt(root.find("mensagem")) or "OK"
    if msg.upper() not in ("OK", "SUCESSO", ""):
        raise RuntimeError(f"Feed retornou: {msg}")

    produtos: list[dict] = []
    for pel in root.findall("produto"):
        ref = _txt(pel.find("referencia"))
        nome = _txt(pel.find("nome"))
        if not ref or not nome:
            continue
        fotos: list[str] = []
        for fel in pel.findall("fotos"):
            u = _txt(fel.find("url_foto"))
            if u:
                fotos.append(u)
        estoques: list[tuple[str, int]] = []
        for eel in pel.findall("estoque"):
            tam = _txt(eel.find("tamanho"))
            try:
                qtd = int(float((_txt(eel.find("quantidade")) or "0").replace(",", ".")))
            except ValueError:
                qtd = 0
            if tam:
                estoques.append((tam, max(0, qtd)))
        dim = _txt(pel.find("dimensao_caixa_cm"))
        alt = larg = prof = None
        if dim:
            parts = re.split(r"[xX×]", dim.replace("cm", "").strip())
            nums = []
            for p in parts:
                d = _dec(p)
                if d is not None:
                    nums.append(float(d))
            if len(nums) >= 3:
                alt, larg, prof = nums[0], nums[1], nums[2]
        peso_g = _dec(_txt(pel.find("peso_gramas")))
        peso_kg = float(peso_g) / 1000.0 if peso_g is not None else None
        produtos.append(
            {
                "referencia": ref,
                "nome": nome,
                "categoria": _txt(pel.find("categoria")),
                "marca": _txt(pel.find("marca")),
                "descricao": _txt(pel.find("descricao")),
                "valor_atacado": _dec(_txt(pel.find("valor_atacado"))),
                "valor_dropshipping": _dec(_txt(pel.find("valor_dropshipping"))),
                "url_produto": _txt(pel.find("url_produto")),
                "fotos": fotos,
                "estoques": estoques,
                "altura_cm": alt,
                "largura_cm": larg,
                "profundidade_cm": prof,
                "peso_kg": peso_kg,
                "gps_estoque": _txt(pel.find("gps_estoque")),
            }
        )
    return produtos, msg


def xml_conectado(cur, id_tenant: int) -> bool:
    garantir_tabelas_xml_dropshipping(cur)
    cur.execute(
        """
        SELECT 1 FROM tbl_integracao_xml_dropshipping
        WHERE id_tenant = %s AND status = 'conectado'
        LIMIT 1
        """,
        (int(id_tenant),),
    )
    return bool(cur.fetchone())


def carregar_config(cur, id_tenant: int) -> dict:
    garantir_tabelas_xml_dropshipping(cur)
    cur.execute(
        """
        SELECT status, url_xml, url_csv, token, id_tenant_acervo, id_deposito,
               origem_nome, origem_documento, origem_cep, origem_logradouro,
               origem_numero, origem_complemento, origem_bairro, origem_cidade,
               origem_uf, origem_telefone, sync_auto, ultima_sync, ultimo_erro,
               conectado_em
        FROM tbl_integracao_xml_dropshipping
        WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row:
        return {
            "status": "desconectado",
            "conectado": False,
            "url_xml": "",
            "url_csv": "",
            "token": "",
            "id_tenant_acervo": None,
            "id_deposito": None,
            **ORIGEM_DEFAULTS,
            "sync_auto": True,
            "ultima_sync": None,
            "ultimo_erro": "",
            "conectado_em": None,
        }
    return {
        "status": row[0] or "desconectado",
        "conectado": (row[0] or "") == "conectado",
        "url_xml": row[1] or "",
        "url_csv": row[2] or "",
        "token": row[3] or "",
        "id_tenant_acervo": int(row[4]) if row[4] else None,
        "id_deposito": int(row[5]) if row[5] else None,
        "origem_nome": row[6] or ORIGEM_DEFAULTS["origem_nome"],
        "origem_documento": row[7] or "",
        "origem_cep": row[8] or "",
        "origem_logradouro": row[9] or "",
        "origem_numero": row[10] or "",
        "origem_complemento": row[11] or "",
        "origem_bairro": row[12] or "",
        "origem_cidade": row[13] or "Bauru",
        "origem_uf": row[14] or "SP",
        "origem_telefone": row[15] or ORIGEM_DEFAULTS["origem_telefone"],
        "sync_auto": bool(row[16]),
        "ultima_sync": row[17].isoformat() if row[17] else None,
        "ultimo_erro": row[18] or "",
        "conectado_em": row[19].isoformat() if row[19] else None,
    }


def _garantir_acervo(cur, id_tenant_vd: int, cfg: dict) -> int:
    """Cria/reusa tenant fornecedor sombra + vínculo ativo + depósito de origem."""
    cur.execute(
        """
        SELECT id_tenant_acervo FROM tbl_integracao_xml_dropshipping
        WHERE id_tenant = %s
        """,
        (int(id_tenant_vd),),
    )
    row = cur.fetchone()
    id_acervo = int(row[0]) if row and row[0] else None
    if id_acervo:
        cur.execute("SELECT id FROM tbl_tenant WHERE id = %s", (id_acervo,))
        if not cur.fetchone():
            id_acervo = None

    slug = f"xmlfd{int(id_tenant_vd)}"
    nome = "Revenda de Calçados"
    if not id_acervo:
        cur.execute("SELECT id FROM tbl_tenant WHERE slug = %s", (slug,))
        ex = cur.fetchone()
        if ex:
            id_acervo = int(ex[0])
        else:
            doc = f"XML{int(id_tenant_vd):011d}"[:18]
            cur.execute(
                """
                INSERT INTO tbl_tenant (
                    tipo_pessoa, tipo_negocio, documento, nome_completo, nome, slug,
                    plano, ativo, cep, logradouro, numero, complemento, bairro, cidade, uf
                ) VALUES (
                    'J', 'fornecedor', %s, %s, %s, %s, 'starter', TRUE,
                    %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
                """,
                (
                    doc,
                    nome,
                    nome,
                    slug,
                    (cfg.get("origem_cep") or "")[:12],
                    (cfg.get("origem_logradouro") or "")[:160],
                    (cfg.get("origem_numero") or "")[:30],
                    (cfg.get("origem_complemento") or "")[:80],
                    (cfg.get("origem_bairro") or "")[:80],
                    (cfg.get("origem_cidade") or "Bauru")[:80],
                    (cfg.get("origem_uf") or "SP")[:2],
                ),
            )
            id_acervo = int(cur.fetchone()[0])

    # Vínculo ativo (sem aprovação — acervo privado do vendedor)
    cur.execute(
        """
        SELECT id, status FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
        LIMIT 1
        """,
        (int(id_tenant_vd), id_acervo),
    )
    vinc = cur.fetchone()
    if vinc:
        if (vinc[1] or "") != "ativo":
            cur.execute(
                """
                UPDATE tbl_vinculo_vendedor_fornecedor
                SET status = 'ativo', respondido_em = NOW()
                WHERE id = %s
                """,
                (int(vinc[0]),),
            )
    else:
        cur.execute(
            """
            INSERT INTO tbl_vinculo_vendedor_fornecedor (
                id_tenant_vendedor, id_tenant_fornecedor, status, solicitado_em, respondido_em
            ) VALUES (%s, %s, 'ativo', NOW(), NOW())
            """,
            (int(id_tenant_vd), id_acervo),
        )

    # Depósito no acervo (origem Revenda)
    cur.execute(
        """
        SELECT id FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND nome = %s
        LIMIT 1
        """,
        (id_acervo, "Revenda de Calçados"),
    )
    dep = cur.fetchone()
    agora = agora_utc()
    campos_dep = (
        id_acervo,
        "Revenda de Calçados",
        (cfg.get("origem_cep") or "")[:12],
        (cfg.get("origem_logradouro") or "")[:160],
        (cfg.get("origem_numero") or "S/N")[:30],
        (cfg.get("origem_complemento") or "")[:80],
        (cfg.get("origem_bairro") or "")[:80],
        (cfg.get("origem_cidade") or "Bauru")[:80],
        (cfg.get("origem_uf") or "SP")[:2],
        (cfg.get("origem_nome") or "Revenda de Calçados")[:160],
        (cfg.get("origem_documento") or "")[:20],
        agora,
    )
    if dep:
        id_dep = int(dep[0])
        cur.execute(
            """
            UPDATE tbl_deposito_expedicao SET
                cep=%s, logradouro=%s, numero=%s, complemento=%s, bairro=%s,
                cidade=%s, uf=%s, remetente_nome=%s, remetente_documento=%s,
                principal=TRUE, ativo=TRUE, atualizado_em=%s
            WHERE id=%s AND id_tenant=%s
            """,
            campos_dep[2:] + (id_dep, id_acervo),
        )
    else:
        cur.execute(
            """
            UPDATE tbl_deposito_expedicao SET principal = FALSE
            WHERE id_tenant = %s
            """,
            (id_acervo,),
        )
        cur.execute(
            """
            INSERT INTO tbl_deposito_expedicao (
                id_tenant, nome, cep, logradouro, numero, complemento,
                bairro, cidade, uf, remetente_nome, remetente_documento,
                principal, ativo, espelho_somente_leitura, atualizado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,TRUE,FALSE,%s)
            RETURNING id
            """,
            campos_dep,
        )
        id_dep = int(cur.fetchone()[0])

    cur.execute(
        """
        UPDATE tbl_integracao_xml_dropshipping
        SET id_tenant_acervo = %s, id_deposito = %s, atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (id_acervo, id_dep, agora, int(id_tenant_vd)),
    )
    return id_acervo


def salvar_conexao(cur, id_tenant: int, dados: dict) -> dict:
    garantir_tabelas_xml_dropshipping(cur)
    url_xml = (dados.get("url_xml") or "").strip()
    token = (dados.get("token") or "").strip() or extrair_token_da_url(url_xml)
    url_final = montar_url_xml(url_xml, token)
    if not url_final:
        raise ValueError(
            "Informe a URL XML completa da Revenda de Calçados "
            "(ex.: https://www.revendadecalcados.com.br/xmldrop?token=...)."
        )

    # Testa o feed antes de conectar
    raw = baixar_xml(url_final)
    produtos, msg = parse_produtos_xml(raw)
    if not produtos:
        raise RuntimeError("Feed OK, mas sem produtos. Verifique a conta dropshipping.")

    cfg = {**ORIGEM_DEFAULTS, **(dados or {})}
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_integracao_xml_dropshipping (
            id_tenant, status, url_xml, url_csv, token,
            origem_nome, origem_documento, origem_cep, origem_logradouro,
            origem_numero, origem_complemento, origem_bairro, origem_cidade,
            origem_uf, origem_telefone, sync_auto, conectado_em, atualizado_em, ultimo_erro
        ) VALUES (
            %s, 'conectado', %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, NULL
        )
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            url_xml = EXCLUDED.url_xml,
            url_csv = EXCLUDED.url_csv,
            token = EXCLUDED.token,
            origem_nome = EXCLUDED.origem_nome,
            origem_documento = EXCLUDED.origem_documento,
            origem_cep = EXCLUDED.origem_cep,
            origem_logradouro = EXCLUDED.origem_logradouro,
            origem_numero = EXCLUDED.origem_numero,
            origem_complemento = EXCLUDED.origem_complemento,
            origem_bairro = EXCLUDED.origem_bairro,
            origem_cidade = EXCLUDED.origem_cidade,
            origem_uf = EXCLUDED.origem_uf,
            origem_telefone = EXCLUDED.origem_telefone,
            sync_auto = TRUE,
            conectado_em = COALESCE(tbl_integracao_xml_dropshipping.conectado_em, EXCLUDED.conectado_em),
            atualizado_em = EXCLUDED.atualizado_em,
            ultimo_erro = NULL
        """,
        (
            int(id_tenant),
            url_final,
            (dados.get("url_csv") or "").strip() or None,
            token,
            (cfg.get("origem_nome") or ORIGEM_DEFAULTS["origem_nome"])[:160],
            (cfg.get("origem_documento") or "")[:20],
            (cfg.get("origem_cep") or "")[:12],
            (cfg.get("origem_logradouro") or "")[:160],
            (cfg.get("origem_numero") or "")[:30],
            (cfg.get("origem_complemento") or "")[:80],
            (cfg.get("origem_bairro") or "")[:80],
            (cfg.get("origem_cidade") or "Bauru")[:80],
            (cfg.get("origem_uf") or "SP")[:2],
            (cfg.get("origem_telefone") or ORIGEM_DEFAULTS["origem_telefone"])[:40],
            agora,
            agora,
        ),
    )
    id_acervo = _garantir_acervo(cur, int(id_tenant), cfg)
    return {
        "ok": True,
        "produtos_no_feed": len(produtos),
        "mensagem_feed": msg,
        "id_tenant_acervo": id_acervo,
        "url_xml": url_final,
    }


def desconectar(cur, id_tenant: int) -> None:
    garantir_tabelas_xml_dropshipping(cur)
    cfg = carregar_config(cur, id_tenant)
    id_acervo = cfg.get("id_tenant_acervo")
    if id_acervo:
        cur.execute(
            """
            UPDATE tbl_vinculo_vendedor_fornecedor
            SET status = 'inativo', respondido_em = NOW()
            WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s
            """,
            (int(id_tenant), int(id_acervo)),
        )
    cur.execute(
        """
        UPDATE tbl_integracao_xml_dropshipping
        SET status = 'desconectado', atualizado_em = %s, ultimo_erro = NULL
        WHERE id_tenant = %s
        """,
        (agora_utc(), int(id_tenant)),
    )


def _garantir_categoria_acervo(
    cur, id_acervo: int, nome_feed: str, id_cat_vd: int | None
) -> int | None:
    nome = (nome_feed or "").strip()
    if id_cat_vd:
        cur.execute(
            """
            SELECT nome FROM tbl_categoria
            WHERE id = %s AND ativo = TRUE
            LIMIT 1
            """,
            (int(id_cat_vd),),
        )
        r = cur.fetchone()
        if r and r[0]:
            nome = str(r[0]).strip()
    if not nome:
        return None
    cur.execute(
        """
        SELECT id FROM tbl_categoria
        WHERE id_tenant = %s AND lower(trim(nome)) = lower(trim(%s))
        LIMIT 1
        """,
        (id_acervo, nome),
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute(
        """
        INSERT INTO tbl_categoria (id_tenant, nome)
        VALUES (%s, %s)
        RETURNING id
        """,
        (id_acervo, nome[:120]),
    )
    return int(cur.fetchone()[0])


def _mapa_categorias(cur, id_tenant: int) -> dict[str, int | None]:
    cur.execute(
        """
        SELECT category_key, id_categoria
        FROM tbl_integracao_xml_categoria_map
        WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    return {str(r[0]): (int(r[1]) if r[1] else None) for r in cur.fetchall()}


def _upsert_cache_categorias(cur, nomes: set[str]) -> int:
    """Grava categorias do feed no cache compartilhado (doador)."""
    agora = agora_utc()
    n = 0
    for nome in sorted(nomes):
        key = _norm_key(nome)
        if not key:
            continue
        cur.execute(
            """
            INSERT INTO tbl_xml_dropshipping_categoria_cache (
                category_key, nome, atualizado_em
            ) VALUES (%s, %s, %s)
            ON CONFLICT (category_key) DO UPDATE SET
                nome = EXCLUDED.nome, atualizado_em = EXCLUDED.atualizado_em
            """,
            (key, nome[:255], agora),
        )
        n += 1
    return n


def _upsert_produto_acervo(
    cur,
    *,
    id_acervo: int,
    id_deposito: int | None,
    prod: dict,
    id_categoria: int | None,
    skus_vivos: set[str],
) -> tuple[bool, int]:
    """Retorna (criado, qtd_variantes)."""
    ref = prod["referencia"]
    sku_pai = ref[:64]
    agora = agora_utc()
    preco = prod.get("valor_dropshipping") or prod.get("valor_atacado") or Decimal("0")
    custo = prod.get("valor_atacado")
    nome = prod["nome"][:255]
    desc = prod.get("descricao") or ""
    marca = (prod.get("marca") or "")[:120]

    cur.execute(
        """
        SELECT id FROM tbl_produto
        WHERE id_tenant = %s AND sku = %s
        LIMIT 1
        """,
        (id_acervo, sku_pai),
    )
    row = cur.fetchone()
    criado = False
    if row:
        prod_id = int(row[0])
        cur.execute(
            """
            UPDATE tbl_produto SET
                nome=%s, descricao=%s, preco=%s, preco_custo=%s, marca=%s,
                id_categoria=%s, publicado=TRUE, formato='E', origem=%s,
                peso_liquido_kg=%s, peso_bruto_kg=%s, altura_cm=%s, largura_cm=%s,
                profundidade_cm=%s, valor_drop=%s, id_deposito_expedicao=%s,
                atualizado_em=%s
            WHERE id=%s AND id_tenant=%s
            """,
            (
                nome,
                desc,
                preco,
                custo,
                marca,
                id_categoria,
                ORIGEM_PRODUTO,
                prod.get("peso_kg"),
                prod.get("peso_kg"),
                prod.get("altura_cm"),
                prod.get("largura_cm"),
                prod.get("profundidade_cm"),
                preco,
                id_deposito,
                agora,
                prod_id,
                id_acervo,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO tbl_produto (
                id_tenant, sku, nome, descricao, preco, preco_custo, marca,
                id_categoria, publicado, formato, origem, peso_liquido_kg, peso_bruto_kg,
                altura_cm, largura_cm, profundidade_cm, valor_drop, id_deposito_expedicao,
                atualizado_em
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,TRUE,'E',%s,%s,%s,%s,%s,%s,%s,%s,%s
            ) RETURNING id
            """,
            (
                id_acervo,
                sku_pai,
                nome,
                desc,
                preco,
                custo,
                marca,
                id_categoria,
                ORIGEM_PRODUTO,
                prod.get("peso_kg"),
                prod.get("peso_kg"),
                prod.get("altura_cm"),
                prod.get("largura_cm"),
                prod.get("profundidade_cm"),
                preco,
                id_deposito,
                agora,
            ),
        )
        prod_id = int(cur.fetchone()[0])
        criado = True

    # Imagens (substitui galeria por URLs do feed)
    fotos = prod.get("fotos") or []
    if fotos:
        cur.execute("DELETE FROM tbl_produto_imagem WHERE id_produto = %s", (prod_id,))
        for i, url in enumerate(fotos[:20]):
            cur.execute(
                """
                INSERT INTO tbl_produto_imagem (id_produto, caminho, ordem, principal)
                VALUES (%s, %s, %s, %s)
                """,
                (prod_id, url, i, i == 0),
            )
        cur.execute(
            "UPDATE tbl_produto SET imagem_url = %s WHERE id = %s",
            (fotos[0], prod_id),
        )

    estoques = prod.get("estoques") or []
    if not estoques:
        from fornecedor.catalogo.srotas_catalogo import garantir_variante_padrao

        vid = garantir_variante_padrao(cur, prod_id, id_acervo)
        cur.execute(
            """
            INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
            VALUES (%s, 0, %s)
            ON CONFLICT (id_variante) DO UPDATE SET
                quantidade = 0, atualizado_em = EXCLUDED.atualizado_em
            """,
            (vid, agora),
        )
        skus_vivos.add(sku_pai)
        return criado, 1

    # Marca produto com grade
    cur.execute(
        "UPDATE tbl_produto SET formato = 'E', atualizado_em = %s WHERE id = %s",
        (agora, prod_id),
    )
    n_var = 0
    total_qtd = 0
    for tam, qtd in estoques:
        sku_var = f"{ref}-{tam}"[:64]
        skus_vivos.add(sku_var)
        attrs = {"Tamanho": tam}
        import json

        cur.execute(
            """
            SELECT id FROM tbl_produto_variante
            WHERE id_produto = %s AND sku = %s
            LIMIT 1
            """,
            (prod_id, sku_var),
        )
        vr = cur.fetchone()
        if vr:
            vid = int(vr[0])
            cur.execute(
                """
                UPDATE tbl_produto_variante SET
                    nome_exibicao=%s, preco=%s, preco_custo=%s, ativo=TRUE,
                    atributos=%s::jsonb, atualizado_em=%s
                WHERE id=%s
                """,
                (f"{nome} · {tam}"[:255], preco, custo, json.dumps(attrs), agora, vid),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_produto_variante (
                    id_produto, sku, nome_exibicao, preco, preco_custo,
                    ativo, atributos, atualizado_em
                ) VALUES (%s,%s,%s,%s,%s,TRUE,%s::jsonb,%s)
                RETURNING id
                """,
                (
                    prod_id,
                    sku_var,
                    f"{nome} · {tam}"[:255],
                    preco,
                    custo,
                    json.dumps(attrs),
                    agora,
                ),
            )
            vid = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
            VALUES (%s, %s, %s)
            ON CONFLICT (id_variante) DO UPDATE SET
                quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
            """,
            (vid, int(qtd), agora),
        )
        total_qtd += int(qtd)
        n_var += 1

    cur.execute(
        """
        INSERT INTO tbl_produto_estoque (id_produto, quantidade, atualizado_em)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_produto) DO UPDATE SET
            quantidade = EXCLUDED.quantidade, atualizado_em = EXCLUDED.atualizado_em
        """,
        (prod_id, total_qtd, agora),
    )
    skus_vivos.add(sku_pai)
    return criado, n_var


def sincronizar_feed_tenant(
    cur,
    id_tenant: int,
    *,
    conn=None,
    produtos_precarregados: list[dict] | None = None,
) -> dict:
    """Baixa XML, atualiza acervo (catálogo) e estoque. Produtos ausentes → estoque 0."""
    garantir_tabelas_xml_dropshipping(cur)
    cfg = carregar_config(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("XML Dropshipping não está conectado.")

    url = montar_url_xml(cfg.get("url_xml") or "", cfg.get("token") or "")
    if not url:
        raise RuntimeError("URL/token do feed ausente.")

    if produtos_precarregados is None:
        raw = baixar_xml(url)
        produtos, _msg = parse_produtos_xml(raw)
    else:
        produtos = produtos_precarregados

    id_acervo = _garantir_acervo(cur, id_tenant, cfg)
    cfg = carregar_config(cur, id_tenant)
    id_dep = cfg.get("id_deposito")
    mapa = _mapa_categorias(cur, id_tenant)

    cats = {p["categoria"] for p in produtos if p.get("categoria")}
    # Cache global de categorias: só o doador (1º que conectou) atualiza
    n_cats = 0
    try:
        from sistema.tarefas_secundarias.doador import obter_id_doador, obter_ou_promover_doador

        codigo_cat = "xml_dropshipping_categorias_cache"
        doador = obter_id_doador(cur, codigo_cat) or obter_ou_promover_doador(cur, codigo_cat)
        if doador and int(doador) == int(id_tenant):
            n_cats = _upsert_cache_categorias(cur, cats)
        elif not doador and cats:
            # Sem doador ainda — este tenant assume e grava
            from sistema.tarefas_secundarias.doador import definir_doador

            definir_doador(cur, codigo_cat, int(id_tenant))
            n_cats = _upsert_cache_categorias(cur, cats)
    except Exception as e:
        _log.warning("Cache categorias XML ignorado: %s", e)

    skus_vivos: set[str] = set()
    criados = atualizados = variantes = 0
    for p in produtos:
        key = _norm_key(p.get("categoria") or "")
        id_cat_vd = mapa.get(key)
        id_cat_acervo = _garantir_categoria_acervo(
            cur, id_acervo, p.get("categoria") or "", id_cat_vd
        )
        criado, n_var = _upsert_produto_acervo(
            cur,
            id_acervo=id_acervo,
            id_deposito=id_dep,
            prod=p,
            id_categoria=id_cat_acervo,
            skus_vivos=skus_vivos,
        )
        if criado:
            criados += 1
        else:
            atualizados += 1
        variantes += n_var

    # Zera estoque de variantes do acervo que não vieram no feed
    zerados = 0
    if skus_vivos:
        cur.execute(
            """
            SELECT v.id
            FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE p.id_tenant = %s AND p.origem = %s AND v.ativo = TRUE
              AND v.sku IS NOT NULL AND NOT (v.sku = ANY(%s))
            """,
            (id_acervo, ORIGEM_PRODUTO, list(skus_vivos)),
        )
        ids = [int(r[0]) for r in cur.fetchall()]
        agora = agora_utc()
        for vid in ids:
            cur.execute(
                """
                INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
                VALUES (%s, 0, %s)
                ON CONFLICT (id_variante) DO UPDATE SET
                    quantidade = 0, atualizado_em = EXCLUDED.atualizado_em
                """,
                (vid, agora),
            )
            zerados += 1

    agora = agora_utc()
    msg = (
        f"Estoque/catálogo atualizados: {len(produtos)} produto(s) no feed · "
        f"{criados} novo(s) · {atualizados} atualizado(s) · "
        f"{variantes} variante(s) · {zerados} estoque(s) zerado(s) · "
        f"{n_cats} categoria(s) em cache."
    )
    cur.execute(
        """
        UPDATE tbl_integracao_xml_dropshipping
        SET ultima_sync = %s, ultimo_erro = NULL, atualizado_em = %s,
            meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb
        WHERE id_tenant = %s
        """,
        (
            agora,
            agora,
            __import__("json").dumps(
                {
                    "ultima_sync_msg": msg,
                    "produtos_feed": len(produtos),
                    "criados": criados,
                    "atualizados": atualizados,
                    "zerados": zerados,
                },
                ensure_ascii=False,
            ),
            int(id_tenant),
        ),
    )
    if conn is not None:
        conn.commit()
    return {
        "produtos_feed": len(produtos),
        "criados": criados,
        "atualizados": atualizados,
        "variantes": variantes,
        "zerados": zerados,
        "categorias_cache": n_cats,
        "mensagem": msg,
        "log_texto": msg,
    }


def listar_tenants_conectados_sync(cur) -> list[int]:
    garantir_tabelas_xml_dropshipping(cur)
    cur.execute(
        """
        SELECT id_tenant FROM tbl_integracao_xml_dropshipping
        WHERE status = 'conectado' AND sync_auto = TRUE
        ORDER BY id_tenant
        """
    )
    return [int(r[0]) for r in cur.fetchall()]


def buscar_categorias_cache(cur, id_tenant: int | None = None, termo: str = "", limit: int = 40) -> list[dict]:
    garantir_tabelas_xml_dropshipping(cur)
    lim = max(1, min(int(limit or 40), 80))
    t = (termo or "").strip()
    if len(t) < 1:
        cur.execute(
            """
            SELECT category_key, nome FROM tbl_xml_dropshipping_categoria_cache
            ORDER BY nome LIMIT %s
            """,
            (lim,),
        )
    else:
        like = f"%{t}%"
        cur.execute(
            """
            SELECT category_key, nome FROM tbl_xml_dropshipping_categoria_cache
            WHERE nome ILIKE %s OR category_key ILIKE %s
            ORDER BY nome LIMIT %s
            """,
            (like, like, lim),
        )
    return [{"category_id": r[0], "nome": r[1], "path_nomes": r[1]} for r in cur.fetchall()]


def listar_mapeamento_categorias(cur, id_tenant: int) -> list[dict]:
    garantir_tabelas_xml_dropshipping(cur)
    cur.execute(
        """
        SELECT c.category_key, c.nome, m.id_categoria, cat.nome
        FROM tbl_xml_dropshipping_categoria_cache c
        LEFT JOIN tbl_integracao_xml_categoria_map m
          ON m.id_tenant = %s AND m.category_key = c.category_key
        LEFT JOIN tbl_categoria cat ON cat.id = m.id_categoria
        ORDER BY c.nome
        """,
        (int(id_tenant),),
    )
    return [
        {
            "category_key": r[0],
            "nome_feed": r[1],
            "id_categoria": int(r[2]) if r[2] else None,
            "nome_categoria": r[3] or "",
        }
        for r in cur.fetchall()
    ]


def salvar_mapeamento_categorias(cur, id_tenant: int, itens: list[dict]) -> int:
    garantir_tabelas_xml_dropshipping(cur)
    agora = agora_utc()
    n = 0
    for it in itens or []:
        key = _norm_key(it.get("category_key") or it.get("category_id") or "")
        if not key:
            continue
        id_cat = it.get("id_categoria")
        id_cat = int(id_cat) if id_cat not in (None, "", 0, "0") else None
        cur.execute(
            """
            INSERT INTO tbl_integracao_xml_categoria_map (
                id_tenant, category_key, id_categoria, atualizado_em
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_tenant, category_key) DO UPDATE SET
                id_categoria = EXCLUDED.id_categoria,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (int(id_tenant), key, id_cat, agora),
        )
        n += 1
    return n
