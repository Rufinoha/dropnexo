-- Pagamento Mercado Pago nos pedidos B2B (Fase 2)

ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS meio_pagamento VARCHAR(10)
    CHECK (meio_pagamento IS NULL OR meio_pagamento IN ('pix', 'cartao'));
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS mp_preference_id VARCHAR(80);
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS mp_payment_id BIGINT;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS mp_payment_status VARCHAR(30);
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS mp_checkout_url TEXT;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS mp_pix_qr TEXT;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS mp_pix_expira_em TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_pedido_mp_payment ON tbl_pedido(mp_payment_id)
    WHERE mp_payment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_pedido_mp_preference ON tbl_pedido(mp_preference_id)
    WHERE mp_preference_id IS NOT NULL;

COMMENT ON COLUMN tbl_pedido.meio_pagamento IS 'Meio escolhido pelo vendedor: pix ou cartao.';
COMMENT ON COLUMN tbl_pedido.mp_payment_id IS 'ID do pagamento no Mercado Pago.';
COMMENT ON COLUMN tbl_pedido.mp_preference_id IS 'ID da preferência Checkout Pro (cartão).';
