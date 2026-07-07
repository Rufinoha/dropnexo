-- Anexos do pedido (NF, etiqueta de envio, etc.)

CREATE TABLE IF NOT EXISTS tbl_pedido_anexo (
    id SERIAL PRIMARY KEY,
    id_pedido INTEGER NOT NULL REFERENCES tbl_pedido(id) ON DELETE CASCADE,
    tipo VARCHAR(32) NOT NULL CHECK (tipo IN ('nf', 'etiqueta')),
    nome_original VARCHAR(255) NOT NULL,
    caminho VARCHAR(512) NOT NULL,
    tamanho_bytes INTEGER,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    id_usuario INTEGER
);

CREATE INDEX IF NOT EXISTS idx_pedido_anexo_pedido ON tbl_pedido_anexo(id_pedido, tipo);

COMMENT ON TABLE tbl_pedido_anexo IS 'Arquivos anexados ao pedido (nota fiscal, etiqueta).';
COMMENT ON COLUMN tbl_pedido_anexo.tipo IS 'nf | etiqueta';
