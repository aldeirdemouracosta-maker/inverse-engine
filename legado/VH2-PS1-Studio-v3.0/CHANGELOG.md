# CHANGELOG

## v3.0.0-alpha

- reconstrução do protótipo v2 como projeto Python executável;
- original v2 preservado em `archive_original/`;
- fonte tratada como read-only;
- projeto `.ps1studio.json` com SHA-256, mapeamentos e ChangeSet;
- Undo/Redo real para alterações;
- validação de limites, bytes originais e sobreposição;
- build de cópia de teste sem tocar no original;
- exportação IPS com validação das limitações do formato;
- Hex Viewer e inspector u8/s8/u16/s16/u32;
- scans por valor, wildcard hex e texto;
- Struct Lab schema-driven;
- perfil VH2 separado do core;
- campos herdados não comprovados reclassificados como `LEGACY-HYPOTHESIS`;
- Magic/Habilidade configurável por campos mapeados, sem offsets inventados;
- scanner/decoder TIM e exportação PNG;
- Battle Appearance Preview com direções, giro, frames e GIF;
- tint de preview para experimentação visual;
- scanner de strings Shift-JIS/ASCII;
- preview de falas com retrato;
- substituição de texto somente quando cabe no espaço original;
- Scene Preview integrado ao projeto, sem fingir escrita de mapas VH2;
- manifesto JSON das alterações;
- scripts Linux/Windows e `gerar_aplicativo.py`;
- auditoria automática: 50 botões, 0 sem callback;
- 3 testes de núcleo aprovados.
