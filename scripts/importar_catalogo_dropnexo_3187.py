"""Importa catalogo_dropnexo.csv no tenant 3187 (Barauna) via motor de importação.

Conexão: túnel SSH local (padrão 127.0.0.1:11691) com postgres, ou vars de ambiente
DROPNEXO_IMPORT_*.
"""
from __future__ import annotations

import csv
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

ID_TENANT = 3187
CSV_PATH = ROOT / "catalogo_dropnexo.csv"


def _conectar():
    import psycopg2

    host = os.getenv("DROPNEXO_IMPORT_HOST", "127.0.0.1")
    port = int(os.getenv("DROPNEXO_IMPORT_PORT", "11691"))
    user = os.getenv("DROPNEXO_IMPORT_USER", "postgres")
    password = os.getenv("DROPNEXO_IMPORT_PASSWORD") or os.getenv("PGPASSWORD") or ""
    dbname = os.getenv("DROPNEXO_IMPORT_DB", "bd_dropnexo")
    if not password:
        raise SystemExit(
            "Defina PGPASSWORD ou DROPNEXO_IMPORT_PASSWORD (túnel prod em 11691)."
        )
    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        options="-c search_path=public -c application_name=dropnexo_import_csv",
    )


def _mapear_linhas(path: Path) -> list[tuple[int, dict]]:
    texto = path.read_text(encoding="utf-8-sig")
    delim = ";" if ";" in texto.splitlines()[0] else ","
    reader = csv.DictReader(io.StringIO(texto), delimiter=delim)
    out: list[tuple[int, dict]] = []
    for num, row in enumerate(reader, start=2):
        nome = (row.get("nome") or "").strip()
        sku = (row.get("sku") or "").strip()
        if not nome or not sku:
            continue
        # marca no CSV parece id Magazord (numérico) — não usar como marca
        mapped = {
            "sku": sku,
            "nome": nome,
            "descricao": (row.get("descricao") or nome).strip(),
            "preco": (row.get("preco_tabela_3") or row.get("preco") or "").strip().replace(",", "."),
            "quantidade": (row.get("estoque_disponivel") or row.get("quantidade") or "0").strip(),
            "imagem_1": (row.get("imagem") or row.get("imagem_1") or "").strip(),
            "unidade": "UN",
            # Obrigatórios do motor; 0 → cadastro ok, fora da rede até completar fiscal/medidas
            "peso_bruto_kg": "0",
            "altura_cm": "0",
            "largura_cm": "0",
            "profundidade_cm": "0",
            "ncm": "00000000",
            "origem_fiscal": "0",
            "publicado": "nao",
        }
        out.append((num, mapped))
    return out


def main() -> int:
    if not CSV_PATH.is_file():
        print("CSV não encontrado:", CSV_PATH)
        return 1

    rows = _mapear_linhas(CSV_PATH)
    print(f"Linhas mapeadas: {len(rows)}")

    from fornecedor.importacao.motor_csv import (
        aplicar_imagens_importacao,
        montar_mapa_colunas,
        processar_linhas_csv,
    )
    from fornecedor.importacao.servico_importacao import (
        MODULO_CATALOGO,
        ORIGEM_ARQUIVO,
        STATUS_CONCLUIDO,
        STATUS_ERRO,
        criar_lote,
        finalizar_lote,
        garantir_layout_padrao_csv,
        obter_layout_detalhe,
        registrar_erro_lote,
    )

    conn = _conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, tipo_negocio FROM tbl_tenant WHERE id = %s",
            (ID_TENANT,),
        )
        tenant = cur.fetchone()
        if not tenant:
            print(f"Tenant {ID_TENANT} não encontrado.")
            return 1
        print(f"Tenant: {tenant[0]} | {tenant[1]} | {tenant[2]}")

        cur.execute(
            "SELECT COUNT(*) FROM tbl_produto WHERE id_tenant = %s",
            (ID_TENANT,),
        )
        antes = int(cur.fetchone()[0] or 0)
        print(f"Produtos antes: {antes}")

        id_layout = garantir_layout_padrao_csv(cur, ID_TENANT)
        layout = obter_layout_detalhe(cur, ID_TENANT, id_layout, MODULO_CATALOGO)
        if not layout:
            print("Layout padrão não encontrado.")
            return 1

        # Cabeçalho sintético = chaves já mapeadas
        fieldnames = list(rows[0][1].keys()) if rows else []
        mapa = montar_mapa_colunas(fieldnames)

        id_lote, numero = criar_lote(
            cur,
            id_tenant=ID_TENANT,
            modulo=MODULO_CATALOGO,
            origem=ORIGEM_ARQUIVO,
            id_layout=int(layout["id"]),
            nome_arquivo=CSV_PATH.name,
            nome_lote="catalogo_dropnexo (agente)",
            meta={"fonte": "scripts/importar_catalogo_dropnexo_3187.py"},
        )

        resultado = processar_linhas_csv(
            cur,
            id_tenant=ID_TENANT,
            rows=rows,
            campos_layout=layout.get("campos") or [],
            mapa_arquivo=mapa,
            modo_imagens=layout.get("modo_imagens") or "colunas",
            delimitador_imagens=layout.get("delimitador_imagens") or ";",
            id_lote=id_lote,
            origem=ORIGEM_ARQUIVO,
        )

        for err in resultado.get("erros") or []:
            registrar_erro_lote(
                cur,
                id_tenant=ID_TENANT,
                id_lote=id_lote,
                modulo=MODULO_CATALOGO,
                linha_arquivo=err.get("linha"),
                sku_registro=err.get("sku") or "",
                mensagem=err.get("erro") or "Erro",
                origem=ORIGEM_ARQUIVO,
            )

        inseridos = int(resultado.get("inseridos") or 0)
        atualizados = int(resultado.get("atualizados") or 0)
        rejeitadas = int(resultado.get("rejeitadas") or 0)
        status = STATUS_ERRO if inseridos + atualizados == 0 else STATUS_CONCLUIDO
        finalizar_lote(
            cur,
            id_lote,
            status=status,
            total_linhas=int(resultado.get("total_linhas") or 0),
            total_importadas=inseridos,
            total_atualizadas=atualizados,
            total_rejeitadas=rejeitadas,
        )
        conn.commit()

        print(
            f"Lote {numero}: inseridos={inseridos} atualizados={atualizados} "
            f"rejeitadas={rejeitadas} fora_rede={len(resultado.get('nao_publicados') or [])}"
        )
        if resultado.get("erros"):
            for e in resultado["erros"][:10]:
                print("  ERRO", e)

        # Baixa imagens em sequência (poucos itens)
        imgs = resultado.get("imagens_pendentes") or []
        ok_img = 0
        for item in imgs:
            try:
                aplicar_imagens_importacao(
                    cur,
                    id_tenant=ID_TENANT,
                    id_produto=int(item["id_produto"]),
                    sku=item.get("sku") or f"P{item['id_produto']}",
                    urls=list(item.get("urls") or []),
                )
                conn.commit()
                ok_img += 1
            except Exception as ex:
                conn.rollback()
                print(f"  imagem falhou sku={item.get('sku')}: {ex}")
        print(f"Imagens processadas: {ok_img}/{len(imgs)}")

        cur.execute(
            "SELECT COUNT(*) FROM tbl_produto WHERE id_tenant = %s",
            (ID_TENANT,),
        )
        depois = int(cur.fetchone()[0] or 0)
        print(f"Produtos depois: {depois} (delta={depois - antes})")
        return 0 if inseridos + atualizados > 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
