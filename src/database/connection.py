import os
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
from urllib.parse import quote_plus


# Load environment variables from .env
load_dotenv()


def get_engine():
    # Read PostgreSQL settings from .env
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    # Encode special characters such as @ in the password
    encoded_password = quote_plus(password)

    # Build PostgreSQL connection URL
    database_url = (
        f"postgresql+psycopg2://{user}:{encoded_password}"
        f"@{host}:{port}/{database}"
    )

    # Create SQLAlchemy engine
    return create_engine(database_url)


if __name__ == "__main__":
    try:
        # Test PostgreSQL connection
        engine = get_engine()

        with engine.connect():
            print("PostgreSQL connection successful!")

    except Exception as error:
        print("Database connection failed.")
        print("Error:", error)