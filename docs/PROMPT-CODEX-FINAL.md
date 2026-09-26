# Prompt para o Codex — terminar o Inverse Engine (VH2 Studio como primeiro perfil)

Repositório: https://github.com/aldeirdemouracosta-maker/inverse-engine (branch `main`).
**Os marcos 1 a 8 estão prontos (núcleo, interface PySide6, Modo Pesquisa, tabelas genéricas, cheats e memory card). Comece pelo marco 9 (áudio VAB).**
Trabalhe **nesse repositório**, marco por marco, com um commit por marco e todos os testes passando.

## 0. Leia antes de começar

### Contexto
VH2 Studio é uma bancada pessoal de modificação de **Vandal Hearts II (USA, SLUS-00940, PS1)**
para o projeto "Rebalance 2026". Linux primeiro (Lubuntu), compatível com Windows.
Núcleo em Python 3.10+ **só com biblioteca padrão**; interface em **PySide6**.

**Inverse Engine** é o modificador genérico de jogos de PS1. VH2 Studio é o **primeiro perfil de jogo**
dentro dele (`profiles/SLUS-00940-USA.json` + `research/findings/SLUS-00940-USA.json` + gabaritos).

- **Núcleo genérico** (sem nada de VH2): imagem do CD, formatos padrão da Sony (TIM, TMD, VAB, memory card),
  perfis, camadas, conflitos, operações, exportação.
- **Perfil de jogo** (dados, não código): tabelas, âncoras, grupos, findings, gabaritos.
- **Interface** (PySide6): só apresenta o núcleo.

Um segundo jogo deve poder entrar com um novo perfil JSON, sem mudar o núcleo.

```
RomImage → RomProfile → PatchStack → ChangeSet → Validation → Export
```

### Situação real do código (importante)
- O código da **v1.1 do VH2 Studio foi perdido** (`vh2_disc.py`, `vh2_tim.py`, `ppf.py`, `bps_patch.py`,
  `vh2_rom_editor.py`, `vh2_studio.py` e as 137 verificações). **Não procure por ele.** EDC/ECC, PPF, BPS,
  TIM/PNG, camadas, ChangeSet, projeto, exportação, relatório e hexa já foram reescritos nos marcos 2 a 4;
  a interface PySide6 no marco 5, o Modo Pesquisa no marco 6 as tabelas genéricas no marco 7 e cheats/memory card no marco 8; o resto é escrito nos marcos 9 em diante.
- `legado/VH2-PS1-Studio-v3.0/` guarda a v3.0-alpha (Tkinter + Pillow + IPS). **Não altere essa pasta** e não a
  importe no núcleo. Pode servir de referência de ideias: busca por valor/hex com curinga `??`/texto
  Shift-JIS, ChangeSet com undo/redo, prévia de aparência (direções, animação, GIF), prévia de falas com
  retrato. O que for aproveitado é **reescrito** no núcleo novo (sem Pillow) e na interface PySide6.
- Os **marcos 1 a 8 estão prontos** (ver 0.2): 165 testes passando. Continue do **marco 9**.

### 0.1 Estrutura do repositório
```
inverse_engine/
  cli.py                      modo terminal: abrir | tabela | findings  (python -m inverse_engine.cli)
  core/      rom_image.py profile.py patch_stack.py paths.py changeset.py project.py export.py hexview.py (prontos)
  formats/   disc.py psexe.py edc_ecc.py ppf.py bps.py tim.py png.py memcard.py (prontos)  vab.py tmd.py wav.py (fazer)
  research/  findings.py profiler.py gabarito.py testbin.py names.py cheats.py (prontos)
  assistant/ rules.py ollama.py context.py      (fazer)
  scripting/ api.py console.py                  (fazer)
  ui/        app.py main_menu.py workspace.py worker.py theme.py terminal.py recent.py themes/*.json (prontos)
profiles/SLUS-00940-USA.json          perfil (armas + habilidades)
research/findings/SLUS-00940-USA.json findings iniciais (F-0001…F-0016, S-0001…S-0003, S-0010…S-0021)
tests/  fixture_cd.py  test_rom_image.py  test_profile_anchors.py  test_profile_data.py
        test_edc_ecc.py  test_ppf_bps.py  test_tim_png.py  test_patch_stack.py  test_changeset_project.py  test_export_hexview.py  test_ui.py  test_research.py  test_tables_names.py  test_cheats_memcard.py
legado/ VH2-PS1-Studio-v3.0 (somente referência)
.github/workflows/tests.yml  (ubuntu-latest, Python 3.10 e 3.12, QT_QPA_PLATFORM=offscreen, PySide6)
```
Rodar os testes: `python -m unittest discover -s tests -t .` (sempre com `-t .`; `tests/` é pacote).

### 0.2 API que já existe (use, não duplique)
- `formats/disc.py`: `RAW_SECTOR=2352`, `USER_SIZE=2048`, `SYNC`, `sector_kind(raw)` →
  `mode1|mode2_form1|mode2_form2|mode0|unknown`, `user_range(kind)`, `open_disc(bytes)` → `Disc`
  (`files: dict[path, DiscFile]`, `raw_sector(lba)`, `kind(lba)`, `user_data(lba)`, `read_file(path)`
  (recusa Form 2), `file_offset_to_lba(path, off)`, `lba_to_file_offset(lba, off)`,
  `bin_offset(lba, off_no_setor)`, `locate_bin_offset(bin_off)` → `(lba, off|None)` (None = byte de sistema)),
  `normalize_path()` (maiúsculas, sem `;1`, separador `/`). Supõe BIN de faixa única começando no LBA 0.
- `formats/psexe.py`: `PsExe.parse(bytes)` (`load_address` = t_addr do cabeçalho), `file_to_ram`, `ram_to_file`.
- `core/rom_image.py`: `RomImage.open(path)` (BIN, `.cue`, arquivo avulso), `RomImage.from_bytes(data, nome)`,
  `.kind` (`bin|file`), `.sha256`, `list_files()`, `has_file()`, `read_file()`, `find_executable()`
  (pelo conteúdo), `file_offset_to_lba()`, `file_offset_to_bin()`, `bin_offset_to_user()`, `non_data_sectors()`.
- `core/profile.py`: `RomProfile.load/load_all`, `.evaluate(image)` → `ProfileMatch(anchors, applies,
  integrity_ok, image_sha256, known_image)`, `match_profiles(image, perfis)`; `TableSpec` genérica
  (`record_offset`, `field_offset`, `read_record`, `read_field`, `read_name` via matriz de ponteiros u32le de
  RAM, `category`, `end`); `TYPES` (u8, s8, u16le, s16le, u32le, s32le).
- `research/findings.py`: `FindingsDB.load/save`, `status(id)`, `policy(id, research_mode)`,
  `edit_policy(status, research_mode)` → `EditPolicy(editable, raw_only, experimental, badge, reason)`,
  `add_evidence`, `set_status` (promover exige evidência nova; rebaixar sempre permitido), `by_status()`.
- `tests/fixture_cd.py`: `CdBuilder().build({"PASTA/ARQ.EXT": bytes}, form2={...})` monta BIN Mode 2 com
  ISO9660 e subpastas, todos os setores com EDC/ECC corretos;
  `raw_sector(lba, payload, form2, mode)`; `make_slus(names, table_offset, stride, count, pointer_table, values)`
  gera SLUS artificial com cabeçalho PS-X EXE, ponteiros de nomes e tabela.
- `formats/edc_ecc.py` (marco 2): `edc(bytes)`, `compute(setor)` (EDC e ECC recalculados), `is_valid(setor)`.
- `formats/ppf.py`: `parse(bytes)` → `Ppf(version, description, records[(offset, bytes)], block, image_size,
  undo, file_id)`, `.check_block(imagem)` (None ou motivo), `.apply_to(imagem)`; `build_ppf3(orig, novo, desc,
  blockcheck, undo)`.
- `formats/bps.py`: `create(origem, destino, metadados)`, `apply(origem, patch)` (confere os três CRC32).
- `formats/png.py`: `write_indexed`, `write_rgba`, `read` → `PngImage(width, height, color_type, rows, palette)`.
- `formats/tim.py`: `parse(dados, offset)` → `TimInfo` (offset, size, bpp, width, height, vram_pos, clut_pos,
  clut_colors, clut_count, pixel_offset…), `scan`, `scan_image(RomImage)` → `[(arquivo, TimInfo)]`,
  `export_png`, `import_drawing`, `import_colors` (devolvem o TIM inteiro, mesmo tamanho), `to_rgba`,
  `from_rgba` (preto opaco → 0x8000), `palette`, `indices`, `build` (para testes).
