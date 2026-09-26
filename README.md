# Inverse Engine

Modificador genérico de jogos de PS1. Linux primeiro (Lubuntu), compatível com Windows.
Núcleo em Python 3.10+ só com biblioteca padrão; interface em PySide6.

O **VH2 Studio** (Vandal Hearts II, SLUS-00940, NTSC-U) é o primeiro perfil de jogo:
`profiles/SLUS-00940-USA.json` + `research/findings/SLUS-00940-USA.json`.

## Arquitetura

```
RomImage → RomProfile → PatchStack → ChangeSet → Validation → Export
```

- `inverse_engine/core` — imagem, perfil, camadas, operações, exportação (sem nada de VH2)
- `inverse_engine/formats` — CD, TIM, TMD, VAB, memory card, PPF, BPS, PNG
- `inverse_engine/research` — findings, perfilador, gabarito, cheats
- `inverse_engine/assistant` — regras + Ollama com contexto do projeto
- `inverse_engine/ui` — PySide6, só apresenta o núcleo
- `profiles/` — perfis de jogo (dados, não código)

## Princípios

1. O arquivo original nunca é alterado. Toda saída é cópia.
2. Nenhum offset é inventado. O que não tem evidência fica `DESCONHECIDO`.
3. A IA nunca escreve bytes: propõe operações, o núcleo valida.
4. Descoberta comprovada e hipótese nunca se misturam.
5. Este repositório **não contém** o jogo, BIOS, patches de terceiros nem texto de guias.

## Interface

```bash
python3 -m pip install --user -r requirements.txt   # PySide6 (só a interface precisa)
./iniciar.sh                                         # Linux  (Windows: iniciar.bat)
```

Atalhos no workspace: Ctrl+Z/Ctrl+Y desfazer/refazer, Ctrl+S salvar, Ctrl+E revisar e exportar,
F5 atualizar, Esc voltar ao menu, Ctrl+Shift+R restaurar layout. Letras sublinhadas = Alt+letra.

## Modo terminal

```bash
python3 -m inverse_engine.cli abrir  "Vandal Hearts II (USA).cue"   # arquivos + âncoras
python3 -m inverse_engine.cli tabela "Vandal Hearts II (USA).cue" weapons --id 182
python3 -m inverse_engine.cli findings
python3 -m inverse_engine.cli tims   "Vandal Hearts II (USA).cue"
python3 -m inverse_engine.cli ppf    "take_turns.ppf" --imagem "Vandal Hearts II (USA).cue"
python3 -m inverse_engine.cli projeto novo ~/vh2 "Rebalance 2026" "Vandal Hearts II (USA).cue"
python3 -m inverse_engine.cli projeto campo ~/vh2/"Rebalance 2026.vh2proj.json" weapons 182 attack 45
python3 -m inverse_engine.cli projeto mostrar ~/vh2/"Rebalance 2026.vh2proj.json"
python3 -m inverse_engine.cli projeto hexa ~/vh2/"Rebalance 2026.vh2proj.json"
python3 -m inverse_engine.cli projeto exportar ~/vh2/"Rebalance 2026.vh2proj.json"
python3 -m inverse_engine.cli reproduzir ~/vh2/saida/"Rebalance 2026.relatorio.json"
python3 -m inverse_engine.cli perfilar "Vandal Hearts II (USA).cue" weapons
python3 -m inverse_engine.cli gabarito "Vandal Hearts II (USA).cue" weapons meu_gabarito.csv
python3 -m inverse_engine.cli teste-campo ~/vh2/"Rebalance 2026.vh2proj.json" weapons 182 0x0C u16le 999
python3 -m inverse_engine.cli nomes "Vandal Hearts II (USA).cue" skills
python3 -m inverse_engine.cli projeto nome ~/vh2/"Rebalance 2026.vh2proj.json" weapons 182 "Rebel"
python3 -m inverse_engine.cli cheat "Vandal Hearts II (USA).cue" weapons 182 attack 45 --pesquisa
python3 -m inverse_engine.cli memcard ~/cartoes/epsxe000.mcr
python3 -m unittest discover -s tests -t .                           # testes (sintéticos)
```

## Estado

| Marco | Situação |
|---|---|
| 1. RomImage + RomProfile + findings | feito: BIN/CUE/executável avulso, ISO9660 com subpastas, Form 2 marcado, offset ↔ LBA ↔ BIN, âncoras, tabelas genéricas, política de edição por estado |
| 2. EDC/ECC + PPF + BPS + TIM/PNG + PatchStack + conflitos | feito: EDC/ECC conferido contra o ECMA-130, PPF 1/2/3, BPS, TIM/PNG sem Pillow, camadas ppf/bps_import/changeset/graphics/raw, conflitos só em dados de usuário, EDC/ECC recalculado no fim |
| 3. ChangeSet com undo/redo + arquivo de projeto | feito: operações com antes/depois/origem/finding, grupos desfeitos de uma vez, `.vh2proj.json` com caminhos relativos, hashes conferidos ao reabrir (P4), salvar/reabrir idêntico |
| 4. Validation + Export + relatório + hexa | feito: BIN + BPS + CUE + relatório .md/.json, conferências (reler BIN, BPS na original, EDC/ECC, original intocado), sobrescrita só com confirmação, relatório reproduz a saída, hexa de escritas/registros/TIM |
| 5. Casca PySide6 (menu inicial + workspace) | feito: menu inicial com recentes e estatísticas, workspace com painéis (arquivos por conteúdo, inspetor hexa, camadas e conflitos, histórico, console + terminal equivalente), abas Tabelas/Gráficos/Exportar/Sistema, portões P2 e P4, temas simples e fantasia (WCAG AA), teclado e nomes acessíveis |
| 6. Modo Pesquisa | feito: perfilador de colunas, gabarito CSV (propostas PROVAVEL com statistical_match, revisadas antes de gravar), marcar hipótese, BIN de teste com um campo, recolorir TIM em magenta, findings G-xxxx, promoção com evidência (P3) |
| 7. Tabelas genéricas + habilidades/magias | feito: armas, habilidades e armaduras com o mesmo código; análise de ponteiros de nomes (204 × 203 exibido, hipóteses de alinhamento, nada gravado sem confirmar); troca de nome do mesmo tamanho ou menor; bytes crus editáveis no Modo Pesquisa |
| 8. Cheats + memory card | feito: GameShark 80/30/D0 a partir de campos do perfil (endereço de RAM só com evidência; sem ela, só experimental no Modo Pesquisa), export .cht/.txt; memory card .mcr: listar, ícone, exportar/importar .mcs com checksums |
| 9. Áudio VAB (só leitura) | próximo |
| 10–14 | pendentes |

`legado/VH2-PS1-Studio-v3.0/` guarda a versão 3.0-alpha (Tkinter) sem alterações, como
referência. O código da v1.1 do VH2 Studio foi perdido; EDC/ECC, PPF, BPS e TIM/PNG foram reescritos
no marco 2, com testes sintéticos novos.
Não existe `items.json` para migrar: os findings iniciais foram registrados direto em
`research/findings/SLUS-00940-USA.json`.
