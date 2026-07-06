-- Vitrine vendedor: pausa persistida + flag produto próprio

ALTER TABLE tbl_produto_vendedor
    ADD COLUMN IF NOT EXISTS pausado_motivo VARCHAR(40),
    ADD COLUMN IF NOT EXISTS pausado_em TIMESTAMPTZ;

COMMENT ON COLUMN tbl_produto_vendedor.pausado_motivo IS
    'Motivo de pausa na vitrine (ex.: fornecedor_oculto_rede). Complementa regra em tempo real.';
