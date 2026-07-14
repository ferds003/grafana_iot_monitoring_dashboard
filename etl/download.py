"""Download the Smart Manufacturing IoT-Cloud Monitoring dataset from Kaggle
and print an exploration summary so we can confirm the real schema.

Requires KAGGLE_USERNAME / KAGGLE_KEY in .env (or ~/.kaggle/kaggle.json).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATASET = "ziya07/smart-manufacturing-iot-cloud-monitoring-dataset"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def ensure_kaggle_credentials():
    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        return
    if username and key:
        kaggle_json.parent.mkdir(parents=True, exist_ok=True)
        kaggle_json.write_text(f'{{"username":"{username}","key":"{key}"}}')
        os.chmod(kaggle_json, 0o600)
        return
    sys.exit(
        "Missing Kaggle credentials. Set KAGGLE_USERNAME/KAGGLE_KEY in .env "
        "or place kaggle.json at ~/.kaggle/kaggle.json"
    )


def download():
    ensure_kaggle_credentials()
    from kaggle.api.kaggle_api_extended import KaggleApi

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api = KaggleApi()
    api.authenticate()
    print(f"Downloading {DATASET} -> {DATA_DIR}")
    api.dataset_download_files(DATASET, path=str(DATA_DIR), unzip=True)


def inspect():
    import pandas as pd

    csvs = list(DATA_DIR.glob("*.csv"))
    if not csvs:
        sys.exit(f"No CSV files found in {DATA_DIR}")
    csv_path = csvs[0]
    print(f"\n=== Inspecting {csv_path.name} ===")
    df = pd.read_csv(csv_path)

    print(f"\nShape: {df.shape}")
    print(f"\nColumns: {list(df.columns)}")
    print("\nDtypes:")
    print(df.dtypes)
    print("\nNull counts:")
    print(df.isnull().sum())

    # Try to find a timestamp-like column
    ts_candidates = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
    if ts_candidates:
        ts_col = ts_candidates[0]
        parsed = pd.to_datetime(df[ts_col], errors="coerce")
        print(f"\nTimestamp column guess: '{ts_col}'")
        print(f"  min: {parsed.min()}  max: {parsed.max()}")

    machine_candidates = [c for c in df.columns if "machine" in c.lower() and "id" in c.lower()]
    if machine_candidates:
        col = machine_candidates[0]
        print(f"\nUnique '{col}': {df[col].nunique()}")
        print(df[col].value_counts().head(10))

    for col in df.columns:
        if df[col].dtype == object and df[col].nunique() < 20:
            print(f"\nValue counts for categorical-looking column '{col}':")
            print(df[col].value_counts())

    print("\nHead:")
    print(df.head(3).to_string())


if __name__ == "__main__":
    if "--skip-download" not in sys.argv:
        download()
    inspect()