- `core/patch_stack.py`: operações `FieldEdit(table, index, field, value)`, `RawEdit(file, offset, data)`,
  `GraphicEdit(file, offset, original, new, kind, palette_index, clut_pos)`; `Layer(name, kind, active, ppf,
  ppf_block_acknowledged, bps_target, edits)` com kind `ppf|bps_import|changeset|graphics|raw`;
  `PatchStack(image, profile, findings, research_mode)`: `add(layer)`, `writes(i)`, `conflicts()` →
  `[Conflict(kind, layers, detail, file, file_range, lba_range, target)]` (kind `CONFLITO|REDUNDANTE|INTEGRIDADE|
  PALETA_COMPARTILHADA`, `.id`, `.needs_ack`), `build(acknowledged=conjunto_de_ids)` → `BuildResult(data,
  touched_sectors, system_bytes_ignored, conflicts, experimental)`, `field_label`, `locate`.
  A política de edição por finding já é aplicada no `FieldEdit`. O ChangeSet do marco 3 deve **gerar camadas
  `changeset`/`graphics`/`raw` com essas operações**, não criar outro mecanismo de escrita.
- `core/paths.py`: `with_ext(caminho, ".ext")`, `replace_ext(caminho, ".bin", ".cue")`.
- `core/changeset.py` (marco 3): `ChangeSet(name)` + `.bind(image, profile, findings, research_mode)`;
  `set_field(tabela, índice, campo, valor, origin)`, `set_raw(arquivo, offset, bytes)` (só Modo Pesquisa),
  `set_graphic(GraphicEdit)` → `Operation(id, kind, target, before, after, origin, finding, date, group,
  group_label, experimental, …)`; `with cs.group("rótulo"):` agrupa (erro no meio desfaz o grupo inteiro);
  `undo()`/`redo()` por grupo, `can_undo/can_redo`, `history()`, `current_field`, `to_layers()` (só o último
  valor de cada alvo), `to_dict/from_dict`. ORIGINS = manual, regras, IA, script.
- `core/project.py`: `Project.create(pasta, nome, imagem[, profile_id])` (detecta o perfil pelas âncoras),
  `add_patch(caminho[, nome])` (PPF/BPS por caminho relativo + SHA-256; entra antes dos changesets),
  `add_changeset(nome)`, `move(nome, índice)`, `set_active(nome, bool)`, `bind(nome_changeset)`,
  `stack(accept_changed_files=False)` → `PatchStack` montado na ordem (hash mudou → `ProjectError` com "P4"),
  `check_hashes()`, `acknowledged` (ids de conflitos reconhecidos), `output` ({folder, name}),
  `save()` (atômico, `<nome>.vh2proj.json`), `Project.load(caminho)`, `rel()/abs()`.
- `core/export.py` (marco 4): `output_paths(projeto)`, `export(projeto, overwrite=False)` → `ExportResult(files,
  report)` (BIN, BPS, CUE, relatório .md/.json; P2 = só quando chamado; conflitos precisam estar em
  `projeto.acknowledged`), `reproduce(relatorio.json)` → `(ok, sha256)`, `report_markdown(report)`.
- `core/hexview.py`: `write_rows(stack)` → `HexRow(layer, file, file_offset, lba, ram, original, new, field)` com
  `.cells()` e `HEADERS`; `record_view(tabela, dados, índice, findings)`; `tim_sections(info)`;
  `tim_changes(info, original, novo)`; `format_table(linhas, cabeçalhos)`.
- `inverse_engine.__version__` = "0.4.0" (suba a cada marco).
- CLI: `abrir`, `tabela`, `findings`, `tims`, `ppf`, `registro`, `reproduzir`,
  `projeto novo|patch|campo|desfazer|refazer|mostrar|hexa|reconhecer|exportar`.
- `core/filetypes.py`: `detect(bytes_iniciais, form2, is_dir)` → tipo pelo conteúdo.
- Interface (marco 5, PySide6): `ui/app.py` `App` (QStackedWidget com `MainMenu` e `Workspace`; `start_project(imagem,
  pasta, nome)`, `open_image`, `open_project`, `options`), `ui/workspace.py` `Workspace` (docks "Arquivos do CD",
  "Inspetor", "Camadas e conflitos", "Histórico", "Console" com "Terminal equivalente"; abas Tabelas, Gráficos,
  Exportar, Sistema; `log(texto, comando)`, `cs()`, `refresh_all()`, `fill_table()`, `scan_tims(sync)`,
  `import_png(tipo, arquivo)`, `add_patch(arquivo)`, `acknowledge_dialog(auto_accept)`, `review_and_export(auto_confirm)`,
  `undo/redo`, `go_back`), `ui/worker.py` (`Task` QThread com progresso/cancelamento, `run_sync`), `ui/theme.py`
  (`contrast`, `check` WCAG AA, `stylesheet`), `ui/terminal.py` (comando de cada ação), `ui/recent.py` (recentes e
  opções em `~/.config/inverse_engine`, `INVERSE_ENGINE_CONFIG` nos testes).
  **Regras para abas novas:** cada módulo novo vira uma aba ou dock no `Workspace` e um botão do menu (os botões
  "Criar cheats", "Modelos 3D" e "Áudio e texturas" já existem desativados: ative-os no marco correspondente);
  todo controle com `setAccessibleName`; todo botão ligado a uma ação; toda ação registra `log(texto, comando)`
  com o comando equivalente do CLI (acrescente o subcomando no `cli.py`); tarefas longas em `Task`;
  `tests/test_ui.py` já confere nomes acessíveis e botões sem ação — acrescente os fluxos novos lá.
  Ainda não feito na interface: aba Assistente (marco 12), .iso de 2048 bytes (só BIN 2352, CUE e executável
  avulso são aceitos).
- Modo Pesquisa (marco 6): `research/profiler.py` `profile(tabela, dados, skip={0})` → `ColumnStats(offset, type,
  min, max, distinct, zeros, mult10, mult5, monotonic, field)` + `.notes()`; `research/gabarito.py` `load(csv|Path,
  tabela, dados)` → `Row(index, attribute, value, source)` (id numérico ou nome), `match(tabela, dados, linhas,
  threshold=0.9, min_records=3)` → `Proposal(... offset, type, matched, total, distinct, sources, existing)`,
  `apply(db, tabela, proposta)` (PROVAVEL com statistical_match; constante → HIPOTESE; nunca CONFIRMADO);
  `research/testbin.py` `value_test(projeto, tabela, índice, posição, tipo, valor)`, `field_test(projeto, arquivo,
  offset, bytes, nome)`, `recolor_test(projeto, arquivo, offset_tim)` (BIN em `<projeto>/testes/`, base + patches,
  sem changesets), `register_tims(db, encontrados)`; `FindingsDB.add_finding(prefixo, assunto, interpretação,
  status, evidências, **campos)`, `next_id`, `find(**campos)`. Aba "Pesquisa" do workspace (habilitada só com o
  Modo Pesquisa ligado): perfilador, gabarito com propostas marcáveis, marcar hipótese, BIN de teste, findings,
  promover/rebaixar (P3: `Workspace.promote(id, estado, tipo, detalhe, confirmed)`). Nos testes, use uma cópia
  dos findings (`project.findings_dir = pasta_temporária`): **testes nunca gravam em `research/findings/`**.
- Tabelas (marco 7): o perfil tem `weapons`, `skills` e `armors` (as duas últimas sem campos: todos os bytes
  DESCONHECIDO). `TableSpec.names_shift`, `name_slot(dados, i)`, `integrity(dados)`; `research/names.py`
  `analyze(tabela, dados)` → `NamesReport(pointer_count, record_count, entries, runs, invalid, hypotheses,
  divergence, summary())`, `confirm_shift(perfil.json, tabela, shift, db, evidência, confirmed)` (só grava com
  confirmação), `encode_name(tabela, dados, i, texto)` (mesmo tamanho ou menor, NUL; maior → `NamesError`);
  `ChangeSet.set_name(tabela, i, texto)` (op `text`). Aba Tabelas: coluna de nome editável conforme a política,
  bytes sem campo como colunas "byte_0xNN (cru)" no Modo Pesquisa, botão "Nomes…" (P3/confirmação).
  Nos testes, copie também o perfil (`project.profiles_dir = pasta_temporária`): **testes nunca gravam em
  `profiles/`**. `tests/test_tables_names.py` tem `make_full_slus()` (armas + habilidades 204×203 com a
  entrada 143 inválida + armaduras) para reaproveitar.
