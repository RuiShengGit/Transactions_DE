import pandas as pd

file_path = "data/raw/kaggle_card_transactions/credit_card_transactions-ibm_v2.csv"

fraud_counts = {"Yes": 0, "No": 0}
total_rows = 0

#Calculate fraud rate in historical data to use for simulated data
for chunk in pd.read_csv(file_path, usecols=["Is Fraud?"], chunksize=500_000):
    counts = chunk["Is Fraud?"].value_counts(dropna=False)

    fraud_counts["Yes"] += counts.get("Yes", 0)
    fraud_counts["No"] += counts.get("No", 0)
    total_rows += len(chunk)

fraud_rate = fraud_counts["Yes"] / total_rows

print(fraud_counts)
print(f"Fraud rate: {fraud_rate:.4%}")