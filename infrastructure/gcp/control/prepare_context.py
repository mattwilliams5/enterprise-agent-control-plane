"""Build a minimal context: only simulation API, not agent or Vault code."""
from pathlib import Path
import shutil
root = Path.cwd()
target = root / '.local' / 'storeguard-control-build'
if target.exists():
    raise SystemExit(f'Refusing to overwrite: {target}')
files = [
    'applications/storeguard/cloud_control/__init__.py',
    'applications/storeguard/cloud_control/core.py',
    'applications/storeguard/cloud_control/api.py',
    'infrastructure/gcp/control/requirements.txt',
]
for name in files:
    p = root / name
    if not p.is_file():
        raise SystemExit(f'Missing: {p}')
    out = target / name
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, out)
for name in ('applications/__init__.py','applications/storeguard/__init__.py'):
    p = target / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
shutil.copy2(root / 'infrastructure/gcp/control/Dockerfile', target / 'Dockerfile')
shutil.copy2(root / 'infrastructure/gcp/control/requirements.txt', target / 'requirements.txt')
(target / '.dockerignore').write_text('**/.git\n**/.local\n**/*secret*\n**/*.key\n**/*.pem\n')
print('Restricted control context:', target)
for p in sorted(target.rglob('*')):
    if p.is_file(): print(p.relative_to(target))
