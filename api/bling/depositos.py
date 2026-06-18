# api/bling/depositos.py — pareamento e consulta de depósitos Bling
from __future__ import annotations

from global_utils import agora_utc


def listar_mapa_depositos(cur, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        SELECT dm.id, dm.id_bling_deposito, dm.nome_bling, dm.id_deposito_dropnexo, d.nome
        FROM tbl_integracao_deposito_map dm
        LEFT JOIN tbl_deposito_expedicao d ON d.id = dm.id_deposito_dropnexo
        WHERE dm.id_tenant = %s
        ORDER BY dm.nome_bling NULLS LAST, dm.id_bling_deposito
        """,
        (id_tenant,),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": r[0],
                "id_bling_deposito": r[1],
                "nome_bling": r[2] or "",
                "id_deposito_dropnexo": r[3],
                "nome_dropnexo": r[4] or "",
            }
        )
    return out


def resolver_deposito_dropnexo(cur, id_tenant: int, id_bling_deposito: str) -> int | None:
    cur.execute(
        """
        SELECT id_deposito_dropnexo FROM tbl_integracao_deposito_map
        WHERE id_tenant = %s AND id_bling_deposito = %s AND id_deposito_dropnexo IS NOT NULL
        LIMIT 1
        """,
        (id_tenant, str(id_bling_deposito)),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] else None


def salvar_vinculo_deposito(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    nome_bling: str | None,
    id_deposito_dropnexo: int | None,
) -> int:
    id_bling = str(id_bling_deposito).strip()
    if not id_bling:
        raise ValueError("Depósito Bling inválido.")
    if id_deposito_dropnexo:
        cur.execute(
            """
            SELECT 1 FROM tbl_deposito_expedicao
            WHERE id = %s AND id_tenant = %s AND ativo = TRUE
            """,
            (id_deposito_dropnexo, id_tenant),
        )
        if not cur.fetchone():
            raise ValueError("Depósito DropNexo inválido.")

    cur.execute(
        """
        INSERT INTO tbl_integracao_deposito_map (
            id_tenant, id_bling_deposito, nome_bling, id_deposito_dropnexo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id_tenant, id_bling_deposito) DO UPDATE SET
            nome_bling = EXCLUDED.nome_bling,
            id_deposito_dropnexo = EXCLUDED.id_deposito_dropnexo,
            atualizado_em = EXCLUDED.atualizado_em
        RETURNING id
        """,
        (id_tenant, id_bling, (nome_bling or "").strip() or None, id_deposito_dropnexo, agora_utc()),
    )
    return int(cur.fetchone()[0])


def sincronizar_depositos_bling_api(cur, id_tenant: int, depositos_bling: list[dict]) -> int:
    """Garante registros no mapa para cada depósito retornado pela API (sem vínculo)."""
    n = 0
    for dep in depositos_bling:
        id_b = str(dep.get("id") or "")
        if not id_b:
            continue
        nome = (dep.get("descricao") or dep.get("nome") or "").strip()
        cur.execute(
            """
            INSERT INTO tbl_integracao_deposito_map (id_tenant, id_bling_deposito, nome_bling, atualizado_em)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_tenant, id_bling_deposito) DO UPDATE SET
                nome_bling = COALESCE(EXCLUDED.nome_bling, tbl_integracao_deposito_map.nome_bling),
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, id_b, nome or None, agora_utc()),
        )
        n += 1
    return n


