# CHANGELOG

## 0.11.1 — AppImage abre a janela em qualquer Linux
- O AppImage 0.11.0 não trazia as bibliotecas libxcb-* (icccm, keysyms, shape, xkb, cursor) e
  libxkbcommon-x11: em sistemas sem elas o Qt não abria a janela. Agora vêm dentro do AppImage
- Release testa a interface de verdade: AppImage sob Xvfb e InverseEngine.exe no Windows, com foto
  da tela (`tela-windows.png`, publicada junto na Release como prévia)

## 0.11.0 — Executáveis para download
- `.github/workflows/release.yml`: tag `v*` monta AppImage (Linux, Ubuntu 22.04) e `.exe` (Windows:
  interface + modo terminal) com PyInstaller e publica na página de Releases; teste rápido de cada um
- `python -m inverse_engine` (e o executável): sem argumentos ou com projeto abre a interface; com
  comando roda o modo terminal
- `core/resources.py`: no executável, perfis e findings vão para a pasta de dados do usuário
  (copiados só se faltarem); fora dele, nada muda
- `packaging/`: build.py, appimage.sh, AppRun, .desktop, ícone
- CI roda os testes também no Windows; testes leem/gravam texto sempre em UTF-8

## Pesquisa anterior do usuário registrada (Exodus e endereços de RAM)
- Perfil: `record_ram` das armas (0x8006C35C, F-0003) e das habilidades (0x8008154C, S-0004), PROVAVEL:
  observação anterior na RAM + conta pelo cabeçalho do executável (t_addr 0x8006C000); cheats das armas
  deixam de ser experimentais nos campos com evidência
- Findings: S-0005 (Exodus = registro 0x90, HIPOTESE), G-0001 (TIMs candidatos 103/106/113/117/131 de
  VH2DATA.BIN, HIPOTESE); evidência nova em S-0001 e F-0014 (tabela de armas ≠ Exodus)
- `research/testbin.mark_pixels` / `mark_test`: marca visual xadrez 8×8 num TIM (mesmo tamanho, BPP,
  paleta e VRAM) em BIN de teste; botão na aba Pesquisa; CLI `teste-marca`
