from pathlib import Path
import kagglehub
from dotenv import load_dotenv
import zipfile

load_dotenv()

DATASET = "ealtman2019/credit-card-transactions"
RAW_DIR = Path("data/raw/kaggle_card_transactions")


FILES_TO_DOWNLOAD = [
    "credit_card_transactions-ibm_v2.csv",
    "sd254_cards.csv",
    "sd254_users.csv",
]


RAW_DIR.mkdir(parents=True, exist_ok=True)


def extract_zip(file_path: Path) -> None:
    if not zipfile.is_zipfile(file_path):
        print(f"{file_path.name} is a normal CSV file.")
        return

    zip_path = file_path.with_suffix(file_path.suffix + ".zip")
    file_path.rename(zip_path)

    print(f"Renamed ZIP file to: {zip_path.name}")

    with zipfile.ZipFile(zip_path, "r") as zip_file:
        zip_file.extractall(RAW_DIR)

    zip_path.unlink()
    print(f"Extracted and deleted ZIP file: {zip_path.name}")

for file_name in FILES_TO_DOWNLOAD:
    file_path = kagglehub.dataset_download(
        DATASET,
        path=file_name,
        output_dir=str(RAW_DIR),
    )
    print(f"Downloaded {file_name} to: {file_path}")

    extract_zip(Path(file_path))
