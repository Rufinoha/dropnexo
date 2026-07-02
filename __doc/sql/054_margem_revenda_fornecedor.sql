-- Margem de revenda sugerida (% sobre valor Drop) — regras do fornecedor

ALTER TABLE tbl_fornecedor_precificacao
    ADD COLUMN IF NOT EXISTS pct_margem_revenda NUMERIC(8, 4) NOT NULL DEFAULT 80;

COMMENT ON COLUMN tbl_fornecedor_precificacao.pct_margem_revenda IS
    'Margem % sugerida para o vendedor incluir sobre o valor Drop na revenda (venda sugerida = Drop + margem).';
