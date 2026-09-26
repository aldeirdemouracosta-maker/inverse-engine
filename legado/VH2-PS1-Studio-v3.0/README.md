# PS1 Archaeology Studio — Vandal Hearts II Profile v3.0-alpha

Aplicativo desktop em Python/Tkinter para investigação e modificação **segura** de binários de PS1, com perfil inicial para Vandal Hearts II.

## Princípio da versão

Esta versão não adiciona botões decorativos. Operações que ainda não possuem um formato VH2 comprovado não são apresentadas como gravação real na ROM. O programa trabalha com:

- arquivo-fonte somente leitura;
- SHA-256;
- scans de valores, bytes/wildcards e texto;
- Hex Viewer + inspector de inteiros;
- mapeamentos de structs com estado de evidência;
- editor genérico de registros para Item/Magia/Habilidade;
- ChangeSet com Undo/Redo, validação e detecção de sobreposição;
- cópia de teste separada do original;
- patch IPS quando os offsets são compatíveis com o formato;
- scanner/decoder TIM real (4/8/16/24 bpp nos formatos suportados);
- preview de aparência com direções, animação e exportação GIF;
- scanner de texto Shift-JIS/ASCII, preview de diálogo e substituição segura de mesmo tamanho;
- retrato importável para preview;
- Scene Preview local integrado ao projeto, claramente marcado como preview até existir schema de mapa VH2 comprovado.

## Por que Item/Magia usa mapeamentos

O perfil `profiles/vh2.json` separa conhecimento comprovado de hipóteses. O campo de ataque em `+0x0A` está marcado como `PROVEN`; campos herdados da v2 são `LEGACY-HYPOTHESIS` até validação. Para magias, use **Definir campo** e informe offsets/tipos descobertos durante a engenharia reversa. Isso evita inventar offsets.

## Linux

```bash
chmod +x instalar.sh iniciar.sh
./instalar.sh
./iniciar.sh
```

Se Pillow já estiver instalado, também pode iniciar diretamente:

```bash
python3 main.py
```

## Windows

Execute:

```text
instalar.bat
iniciar.bat
```

ou:

```text
py main.py
```

com Pillow instalado.

## Gerar executável

Linux:

```bash
python3 gerar_aplicativo.py
```

Windows:

```text
py gerar_aplicativo.py
```

O script cria `.venv-build`, instala apenas as dependências de build e gera:

- Linux: `dist/VH2-PS1-Studio`
- Windows: `dist/VH2-PS1-Studio.exe`

Não existe cross-build disfarçado: Windows deve gerar a build Windows e Linux deve gerar a build Linux.

## Atalhos

- `Ctrl+O`: abrir fonte
- `Ctrl+S`: salvar projeto
- `Ctrl+Z`: Undo do ChangeSet
- `Ctrl+Y`: Redo
- `F5`: atualizar interface

## Estado dos módulos

| Módulo | Estado nesta versão |
|---|---|
| Projeto / SHA-256 | funcional |
| Hex Viewer / Inspector | funcional |
| Scan valor/hex/texto | funcional |
| Struct Lab | funcional e user-mapped |
| Item Lab | funcional com evidência explícita |
| Magic Lab | funcional via campos mapeados pelo usuário/evidência |
| TIM scanner/preview | funcional |
| Battle Appearance Preview | funcional para assets TIM/PNG mapeados/importados |
| Giro por direções | funcional |
| GIF preview/export | funcional |
| Falas / Shift-JIS / ASCII | funcional |
| Face/retrato preview | funcional |
| Substituição de texto no ChangeSet | funcional quando cabe no espaço original |
| Scene Preview | funcional como preview de projeto; escrita de mapa VH2 bloqueada até schema comprovado |
| ChangeSet / Undo / Redo | funcional |
| Build de cópia de teste | funcional |
| IPS | funcional dentro das limitações do IPS |
| Persuasion / Deployment / nova lógica de batalha | **não exposto como botão falso**; requer descoberta/injeção de código real |
| MIPS decompiler / PCSX live control | **não incluído nesta build**; não há botão sem backend |

## Preservação

A pasta `archive_original/` contém o HTML original da v2 e o código Python extraído, sem alterações.