- Cheats e memory card (marco 8): `TableSpec.record_ram` / `record_ram_finding` (chave opcional `record_ram:
  {address, finding}` na tabela do perfil — o perfil real ainda não tem, por falta de evidência);
  `research/cheats.py` `field_cheat(tabela, dados, i, campo, valor, findings, research_mode, only_if)` → `Cheat(name,
  lines, experimental, address, note)`, `write16/write8/if_equal16`, `to_duckstation`, `to_text`;
  `formats/memcard.py` `MemCard(bytes)`, `.blank()`, `saves()` → `Save(slot, name, size, blocks, title, icon_frames,
  palette, checksum_ok)`, `free_slots`, `bad_checksums`, `export_mcs`, `import_mcs`, `icon_png`, `to_bytes`.
  Abas "Cheats" e "Memory Card" no workspace; `App.open_cheats()` (botão do menu). O CLI mostra erros sem
  traceback (`Erro: …`, código 2) — mantenha as mensagens do núcleo em português.

Se precisar mudar uma dessas APIs, adapte os testes **mantendo a mesma verificação**. Nunca apague nem
enfraqueça um teste.

### 0.3 Convenções
- Português do Brasil em textos, mensagens, nomes de testes e commits. Frases diretas.
- Núcleo só com biblioteca padrão. PySide6 só em `inverse_engine/ui/`. Nada de Pillow, numpy etc. no núcleo.
- Nomes de saída com o helper `with_ext(path, ext)` (já existe em `core/paths.py`): **acrescenta** a extensão
  ao nome, nunca usa `Path.with_suffix` (nomes de jogo têm pontos: `SLUS_009.40`, `Vandal Hearts II (USA).bin`).
- Toda escrita de arquivo de saída que já existe exige confirmação explícita (parâmetro `overwrite=True`
  no núcleo; diálogo na interface).
- Cada marco: código + testes sintéticos + atualizar a tabela "Estado" do `README.md` + `CHANGELOG.md` + commit.
- Cada ação da interface registra no painel "Terminal equivalente" o comando Linux correspondente
  (o usuário está aprendendo Linux). Para isso, toda ação da interface deve ter um subcomando equivalente
  em `python -m inverse_engine.cli`.

### 0.4 Referências técnicas (CD, EDC/ECC, PPF, BPS, TIM e PNG já implementados no marco 2; ficam como referência)

**Setor de CD (2352 bytes).** Sync 12 (`00 FF×10 00`), cabeçalho 4 (MSF em BCD, LBA+150; modo),
Mode 2: subcabeçalho 8 (arquivo, canal, submodo, codificação, repetido; submodo bit 0x20 = Form 2).
Form 1: dados 2048 em 24, EDC 4 em 2072, ECC P 172 em 2076 (0x81C), ECC Q 104 em 2248 (0x8C8).
Form 2: dados 2324 em 24, EDC 4 em 2348 (pode ser zero). Mode 1: dados 2048 em 16, EDC em 2064, 8 zeros,
ECC P em 2076, Q em 2248.

**EDC** = CRC-32 refletido, polinômio 0x8001801B (tabela: `e=i; 8×: e = (e>>1) ^ (0xD8018001 if e&1 else 0)`),
valor inicial 0, sem XOR final, gravado little-endian. Mode 2 Form 1: sobre bytes 16..2071 (subcabeçalho+dados).
Form 2: 16..2347. Mode 1: 0..2063.

**ECC** (algoritmo do ECM, de Neill Corlett): tabelas GF(2^8)
`for i in 0..255: j = ((i<<1) ^ (0x11D if i&0x80 else 0)) & 0xFF; f[i]=j; b[i^j]=i`.
```
computeblock(src, major_count, minor_count, major_mult, minor_inc, dest):
  size = major_count * minor_count
  for major in range(major_count):
    index = (major >> 1) * major_mult + (major & 1); a = c = 0
    for minor in range(minor_count):
      t = src[index]; index += minor_inc
      if index >= size: index -= size
      a ^= t; c ^= t; a = f[a]
    a = b[f[a] ^ c]
    dest[major] = a; dest[major + major_count] = a ^ c
```
`src` = setor a partir do byte 12. P: `(86, 24, 2, 86)` → 0x81C. Q: `(52, 43, 86, 88)` → 0x8C8 (Q é
calculado depois de P, e o bloco-fonte de Q inclui P). Em Mode 2, **zere os 4 bytes de cabeçalho (12..15)
durante o cálculo** e restaure depois. Testes obrigatórios: (a) regravar EDC/ECC de um setor válido não
muda nada; (b) um bit trocado nos dados é detectado; (c) **conferência cruzada**: se houver um compilador C
no ambiente, compile a implementação de referência do ECM num diretório temporário (fora do repositório) e
compare 40 setores aleatórios; se não houver, o teste é pulado com aviso claro (não marcar como aprovado).

**PPF.** PPF1: `"PPF10"`, codificação 0, descrição 50; registros `u32le offset, u8 len, dados`.
PPF2: `"PPF20"`, cod. 1, descrição 50, `u32le tamanho da imagem`, bloco de conferência 1024 bytes
(= imagem em 0x9320), registros `u32le offset, u8 len, dados`. PPF3: `"PPF30"`, cod. 2, descrição 50,
`imagetype u8` (0 BIN, 1 GI), `blockcheck u8`, `undo u8`, `dummy u8`, bloco 1024 se blockcheck,
registros `u64le offset, u8 len, dados` (+ `len` bytes de undo se undo). PPF2/3 podem terminar com
`@BEGIN_FILE_ID.DIZ` … `@END_FILE_ID.DIZ` + tamanho (confira a especificação oficial ppf3.txt para o
tamanho do campo final e trate os dois casos). Bloco de conferência diferente → recusar (portão P4 para
continuar mesmo assim). Criar também `build_ppf3(original, novo, descricao)` para os testes.

**BPS.** `"BPS1"`, VLQ(tamanho origem), VLQ(tamanho destino), VLQ(tamanho metadados) + metadados,
ações `VLQ(((len-1) << 2) | ação)`: 0 SourceRead, 1 TargetRead (+bytes), 2 SourceCopy (+VLQ offset relativo
com sinal no bit 0), 3 TargetCopy (idem); no fim CRC32 da origem, do destino e do próprio patch (sobre todos os
bytes anteriores), little-endian. VLQ: `loop: x = n & 0x7F; n >>= 7; if n == 0: out(0x80|x); break; out(x); n -= 1`.
Criador: pode ser simples (SourceRead/TargetRead por faixas iguais/diferentes), o importante é aplicar e conferir.

**EDC/ECC — conferência já feita:** os testes do marco 2 reconstroem o polinômio do EDC a partir do ECMA-130 e
conferem que as síndromes Reed-Solomon de todas as colunas P e diagonais Q dão zero em 40 setores aleatórios.
Isso substitui a comparação com o ECM compilado.

**TIM.** `u32 0x10`, `u32 flags` (bits 0–1: 0=4bpp, 1=8bpp, 2=16bpp, 3=24bpp; bit 3 = tem CLUT).
Bloco CLUT: `u32 tamanho (inclui 12)`, `u16 x, y, largura (cores), altura (paletas)`, cores 16 bits.
Bloco de imagem: `u32 tamanho`, `u16 x, y, largura em unidades de 16 bits, altura`, pixels (4bpp: nibble baixo
primeiro). Cor 16 bits: `R 0–4, G 5–9, B 10–14, STP 15`; `0x0000` = transparente; **preto opaco é gravado
como 0x8000** (bit STP). Procura em qualquer arquivo do CD (Form 2 ignorado), validando tamanhos coerentes.

**PNG sem Pillow** (zlib + struct): escrever PNG indexado (tipo 3, profundidade 8, PLTE + tRNS) para 4/8bpp e
RGBA para 16bpp; ler PNG indexado ou RGBA 8 bits, **recusar entrelaçado**, tamanho diferente do TIM e cor fora
da paleta. Reimportação de desenho mapeia por cor (aceita paleta reordenada); reimportação de cores troca só a
paleta. Sempre o mesmo tamanho em bytes e mesma posição na VRAM.

**Formatos dos marcos 8 a 10 (ainda não implementados).** Use como fonte a documentação "psx-spx"
(Nocash PSX specifications) e confira cada detalhe com fixtures sintéticas:
- Memory card: 128 KiB = 16 blocos de 8 KiB; bloco 0 é o diretório (quadros de 128 bytes; o último byte de cada
  quadro é o XOR dos 127 anteriores); cada save começa com "SC", ícone 16×16 4bpp e paleta de 16 cores.
- VAB: cabeçalho "pBAV" (VH) com programas, tons e tabela de tamanhos das amostras; o corpo (VB) tem as amostras
  em SPU-ADPCM (blocos de 16 bytes: 1 byte de shift/filtro, 1 de flags, 14 de dados = 28 amostras; filtros
  (0,0), (60,0), (115,-52), (98,-55), (122,-60) sobre 64).
