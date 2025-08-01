# app/tools/misconfiguration_ml.py
"""Scoring avec le modèle One-Class SVM pour détecter les tasks suspectes."""

from pathlib import Path
import joblib, pandas as pd, numpy as np
from backend.db import client
from datetime import datetime, timedelta

MODEL_PATH = Path(__file__).with_suffix(".pkl").with_name("misconfig_ocsvm.pkl")
PACK       = joblib.load(MODEL_PATH)

FEATURES = PACK["features"]
SCALE    = PACK["scaler"].transform
MODEL    = PACK["model"].decision_function

# ──────────────────────────────────────────────────────────────────────────────
def _compute_features(stats_df: pd.DataFrame) -> pd.DataFrame:
    """Reconstruit localement les mêmes features que lors de l’entraînement."""
    df = stats_df.copy()
    df["err_rate"]    = df["err_freq_20runs"] / 20
    df["log_minutes"] = np.log1p(df["minutes_since_last_err"].clip(upper=10080))
    df["err_after_reset_rate"] = (
        df["max_consec_errors"] / df["err_freq_20runs"].replace(0, np.nan)
    ).fillna(0)
    return df[FEATURES]

# ──────────────────────────────────────────────────────────────────────────────
def detect_misconfig_ml(company: str, since_days: int = 30) -> pd.DataFrame:
    """
    Retourne un DataFrame des tasks triées par score d’anomalie.
    """
    from backend.extract import build_features  # import local

    TMP_PARQUET = f"/tmp/{company}_feat.parquet"
    build_features(
        mongo_uri="mongodb://localhost:27017",
        dbname=company,
        since_days=since_days,
        out_parquet=TMP_PARQUET
    )
    raw = pd.read_parquet(TMP_PARQUET)
    X   = _compute_features(raw)
    scores = MODEL(SCALE(X))
    raw["anomaly_score"] = scores
    raw["is_anomaly"]    = scores < 0
    return raw.sort_values("anomaly_score")    # plus négatif = plus suspect
