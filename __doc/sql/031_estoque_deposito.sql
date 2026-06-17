-- DropNexo — Estoque por depósito (variante × depósito) + índices

CREATE TABLE IF NOT EXISTS tbl_produto_estoque_deposito (
    id SERIAL PRIMARY KEY,
    id_variante INTEGER NOT NULL REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
    id_deposito INTEGER NOT NULL REFERENCES tbl_deposito_expedicao(id) ON DELETE CASCADE,
    quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_variante, id_deposito)
);

CREATE INDEX IF NOT EXISTS ix_ped_variante ON tbl_produto_estoque_deposito(id_variante);
CREATE INDEX IF NOT EXISTS ix_ped_deposito ON tbl_produto_estoque_deposito(id_deposito);

-- Migrar estoque legado (variante única) para o depósito principal do tenant
INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
SELECT v.id, d.id, COALESCE(e.quantidade, 0), COALESCE(e.atualizado_em, NOW())
FROM tbl_produto_variante v
JOIN tbl_produto p ON p.id = v.id_produto
JOIN tbl_deposito_expedicao d ON d.id_tenant = p.id_tenant AND d.ativo = TRUE
LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
WHERE d.principal = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM tbl_produto_estoque_deposito x
      WHERE x.id_variante = v.id AND x.id_deposito = d.id
  );

-- Depósitos sem principal: usa o primeiro depósito ativo do tenant
INSERT INTO tbl_produto_estoque_deposito (id_variante, id_deposito, quantidade, atualizado_em)
SELECT v.id, d.id, COALESCE(e.quantidade, 0), COALESCE(e.atualizado_em, NOW())
FROM tbl_produto_variante v
JOIN tbl_produto p ON p.id = v.id_produto
JOIN LATERAL (
    SELECT id FROM tbl_deposito_expedicao
    WHERE id_tenant = p.id_tenant AND ativo = TRUE
    ORDER BY principal DESC, id
    LIMIT 1
) d ON TRUE
LEFT JOIN tbl_produto_variante_estoque e ON e.id_variante = v.id
WHERE NOT EXISTS (SELECT 1 FROM tbl_produto_estoque_deposito x WHERE x.id_variante = v.id);