- TMD: id 0x41, cabeçalho com número de objetos; cada objeto aponta para vértices (SVECTOR 8 bytes), normais e
  primitivas (cabeçalho olen/ilen/flag/mode por primitiva). Comece só com contagens e triângulos/quadriláteros
  planos e texturizados; exporte OBJ.

---

## Princípios (não negociáveis)

1. O arquivo original nunca é alterado. Toda saída é cópia.
2. Nenhum offset é inventado. O que não tem evidência fica `DESCONHECIDO`.
3. A IA nunca escreve bytes. Ela propõe operações; o núcleo valida.
4. Descoberta comprovada e hipótese nunca se misturam (ver `findings.json`).
5. O repositório não contém o jogo, BIOS nem texto de guias de terceiros.
   Hashes, offsets e fatos numéricos podem ficar.
6. Nenhum teste existente pode ser apagado ou enfraquecido. Se a API mudar,
   adapte o teste mantendo a mesma verificação.
7. Gráficos nunca mudam de tamanho em bytes nem de posição na VRAM nesta fase.
   Redesenho usa só cores da paleta; recolorir não mexe em pixels.
8. **Automático por padrão.** O app faz sozinho tudo o que for leitura, análise, proposta e
   conferência. O usuário só é chamado nos **portões** abaixo, com uma tela de revisão e um
   clique (aprovar tudo / aprovar selecionados / recusar):
   - **P1** aplicar operações ao projeto (entrar nas pendentes);
   - **P2** gerar a saída final (BIN/BPS);
   - **P3** promover um finding a `CONFIRMADO` (a evidência automática aparece pronta; o
     usuário só confirma o que viu, por exemplo o print do emulador);
   - **P4** reconhecer um conflito ou uma âncora que falhou.
   Nada fora desses portões pede confirmação. Nada dentro deles acontece sem ela.

---

## 1. RomImage (pronto no marco 1 — referência)

Abstração sobre a imagem aberta (`.bin` 2352 bytes/setor ou executável avulso).

- Lista arquivos do CD, lê arquivo como bytes, converte offset de arquivo ↔ (LBA, offset no setor).
- Expõe só **dados de usuário** (2048 bytes por setor Mode 2 Form 1). Sync, cabeçalho,
  subcabeçalho e EDC/ECC são "bytes de sistema" e nunca são alvo de edição.
- Setores que não são Mode 2 Form 1 são marcados e tratados em bytes crus (raro; avisar).

## 2. RomProfile — identificação por âncoras (pronto no marco 1 — referência)

**Não identificar a versão pelo SHA-256 do arquivo inteiro.** A BIN muda de hash conforme
a cópia do disco, e o executável muda de hash quando o Take Turns é aplicado, mesmo com
a tabela de armas intacta. O hash inteiro serve para **registrar** qual arquivo foi usado;
a decisão "estes offsets valem aqui" vem das **âncoras**.

Arquivo: `profiles/SLUS-00940-USA.json`

```json
{
  "profile_id": "SLUS-00940-USA",
  "game": "Vandal Hearts II",
  "region": "NTSC-U",
  "executable": {
    "name": "SLUS_009.40", "format": "PS-X EXE",
    "load_address": "0x8006C000", "header_size": "0x800"
  },
  "identify": {
    "anchors": [
      {"type": "bytes", "file": "SLUS_009.40", "offset": "0x0", "hex": "50532D5820455845"},
      {"type": "sha256_range", "file": "SLUS_009.40", "offset": "0xB5C", "length": 4730,
       "sha256": "5bf7dbf0933309437cbd79476e77a14057ea2ed4bb0f3e086b9a1c3a52d2b06f",
       "meaning": "tabela de armas 215 × 22 intacta"},
      {"type": "catalog_name", "table": "weapons", "id": 182, "name": "Rebelrod"}
    ],
    "required": ["bytes", "catalog_name"],
    "table_integrity": ["sha256_range"]
  },
  "known_images": [
    {"kind": "bin", "sha256": "2ee08a8f67e495dca429c52d2b596880f6365445faa30ec1f59af0f76ba948f1",
     "note": "BIN aprovada no LVCP Engine"}
  ],
  "tables": {
    "weapons": {
      "file": "SLUS_009.40", "offset": "0xB5C", "stride": 22, "count": 215,
      "names": {"pointer_table": "0x800"},
      "groups": [
        {"category": "espada", "start": 1, "end": 21}, {"category": "machado", "start": 22, "end": 41},
        {"category": "lanca", "start": 42, "end": 61}, {"category": "arremesso", "start": 62, "end": 81},
        {"category": "arco", "start": 82, "end": 101}, {"category": "cajado", "start": 102, "end": 137},
        {"category": "faca", "start": 138, "end": 157}, {"category": "escudo", "start": 158, "end": 178},
        {"category": "especial", "start": 179, "end": 200}, {"category": "monstro", "start": 201, "end": 214}
      ],
      "fields": {
        "range":  {"offset": "0x7",  "type": "u8",    "finding": "F-0010"},
        "attack": {"offset": "0xA",  "type": "u16le", "finding": "F-0011"},
        "price":  {"offset": "0xC",  "type": "u16le", "finding": "F-0012"},
        "weight": {"offset": "0xE",  "type": "u16le", "finding": "F-0013"},
        "visual_index_candidate": {"offset": "0x10", "type": "u16le", "finding": "F-0014"},
        "descriptor_code": {"offset": "0x12", "type": "u16le", "finding": "F-0015"},
        "lookup_key": {"offset": "0x14", "type": "u16le", "finding": "F-0016"}
      }
    }
  }
}
```

Regras:
- Ao abrir: avaliar todas as âncoras e mostrar o resultado de cada uma.
- `required` falhou → perfil não se aplica; nenhuma edição por perfil.
- `table_integrity` falhou → avisar em destaque (a tabela foi alterada por algum patch base);
  permitir continuar só com confirmação explícita.
- Não existe mais `items.json` para migrar (a v1.1 se perdeu). Se o usuário fornecer os 24 valores conhecidos
  (ataque e descritor de 12 armas), eles entram como **evidência** `static_values` em F-0011/F-0015, não no perfil.

## 3. findings.json — banco de descobertas (pronto no marco 1 — referência)

Arquivo: `research/findings/<perfil>.json`. Cada campo do perfil aponta para um finding.

```json
{
  "id": "F-0011",
  "subject": "weapons.attack",
  "file": "SLUS_009.40",
  "record_offset": "0xA", "size": 2, "type": "u16le",
  "interpretation": "ataque base da arma",
  "status": "PROVAVEL",
  "evidence": [
    {"kind": "static_values", "detail": "12 armas especiais (0xB3–0xC6) com valores coerentes", "date": "2026-08"},
    {"kind": "reference_value", "detail": "Evildoll 0xC7 = 115 segundo guia de 2000 — conferir", "date": null}
  ],
  "profiles": ["SLUS-00940-USA"],
  "history": [{"date": "...", "from": "HIPOTESE", "to": "PROVAVEL", "why": "..."}]
}
```

Estados: `CONFIRMADO`, `PROVAVEL`, `HIPOTESE`, `DESCONHECIDO`.
Tipos de evidência: `static_values`, `reference_value`, `statistical_match`, `in_game_test`,
`emulator_breakpoint`, `lvcp_evidence`.

Estado inicial (não promova nada sem evidência nova):

| Finding | Assunto | Estado inicial |
|---|---|---|
| F-0001 | geometria da tabela (0xB5C, 22, 215) | CONFIRMADO (hash do LVCP + ordem de IDs de fonte independente) |
| F-0002 | matriz de nomes em 0x800 | CONFIRMADO após a âncora Rebelrod passar |
| F-0011 | attack | PROVAVEL |
| F-0015 | descriptor_code | PROVAVEL |
| F-0010, F-0012, F-0013, F-0014, F-0016 | range, price, weight, visual, lookup | HIPOTESE |

Descobertas de gráficos também viram findings, por exemplo:

```json
{"id": "G-0001", "subject": "graphics.tim", "file": "DATA/XXXX.BIN", "offset": "0x2BC",
 "size": 1356, "type": "TIM 4bpp 32×16, 2 paletas, VRAM (320,0), paleta (0,480)",
 "interpretation": "sprite de ?", "status": "HIPOTESE",
 "evidence": [{"kind": "tim_scan", "detail": "cabeçalho TIM coerente"}]}
```

