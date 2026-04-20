"""
Connexion Google Sheets via service account.
Si les credentials ne sont pas configurés, repli sur un CSV local.
"""

import streamlit as st
import pandas as pd
import os
import csv
from datetime import datetime
from typing import Optional

SHEET_NAME  = "RSVPs - Adakou & Ata-Sé"
FALLBACK    = "rsvp_data.csv"
RSVP_COLS   = ["timestamp", "prenom", "nom", "presence", "nb_personnes", "regime", "message"]


def _sheet():
    """Retourne la première feuille du Google Sheet, ou None."""
    try:
        import gspread
        creds = dict(st.secrets["gsheets"])
        gc = gspread.service_account_from_dict(creds)
        try:
            sh = gc.open(SHEET_NAME)
        except gspread.SpreadsheetNotFound:
            sh = gc.create(SHEET_NAME)
            sh.share(st.secrets.get("owner_email", ""), perm_type="user", role="owner")
        ws = sh.sheet1
        # Créer les en-têtes si vide
        if not ws.row_values(1):
            ws.append_row(RSVP_COLS)
        return ws
    except Exception:
        return None


def save_rsvp(data: dict) -> bool:
    data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [data.get(c, "") for c in RSVP_COLS]

    ws = _sheet()
    if ws:
        try:
            ws.append_row(row)
            return True
        except Exception:
            pass

    # Repli CSV
    exists = os.path.exists(FALLBACK)
    with open(FALLBACK, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RSVP_COLS)
        if not exists:
            w.writeheader()
        w.writerow({c: data.get(c, "") for c in RSVP_COLS})
    return True


def get_all_rsvps() -> pd.DataFrame:
    ws = _sheet()
    if ws:
        try:
            records = ws.get_all_records()
            return pd.DataFrame(records) if records else pd.DataFrame(columns=RSVP_COLS)
        except Exception:
            pass
    if os.path.exists(FALLBACK):
        return pd.read_csv(FALLBACK)
    return pd.DataFrame(columns=RSVP_COLS)


def storage_mode() -> str:
    ws = _sheet()
    return "Google Sheets ✅" if ws else "CSV local ⚠️"
