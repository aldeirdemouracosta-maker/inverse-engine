"""Terminal equivalente: o comando Linux de cada ação da interface (o usuário está aprendendo Linux)."""
from __future__ import annotations

import shlex

CLI = "python3 -m inverse_engine.cli"


def q(path) -> str:
    return shlex.quote(str(path))


def abrir(imagem) -> str:
    return f"{CLI} abrir {q(imagem)}"


def hash_arquivo(path) -> str:
    return f"sha256sum {q(path)}"


def tims(imagem) -> str:
    return f"{CLI} tims {q(imagem)}"


def tabela(imagem, tabela_nome: str, index: int | None = None) -> str:
    return f"{CLI} tabela {q(imagem)} {tabela_nome}" + (f" --id {index}" if index is not None else "")


def registro(imagem, tabela_nome: str, index: int) -> str:
    return f"{CLI} registro {q(imagem)} {tabela_nome} {index}"


def projeto_novo(pasta, nome, imagem) -> str:
    return f"{CLI} projeto novo {q(pasta)} {q(nome)} {q(imagem)}"


def projeto(acao: str, proj, *extra) -> str:
    return " ".join([CLI, "projeto", acao, q(proj)] + [q(e) if not isinstance(e, int) else str(e) for e in extra])


def campo(proj, tabela_nome: str, index: int, field: str, value: int) -> str:
    return projeto("campo", proj, tabela_nome, str(index), field, str(value))


def reproduzir(relatorio) -> str:
    return f"{CLI} reproduzir {q(relatorio)}"


def emulador(programa: str, bin_path) -> str:
    return f"{programa} {q(bin_path)}"


INSTALL = {
    "duckstation": "flatpak install flathub org.duckstation.DuckStation",
    "pcsx-redux": "flatpak install flathub io.github.grumpycoders.pcsx-redux",
    "ollama": "curl -fsSL https://ollama.com/install.sh | sh",
    "ghidra": "sudo snap install ghidra",
}
