#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
printf '\nInstalação concluída. Inicie com: ./iniciar.sh\n'
