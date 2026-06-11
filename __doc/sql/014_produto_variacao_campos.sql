-- Variante: herança do pai + campos próprios (logística / fiscal)

ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS herda_pai BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS peso_liquido_kg NUMERIC(10, 3);
ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS peso_bruto_kg NUMERIC(10, 3);
ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS altura_cm NUMERIC(10, 2);
ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS largura_cm NUMERIC(10, 2);
ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS profundidade_cm NUMERIC(10, 2);
ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS gtin VARCHAR(20);
ALTER TABLE tbl_produto_variante ADD COLUMN IF NOT EXISTS ncm VARCHAR(10);
