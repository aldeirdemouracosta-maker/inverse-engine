# Pesquisa: magia Exodus (Vandal Hearts II, SLUS-00940)

Objetivo: entender como a Exodus é feita para, depois, criar invocações novas **reaproveitando o
summon handler do jogo** em vez de construir uma magia do zero.

Regra desta pesquisa: **não misturar tabelas.** Endereços da tabela de armas (RAM `0x8006C35C`,
SLUS `+0xB5C`, stride `0x16`, campo `+0x10`) vieram do trabalho com Rebelrod/Silver Knuckles e
**não servem para localizar a Exodus**.

## O que já está estabelecido

| Fato | Estado | Finding |
|---|---|---|
| Tabela de habilidades em SLUS `0x15D4C`, 18 bytes, 203 registros | PROVAVEL (hash do LVCP) | S-0001 |
| A mesma tabela na RAM em `0x8008154C` (= `0x8006C000 + 0x15D4C − 0x800`) | PROVAVEL (observação anterior + conta pelo cabeçalho) | S-0004 |
| 204 ponteiros de nome válidos em `0x15A1C` (textos `\|Nome\|…`); alinhamento com os 203 registros em aberto | HIPOTESE | S-0002 |
| Exodus = registro `0x90` (144): SLUS `0x1676C`, RAM `0x80081F6C` | HIPOTESE (pesquisa anterior) | S-0005 |
| TIMs candidatos em `VH2DATA.BIN` (numeração da ferramenta anterior): 103 aura/partículas, 106 impacto, 113 entidade grande, 117 criatura/animação, 131 portal/fumaça | HIPOTESE | G-0001 |
| Qual campo do registro aponta para gráfico/animação/entidade | DESCONHECIDO | S-0016… |

Cuidado: a numeração 103/113/117 é da ferramenta anterior (224 TIMs). Use `tims` do Inverse Engine
(numera por arquivo: `#k`) e case pelo **offset**, não só pelo número.

## O que falta provar (a cadeia)

```
Exodus → tabela de habilidades → dispatcher de magias → summon handler
       → carga de TIM/modelo → sequência de animação → dano / área
```

Nenhum elo depois da tabela foi provado ainda. O summon handler (rotina MIPS no `SLUS_009.40`) é o
alvo principal.

## Método

### 1. Confirmar o registro e o nome (sem emulador)
```bash
python3 -m inverse_engine.cli nomes "Vandal Hearts II (USA).cue" skills
```
Se o nome "Exodus" cair no registro 0x90 em um dos alinhamentos (shift 0 ou 1), isso confirma S-0005
e decide o alinhamento dos nomes (S-0002).

### 2. Marca visual (identifica o recurso gráfico sem ambiguidade)
Um bloco xadrez 8×8 no TIM candidato; paleta, BPP, tamanho e posição na VRAM não mudam.
```bash
python3 -m inverse_engine.cli tims "Vandal Hearts II (USA).cue" | grep VH2DATA      # achar o offset
python3 -m inverse_engine.cli teste-marca ~/vh2/"Rebalance 2026.vh2proj.json" VH2DATA.BIN 0xOFFSET
```
Abra a BIN de `testes/` no emulador, solte a Exodus: se o xadrez aparecer na criatura/efeito, o TIM é
dela (evidência `in_game_test` no G-0001; CONFIRMADO só com o portão P3). Melhor que recolorir a
paleta, que afeta todo sprite que a compartilha.

### 3. PCSX-Redux (rastrear o que a magia carrega)
1. save-state imediatamente antes da Exodus;
2. VRAM Viewer + GPU Logger abertos;
3. soltar a magia;
4. capturar os primitives enviados à GPU;
5. anotar `TPAGE`, `U/V`, `CLUT` e a origem do DMA;
6. casar a região da VRAM com os TIMs de `VH2DATA.BIN` (o Inverse Engine já calcula página de textura e
   posição da paleta: `formats/tmd.texture_page`, `clut_position`, `find_texture`);
7. seguir o endereço de origem do DMA até a rotina no `SLUS_009.40` (breakpoint de leitura no registro
   `0x80081F6C` também leva ao dispatcher).

O marco 11 (automação do emulador) e o marco 13 (Ghidra) automatizam esses passos.

### 4. Ghidra (marco 13)
Aplicar o `struct` de 18 bytes das habilidades em `0x8008154C`, listar quem lê o registro 0x90 e
decompilar: dispatcher → summon handler.

## Estrutura-alvo: invocação reaproveitável

Se o summon handler da Exodus for localizado, uma invocação nova seria uma variação dos parâmetros
dele, não código novo:

```
EXODUS
 ├── summon ID
 ├── graphics ID
 ├── animation/script ID
 ├── palette/CLUT
 ├── sound ID
 ├── camera sequence
 ├── effect pattern
 ├── damage formula
 └── target/area parameters
```

Cada item vira um finding (DESCONHECIDO → HIPOTESE → PROVAVEL → CONFIRMADO) conforme for provado. Os
sons podem vir dos 33 bancos VAB já achados em `SD_BULK.BIN` (aba Áudio).

## Limites desta fase

- Texto, TIM e registros só mudam **no mesmo tamanho** (sem realocar).
- Roteiro de animação, câmera e partículas são formato próprio do jogo: fora do escopo até o Ghidra.
- Código novo (patch MIPS) entra como camada `code_patch` no marco 13, sempre testado no emulador antes.
