# Button Map — ações ligadas a backend

Este arquivo documenta as ações principais da GUI. O smoke test também percorre todos os `TButton` e falha se houver botão sem `command`.

## Barra superior

- Novo Projeto → `new_project`
- Abrir Projeto → `open_project`
- Salvar Projeto → `save_project`
- Abrir BIN/EXE → `open_source`
- Verificar Hash → `verify_source_hash`
- Undo → `undo`
- Redo → `redo`

## Dashboard

- Abrir fonte → `open_source`
- Ir para Hex/Scan → seleciona aba Hex
- Validar ChangeSet → `validate_changes`
- Construir cópia de teste → `build_test_copy`

## Hex & Scan

- Buscar → `run_scan`
- Usar offset selecionado no Struct Lab → `scan_to_record_lab`
- Ir → `goto_hex`
- ◀ / ▶ → `shift_hex`

## Structs / Itens / Magias

- Mapear registro → `map_record`
- Definir campo → `add_custom_field`
- Atualizar leitura → `refresh_record_fields`
- Editar campo selecionado → `edit_selected_field`
- Ir ao Hex → `field_to_hex`
- Remover mapeamento → `remove_record`

## TIM & Aparência

- Scan TIM → `scan_tim_assets`
- Exportar TIM como PNG → `export_current_tim`
- Importar PNG para Preview → `import_preview_image`
- Girar ← / → → `rotate_actor`
- Usar imagem na direção → `assign_direction_image`
- Frame animação → `add_animation_frame`
- Play → `play_appearance`
- Stop → `stop_appearance`
- Exportar GIF → `export_appearance_gif`
- Aplicar tint → `tint_current_asset`
- Limpar animação → `clear_animation`

## Falas & Faces

- Procurar falas/textos → `scan_strings`
- Importar retrato → `import_portrait`
- Ir ao Hex → `dialogue_to_hex`
- Encenação segura da substituição → `stage_dialogue_edit`

## Scene Preview

- Limpar cena → `clear_scene`
- Salvar no projeto → `save_scene_state`
- Terreno / Unidade / Evento → `set_scene_tool`
- Preview da cena → `scene_play_preview`
- Clique no grid → `on_scene_click`

## ChangeSet & Build

- Ativar/Desativar → `toggle_change`
- Remover → `remove_change`
- Validar → `validate_changes`
- Exportar manifesto JSON → `export_manifest`
- Exportar IPS → `export_ips`
- Construir cópia de teste → `build_test_copy`
