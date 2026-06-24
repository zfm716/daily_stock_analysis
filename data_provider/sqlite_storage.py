import os
import sqlite3
from pathlib import Path
from typing import List, Tuple
import pandas as pd

DB_FILENAME = "etf_cache.db"

def _get_db_path() -> Path:
    """Return absolute path to the SQLite DB file inside the project root.
    The DB file is stored under a hidden '.cache' directory for consistency with other caches.
    """
    root = Path(__file__).resolve().parents[2]  # project root (daily_stock_analysis)
    cache_dir = root / ".cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / DB_FILENAME

def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_data (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL NOT NULL,
            PRIMARY KEY (code, date)
        )
        """
    )
    conn.commit()

def upsert_etf_data(df: pd.DataFrame, code: str) -> None:
    """Insert or replace rows for a given ETF code.
    ``df`` must contain columns ``date`` (YYYY-MM-DD) and ``close`` (float).
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        _ensure_table(conn)
        records: List[Tuple[str, str, float]] = []
        for _, row in df.iterrows():
            records.append((code, str(row["date"]), float(row["close"])) )
        conn.executemany(
            "INSERT OR REPLACE INTO etf_data (code, date, close) VALUES (?, ?, ?)",
            records,
        )
        conn.commit()
    finally:
        conn.close()

def query_etf_data(code: str, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """Return stored ETF data for ``code``.
    Optional ``start_date`` / ``end_date`` filter (inclusive) in ``YYYY-MM-DD``.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        _ensure_table(conn)
        sql = "SELECT date, close FROM etf_data WHERE code = ?"
        params: List[str] = [code]
        if start_date:
            sql += " AND date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND date <= ?"
            params.append(end_date)
        sql += " ORDER BY date ASC"
        rows = conn.execute(sql, params).fetchall()
        return pd.DataFrame(rows, columns=["date", "close"])
    finally:
        conn.close()
