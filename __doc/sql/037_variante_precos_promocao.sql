-- Preços da variante: valor Drop manual e promoção com validade / até zerar estoque

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS valor_drop_manual BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS promocao_validade DATE;

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS promocao_ate_zerar_estoque BOOLEAN NOT NULL DEFAULT FALSE;