- CLI `tims` numera os TIMs por arquivo (#k) para casar com catálogos anteriores pelo offset
- `docs/PESQUISA-EXODUS.md`: o que está estabelecido, a cadeia que falta provar e o método

## Marco 10 — modelos TMD (só leitura)
- `formats/tmd.py`: cabeçalho 0x41 (ponteiros relativos ou FIXP), objetos, vértices, normais, primitivas;
  8 layouts de polígono com luz decodificados (triângulo/quadrilátero, plano/Gouraud, com/sem textura);
  sem luz ou índice fora do intervalo → contado como "layout desconhecido", nunca inventado;
  UV, CBA e TSB; `find_texture` associa o TIM pela página de textura e pela posição da paleta na VRAM;
  exportação OBJ (quad → 2 triângulos na ordem do PS1)
- Aba Modelos 3D com visualizador em arame (QPainter: mouse/setas giram, roda/+/- dão zoom), sem
  depender de OpenGL; botão "Modelos 3D" do menu ativado (todos os botões do menu ativos)
- CLI `tmd [--exportar ARQUIVO OFFSET saida.obj]`
- Layouts escritos a partir da documentação; ainda não conferidos com um TMD real

## Correção com a BIN real — nomes das armas
- Diagnóstico na BIN real (SHA-256 2ee08a8f…48f1): os ponteiros em 0x800 são endereços de RAM
  (t_addr 0x8006C000) e apontam para textos "prefixo|Nome|resto" (arma 182 → "I?200?017|Rebelrod|C1…").
  O leitor lia o texto inteiro, achava bytes fora do ASCII depois do nome e devolvia None: a âncora
  Rebelrod falhava e o perfil não se aplicava.
- Perfil: `names.separator = "|"`, `names.field = 1` nas armas; `TableSpec.string_offset`, `name_at`
- Troca de nome dentro de texto com campos: mesmo tamanho (NUL cortaria o resto do texto); no Modo
  Pesquisa o menor é completado com espaços e marcado experimental; o separador é recusado no nome
- F-0002 com a evidência da BIN real (continua PROVAVEL até a confirmação P3); F-0020 (prefixo
  "I?NNN?NNN" e campos depois do nome) DESCONHECIDO
- Fixture `make_slus` gera o mesmo formato "prefixo|Nome|resto"; CLI `nomes` mostra o texto bruto

## Marco 9 — áudio VAB (só leitura)
- `formats/adpcm.py`: SPU-ADPCM (shift, 5 filtros, saturação em 16 bits, flags de fim/laço)
- `formats/vab.py`: VH "pBAV" (programas, tons com nota central e ADSR, tabela de tamanhos), VB junto ou
  em outro arquivo (`attach_vb`), procura em todos os arquivos (Form 2 ignorado)
- `formats/wav.py`: WAV PCM 16 bits com o módulo `wave`
- Aba Áudio: bancos, amostras, forma de onda, tocar (se houver QtMultimedia), exportar WAV;
  botão "Áudio e texturas" do menu ativado
- CLI `vab [--exportar ARQUIVO OFFSET PASTA]`

## Marco 8 — cheats e memory card
- `research/cheats.py`: códigos GameShark (80 16 bits, 30 8 bits, D0 condicional; 16 bits em endereço
  ímpar vira dois 30) a partir de um campo do perfil; endereço de RAM de `record_ram` só com finding
  PROVAVEL/CONFIRMADO; no Modo Pesquisa aceita o endereço de carga do executável como experimental;
  exporta .cht (DuckStation) e texto
- `formats/memcard.py`: cartão de 128 KiB, diretório com checksum XOR, saves encadeados, título
  Shift-JIS, ícone PNG, exportar/importar .mcs (blocos não contíguos), cartão vazio
- Abas Cheats e Memory Card; botão "Criar cheats" do menu ativado; cartão original nunca sobrescrito
- CLI `cheat`, `memcard`; erros do CLI sem traceback (código de saída 2)

## Marco 7 — tabelas genéricas, habilidades e armaduras
- Perfil: armaduras (0x16FA4, 26 bytes, 158 registros, nomes em 0x16D2C, hash do LVCP) e hash de
  integridade por tabela; findings A-0001 (geometria PROVAVEL), A-0002 (nomes HIPOTESE) e um
  DESCONHECIDO por byte do registro
- `research/names.py`: análise da matriz de ponteiros (quantidade entre a matriz e a tabela,
  sequências válidas, entradas inválidas, divergência, amostras por hipótese de alinhamento);
  `confirm_shift` só grava com confirmação + evidência; `encode_name` recusa texto maior
- `TableSpec`: `names_shift`, `name_slot`, `integrity`
- ChangeSet `set_name` (nomes em HIPOTESE só no Modo Pesquisa); relatório mostra antes/depois do texto
- Aba Tabelas: nome editável, bytes sem campo como colunas de byte cru no Modo Pesquisa, botão Nomes…
- CLI `nomes [--gravar-shift N --evidencia ... --confirmo]`, `projeto nome`

## Marco 6 — Modo Pesquisa
- `research/profiler.py`: estatísticas de cada posição (u8 e u16le): mín/máx, distintos, zeros,
  múltiplos de 10 e 5, crescimento dentro dos grupos, notas
- `research/gabarito.py`: CSV `id,atributo,valor,fonte` (id numérico ou nome), casamento por posição
  e tipo com limite configurável; proposta vira PROVAVEL com `statistical_match` (coluna constante só
  HIPOTESE; nunca CONFIRMADO)
- `research/testbin.py`: BIN de teste com um único campo (base + patches, sem os changesets) em
  `testes/`, recolorir TIM em magenta, findings G-xxxx dos TIMs e DESCONHECIDO "sem TIM solto"
- FindingsDB: `add_finding`, `next_id`, `find`
- Aba Pesquisa (só com o Modo Pesquisa ligado) e diálogo P3 (CONFIRMADO exige confirmação do usuário)
- CLI `perfilar`, `gabarito [--registrar]`, `teste-campo`

## Marco 5 — interface PySide6
- AppState com MainMenuState e EditorWorkspaceState (QStackedWidget); `python3 -m inverse_engine.ui.app`
- Menu inicial: iniciar projeto, abrir imagem (mostra âncoras), abrir projeto, opções (tema e fonte),
  recentes com estatísticas; cheats/3D/áudio desativados com o marco em que chegam
- Workspace com QDockWidget: arquivos do CD (tipo pelo conteúdo), inspetor em hexa, camadas e
  conflitos (ativar, ordenar, adicionar PPF/BPS, reconhecer P4), histórico (Ctrl+Z/Ctrl+Y),
  console com log e Terminal equivalente; layout salvo por projeto
- Abas: Tabelas (edição respeita a política de findings; Modo Pesquisa), Gráficos (TIMs, prévia,
  exportar PNG, importar desenho/cores), Exportar (revisão P2, emulador), Sistema (ferramentas)
- Temas simples e fantasia com checagem automática de contraste WCAG AA; arte de fundo é arquivo
  do usuário (não vem no repositório); tarefas longas em QThread

## Marco 4 — exportação, relatório e hexa
- `core/export.py`: BIN nova + BPS contra a original + CUE + relatório .md/.json (âncoras, camadas com
  hash, operações com estado do finding, faixas com arquivo/LBA/RAM/campo, conflitos reconhecidos,
  hashes de saída); conferências antes e depois de gravar; sobrescrita só com confirmação;
  `reproduce()` remonta a saída pelo relatório e compara o SHA-256
- `core/hexview.py`: linhas OFFSET | LBA | RAM | ORIGINAL | NOVO | CAMPO, registro com fronteiras
  dos campos (bytes sem campo como byte_0xNN), blocos do TIM e só as faixas alteradas
- CLI `projeto hexa|reconhecer|exportar`, `registro`, `reproduzir`

## Marco 3 — ChangeSet e projeto
- ChangeSet: operações {alvo, antes, depois, origem, finding, data, grupo}; grupos desfeitos/refeitos
  de uma vez; erro no meio de um grupo não deixa operação pela metade; gera camadas do PatchStack
  com só o último valor de cada alvo
- Projeto `<nome>.vh2proj.json`: imagem base e patches por caminho relativo + SHA-256 (mudou → P4),
  ordem e ativação das camadas, changesets com histórico e refazer, conflitos reconhecidos, saída;
  gravação atômica; salvo e reaberto idêntico
- CLI `projeto novo|patch|campo|desfazer|refazer|mostrar`

## Marco 2 — camadas e formatos
- EDC/ECC (Mode 1, Mode 2 Form 1/2) conferido pelas síndromes Reed-Solomon do ECMA-130
- PPF 1/2/3 (bloco de conferência, FILE_ID.DIZ, undo) e `build_ppf3`
- BPS: criação e aplicação com CRC32
- TIM/PNG sem Pillow: procura, exportação, reimportação de desenho e de cores (mesmo tamanho)
- PatchStack: camadas ppf, bps_import, changeset, graphics e raw; conflitos (CONFLITO, REDUNDANTE,
  INTEGRIDADE, PALETA_COMPARTILHADA) só em dados de usuário; EDC/ECC conferido no original e
  recalculado uma vez, no fim, só nos setores tocados; política de edição por finding aplicada
- `with_ext` para nomes com pontos; CLI `tims` e `ppf`

## Marco 1 — imagem e perfil
- RomImage (BIN, CUE, executável avulso), ISO9660 com subpastas, Form 2 marcado
- RomProfile com âncoras, tabelas genéricas, findings e política de edição
- `legado/` com o VH2-PS1-Studio v3.0-alpha sem alterações
