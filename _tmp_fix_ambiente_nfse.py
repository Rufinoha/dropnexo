"""Inspeciona e corrige ambiente histórico das NFS-e autorizadas."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/srv/dropnexo/.env")
os.environ["MODO_PRODUCAO"] = "true"

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME_PROD"),
    user=os.getenv("DB_USER_PROD"),
    password=os.getenv("DB_PASSWORD_PROD"),
    host=os.getenv("DB_HOST_PROD", "127.0.0.1"),
    port=os.getenv("DB_PORT_PROD", "5432"),
)
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute(
    """
    SELECT id, numero_dps, serie_dps, numero_nfse, status, ambiente,
           (xml_dps_encriptado IS NOT NULL) AS tem_dps,
           (xml_nfse_encriptado IS NOT NULL) AS tem_nfse,
           LEFT(COALESCE(resposta_metadata::text, ''), 180) AS meta,
           LEFT(COALESCE(chave_nfse, ''), 50) AS chave
      FROM tbl_nfse_nota
     WHERE status IN ('autorizada', 'cancelada')
     ORDER BY id DESC
     LIMIT 10
    """
)
rows = cur.fetchall()
print("=== ANTES ===")
for r in rows:
    print(
        f"id={r['id']} dps={r['numero_dps']}/{r['serie_dps']} nfse={r['numero_nfse']} "
        f"amb={r['ambiente']!r} dps_xml={r['tem_dps']} nfse_xml={r['tem_nfse']} chave={r['chave']}"
    )
    print(f"  meta={r['meta']!r}")

# Importa helpers do app se possível
amb_fix = {}
try:
    import sys

    sys.path.insert(0, "/srv/dropnexo")
    from sistema.fiscal.nfse.crypto_certificado import descriptografar
    from lxml import etree

    def amb_xml(blob):
        if not blob:
            return None
        root = etree.fromstring(descriptografar(blob))
        for el in root.xpath("//*[local-name()='tpAmb']"):
            t = (el.text or "").strip()
            if t == "1":
                return "producao"
            if t == "2":
                return "homologacao"
        return None

    cur.execute(
        """
        SELECT id, ambiente, xml_dps_encriptado, xml_nfse_encriptado, resposta_metadata, numero_nfse
          FROM tbl_nfse_nota
         WHERE status IN ('autorizada', 'cancelada')
           AND (ambiente IS NULL OR TRIM(COALESCE(ambiente, '')) = '')
         ORDER BY id
        """
    )
    vazias = cur.fetchall()
    print(f"\n=== VAZIAS: {len(vazias)} ===")
    for r in vazias:
        inferido = amb_xml(r["xml_dps_encriptado"]) or amb_xml(r["xml_nfse_encriptado"])
        if not inferido and isinstance(r.get("resposta_metadata"), dict):
            meta = r["resposta_metadata"]
            for k in ("ambiente", "tpAmb", "tipoAmbiente", "tipo_ambiente"):
                v = str(meta.get(k) or "").strip().lower()
                if v in {"homologacao", "homologação", "2"}:
                    inferido = "homologacao"
                    break
                if v in {"producao", "produção", "1"}:
                    inferido = "producao"
                    break
        if inferido:
            cur.execute(
                """
                UPDATE tbl_nfse_nota
                   SET ambiente=%s, dt_atualizacao=NOW()
                 WHERE id=%s
                   AND (ambiente IS NULL OR TRIM(COALESCE(ambiente, '')) = '')
                """,
                (inferido, r["id"]),
            )
            amb_fix[r["id"]] = inferido
            print(f"id={r['id']} nfse={r['numero_nfse']}: corrigido -> {inferido}")
        else:
            print(f"id={r['id']} nfse={r['numero_nfse']}: sem como inferir")
    conn.commit()
except Exception as exc:
    conn.rollback()
    print("ERRO_CORRECAO", type(exc).__name__, str(exc)[:400])

cur.execute(
    """
    SELECT id, numero_dps, serie_dps, numero_nfse, status, ambiente
      FROM tbl_nfse_nota
     WHERE status IN ('autorizada', 'cancelada')
     ORDER BY id DESC
     LIMIT 10
    """
)
print("\n=== DEPOIS ===")
for r in cur.fetchall():
    print(
        f"id={r['id']} dps={r['numero_dps']}/{r['serie_dps']} nfse={r['numero_nfse']} "
        f"amb={r['ambiente']!r}"
    )
print("fixados", amb_fix)
conn.close()
