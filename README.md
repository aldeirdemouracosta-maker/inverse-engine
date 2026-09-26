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

## Modo terminal

```bash
python3 -m inverse_engine.cli abrir  "Vandal Hearts II (USA).cue"   # arquivos + âncoras
python3 -m inverse_engine.cli tabela "Vandal Hearts II (USA).cue" weapons --id 182
python3 -m inverse_engine.cli findings
python3 -m unittest discover -s tests -t .                           # testes (sintéticos)
```

## Estado

| Marco | Situação |
|---|---|
| 1. RomImage + RomProfile + findings | feito: BIN/CUE/executável avulso, ISO9660 com subpastas, Form 2 marcado, offset ↔ LBA ↔ BIN, âncoras, tabelas genéricas, política de edição por estado |
| 2. PatchStack + conflitos + EDC/ECC | próximo |
| 3–14 | pendentes |

`legado/VH2-PS1-Studio-v3.0/` guarda a versão 3.0-alpha (Tkinter) sem alterações, como
referência. O código da v1.1 do VH2 Studio (EDC/ECC, PPF, BPS, TIM sem Pillow) foi perdido;
essas partes são reescritas nos marcos seguintes, com testes sintéticos novos.
Não existe `items.json` para migrar: os findings iniciais foram registrados direto em
`research/findings/SLUS-00940-USA.json`.
