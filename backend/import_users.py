"""Copy teams, roles and user accounts (same IDs and password hashes) from the WiaNews database.

Run from the repository root: backend/.venv/bin/python -m backend.import_users [--source PATH]
Accounts are upserted by ID, so running it again brings over later WiaNews changes. Sessions are not copied.
"""
import argparse
import sqlite3
from pathlib import Path

from .auth import SCHEMA
from .config import PROJECT_ROOT, database_path
from .database import Database

DEFAULT_SOURCE = PROJECT_ROOT.parent / 'wianews/backend/app.db'
TABLES = [('teams', 'team_id'), ('roles', 'role_id'), ('users', 'user_id')]  # Parents before users.


def import_users(source, target):
    source = sqlite3.connect(f'file:{Path(source).resolve()}?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    database = Database(target)
    database.initialize()
    counts = {}
    with database.connect() as db:
        db.executescript(SCHEMA)
        db.execute('PRAGMA foreign_keys=ON')
        for table, key in TABLES:
            columns = [row[1] for row in db.execute(f'PRAGMA table_info({table})')]
            rows = source.execute(f'SELECT {", ".join(columns)} FROM {table}').fetchall()
            updates = ', '.join(f'{column}=excluded.{column}' for column in columns if column != key)
            db.executemany(f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({", ".join("?" * len(columns))}) '
                           f'ON CONFLICT({key}) DO UPDATE SET {updates}', [tuple(row) for row in rows])
            counts[table] = len(rows)
    source.close()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', default=DEFAULT_SOURCE, type=Path)
    parser.add_argument('--target', default=database_path(), type=Path)
    args = parser.parse_args()
    counts = import_users(args.source, args.target)
    print(', '.join(f'{table} {count}' for table, count in counts.items()) + f' -> {args.target}')


if __name__ == '__main__':
    main()
