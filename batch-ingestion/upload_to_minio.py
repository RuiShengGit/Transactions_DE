import boto3
import re
import pandas as pd
from pathlib import Path
from datetime import datetime
import os

import tempfile
from dotenv import load_dotenv



# -----------------------------
# Load secrets from .env
# -----------------------------
load_dotenv()


RAW_DIR = Path("data/raw/kaggle_card_transactions")

TRANSACTIONS_FILE = RAW_DIR / "credit_card_transactions-ibm_v2.csv"
CARDS_FILE = RAW_DIR / "sd254_cards.csv"
USERS_FILE = RAW_DIR / "sd254_users.csv"

CHUNK_SIZE = 5000000
INGESTION_DATE = datetime.now().strftime("%Y-%m-%d")

MINIO_BUCKET = os.getenv("MINIO_BUCKET")

# MinIO client
s3 = boto3.client(
    's3',
    endpoint_url=os.getenv("MINIO_ENDPOINT"),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY")
)

# Create bucket if not exists
def create_bucket_if_not_exists() -> None:
    existing_buckets = [bucket["Name"] for bucket in s3.list_buckets()["Buckets"]]

    if MINIO_BUCKET not in existing_buckets:
        s3.create_bucket(Bucket=MINIO_BUCKET)
        print(f"Created bucket: {MINIO_BUCKET}")
    else:
        print(f"Bucket already exists: {MINIO_BUCKET}")


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = [
        re.sub(r"_+", "_", re.sub(r"[^a-zA-Z0-9]+", "_", col.strip().lower())).strip("_")
        for col in df.columns
    ]

    return df


def upload_small_files(file_path: Path, table_name: str) -> None:
    df = pd.read_csv(file_path)
    df = clean_column_names(df)
    df["ingestion_date"] = INGESTION_DATE

    s3_key = (
        f"historical/{table_name}/"
        f"ingestion_date={INGESTION_DATE}/"
        f"{table_name}.parquet"
    )

    upload_parquet(df, s3_key)


def upload_parquet(df: pd.DataFrame, s3_key: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        local_parquet_path = tmp.name

    df.to_parquet(local_parquet_path, engine="pyarrow", index=False)

    s3.upload_file(local_parquet_path, MINIO_BUCKET, s3_key)
    os.remove(local_parquet_path)

    print(f"Uploaded {len(df):,} rows to s3://{MINIO_BUCKET}/{s3_key}")

def upload_large_file_in_chunks(file_path: Path, table_name: str) -> None:
    partition_number = {}

    for chunk in pd.read_csv(file_path, chunksize=CHUNK_SIZE, encoding="utf-8"):
        chunk = clean_column_names(chunk)
        chunk["ingestion_date"] = INGESTION_DATE

        if "year" not in chunk.columns:
            raise ValueError("Expected a 'year' column in the transactions file.")

        for year, year_df in chunk.groupby("year"):
            year = int(year)

            if year not in partition_number:
                partition_number[year] = 1

            s3_key = (
                f"historical/transactions/"
                f"year={year}/"
                f"ingestion_date={INGESTION_DATE}/"
                f"transactions_part_{partition_number[year]:06d}.parquet"
            )

            upload_parquet(year_df, s3_key)

            partition_number[year] += 1


def main() -> None:
    create_bucket_if_not_exists()
    upload_small_files(CARDS_FILE, "cards")
    upload_small_files(USERS_FILE, "users")
    upload_large_file_in_chunks(TRANSACTIONS_FILE, "transactions")




if __name__ == "__main__":
    main()