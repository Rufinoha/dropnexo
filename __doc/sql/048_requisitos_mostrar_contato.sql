-- Exibir contato do responsável ao vendedor na solicitação de vínculo

ALTER TABLE tbl_fornecedor_requisitos_vendedor
    ADD COLUMN IF NOT EXISTS mostrar_contato_vendedor BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN tbl_fornecedor_requisitos_vendedor.mostrar_contato_vendedor IS
    'Se TRUE, exibe nome, e-mail e WhatsApp do responsável na tela de solicitação de vínculo.';
