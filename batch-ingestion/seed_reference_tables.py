import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv


load_dotenv()

RAW_DIR = Path("data/raw/kaggle_card_transactions")
CARDS_FILE = RAW_DIR / "sd254_cards.csv"
MERCHANT_REFERENCE_FILE = RAW_DIR / "merchant_reference.csv"


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def connect_to_postgres():
    return psycopg2.connect(
        host=get_required_env("POSTGRES_HOST"),
        port=get_required_env("POSTGRES_PORT"),
        dbname=get_required_env("POSTGRES_DB"),
        user=get_required_env("POSTGRES_USER"),
        password=get_required_env("POSTGRES_PASSWORD"),
    )


def create_reference_tables(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            user_id INTEGER NOT NULL,
            card_index INTEGER NOT NULL,
            PRIMARY KEY (user_id, card_index)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS merchant_reference (
            merchant_name TEXT NOT NULL,
            merchant_city TEXT NOT NULL,
            merchant_state TEXT,
            merchant_zip TEXT,
            mcc TEXT
        )
    """)


def seed_cards_if_empty(cur) -> None:
    cur.execute("SELECT COUNT(*) FROM cards")
    card_count = cur.fetchone()[0]

    if card_count > 0:
        print(f"cards already seeded with {card_count} rows")
        return

    df = pd.read_csv(CARDS_FILE)

    df = df.rename(columns={
        "User": "user_id",
        "CARD INDEX": "card_index",
    })

    df = df[["user_id", "card_index"]].drop_duplicates()

    rows = list(df.itertuples(index=False, name=None))

    cur.executemany(
        """
        INSERT INTO cards (user_id, card_index)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        rows,
    )

    print(f"Seeded {len(rows)} card rows")


def seed_merchant_reference_if_empty(cur) -> None:
    cur.execute("SELECT COUNT(*) FROM merchant_reference")
    merchant_count = cur.fetchone()[0]

    if merchant_count > 0:
        print(f"merchant_reference already seeded with {merchant_count} rows")
        return

    if not MERCHANT_REFERENCE_FILE.exists():
        raise FileNotFoundError(
            "merchant_reference.csv not found. Run your create merchant reference script first."
        )

    df = pd.read_csv(MERCHANT_REFERENCE_FILE, dtype=str)

    df = df.rename(columns={
        "Merchant Name": "merchant_name",
        "Merchant City": "merchant_city",
        "Merchant State": "merchant_state",
        "Zip": "merchant_zip",
        "MCC": "mcc",
    })

    df = df[
        ["merchant_name", "merchant_city", "merchant_state", "merchant_zip", "mcc"]
    ].drop_duplicates()

    rows = list(df.itertuples(index=False, name=None))

    cur.executemany(
        """
        INSERT INTO merchant_reference (
            merchant_name,
            merchant_city,
            merchant_state,
            merchant_zip,
            mcc
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        rows,
    )

    print(f"Seeded {len(rows)} merchant reference rows")


def main() -> None:
    conn = connect_to_postgres()

    try:
        conn.autocommit = False

        with conn.cursor() as cur:
            create_reference_tables(cur)
            seed_cards_if_empty(cur)
            seed_merchant_reference_if_empty(cur)

        conn.commit()
        print("Reference tables seeded successfully")

    except Exception:
        conn.rollback()
        print("Seeding failed. Rolled back changes.")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()