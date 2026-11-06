"""Operator-only, local enrollment of 40 independent demo store identities.

Never upload the output directory, or run this as a public API.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from applications.storeguard.cloud_dr.store_identity import (
    StoreIdentityRegistry, generate_private_key, private_key_bytes, public_key_bytes,
)


def enroll_fleet(directory: Path, *, count: int = 40, start: int = 1800) -> list[str]:
    if not 1 <= count <= 1000 or not 1 <= start <= 999999:
        raise ValueError('Invalid fleet dimensions')
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Refusing symlinked identity directory')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    registry_path = directory / 'trusted_stores.sqlite3'
    if registry_path.exists():
        raise FileExistsError('Existing registry: refusing to re-enroll or overwrite')
    # Atomic exclusive creation prevents accidental overwrite; cleanup of partial
    # provisioning is intentionally manual, not destructive.
    fd = os.open(registry_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    registry = StoreIdentityRegistry(registry_path)
    created = []
    try:
        for number in range(start, start + count):
            store_id = str(number)
            key_id = 'key-v1'
            key = generate_private_key()
            secret_path = directory / f'store-{store_id}.ed25519'
            with os.fdopen(os.open(secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
                stream.write(private_key_bytes(key))
            created.append(store_id)
            registry.enroll(store_id, key_id, public_key_bytes(key))
    finally:
        registry.close()
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='.local/storeguard-identity-demo')
    parser.add_argument('--count', type=int, default=40)
    parser.add_argument('--start', type=int, default=1800)
    args = parser.parse_args()
    stores = enroll_fleet(Path(args.directory), count=args.count, start=args.start)
    print(f'Enrolled {len(stores)} local store identities ({stores[0]}..{stores[-1]})')
    print(f'Registry: {Path(args.directory) / "trusted_stores.sqlite3"}')
    print('Private keys remain local. Do not commit, sync, or publish this directory.')


if __name__ == '__main__':
    main()
