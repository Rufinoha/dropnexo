-- DropNexo — valor_drop editado manualmente (não sobrescrever até reaplicar precificação)

ALTER TABLE tbl_produto ADD COLUMN IF NOT EXISTS valor_drop_manual BOOLEAN NOT NULL DEFAULT FALSE;
