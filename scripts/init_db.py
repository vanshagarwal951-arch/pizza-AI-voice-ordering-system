#!/usr/bin/env python3
"""Initialize Postgres tables. Run after docker compose up."""

from menu_engine import init_db
from menu_engine.db.models import create_db_engine, get_database_url


def main() -> None:
    url = get_database_url()
    print(f"Initializing database: {url.split('@')[-1]}")
    engine = create_db_engine(url)
    init_db(engine)
    print("Tables created successfully.")


if __name__ == "__main__":
    main()
