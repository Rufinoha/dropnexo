-- Estado da sincronização manual de estoque por depósito vinculado
ALTER TABLE tbl_integracao_deposito_map
    ADD COLUMN IF NOT EXISTS estoque_sync_pendente BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS estoque_sync_concluido_em TIMESTAMPTZ;

-- Depósitos já vinculados sem sync concluída: habilitar botão "Atualizar estoque"
UPDATE tbl_integracao_deposito_map
SET estoque_sync_pendente = TRUE
WHERE id_deposito_dropnexo IS NOT NULL
  AND estoque_sync_concluido_em IS NULL;
