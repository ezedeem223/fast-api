"""
Postgres backup helper using pg_dump.

Usage:
    python scripts/db_backup.py --out backups/db_backup.sql.gz

Environment:
    DATABASE_URL or DATABASE_HOSTNAME/PORT/USERNAME/PASSWORD/NAME
Requires:
    pg_dump on PATH.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus


def resolve_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("DATABASE_HOSTNAME", "localhost")
    port = os.getenv("DATABASE_PORT", "5432")
    user = os.getenv("DATABASE_USERNAME") or os.getenv("POSTGRES_USER")
    password = os.getenv("DATABASE_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    name = os.getenv("DATABASE_NAME") or os.getenv("POSTGRES_DB")
    if not (user and password and name):
        raise SystemExit("Missing database credentials; set DATABASE_URL or username/password/name envs.")
    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"


def main():
    parser = argparse.ArgumentParser(description="Backup Postgres database with pg_dump")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("backups") / f"db_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sql.gz",
        help="Output file path (.sql or .sql.gz). Default: backups/db_backup_<timestamp>.sql.gz",
    )
    args = parser.parse_args()

    db_url = resolve_db_url()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["pg_dump", db_url]
    use_gzip = str(args.out).endswith(".gz")
    try:
        with open(args.out, "wb") as fh:
            proc_env = os.environ.copy()
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=proc_env)
            if use_gzip:
                import gzip

                with gzip.open(fh, "wb") as gz:
                    if proc.stdout:
                        gz.writelines(proc.stdout)
            else:
                if proc.stdout:
                    fh.writelines(proc.stdout)
            ret = proc.wait()
            if ret != 0:
                raise SystemExit(f"pg_dump exited with code {ret}")
    except FileNotFoundError:
        raise SystemExit("pg_dump not found on PATH. Install PostgreSQL client tools.")

    print(f"Backup written to {args.out}")


if __name__ == "__main__":
    main()
