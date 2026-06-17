-- Imagens da variante: subconjunto ordenado da galeria do pai

CREATE TABLE IF NOT EXISTS tbl_produto_variante_imagem (
    id_variante INTEGER NOT NULL REFERENCES tbl_produto_variante(id) ON DELETE CASCADE,
    id_imagem INTEGER NOT NULL REFERENCES tbl_produto_imagem(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (id_variante, id_imagem)
);

CREATE INDEX IF NOT EXISTS ix_variante_imagem_variante
    ON tbl_produto_variante_imagem(id_variante);

CREATE INDEX IF NOT EXISTS ix_variante_imagem_imagem
    ON tbl_produto_variante_imagem(id_imagem);

-- Legado: uma imagem principal vira primeira da lista
INSERT INTO tbl_produto_variante_imagem (id_variante, id_imagem, ordem)
SELECT v.id, v.id_imagem_principal, 0
FROM tbl_produto_variante v
WHERE v.id_imagem_principal IS NOT NULL
  AND COALESCE(v.herda_pai, TRUE) = FALSE
ON CONFLICT (id_variante, id_imagem) DO NOTHING;
