import pandas as pd

file_path = "data/raw/kaggle_card_transactions/credit_card_transactions-ibm_v2.csv"

total_rows = 0
error_count = 0

for chunk in pd.read_csv(file_path, usecols=["Errors?"], chunksize=500_000):
    total_rows += len(chunk)
    error_count += chunk["Errors?"].notna().sum()

error_rate = error_count / total_rows
print(f"Error Rate: {error_rate:.4%}")