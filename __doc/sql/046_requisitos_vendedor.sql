-- Requisitos que o fornecedor exige do vendedor para aprovar vínculo B2B

CREATE TABLE IF NOT EXISTS tbl_fornecedor_requisitos_vendedor (
    id_tenant INTEGER PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
    exige_cnpj BOOLEAN NOT NULL DEFAULT FALSE,
    exige_nf BOOLEAN NOT NULL DEFAULT FALSE,
    cobra_taxa_vinculo BOOLEAN NOT NULL DEFAULT FALSE,
    valor_taxa_vinculo NUMERIC(12, 2) NOT NULL DEFAULT 0,
    cobra_taxa_mensal BOOLEAN NOT NULL DEFAULT FALSE,
    valor_taxa_mensal NUMERIC(12, 2) NOT NULL DEFAULT 0,
    cobra_taxa_pedido BOOLEAN NOT NULL DEFAULT FALSE,
    valor_taxa_pedido NUMERIC(12, 2) NOT NULL DEFAULT 0,
    mostrar_contato_vendedor BOOLEAN NOT NULL DEFAULT TRUE,
    texto_adicional TEXT,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE tbl_fornecedor_requisitos_vendedor IS
    'Critérios comerciais exibidos ao vendedor antes de solicitar vínculo com o fornecedor.';
