from pathlib import Path

import psycopg

from app.config import settings


def main() -> None:
    migrations_path = Path(__file__).parent.parent / "db" / "migrations"
    migration_files = sorted(migrations_path.glob("*.sql"))
    if not migration_files:
        raise SystemExit("No migration files found")

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            for migration in migration_files:
                sql = migration.read_text()
                cur.execute(sql)
        conn.commit()


if __name__ == "__main__":
    main()
