import pandas as pd
import re
from typing import List, Tuple, Optional

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def guess_name_column(columns: List[str]) -> Optional[str]:
    candidates = [
        col
        for col in columns
        if re.search(r"\b(name|full.?name|first.?name)\b", col, re.I)
    ]
    if candidates:
        # Prefer exact match "name"
        exact = [col for col in candidates if col.strip().lower() == "name"]
        return exact[0] if exact else candidates[0]
    return None


def guess_email_column(columns: List[str]) -> Optional[str]:
    candidates = [
        col for col in columns if re.search(r"\b(e?-?mail|email|e_mail)\b", col, re.I)
    ]
    if candidates:
        exact = [
            col for col in candidates if col.strip().lower() in ("email", "e-mail")
        ]
        return exact[0] if exact else candidates[0]
    return None


def read_excel(file_path: str) -> Tuple[List[str], List[dict]]:
    """Return (column_names, list_of_row_dicts)"""
    try:
        df = pd.read_excel(file_path, engine="openpyxl")
    except Exception:
        # Fallback for .xls
        df = pd.read_excel(file_path, engine="xlrd")
    df = df.where(pd.notnull(df), None)  # Keep None for empty cells
    columns = df.columns.tolist()
    rows = df.to_dict(orient="records")
    # Convert all values to string (or keep None for empty)
    clean_rows = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                clean[k] = ""
            else:
                clean[k] = str(v)
        clean_rows.append(clean)
    return columns, clean_rows


def validate_email_column(rows: List[dict], col_name: str) -> bool:
    """Check if at least 80% of values in that column look like emails."""
    count = 0
    valid = 0
    for row in rows:
        val = row.get(col_name)
        if val:
            count += 1
            if EMAIL_PATTERN.match(str(val).strip()):
                valid += 1
    return count > 0 and (valid / count) >= 0.8
