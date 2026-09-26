# CHANGELOG

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
