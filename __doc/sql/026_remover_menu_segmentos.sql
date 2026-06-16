-- DropNexo — remove menu/tela Segmentos (nichos em Minha empresa)

UPDATE tbl_menu SET
    status = FALSE,
    descricao = 'Movido para Minha conta > Minha empresa',
    data_page = '/meu-perfil?aba=empresa',
    obs = 'fn_segmentos descontinuado'
WHERE nav_codigo = 'fn_segmentos';
