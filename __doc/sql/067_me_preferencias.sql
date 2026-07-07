-- Preferências do vendedor na integração Melhor Envio

ALTER TABLE tbl_integracao_melhor_envio
    ADD COLUMN IF NOT EXISTS opcao_recebimento BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS opcao_maos_proprias BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN tbl_integracao_melhor_envio.opcao_recebimento IS
    'Incluir Aviso de Recebimento nas cotações (Correios/JadLog).';
COMMENT ON COLUMN tbl_integracao_melhor_envio.opcao_maos_proprias IS
    'Incluir Mãos Próprias nas cotações (Correios).';
