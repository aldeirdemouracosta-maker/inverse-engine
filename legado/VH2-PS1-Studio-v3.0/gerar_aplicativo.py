#!/usr/bin/env python3
"""Build local e reproduzível. Não usa sudo e não tenta cross-compile."""
from __future__ import annotations
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VENV=ROOT/'.venv-build'
DIST=ROOT/'dist'
BUILD=ROOT/'build'
APP='VH2-PS1-Studio'


def run(cmd, **kw):
    print('+', ' '.join(map(str,cmd)))
    subprocess.run(list(map(str,cmd)), check=True, **kw)


def main():
    # syntax gate
    pyfiles=[ROOT/'main.py', *sorted((ROOT/'vh2studio').glob('*.py'))]
    for f in pyfiles:
        run([sys.executable,'-m','py_compile',f])
    print(f'PASS_SYNTAX: {len(pyfiles)} arquivo(s)')

    if not VENV.exists():
        print('Criando ambiente de build:',VENV)
        venv.EnvBuilder(with_pip=True).create(VENV)
    py=VENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    run([py,'-m','pip','install','--upgrade','pip'])
    run([py,'-m','pip','install','-r',ROOT/'requirements.txt','pyinstaller>=6'])

    shutil.rmtree(DIST,ignore_errors=True);shutil.rmtree(BUILD,ignore_errors=True)
    sep=';' if os.name=='nt' else ':'
    cmd=[py,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
         '--name',APP,'--add-data',f'{ROOT / "profiles"}{sep}profiles',ROOT/'main.py']
    run(cmd,cwd=ROOT)
    out=DIST/(APP+'.exe' if os.name=='nt' else APP)
    if not out.exists():raise SystemExit('BUILD FAIL: artefato final não encontrado')
    if os.name!='nt':out.chmod(out.stat().st_mode|0o111)
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    sha=out.with_suffix(out.suffix+'.sha256')
    sha.write_text(f'{digest}  {out.name}\n',encoding='utf-8')
    print('\nBUILD PASS')
    print('Sistema:',platform.platform())
    print('Arquivo:',out)
    print('Tamanho:',out.stat().st_size,'bytes')
    print('SHA-256:',digest)
    print('Observação: builds Windows devem ser geradas no Windows; Linux no Linux.')

if __name__=='__main__':main()
