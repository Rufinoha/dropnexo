-- Descrição própria por variante (herda do pai quando herda_pai = TRUE)

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS descricao TEXT;

-- Preencher legado: descrição do pai quando vazio
UPDATE tbl_produto_variante v
SET descricao = NULLIF(TRIM(p.descricao), '')
FROM tbl_produto p
WHERE p.id = v.id_produto
  AND (v.descricao IS NULL OR TRIM(v.descricao) = '')
  AND COALESCE(TRIM(p.descricao), '') <> '';
