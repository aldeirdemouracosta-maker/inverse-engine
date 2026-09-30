"""`python -m inverse_engine` (e o executável): sem argumentos, ou com um projeto, abre a interface;
com um comando (abrir, tabela, …) roda o modo terminal."""
import sys

from inverse_engine.core.project import EXT


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0].endswith(EXT):
        from inverse_engine.ui.app import main as gui
        return gui([sys.argv[0], *args])
    from inverse_engine.cli import main as cli
    return cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