def _endereco_tenant(cur, id_tenant: int) -> dict | None:
    cur.execute(
        """
        SELECT nome, cep, logradouro, numero, complemento, bairro, cidade, uf
        FROM tbl_tenant WHERE id = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return None
    cep = "".join(ch for ch in str(row[1] or "") if ch.isdigit())
    if len(cep) != 8:
        return None
    log = (row[2] or "").strip()
    bairro = (row[5] or "").strip()
    cidade = (row[6] or "").strip()
    uf = (row[7] or "").strip()[:2].upper()
    if not log or not bairro or not cidade or len(uf) != 2:
        return None
    return {
        "nome_tenant": (row[0] or "").strip(),
        "cep": cep,
        "logradouro": log,
        "numero": (row[3] or "S/N").strip() or "S/N",
        "complemento": (row[4] or "").strip() or None,
        "bairro": bairro,
        "cidade": cidade,
        "uf": uf,
    }


def _criar_deposito_dropnexo(
    cur,
    id_tenant: int,
    *,
    nome: str,
    endereco: dict,
    principal: bool = False,
) -> int:
    if principal:
        cur.execute(
            "UPDATE tbl_deposito_expedicao SET principal = FALSE WHERE id_tenant = %s",
            (id_tenant,),
        )
    cur.execute(
        """
        INSERT INTO tbl_deposito_expedicao (
            id_tenant, nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
            remetente_nome, principal, ativo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
        RETURNING id
        """,
        (
            id_tenant,
            (nome or "Depósito").strip()[:120],
            endereco["cep"],
            endereco["logradouro"],
            endereco["numero"],
            endereco.get("complemento"),
            endereco["bairro"],
            endereco["cidade"],
            endereco["uf"],
            endereco.get("nome_tenant"),
            principal,
            agora_utc(),
        ),
    )
    return int(cur.fetchone()[0])


def _normalizar_nome_dep(nome: str) -> str:
    return " ".join((nome or "").strip().lower().split())


def criar_deposito_igual_bling(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    nome_bling: str | None = None,
    padrao_bling: bool = False,
) -> int:
    """
    Cria depósito DropNexo espelhando o depósito Bling (nome e flag principal)
    e usa o endereço cadastrado da empresa.
    """
    endereco = _endereco_tenant(cur, id_tenant)
    if not endereco:
        raise ValueError(
            "Complete o endereço da empresa (Minha Empresa) antes de criar depósitos automaticamente."
        )

    nome = (nome_bling or "").strip()
    if not nome:
        cur.execute(
            """
            SELECT nome_bling FROM tbl_integracao_deposito_map
            WHERE id_tenant = %s AND id_bling_deposito = %s
            LIMIT 1
            """,
            (id_tenant, str(id_bling_deposito)),
        )
        row = cur.fetchone()
        nome = (row[0] if row else "") or "Depósito Bling"

    cur.execute(
        """
        SELECT id FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE
          AND LOWER(TRIM(nome)) = LOWER(TRIM(%s))
        LIMIT 1
        """,
        (id_tenant, nome),
    )
    existente = cur.fetchone()
    if existente:
        return int(existente[0])

    cur.execute(
        "SELECT COUNT(*) FROM tbl_deposito_expedicao WHERE id_tenant = %s AND ativo = TRUE",
        (id_tenant,),
    )
    sem_depositos = int(cur.fetchone()[0] or 0) == 0
    principal = padrao_bling or sem_depositos

    try:
        return _criar_deposito_dropnexo(
            cur,
            id_tenant,
            nome=nome,
            endereco=endereco,
            principal=principal,
        )
    except Exception as exc:
        err = str(exc).lower()
        if "unique" in err and "cep" in err:
            raise ValueError(
                "Já existe um depósito com o CEP da empresa. "
                "Cadastre outro endereço em Expedição ou vincule a um depósito existente."
            ) from exc
        raise


def vincular_ou_criar_deposito_bling(
    cur,
    id_tenant: int,
    *,
    id_bling_deposito: str,
    nome_bling: str | None,
    id_deposito_dropnexo: int | None,
    criar_igual: bool = False,
    padrao_bling: bool = False,
) -> tuple[int, int | None, bool]:
    """
    Salva vínculo Bling ↔ DropNexo. Se criar_igual, cria depósito antes de vincular.
    Retorna (id_mapa, id_deposito_dropnexo, criou_deposito).
    """
    id_drop = id_deposito_dropnexo
    criou = False
    if criar_igual:
        id_drop = criar_deposito_igual_bling(
            cur,
            id_tenant,
            id_bling_deposito=id_bling_deposito,
            nome_bling=nome_bling,
            padrao_bling=padrao_bling,
        )
        criou = True

    rid = salvar_vinculo_deposito(
        cur,
        id_tenant,
        id_bling_deposito=id_bling_deposito,
        nome_bling=nome_bling,
        id_deposito_dropnexo=id_drop,
    )
    return rid, id_drop, criou


def garantir_depositos_bling_vinculados(cur, id_tenant: int) -> dict:
    """
    Sincroniza depósitos do Bling, vincula por nome ou cria DropNexo quando possível.
    Retorna resumo: mapa, vinculados, criados, pendentes.
    """
    from api.bling.sync_estoque import sincronizar_depositos_tenant

    n_mapa = sincronizar_depositos_tenant(cur, id_tenant)
    mapa = listar_mapa_depositos(cur, id_tenant)

    cur.execute(
        """
        SELECT id, nome FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE
        ORDER BY principal DESC, nome
        """,
        (id_tenant,),
    )
    deps_local = [{"id": r[0], "nome": r[1] or ""} for r in cur.fetchall()]
    ids_vinculados_local = {
        m["id_deposito_dropnexo"]
        for m in mapa
        if m.get("id_deposito_dropnexo")
    }

    vinculados = 0
    criados = 0
    endereco = _endereco_tenant(cur, id_tenant)

    for item in mapa:
        if item.get("id_deposito_dropnexo"):
            continue
        nome_bling = (item.get("nome_bling") or "").strip()
        id_bling = str(item.get("id_bling_deposito") or "")
        alvo = None
        nb = _normalizar_nome_dep(nome_bling)
        for dep in deps_local:
            if dep["id"] in ids_vinculados_local:
                continue
            if nb and _normalizar_nome_dep(dep["nome"]) == nb:
                alvo = dep["id"]
                break
        if alvo:
            salvar_vinculo_deposito(
                cur,
                id_tenant,
                id_bling_deposito=id_bling,
                nome_bling=nome_bling,
                id_deposito_dropnexo=alvo,
            )
            ids_vinculados_local.add(alvo)
            vinculados += 1
            continue

    mapa = listar_mapa_depositos(cur, id_tenant)
    pendentes = [m for m in mapa if not m.get("id_deposito_dropnexo")]

    if pendentes and endereco and not deps_local:
        dep_id = _criar_deposito_dropnexo(
            cur,
            id_tenant,
            nome=(pendentes[0].get("nome_bling") or "Depósito Bling"),
            endereco=endereco,
            principal=True,
        )
        deps_local.append({"id": dep_id, "nome": pendentes[0].get("nome_bling") or ""})
        salvar_vinculo_deposito(
            cur,
            id_tenant,
            id_bling_deposito=str(pendentes[0]["id_bling_deposito"]),
            nome_bling=pendentes[0].get("nome_bling"),
            id_deposito_dropnexo=dep_id,
        )
        criados += 1
        vinculados += 1
        pendentes = pendentes[1:]

    if len(pendentes) == 1 and len(deps_local) == 1:
        unico = deps_local[0]
        if unico["id"] not in ids_vinculados_local:
            salvar_vinculo_deposito(
                cur,
                id_tenant,
                id_bling_deposito=str(pendentes[0]["id_bling_deposito"]),
                nome_bling=pendentes[0].get("nome_bling"),
                id_deposito_dropnexo=unico["id"],
            )
            vinculados += 1
            pendentes = []

    return {
        "mapa": n_mapa,
        "vinculados": vinculados,
        "criados": criados,
        "pendentes": len(pendentes),
    }
