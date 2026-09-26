# CHANGELOG

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
