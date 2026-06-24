import os
import sys

# Ensure repo root is in PYTHONPATH
sys.path.append(os.path.abspath('.'))

from data_provider import DataFetcherManager

def fetch(code: str):
    manager = DataFetcherManager()
    try:
        df = manager.get_daily_data(code, days=5)
        print(f"Data for {code}:")
        print(df.head())
    except Exception as e:
        print(f"Error fetching {code}: {e}")

if __name__ == "__main__":
    raw = "F021894"
    # 去掉前缀 F
    code = raw.lstrip('F')
    fetch(code)
