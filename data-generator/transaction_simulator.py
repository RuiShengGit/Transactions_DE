import time
import yaml
import psycopg2
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from pathlib import Path
from faker import Faker
import random
import argparse
import pandas as pd
import sys
import os
import hashlib
from psycopg2.extras import execute_values
from dotenv import load_dotenv


DEFAULT_LOOP = True
load_dotenv()

# -----------------------------
# CLI override
# -----------------------------
parser = argparse.ArgumentParser(description="Run fake transaction data generator")
parser.add_argument("--once", action="store_true", help="Run a single iteration and exit")
args = parser.parse_args()

LOOP = not args.once and DEFAULT_LOOP

# -----------------------------
# Helpers
# -----------------------------
fake = Faker()

def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value

def load_generator_config():
    config = load_config()
    generator_config = config["generator"]
    return generator_config


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as file:
        return yaml.safe_load(file)


def calculate_fraud_probability() -> float:
    file_path = "data/raw/kaggle_card_transactions/credit_card_transactions-ibm_v2.csv"

    fraud_yes = 0
    total_rows = 0

    for chunk in pd.read_csv(file_path, usecols=["Is Fraud?"], chunksize=500_000):
        fraud_col = chunk["Is Fraud?"].fillna("No")
        fraud_yes += (fraud_col == "Yes").sum()
        total_rows += len(chunk)

    fraud_rate = fraud_yes / total_rows
    return fraud_rate

def calculate_error_probability() -> tuple[float, dict[str, float]]:
    file_path = "data/raw/kaggle_card_transactions/credit_card_transactions-ibm_v2.csv"

    error_counts = {}
    total_rows = 0
    error_rows = 0

    for chunk in pd.read_csv(file_path, usecols=["Errors?"], chunksize=500_000):
        error_col = chunk["Errors?"]

        total_rows += len(error_col)
        error_rows += error_col.notna().sum()

        value_counts = error_col.dropna().value_counts()

        for error_type, count in value_counts.items():
            error_counts[error_type] = error_counts.get(error_type, 0) + count

    error_probability = error_rows / total_rows

    error_type_distribution = {
        error_type: count / error_rows
        for error_type, count in error_counts.items()
    }

    return error_probability, error_type_distribution


def calculate_chip_usage_probability() -> dict[str, float]:
    file_path = "data/raw/kaggle_card_transactions/credit_card_transactions-ibm_v2.csv"

    counts = {}
    total_rows = 0

    for chunk in pd.read_csv(file_path, usecols=["Use Chip"], chunksize=500_000):
        value_counts = chunk["Use Chip"].value_counts(dropna=False)

        for value, count in value_counts.items():
            counts[value] = counts.get(value, 0) + count

        total_rows += len(chunk)

    return {
        value: count / total_rows
        for value, count in counts.items()
    }
    

# -----------------------------
# Connect to Postgres
# -----------------------------
conn = psycopg2.connect(
    host=get_required_env("POSTGRES_HOST"),
    port=get_required_env("POSTGRES_PORT"),
    dbname=get_required_env("POSTGRES_DB"),
    user=get_required_env("POSTGRES_USER"),
    password=get_required_env("POSTGRES_PASSWORD"),
)

conn.autocommit = False
cur = conn.cursor()


# -----------------------------
# Create transactions table if it doesn't exist
# -----------------------------
def create_tables_if_not_exists():
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

            user_id INTEGER NOT NULL,
            card_index INTEGER NOT NULL,

            transaction_year INTEGER NOT NULL,
            transaction_month INTEGER NOT NULL,
            transaction_day INTEGER NOT NULL,
            transaction_time TIME NOT NULL,

            amount NUMERIC(12, 2) NOT NULL,
            use_chip TEXT NOT NULL,

            merchant_name TEXT NOT NULL,
            merchant_city TEXT NOT NULL,
            merchant_state TEXT,
            merchant_zip TEXT,
            mcc TEXT,

            errors TEXT,
            is_fraud TEXT NOT NULL,

            source_type TEXT NOT NULL DEFAULT 'streaming_generator',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


# -----------------------------
# Fetch existing users, chip options and merchant data from Postgres
# -----------------------------
def get_user_card_pairs():
    cur.execute(
        """
        SELECT user_id, card_index
        FROM cards
        ORDER BY user_id, card_index
        """
    )

    return cur.fetchall()


