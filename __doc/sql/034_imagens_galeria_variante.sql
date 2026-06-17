-- Galeria do pai, modo link/upload exclusivo, vínculo de imagem por variante e por atributo

ALTER TABLE tbl_produto
    ADD COLUMN IF NOT EXISTS imagem_modo VARCHAR(10)
        CHECK (imagem_modo IS NULL OR imagem_modo IN ('link', 'upload'));

ALTER TABLE tbl_produto_imagem
    ADD COLUMN IF NOT EXISTS origem VARCHAR(20) NOT NULL DEFAULT 'manual_upload'
        CHECK (origem IN ('bling_interna', 'bling_externa', 'manual_url', 'manual_upload'));

ALTER TABLE tbl_produto_variante
    ADD COLUMN IF NOT EXISTS id_imagem_principal INTEGER
        REFERENCES tbl_produto_imagem(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_variante_imagem_principal
    ON tbl_produto_variante(id_imagem_principal)
    WHERE id_imagem_principal IS NOT NULL;

CREATE TABLE IF NOT EXISTS tbl_produto_atributo_imagem (
    id SERIAL PRIMARY KEY,
    id_produto INTEGER NOT NULL REFERENCES tbl_produto(id) ON DELETE CASCADE,
    nome_atributo VARCHAR(60) NOT NULL,
    valor VARCHAR(120) NOT NULL,
    id_imagem INTEGER NOT NULL REFERENCES tbl_produto_imagem(id) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_produto, nome_atributo, valor)
);

CREATE INDEX IF NOT EXISTS ix_produto_atributo_imagem_produto
    ON tbl_produto_atributo_imagem(id_produto);

-- Modo do produto a partir da galeria legada
UPDATE tbl_produto p
SET imagem_modo = sub.modo
FROM (
    SELECT i.id_produto,
           CASE
               WHEN bool_or(i.caminho ILIKE 'http://%' OR i.caminho ILIKE 'https://%') THEN 'link'
               ELSE 'upload'
           END AS modo
    FROM tbl_produto_imagem i
    WHERE i.id_variante IS NULL
    GROUP BY i.id_produto
) sub
WHERE p.id = sub.id_produto
  AND p.imagem_modo IS NULL;

UPDATE tbl_produto p
SET imagem_modo = CASE
    WHEN p.imagem_url ILIKE 'http://%' OR p.imagem_url ILIKE 'https://%' THEN 'link'
    WHEN COALESCE(TRIM(p.imagem_url), '') <> '' THEN 'upload'
    ELSE p.imagem_modo
END
WHERE p.imagem_modo IS NULL
  AND COALESCE(TRIM(p.imagem_url), '') <> '';

UPDATE tbl_produto_imagem
SET origem = 'manual_url'
WHERE (caminho ILIKE 'http://%' OR caminho ILIKE 'https://%')
  AND origem = 'manual_upload';

UPDATE tbl_produto_imagem
SET origem = 'manual_upload'
WHERE caminho NOT ILIKE 'http://%'
  AND caminho NOT ILIKE 'https://%'
  AND origem = 'manual_upload';

-- Vincular variantes à galeria quando imagem_url coincide com item da galeria
UPDATE tbl_produto_variante v
SET id_imagem_principal = i.id
FROM tbl_produto_imagem i
WHERE i.id_produto = v.id_produto
  AND i.id_variante IS NULL
  AND v.id_imagem_principal IS NULL
  AND v.imagem_url IS NOT NULL
  AND TRIM(v.imagem_url) <> ''
  AND (
      i.caminho = v.imagem_url
      OR i.caminho = TRIM(v.imagem_url)
  );
