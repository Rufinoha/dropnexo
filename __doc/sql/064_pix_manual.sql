-- PIX Manual — chave do fornecedor + comprovante validado manualmente

CREATE TABLE IF NOT EXISTS tbl_integracao_pix_manual (
    id_tenant INTEGER PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    ativo BOOLEAN NOT NULL DEFAULT FALSE,
    tipo_chave VARCHAR(20) NOT NULL DEFAULT 'aleatoria'
        CHECK (tipo_chave IN ('cpf', 'cnpj', 'email', 'telefone', 'aleatoria')),
    chave_pix VARCHAR(120) NOT NULL DEFAULT '',
    nome_beneficiario VARCHAR(25) NOT NULL DEFAULT '',
    cidade_beneficiario VARCHAR(15) NOT NULL DEFAULT '',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE tbl_integracao_pix_manual IS 'PIX estático do fornecedor para pagamento manual B2B.';

-- Meio de pagamento e status do comprovante
ALTER TABLE tbl_pedido DROP CONSTRAINT IF EXISTS tbl_pedido_meio_pagamento_check;
ALTER TABLE tbl_pedido ADD CONSTRAINT tbl_pedido_meio_pagamento_check
    CHECK (meio_pagamento IS NULL OR meio_pagamento IN ('pix', 'cartao', 'pix_manual'));

ALTER TABLE tbl_pedido DROP CONSTRAINT IF EXISTS tbl_pedido_status_pagamento_check;
ALTER TABLE tbl_pedido ADD CONSTRAINT tbl_pedido_status_pagamento_check
    CHECK (status_pagamento IN ('pendente', 'pago', 'cancelado', 'comprovante_enviado'));

ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS pix_manual_payload TEXT;
ALTER TABLE tbl_pedido ADD COLUMN IF NOT EXISTS pix_manual_txid VARCHAR(25);

COMMENT ON COLUMN tbl_pedido.pix_manual_payload IS 'Copia e cola EMV do PIX manual gerado para o pedido.';
COMMENT ON COLUMN tbl_pedido.pix_manual_txid IS 'TXID/referência no QR (ex.: número do pedido).';

-- Anexo de comprovante PIX
ALTER TABLE tbl_pedido_anexo DROP CONSTRAINT IF EXISTS tbl_pedido_anexo_tipo_check;
ALTER TABLE tbl_pedido_anexo ADD CONSTRAINT tbl_pedido_anexo_tipo_check
    CHECK (tipo IN ('nf', 'etiqueta', 'comprovante_pix'));