def get_merchant_reference():
    cur.execute(
        """
        SELECT merchant_name, merchant_city, merchant_state, merchant_zip, mcc
        FROM merchant_reference
        ORDER BY merchant_name, merchant_city
        """
    )

    return cur.fetchall()


def generate_use_chip(chip_distribution: dict[str, float]) -> str:
    return random.choices(
        list(chip_distribution.keys()),
        weights=list(chip_distribution.values()),
        k=1
    )[0]

def generate_error(error_probability, error_type_distribution) -> str | None:
    if random.random() >= error_probability:
        return None

    error_types = list(error_type_distribution.keys())
    error_weights = list(error_type_distribution.values())

    return random.choices(
        error_types,
        weights=error_weights,
        k=1
    )[0]


# -----------------------------
# Core simulation logic
# -----------------------------

def run_iterations(generator_config, historical_stats) -> int:
    inserted_count = 0

    NORMAL_MIN_AMOUNT = Decimal(str(generator_config["normal_min_amount"]))
    NORMAL_MAX_AMOUNT = Decimal(str(generator_config["normal_max_amount"]))
   

    fraud_probability = historical_stats["fraud_probability"]
    error_probability = historical_stats["error_probability"]
    error_type_distribution = historical_stats["error_type_distribution"]
    chip_distribution = historical_stats["chip_distribution"]
        
    
    user_card_pairs = get_user_card_pairs()
    merchant_reference = get_merchant_reference()

    if not user_card_pairs:
        raise RuntimeError("No user-card pairs found. Seed the cards table first.")

    if not merchant_reference:
        raise RuntimeError("No merchant reference data found. Seed merchant_reference first.")

    # Simulate a transaction
    for _ in range(generator_config["transactions_per_batch"]):
        user, card_index = random.choice(user_card_pairs)

        amount = Decimal(random.uniform(float(NORMAL_MIN_AMOUNT), float(NORMAL_MAX_AMOUNT))).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        errors = generate_error(error_probability, error_type_distribution)
        is_fraud = "Yes" if random.random() < fraud_probability else "No"
        use_chip = generate_use_chip(chip_distribution)

        merchant = random.choice(merchant_reference)
        now = datetime.now()
        year = now.year
        month = now.month
        day = now.day
        time = now.time()

        cur.execute(
            """
            INSERT INTO transactions (
                user_id,
                card_index,
                transaction_year,
                transaction_month,
                transaction_day,
                transaction_time,
                amount,
                use_chip,
                merchant_name,
                merchant_city,
                merchant_state,
                merchant_zip,
                mcc,
                errors,
                is_fraud
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user,
                card_index,
                year,
                month,
                day,
                time,
                amount,
                use_chip,
                merchant[0],
                merchant[1],
                merchant[2],
                merchant[3],
                merchant[4],
                errors,
                is_fraud,
            ),
        )

        inserted_count += 1

    print(
        f"✅ Generated {inserted_count} transactions "
        f"using {len(user_card_pairs)} card pairs and {len(merchant_reference)} merchants."
    )

    return inserted_count
# -----------------------------
# Main loop
# -----------------------------



def main() -> None:
    try:

        print("Calculating historical probabilities from Kaggle data. This may take a while...")
        error_probability, error_type_distribution = calculate_error_probability()

        historical_stats = {
            "fraud_probability": calculate_fraud_probability(),
            "error_probability": error_probability,
            "error_type_distribution": error_type_distribution,
            "chip_distribution": calculate_chip_usage_probability(),
        }

        print("Historical probabilities loaded.")
        print(f"Fraud probability: {historical_stats['fraud_probability']:.4%}")
        print(f"Error probability: {historical_stats['error_probability']:.4%}")
        print(f"Chip distribution: {historical_stats['chip_distribution']}")

        generator_config = load_generator_config()
        SLEEP_SECONDS = generator_config["sleep_seconds"]
        
        create_tables_if_not_exists()
        
        conn.commit()

        iteration = 0

        while True:
            iteration += 1
            print(f"\n--- Iteration {iteration} started ---")

            try:
                inserted_count = run_iterations(generator_config, historical_stats)
                conn.commit()
                print(f"--- Iteration {iteration} finished. Committed {inserted_count} transactions. ---")

            except Exception as e:
                conn.rollback()
                print(f"Iteration {iteration} failed. Rolled back changes.")
                print(f"Error: {e}")

            if not LOOP:
                break

            time.sleep(SLEEP_SECONDS)

    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting gracefully...")

    finally:
        cur.close()
        conn.close()



if __name__ == "__main__":
    main()