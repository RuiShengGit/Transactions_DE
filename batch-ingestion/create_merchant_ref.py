import pandas as pd
from pathlib import Path

RAW_DIR = Path("data/raw/kaggle_card_transactions")
TRANSACTIONS_FILE = RAW_DIR / "credit_card_transactions-ibm_v2.csv"
MERCHANT_REFERENCE_FILE = RAW_DIR / "merchant_reference.csv"

merchant_cols = [
    "Merchant Name",
    "Merchant City",
    "Merchant State",
    "Zip",
    "MCC",
]

all_merchants = []

for chunk in pd.read_csv(
    TRANSACTIONS_FILE,
    usecols=merchant_cols,
    chunksize=500_000,
    dtype={
        "Merchant Name": "string",
        "Merchant City": "string",
        "Merchant State": "string",
        "Zip": "string",
        "MCC": "string",
    },
):
    merchants = chunk.drop_duplicates()
    all_merchants.append(merchants)

merchant_reference = pd.concat(all_merchants).drop_duplicates()

merchant_reference.to_csv(MERCHANT_REFERENCE_FILE, index=False)

print(f"Saved {len(merchant_reference):,} unique merchants to {MERCHANT_REFERENCE_FILE}")