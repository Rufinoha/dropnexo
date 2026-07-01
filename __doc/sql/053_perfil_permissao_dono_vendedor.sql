-- Dono/admin: todas as permissões ativas (exceto plataforma.dev), incluindo módulos vendedor adicionados depois do seed

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, perm.id
FROM tbl_perfil p
CROSS JOIN tbl_permissao perm
WHERE p.codigo IN ('dono', 'admin')
  AND perm.ativo = TRUE
  AND perm.codigo <> 'plataforma.dev'
ON CONFLICT DO NOTHING;

-- Permissões vd_* usadas nas rotas (caso ainda não existam no catálogo)
INSERT INTO tbl_permissao (codigo, modulo, descricao) VALUES
    ('vd_precificacao.ver', 'vd_precificacao', 'Ver precificação (vendedor)'),
    ('vd_precificacao.editar', 'vd_precificacao', 'Editar precificação (vendedor)'),
    ('vd_usuarios.ver', 'vd_usuarios', 'Ver equipe do vendedor'),
    ('vd_usuarios.editar', 'vd_usuarios', 'Gerenciar equipe do vendedor')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tbl_perfil_permissao (id_perfil, id_permissao)
SELECT p.id, m.id
FROM tbl_perfil p
JOIN tbl_permissao m ON m.codigo IN (
    'vd_precificacao.ver', 'vd_precificacao.editar',
    'vd_usuarios.ver', 'vd_usuarios.editar',
    'vd_catalogo.ver', 'vd_catalogo.editar',
    'precificacao.ver', 'precificacao.editar'
)
WHERE p.codigo IN ('dono', 'admin', 'vendedor')
ON CONFLICT DO NOTHING;
