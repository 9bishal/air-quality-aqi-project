import sys
from pathlib import Path

# pyrefly: ignore [missing-import]
from sqlalchemy import text


# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database.connection import get_engine


# Analytics SQL file
SQL_FILE = PROJECT_ROOT / "sql/analytics.sql"


def run_analytics():
    print("Starting analytical SQL...")

    # Read the SQL file
    with open(SQL_FILE, "r") as file:
        sql = file.read()

    # Connect to PostgreSQL
    engine = get_engine()

    try:
        # Execute the SQL statements
        with engine.begin() as connection:
            for statement in sql.split(";"):
                if statement.strip():
                    connection.execute(text(statement))

        print("Analytical tables created successfully.")

    except Exception as error:
        print("Failed to create analytical tables.")
        print("Error:", error)


if __name__ == "__main__":
    run_analytics()