O que a imagem representa (personagem, classe, retrato) começa como `HIPOTESE` e só sobe com
evidência (`in_game_test`: recolorir e ver no emulador). Os nomes de arquivo acima são exemplo;
não invente caminhos do jogo real.

Política de edição:
- `CONFIRMADO` e `PROVAVEL`: editáveis normalmente (PROVAVEL mostra um selo discreto).
- `HIPOTESE`: editável só no Modo Pesquisa, com aviso claro; a operação fica marcada como experimental no relatório.
- `DESCONHECIDO`: não editável por campo; só como byte cru no Modo Pesquisa.
- Promover estado exige nova evidência registrada. Rebaixar é sempre permitido.

## 4. PatchStack — camadas

Projeto = imagem base + pilha ordenada de camadas, cada uma ativável/desativável:

```
Original → [PPF Take Turns] → [ChangeSet Rebalance] → [ChangeSet manual] → saída
```

Tipos de camada: `ppf`, `bps_import` (opcional), `changeset` (campos do perfil),
`graphics` (trocas de bytes de TIM em qualquer arquivo do CD), `raw` (Modo Pesquisa).
Um `changeset` e uma camada `graphics` podem estar no mesmo projeto e na mesma saída.

Regras:
- Toda camada é normalizada para **escritas em dados de usuário**: `(arquivo ou LBA, offset, bytes)`.
  PPF grava offsets da BIN; converter para (LBA, offset no setor). Bytes do PPF que caem em
  sync/cabeçalho/EDC/ECC são registrados como "bytes de sistema ignorados" (informativo),
  porque o EDC/ECC é recalculado no fim.
- A saída é **sempre reconstruída a partir do original**, aplicando as camadas ativas em ordem.
  Desativar uma camada = gerar de novo.
- EDC/ECC é recalculado **uma vez**, no fim, só nos setores tocados. Antes, validar o EDC/ECC
  desses setores no original (setor original com EDC/ECC inválido → recusar).
- O `ChangeSet` edita campos do perfil (em offsets do SLUS); o núcleo resolve para LBA ao montar.
- A camada `graphics` guarda, por imagem, `{arquivo no CD, offset, bytes originais, bytes novos,
  tipo: desenho|cores, paleta}`. Ao montar, confere que os bytes originais ainda estão no lugar
  (senão recusa: o arquivo base mudou).

## 5. Detector de conflitos

Comparar **somente dados de usuário**, nunca bytes de sistema (senão todo PPF antigo gera
conflito falso com qualquer edição no mesmo setor).

- Mesma faixa, mesmos bytes → `REDUNDANTE` (informativo).
- Mesma faixa, bytes diferentes → `CONFLITO`: camadas envolvidas, faixa em offset de arquivo e
  em LBA, campo do perfil se houver ("weapons[182].attack"). A camada posterior vence, mas a
  exportação exige que o usuário reconheça o conflito.
- Camada que toca a faixa da tabela de armas sem ser `changeset` → aviso de integridade.
- Gráfico × campo na mesma faixa do executável e gráfico × gráfico sobrepostos → `CONFLITO`
  (no detector único).
- Duas imagens com a mesma posição de paleta na VRAM (`clut_pos`) e uma delas recolorida →
  aviso "paleta possivelmente compartilhada no jogo" (não é conflito de bytes).

## 6. ChangeSet — operações com undo/redo

- Cada edição é uma operação: `{id, alvo: "weapons[182].attack", antes, depois, origem: manual|regras|IA, finding, data}`.
- Pilhas de undo e redo (Ctrl+Z / Ctrl+Y), histórico visível, operações agrupáveis
  (uma frase do assistente = um grupo desfeito de uma vez).
- Persistido no arquivo de projeto.

## 7. Arquivo de projeto

`<nome>.vh2proj.json` na pasta escolhida pelo usuário (pode ser partição compartilhada
Windows/Linux). Guarda: caminho e hash da imagem base, perfil, camadas (ordem, ativa, arquivo, hash),
changesets e configurações de saída. Caminhos relativos à pasta do projeto quando possível.

## 8. Validation e Export

Exportar gera: BIN nova + BPS contra a original + CUE + **relatório** (`.md` e `.json`) com:
data, versão da ferramenta, perfil e resultado das âncoras, hash da imagem original, camadas
(tipo, arquivo, hash, ativa), operações (antes/depois/origem/estado do finding),
faixas afetadas (arquivo e LBA), conflitos reconhecidos, hashes de saída.
Conferências que já existem e devem continuar: reler a BIN nova e comparar; aplicar o BPS no
original e comparar; original intocado.

## 9. Visualização em hexa

Para qualquer operação ou registro: `OFFSET (arquivo) | LBA | RAM | ORIGINAL (hex) | NOVO (hex) | CAMPO`,
e o registro de 22 bytes com as fronteiras dos campos marcadas. Para gráficos: cabeçalho do TIM,
bloco de paleta e bloco de pixels marcados, e só as faixas alteradas listadas.
Não é um editor hexa completo.

## 10. Modo Pesquisa (depois do núcleo)

Unifica "Modo Pesquisa" e "modo Descoberta":
- Selecionar um registro mostra bytes crus (registro e vizinhos) com os campos interpretados por cima.
- Marcar bytes → criar finding `HIPOTESE`.
- **Perfilador de colunas:** para cada posição do registro, estatísticas nos 214 registros
  (mín/máx, distintos, monotonia dentro do grupo, múltiplos de 10).
- **Gabarito:** importar CSV preenchido pelo usuário (`id,atributo,valor,fonte`), por exemplo
  máximo de técnicas, duas mãos, elemento, ataques conhecidos. O casador procura posições onde
  os valores batem em ≥ N% dos registros e propõe finding `PROVAVEL` com evidência `statistical_match`.
  Não incluir no repositório texto de guias; só o CSV do usuário.
- Gerar BIN de teste alterando **um** campo, para confirmar no emulador e promover a `CONFIRMADO` (`in_game_test`).
- Gráficos: a lista de TIMs encontrados alimenta findings `G-xxxx`; um botão "recolorir para
  teste" (por exemplo, trocar a paleta inteira por magenta) gera uma BIN de teste para
  identificar no emulador qual sprite é aquele.
- Se a procura não achar TIMs dos personagens, registrar finding `DESCONHECIDO` para
  "sprites de personagem" com a evidência "sem TIM solto": é o sinal para a fase Ghidra
  (descompressor). Não tentar adivinhar formatos comprimidos.

## 11. Próxima tabela: habilidades e magias (depois das armas)

No VH2, as magias são técnicas aprendidas pelas armas (as dos cajados/varas). Ficam na mesma
tabela de habilidades do `SLUS_009.40`. Dados do LVCP Engine (Gate 02):

- Tabela: offset **0x15D4C**, registros de **18 bytes**, **203** registros, termina em 0x16B92,
  `table_sha256` = `cfd77b35c2bc07e0d8e48bd791f5c7bf2affa58870c583b1af06242aff90186b`.
  Significado dos campos: **desconhecido** (o LVCP marca `UNMAPPED`).
- Nomes: o LVCP achou duas sequências de ponteiros, 0x15A1C (143) e 0x15C5C (60).
  Observação nossa, a verificar: 0x15A1C até 0x15D4C são exatamente **204** ponteiros
  (0x330 / 4), imediatamente antes da tabela, o mesmo padrão das armas (ponteiros em 0x800,
  tabela em 0xB5C) e das armaduras (ponteiros em 0x16D2C, tabela em 0x16FA4). A quebra em
  143 + 60 provavelmente é uma entrada que aponta para fora da faixa de textos.
  **204 ponteiros × 203 registros não fecham**: descobrir se a tabela tem 204 registros, se o
  primeiro ponteiro é deslocado, ou se há uma entrada vazia. Não assumir; testar as hipóteses
  e registrar a evidência.
- Âncora candidata (a confirmar, não usar como verdade): o LVCP associa o nome "Balloonbomb" ao
  índice 182 da lista de habilidades. Um guia independente de 2000 diz que a Balloonbomb é a
  técnica da Nail Bat (arma 0xB8), **não** da arma 0xB6; ou seja, o índice da habilidade não é
  o índice da arma que a ensina. Qual arma ensina qual habilidade é uma descoberta separada.

Perfil (acrescentar em `tables`):

```json
"skills": {
  "file": "SLUS_009.40", "offset": "0x15D4C", "stride": 18, "count": 203,
  "names": {"pointer_table": "0x15A1C", "status": "HIPOTESE"},
  "integrity_sha256": "cfd77b35c2bc07e0d8e48bd791f5c7bf2affa58870c583b1af06242aff90186b",
  "fields": {}
}
```

Findings iniciais:

