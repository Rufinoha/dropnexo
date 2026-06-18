-- Permite vários depósitos lógicos no mesmo CEP (ex.: Geral vs Fulfillment Magalu via Bling)
ALTER TABLE tbl_deposito_expedicao
    DROP CONSTRAINT IF EXISTS tbl_deposito_expedicao_id_tenant_cep_key;

CREATE INDEX IF NOT EXISTS ix_deposito_tenant_nome
    ON tbl_deposito_expedicao(id_tenant, nome);
