"""Bundle the host's 64-bit CPython and plot dependencies into a Windows EXE."""
from pathlib import Path
import os
import subprocess
import sys
import zipfile

base = Path(__file__).resolve().parent
python = Path(sys.base_prefix)
runtime = base / 'Runtime.zip'
site = python / 'Lib' / 'site-packages'
packages = {'numpy', 'matplotlib', 'contourpy', 'cycler', 'kiwisolver', 'packaging',
            'PIL', 'pillow', 'pyparsing', 'dateutil', 'python_dateutil', 'six', 'fontTools', 'fonttools'}
ignored = {'__pycache__', 'test', 'tests', 'idlelib', 'ensurepip', 'turtledemo'}

with zipfile.ZipFile(runtime, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
    def add(source, destination, exclude=()):
        if source.is_file():
            archive.write(source, destination)
            return
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            if path.is_file() and not (set(relative.parts) & (ignored | set(exclude))):
                archive.write(path, Path(destination) / relative)

    for path in python.iterdir():
        if path.suffix.lower() in {'.exe', '.dll'} or path.name == 'LICENSE.txt':
            add(path, path.name)
    for name in ('DLLs', 'Lib', 'tcl'):
        add(python / name, name, {'site-packages'})
    for path in site.iterdir():
        if any(path.name == name or path.name.startswith((name + '.', name + '-')) for name in packages):
            add(path, Path('Lib/site-packages') / path.name)
    for name in ('app.py', 'core.py', 'metrology.py', 'metrology_ui.py'):
        add(base / name, name)

out = base / 'dist' / 'ProfileStudio-Metrology.exe'
out.parent.mkdir(exist_ok=True)
compiler = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
                '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
                '/reference:System.Windows.Forms.dll', f'/resource:{runtime},Runtime.zip',
                f'/out:{out}', str(base / 'Launcher.cs')], check=True)
print(out, out.stat().st_size)