| Finding | Assunto | Estado |
|---|---|---|
| S-0001 | geometria da tabela de habilidades (0x15D4C, 18, 203) | PROVAVEL (hash do LVCP; contagem a confirmar) |
| S-0002 | nomes via ponteiros em 0x15A1C | HIPOTESE (204 × 203 em aberto) |
| S-0003 | vínculo arma → habilidade | DESCONHECIDO (índice compartilhado refutado por fonte independente) |
| S-0010… | cada posição do registro de 18 bytes | DESCONHECIDO |

O que construir (reaproveitando tudo das armas, sem código específico duplicado):
- Generalizar a tabela de armas para **qualquer tabela do perfil** (armas, habilidades e,
  depois, armaduras: 0x16FA4, 26 bytes, 158 registros, nomes em 0x16D2C, hash
  `f51ae2dc8ebfeb70f31f01b0ddd17bad22ba5fe2359c0a405d9093d5d3e61fc2`).
  Aba "Tabelas" com seletor, em vez de uma aba por tabela.
- Importar nomes das habilidades com a hipótese de ponteiros e mostrar amostras para o
  usuário conferir antes de gravar (como a âncora Rebelrod nas armas).
- Modo Pesquisa aplicado às habilidades: perfilador de colunas nos 203 registros e gabarito
  CSV do usuário (ex.: `nome,custo,poder,alcance,area,elemento,fonte`).
- Enquanto um campo estiver DESCONHECIDO/HIPOTESE, a edição só existe no Modo Pesquisa, como
  byte cru, com BIN de teste para conferir no emulador (por exemplo: mudar um byte candidato
  a "custo" e ver o menu).
- Texto (nomes e descrições): edição com o **mesmo tamanho ou menor** (preencher com NUL).
  Texto maior exige realocação e ajuste de ponteiros: deixar para a fase de tradução,
  documentado como limite.
- Efeitos visuais: texturas de efeitos entram pela camada `graphics` se forem TIM. A animação
  do efeito (roteiro, tempo, partículas) é formato próprio: **fora do escopo**; registrar como
  DESCONHECIDO para a fase Ghidra/PCSX-Redux.

Testes (sintéticos): SLUS artificial com tabela de 18 bytes e matriz de 204 ponteiros com uma
entrada fora da faixa; verificar que a importação de nomes mostra a divergência 204 × 203 e
não grava sem confirmação; edição de texto maior que o original é recusada; perfilador acha
uma coluna plantada (ex.: múltiplos de 5 crescentes); tabela genérica funciona para armas e
habilidades com o mesmo código.

## 12. Interface do Inverse Engine (depois do marco 4)

Framework: **PySide6** (não trocar). Duas telas, com troca por `QStackedWidget`:

### MainMenuState (tela inicial)
- Botões: **Iniciar projeto** (assistente: escolher imagem + perfil), **Abrir imagem**
  (`.bin`, `.cue`, `.iso`; o `.cue` resolve a `.bin`), **Criar cheats**, **Modelos 3D**,
  **Áudio e texturas**, **Opções**, **Sair**.
- Painel lateral: projetos recentes (nome, perfil, data, resultado das âncoras) e estatísticas
  do último projeto (tabelas mapeadas, findings por estado, pendências).
- **Temas**: `simples` (padrão, alto contraste) e `fantasia` (arte de fundo). Regras para os
  dois: contraste mínimo WCAG AA em todo texto (no tema fantasia, painel sólido atrás dos
  botões), navegação completa por teclado (Tab/Enter/Esc, atalhos visíveis), nomes acessíveis
  (`setAccessibleName`) em todos os controles, tamanho de fonte ajustável.
- Arte de fundo: **só arte original** (própria ou gerada por IA). Nunca imagens extraídas de
  jogos. A arte é um arquivo configurável em `themes/`, não embutido no código.

### EditorWorkspaceState (workspace com painéis)
Painéis com `QDockWidget` (mover, fechar, restaurar layout; salvar layout por projeto):
- **Arquivos do CD** (esquerda): árvore com todos os arquivos (subpastas), tipo detectado
  por conteúdo (TIM, TMD, VAB, PS-EXE, STR/XA Form 2, desconhecido), não pela extensão.
- **Área central com abas**: Tabelas (armas/habilidades/…), Gráficos, Modelos 3D, Áudio,
  Dados do jogo, Cheats, Memory Card, Pesquisa.
- **Inspetor** (direita): propriedades do item selecionado + **visualização em hexa** (seção 9).
- **Camadas e conflitos** (painel próprio): a pilha da seção 4 com ativar/desativar e a lista
  de conflitos da seção 5.
- **Histórico**: operações com desfazer/refazer (seção 6).
- **Console** (embaixo): log do núcleo + **Terminal equivalente** (comando Linux de cada ação).
- **Scripts**: console de scripts (ver abaixo).

### Módulos novos (todos começam SÓ LEITURA; edição só depois, com testes)

| Módulo | Formato | Primeira entrega | Depois |
|---|---|---|---|
| Modelos 3D | TMD (Sony, id 0x41) | visualizador `QOpenGLWidget`: vértices, faces, UV, textura TIM associada quando a posição de VRAM bater | exportar OBJ; edição de vértices sem mudar contagem |
| Áudio | VAB (VH `pBAV` + VB) | listar programas/amostras, decodificar SPU-ADPCM para WAV, forma de onda, tocar, exportar | reimportar amostra com o mesmo tamanho (codificador ADPCM) |
| Memory card | `.mcr`/`.mcd` 128 KiB (15 blocos + diretório, checksum XOR por quadro) | listar saves, ícone, exportar/importar save, hexa | edição de campos de save quando houver perfil para isso |
| Cheats | GameShark (`80XXXXXX YYYY` 16 bits, `30XXXXXX 00YY` 8 bits, `D0…` condicional) | gerar códigos a partir de campos do perfil (RAM conhecida) e exportar para DuckStation/`.cht` | busca de valores na RAM via PCSX-Redux |

Observações:
- O VH2 usa **sprites** nos personagens; o visualizador 3D pode não achar TMD nele. Isso não é
  erro: o módulo é genérico. Mapas de batalha provavelmente são formato próprio (DESCONHECIDO).
- XA/STR (Form 2) só são listados; decodificação fica para depois.
- **Cheats como ferramenta de pesquisa**: a tabela de armas fica na RAM (`record_ram` no perfil).
  Um código `80…` permite testar uma hipótese de campo no emulador em segundos, sem gerar BIN.
  O resultado do teste vira evidência `in_game_test` no finding. O cheat nunca substitui o
  patch final.

### Console de scripts
- Linguagem inicial: **Python** (sem dependência nova). Lua pode vir depois como plugin opcional.
- Scripts usam **só a API do núcleo** (`project.table("weapons")[182].set("attack", 30)`,
  `project.find_tims()`, …). Toda escrita vira **operação no ChangeSet**, com a mesma validação,
  conflitos e desfazer. Nenhuma API de script grava bytes direto, nem mesmo no Modo Pesquisa
  (lá, a operação é do tipo `raw`, ainda registrada e reversível).
- Execução com tempo limite e em thread separada; saída no console.

### Handlers e estados
- `AppState` com `MainMenuState` e `EditorWorkspaceState`; abrir imagem ou projeto →
  avaliar âncoras de todos os perfis → escolher perfil (ou "nenhum": só formatos genéricos) →
  workspace.
- Sem perfil, o Inverse Engine ainda funciona para qualquer jogo PS1: arquivos, TIM, TMD,
  VAB, memory card, hexa. Tabelas e assistente só aparecem com perfil.

## 13. Automação de ponta a ponta

### Análise automática ao abrir
Ao abrir uma imagem, uma fila de tarefas em segundo plano (com barra de progresso, cancelável,
retomável) roda sem perguntar nada:
1. listar arquivos e detectar tipos pelo conteúdo;
2. avaliar âncoras de todos os perfis e escolher o perfil (portão P4 só se nenhum servir ou se
   houver empate);
3. importar nomes das tabelas cujas âncoras passaram;
4. procurar TIM, TMD, VAB em todos os arquivos (Form 2 ignorado);
5. rodar o perfilador de colunas em todas as tabelas do perfil;
6. se houver gabaritos na pasta do projeto, rodar o casamento e gerar findings `PROVAVEL`
   com evidência `statistical_match`;
7. gerar um **relatório "O que o app encontrou"**: âncoras, tabelas, imagens por tipo,
   findings novos, próximos testes sugeridos.
Resultados ficam em cache por hash de arquivo: reabrir o mesmo projeto é instantâneo.

