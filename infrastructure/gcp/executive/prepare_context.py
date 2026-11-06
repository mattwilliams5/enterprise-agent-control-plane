"""Create a new, minimal and inspectable container build context.

Run from repository root. Refuses to overwrite a previous context.
"""
from pathlib import Path
import shutil

source = Path.cwd()
destination = source / '.local' / 'storeguard-executive-build'
if destination.exists():
    raise SystemExit(f'Refusing to overwrite: {destination}')
files = [
    'ui/storeguard/app.py',
    'ui/storeguard/cloud_overview.py',
    'ui/storeguard/cloud_control_client.py',
    'ui/storeguard/cloud_live_dr.py',
    'ui/storeguard/cloud_tornado.py',
    'ui/storeguard/cloud_data.py',
    'infrastructure/gcp/executive/requirements-cloud.txt',
]
for name in files:
    if not (source / name).is_file():
        raise SystemExit(f'Missing required file: {name}')
for name in files:
    out = destination / name
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / name, out)
for name in ['ui/__init__.py', 'ui/storeguard/__init__.py']:
    out = destination / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('')
shutil.copy2(source / 'infrastructure/gcp/executive/Dockerfile', destination / 'Dockerfile')
(destination / '.dockerignore').write_text('**/.git\n**/.local\n**/__pycache__\n**/*.sqlite3\n**/*.db\n**/*.key\n**/*.pem\n**/*secret*\n')
print('Restricted executive context:', destination)
for p in sorted(destination.rglob('*')):
    if p.is_file(): print(p.relative_to(destination))
