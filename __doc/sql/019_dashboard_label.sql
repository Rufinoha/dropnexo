-- Renomeia item de menu Início → Dashboard (DBs já existentes)
UPDATE tbl_menu
SET nome_menu = 'Dashboard', descricao = 'Painel inicial'
WHERE nav_codigo = 'inicio' AND nome_menu = 'Início';