### Planos de rebalanceamento em lote
- Aceitar um **arquivo de plano** (JSON/CSV) com regras, por exemplo "machados: ataque −10%",
  "arma 0xB6: ataque 30", "tier 3: preço ×1,5". O `arsenal-tier-plan.json` do LVCP deve poder
  ser convertido para esse formato.
- O app gera o ChangeSet inteiro sozinho, valida tudo e mostra **uma** tela de revisão (P1).
- Frases do assistente geram o mesmo tipo de plano.

### Testes no emulador automatizados (PCSX-Redux)
O usuário faz **uma vez** alguns savestates de referência (tela de loja, início de batalha,
menu de magias) e os registra no projeto. A partir daí, sem intervenção:
1. para cada hipótese de campo, o app gera uma BIN de teste (ou cheat `80…`) alterando só
   aquele campo;
2. inicia o PCSX-Redux com a BIN e o savestate, via linha de comando + script Lua e/ou a API
   do servidor web do PCSX-Redux;
3. avança N quadros, lê a região de RAM da tabela, **tira um print** e registra quais
   instruções leram o endereço (breakpoint de leitura);
4. confere automaticamente se o valor novo está na RAM e anexa print + endereços das
   instruções como evidência `in_game_test`/`emulator_breakpoint`;
5. o usuário vê o print lado a lado com o original e confirma com um clique (P3).
Se o PCSX-Redux não estiver instalado ou a automação falhar, o app gera a BIN de teste e as
instruções, e o fluxo segue manual para aquele teste.

### Rotina de projeto
Salvamento automático do projeto, backup rotativo de perfis/findings, relatório gerado a cada
exportação, detecção de ferramentas (Ollama, PCSX-Redux, DuckStation, Ghidra) com o comando
de instalação no Terminal equivalente.

## 14. Assistente com contexto do projeto (sem treino de modelo)

A IA é especializada no jogo **pelo contexto**, não por treino. A cada pergunta, o núcleo monta
o contexto automaticamente:
- resumo do perfil (tabelas, campos e **estado de cada finding**);
- findings relevantes à pergunta (busca por palavras-chave/BM25 com biblioteca padrão;
  embeddings pelo Ollama, ex. `nomic-embed-text`, como opção);
- só os itens da tabela citada, não o banco inteiro;
- limite de tokens configurável; enviar `num_ctx` explícito ao Ollama (o padrão do Ollama é
  pequeno e cortaria o contexto em silêncio).

Três modos:
- **Editar**: como hoje (JSON validado por schema), mas o schema só aceita campos cuja política
  permita edição naquele modo.
- **Perguntar**: respostas só de leitura ("o que sabemos do byte 0x05 das habilidades?"),
  **citando os IDs dos findings** usados. Sem finding no contexto, a resposta é "desconhecido";
  o prompt de sistema proíbe inventar offsets e o app remove da resposta qualquer offset que
  não esteja no contexto (checagem simples por expressão regular).
- **Pesquisar**: recebe as estatísticas do perfilador e propõe hipóteses e o próximo teste
  automático; a proposta vira finding `HIPOTESE`, nunca mais que isso.

Escolha de modelo automática: listar os modelos do Ollama e sugerir o maior que caiba na VRAM
detectada (RX 580: 8 GB → até ~8B em Q4); editável nas opções.
Testes: servidor Ollama simulado (`http.server` local numa thread) verificando que o
contexto inclui os findings certos, respeita o limite e que offsets inventados são removidos.

## 15. Pesquisa de código automatizada (Ghidra + PCSX-Redux)

Depois do marco 10. Tudo em modo lote, sem abrir o Ghidra na mão:
- Detectar Ghidra (12.0+) e o loader `ghidra_psx_ldr`; se faltarem, mostrar como instalar.
- Rodar o **Ghidra em modo headless** (`analyzeHeadless`, scripts via PyGhidra) sobre o
  executável extraído, criando um projeto Ghidra na pasta do projeto.
- **Gerar tipos a partir do perfil**: cada tabela vira um `struct` (C header) com os campos
  conhecidos e `byte_0x..` para os desconhecidos; o script aplica os tipos e rótulos nos
  endereços RAM das tabelas.
- Listar automaticamente as **referências** (quem lê cada tabela/campo) e decompilar essas
  funções; guardar o pseudo-C na pasta de pesquisa.
