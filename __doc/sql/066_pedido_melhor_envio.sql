-- Cotação e contratação Melhor Envio no pedido (vendedor)

ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS me_cotacao_json JSONB;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS me_service_id INTEGER;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS me_preco_cotado NUMERIC(12, 2);
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS me_prazo_dias INTEGER;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS me_etiqueta_status VARCHAR(30);

COMMENT ON COLUMN tbl_pedido.me_cotacao_json IS 'Snapshot da cotação ME escolhida no pedido.';
COMMENT ON COLUMN tbl_pedido.me_service_id IS 'ID do serviço ME (transportadora) escolhido.';
COMMENT ON COLUMN tbl_pedido.me_etiqueta_status IS 'pendente|gerada|erro — compra da etiqueta após pagamento.';
