"""Safely back up the former SQLite database into app.db; never overwrite it."""
import argparse
from contextlib import closing
import os
import sqlite3
import tempfile
from pathlib import Path


def migrate(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(f'{target} already exists; refusing to overwrite')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.app-migration-', suffix='.db', dir=target.parent)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as old:
            with closing(sqlite3.connect(temporary)) as new:
                old.backup(new)
                if new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Database integrity check failed')
                original = old.execute('SELECT * FROM workspaces ORDER BY token_hash').fetchall()
                copied = new.execute('SELECT * FROM workspaces ORDER BY token_hash').fetchall()
                if original != copied:
                    raise RuntimeError('Database contents changed during migration; stop the old server first')
        # Same-directory hard link is atomic and fails if another process created the target.
        os.link(temporary, target)
        return len(copied)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == '__main__':
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=folder / 'data/wiacoding.sqlite')
    parser.add_argument('--target', type=Path, default=folder / 'app.db')
    args = parser.parse_args()
    print(f'Migrated {migrate(args.source, args.target)} workspaces to {args.target}. Original retained.')
