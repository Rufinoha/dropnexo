-- DropNexo — mapa de integração: entidade categoria (Bling → DropNexo)

ALTER TABLE tbl_integracao_map DROP CONSTRAINT IF EXISTS tbl_integracao_map_entidade_check;

ALTER TABLE tbl_integracao_map ADD CONSTRAINT tbl_integracao_map_entidade_check
    CHECK (entidade IN ('produto', 'estoque', 'pedido', 'deposito', 'categoria'));