- O assistente (modo Pesquisar) explica cada função e propõe hipóteses (ex.: "esta função usa o
  byte 0x0A no cálculo de dano"). Evidência `analysis_note`: sozinha nunca passa de `HIPOTESE`;
  combinada com `emulator_breakpoint` na mesma instrução, pode chegar a `PROVAVEL`.
- Patches de código (tipo Take Turns) entram como camada `code_patch` (bytes de instruções
  MIPS com endereço e descrição), com as mesmas regras de conflito. Rascunho da IA sempre
  marcado como não testado até passar no teste automático do emulador.

## 16. Exportação aberta (preparação para um remake em Godot, sem compromisso agora)

Um comando **Exportar pacote de dados** grava, na pasta local do usuário (nunca no repositório):
- tabelas em JSON e CSV, com o estado de cada campo (finding);
- gráficos em PNG + JSON com paletas, dimensões e posições de VRAM;
- áudio em WAV + JSON com metadados do VAB;
- modelos em OBJ + JSON;
- `manifest.json` com hashes da imagem de origem, perfil e versão da ferramenta.
Formatos neutros, sem nada específico de Godot. Um remake futuro leria esse pacote gerado a
partir da cópia do próprio jogador (o mesmo modelo de projetos como o OpenMW). Nenhum pacote
exportado é distribuído pelo projeto.

---

## Ordem de entrega (cada marco com testes passando e um commit)

1. ~~RomImage + RomProfile + findings~~ **pronto**.
2. ~~EDC/ECC + PPF + BPS + PatchStack + conflitos (incluindo a camada `graphics`, TIM e PNG)~~ **pronto**.
   Aceite: EDC/ECC conforme 0.4 (com a conferência cruzada ou o aviso de pulado); PPF 1/2/3 aplicado em BIN
   sintética; PPF + changeset no mesmo setor **sem conflito falso**; conflito real detectado com camadas, faixas
   (arquivo e LBA) e campo (`weapons[182].attack`); gráfico e arma saem na mesma BIN; desativar camada e gerar de
   novo reproduz a saída esperada; EDC/ECC só recalculado no fim e só nos setores tocados; setor original com
   EDC/ECC inválido recusado; gráfico em subpasta exportado corretamente; `fixture_cd.py` passa a gravar EDC/ECC.
3. ~~ChangeSet com undo/redo + arquivo de projeto~~ **pronto** (`<nome>.vh2proj.json`). O ChangeSet guarda operações
   `{id, alvo, antes, depois, origem: manual|regras|IA|script, finding, data, grupo}` e gera as camadas do
   `PatchStack`; camadas PPF/BPS guardam caminho relativo + SHA-256 do arquivo de patch. Aceite: desfazer/refazer
   grupos; projeto salvo e reaberto idêntico; caminhos relativos à pasta do projeto; patch com hash diferente do
   registrado é recusado ao reabrir (P4).
4. ~~Validation + Export + relatório + hexa~~ **pronto**. Feito em `core/export.py` uma função
   `export(projeto, overwrite=False)` que usa `project.stack().build(acknowledged=set(project.acknowledged))`,
   grava em `project.output["folder"]` (relativa à pasta do projeto) a BIN nova, o BPS contra a original, o CUE
   (use `replace_ext`/`with_ext`, nunca `with_suffix`) e o relatório; e `core/hexview.py` com as linhas da
   seção 9 (use `PatchStack.writes`, `locate`, `field_label` e `PsExe.file_to_ram`). Portão P2: a exportação
   só acontece chamada explicitamente. Acrescente `projeto exportar PROJ` e `hexa PROJ ALVO` no CLI. Aceite: BIN nova + BPS + CUE + relatório `.md`/`.json`; relatório
   JSON reproduz a saída (mesmo hash) a partir do original + camadas; reler a BIN nova e comparar; aplicar o BPS no
   original e comparar; original intocado; sobrescrita exige confirmação.
5. ~~Casca do Inverse Engine~~ **pronto** (seção 12), PySide6: MainMenuState + EditorWorkspaceState com os painéis, usando
   só o núcleo (`Project`, `ChangeSet`, `PatchStack.conflicts`, `export`, `hexview`, `tim`, `RomImage`,
   `match_profiles`). Toda operação longa (abrir imagem, procurar TIMs, exportar) roda em `QThread` com
   progresso e cancelamento. Portões: P1 = tela de revisão antes de operações entrarem no ChangeSet em lote;
   P2 = tela de revisão (camadas, operações, conflitos, faixas) antes de `export`; P3 = promover finding;
   P4 = diálogo que lista conflitos/hashes/âncoras e grava em `projeto.acknowledged`. Deve oferecer tudo o que a v1.1 oferecia: Projeto, Tabelas (armas), Pendentes, Assistente,
   Gráficos, Patch, Emulador (abrir a BIN gerada no DuckStation/PCSX-Redux, se instalados), Sistema (ferramentas
   detectadas). Aceite: temas simples e fantasia passam na checagem de contraste WCAG AA (teste automático
   calculando a razão de contraste das cores do tema); navegação completa por teclado; `setAccessibleName` em todos
   os controles (teste percorre os widgets); nenhum botão sem ação (teste percorre os botões); abre com
   `QT_QPA_PLATFORM=offscreen` no CI.
6. ~~Modo Pesquisa~~ **pronto** (seção 10). Aceite: perfilador acha uma coluna plantada; gabarito CSV sintético gera finding
   `PROVAVEL` com `statistical_match`; BIN de teste com **um** campo alterado; recolorir para teste gera BIN.
7. ~~Tabelas genéricas + habilidades/magias~~ **pronto** (seção 11), com armaduras. A tabela genérica já existe
   (`TableSpec`, aba Tabelas com seletor, perfilador e gabarito funcionam para qualquer tabela do perfil). Falta:
   importação de nomes com a hipótese de ponteiros mostrando amostras e a divergência 204 × 203 antes de gravar
   (nada gravado sem confirmação); edição de texto do mesmo tamanho ou menor (NUL) com recusa do maior; edição de
   byte cru das habilidades pela aba Tabelas no Modo Pesquisa (hoje só pela aba Pesquisa → BIN de teste);
   armaduras (0x16FA4, 26 bytes, 158 registros, nomes em 0x16D2C, hash f51ae2dc…) no perfil com os findings
   iniciais (geometria PROVAVEL pelo hash do LVCP; campos DESCONHECIDO). Use `make_slus(size=...)` maior para
   caber as tabelas de habilidades e armaduras nos testes. Aceite: armas continuam passando em
   todos os testes com o código genérico; habilidades aparecem com campos DESCONHECIDOS, editáveis só como byte
   cru no Modo Pesquisa; divergência 204 × 203 exibida e nada gravado sem confirmação; texto maior que o original
   recusado; nada promovido sem evidência.
8. ~~Cheats + memory card~~ **pronto**. Cheats: `research/cheats.py` gera códigos GameShark (`80XXXXXX YYYY` 16 bits,
   `30XXXXXX 00YY` 8 bits, `D0…` condicional) a partir de um campo do perfil, usando o endereço de RAM do
   registro. O endereço vem de `record_ram` na tabela do perfil **só quando houver evidência** (finding
   CONFIRMADO/PROVAVEL, ex.: `emulator_breakpoint`); sem isso, o gerador recusa. Enquanto não houver essa
   evidência, `PsExe.file_to_ram` dá o endereço onde o executável é carregado, que só vale se a tabela não for
   copiada para outro lugar em tempo de execução — registre isso como HIPOTESE, não como verdade. Exportar para
   DuckStation (`.cht`) e texto simples. Memory card: `formats/memcard.py` (ver 0.4). Botão "Criar cheats" e
   aba "Memory Card" no workspace (ative o botão do menu). Aceite: código gerado a partir de um campo do perfil bate com o endereço RAM
   esperado (`record_ram` no perfil, só quando houver evidência; senão o gerador recusa); memory card sintético
   listado, exportado e reimportado com checksum correto.
9. **Áudio VAB** (só leitura). `formats/vab.py`: VH ("pBAV", programas, tons, tamanhos das amostras) + VB
   (SPU-ADPCM, ver 0.4); `formats/wav.py` com `wave` da biblioteca padrão (PCM 16 bits); procurar VAB em todos os
   arquivos (e VH/VB separados quando o VB vier em outro arquivo: registrar como HIPOTESE); aba "Áudio" com lista
   de programas/amostras, forma de onda (QPainter), tocar (QtMultimedia é opcional: sem ele, só exportar WAV) e
   exportar; ative o botão "Áudio e texturas" do menu. Aceite: VAB sintético decodificado para WAV igual ao esperado.
10. **Modelos TMD** (só leitura). Aceite: TMD sintético com contagem certa de vértices/faces.
11. **Automação** (seção 13). Aceite: com imagem sintética, abrir o projeto gera o relatório "O que o app
    encontrou" sem nenhum clique; um plano de 20 regras vira um ChangeSet revisado em uma tela (P1); a automação
    do emulador é testada com executor simulado (PCSX-Redux real opcional).
12. **Assistente com contexto** (seção 14). Pode ser antecipado para logo depois do marco 3.
13. **Pesquisa de código automatizada** (seção 15). Aceite: header C gerado do perfil compila como tipo válido
    (se houver compilador; senão pulado com aviso); script headless roda num executável sintético ou é pulado com
    aviso claro se o Ghidra não estiver instalado.
14. **Exportação aberta** (seção 16). Aceite: pacote exportado recria as tabelas e PNGs idênticos.

Ao terminar cada marco: rode `python -m unittest discover -s tests -t .`, atualize a tabela "Estado" do README
e o CHANGELOG, faça commit com mensagem em português descrevendo o marco e envie para `main`.

## Testes

- Manter todos os testes existentes (adaptar chamadas, nunca remover verificações).
- Cada módulo novo com testes próprios usando **fixtures sintéticas** (BIN Mode 2 Form 1 gerada em tempo de
  teste com `tests/fixture_cd.py`, SLUS artificial com `make_slus`, PPF gerado por `build_ppf3`, TIM/PNG/VAB/TMD/
  memory card artificiais).
- Casos obrigatórios: âncora falhando; tabela alterada por PPF; conflito falso de EDC/ECC evitado; conflito real;
  setor original com EDC/ECC inválido recusado; sobrescrita exige confirmação; original intocado; PNG com cor
  fora da paleta, tamanho diferente ou entrelaçado recusado; recolorir não altera pixels; preto opaco recebe o
  bit STP (0x8000); arquivo Form 2 ignorado na procura; gráfico em subpasta exportado corretamente; nome com
  pontos gera saída correta (`with_ext`).
- Testes de interface com `QT_QPA_PLATFORM=offscreen`; se PySide6 não estiver instalado, esses testes são
  pulados com `unittest.skipUnless` (o núcleo nunca depende dele).
- CI no GitHub Actions já existe (`.github/workflows/tests.yml`): mantenha verde em 3.10 e 3.12.

## Não fazer

- Não recomeçar o repositório, não trocar a stack (PySide6 na interface, biblioteca padrão no núcleo).
- Não alterar `legado/` nem importar dele.
- Não acrescentar abas antes do marco 4.
- Não deixar a tela inicial ou o workspace avançarem antes do núcleo (marcos 3–4).
- Não dar ao console de scripts acesso direto a bytes nem ao sistema de arquivos fora do projeto.
- Não embutir arte, sons ou modelos de jogos no repositório (inclusive em temas e testes).
- Não pedir confirmação fora dos portões P1–P4, e nunca pular um portão em nome da automação.
- Não treinar nem ajustar modelos de IA: a especialização vem do contexto (seção 14).
- Não dar nomes a campos de habilidades ("custo", "poder") sem evidência registrada; até lá eles são `byte_0x05` etc.
- Não usar bibliotecas externas no núcleo (só na GUI: PySide6).
- Não remover o modo terminal (`python -m inverse_engine.cli`), que serve para diagnóstico.
- Não promover findings sem evidência nova registrada. F-0002 (nomes em 0x800) só vira CONFIRMADO depois que a
  âncora Rebelrod passar na BIN real do usuário e ele confirmar (P3).
- Não colocar no repositório ROM, BIOS, patches de terceiros (ex.: Take Turns) ou texto de guias.
  O `.gitignore` já bloqueia `*.bin`, `*.cue`, `*.iso`, `*.ppf`, `*.bps`, `*.mcr`, `*.mcd`, `SLUS_*`.
- Não usar `Path.with_suffix` para montar nomes de saída; usar `with_ext`.
- Não mudar tamanho de TIM, não realocar VRAM e não adicionar dependências de imagem (Pillow etc.) no núcleo.
- Não inventar offsets, endereços de RAM, nomes de arquivo do jogo real nem valores: o que não tem evidência
  fica `DESCONHECIDO`. Em exemplos e testes, use só dados sintéticos.

## Interface e textos

Português do Brasil, frases diretas. Manter o painel "Terminal equivalente": o usuário está aprendendo Linux e
cada ação mostra o comando correspondente.
