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

## Estado

Marco 0: estrutura, perfil e findings iniciais. O código da v1.1 do VH2 Studio
(`vh2_rom_editor.py`, `vh2_disc.py`, `vh2_tim.py`, `ppf.py`, `bps_patch.py`,
`vh2_studio.py`, `tests/`) entra a seguir e é migrado para `inverse_engine/`.
