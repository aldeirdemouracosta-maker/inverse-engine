#!/usr/bin/env bash
# Abre o Inverse Engine (interface). Primeira vez: python3 -m pip install --user -r requirements.txt
cd "$(dirname "$0")" && exec python3 -m inverse_engine.ui.app "$@"
