"""
detection_engine.py
Pure detection logic extracted from app.py for testability.
No Kafka, no Docker dependencies - just detection functions.
"""

import time
import os
import warnings
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split
import joblib

# Suppress sklearn feature name warnings for live inference
warnings.filterwarnings("ignore", message="X does not have valid feature names")

# Default configuration
DEFAULT_CONFIG = {
    'velocity_time_window': 5.0,
    'velocity_max_transactions': 2,
    'n_estimators': 150,
    'contamination': 0.00172,
    'random_state': 42,
    'kaggle_csv_path': '/app/data/creditcard.csv',
    'model_path': '/app/fraud_model.pkl',
    'scaler_path': '/app/scaler.pkl',
}


def normalize_timestamp(ts):
    """Convert any timestamp format to a Unix float.

    Accepts:
        - int/float: returned as-is (Unix timestamp)
        - str: parsed as ISO format (e.g. '2026-06-30T12:00:00Z')
        - None or invalid: returns current time as fallback
    """
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        ts_clean = ts.replace('Z', '+00:00')
        try:
            dt = datetime.fromisoformat(ts_clean)
            return dt.timestamp()
        except ValueError:
            pass
    return time.time()


def check_hard_rules(transaction, user_history, config=None):
    """Apply rule-based fraud detection.

    Rules:
        1. International Card Present: card_present transaction from non-US country
        2. Velocity Check: more than N transactions from same user within time window

    Args:
        transaction: dict with keys user_id, _unix_timestamp, transaction_type, country
        user_history: defaultdict(list) tracking per-user transaction history
        config: optional dict overriding DEFAULT_CONFIG values

    Returns:
        list of reason strings (empty if no rules triggered)
    """
    if config is None:
        config = DEFAULT_CONFIG

    velocity_window = config.get('velocity_time_window', DEFAULT_CONFIG['velocity_time_window'])
    velocity_max = config.get('velocity_max_transactions', DEFAULT_CONFIG['velocity_max_transactions'])

    user_id = transaction.get('user_id', 'UNKNOWN')
    current_time = transaction.get('_unix_timestamp', time.time())
    reasons = []

    # Rule 1: International Card Present
    tx_type = transaction.get('transaction_type', 'online')
    country = transaction.get('country', 'US')
    if tx_type == 'card_present' and country != 'US':
        reasons.append("International physical card transaction")

    # Rule 2: Velocity Check
    recent_txs = [
        t for t in user_history[user_id]
        if current_time - t.get('_unix_timestamp', 0) <= velocity_window
    ]
    if len(recent_txs) >= velocity_max:
        reasons.append(f"Velocity hit: {len(recent_txs)+1} transactions in {velocity_window}s")

    # Record this transaction in history
    user_history[user_id].append(transaction)
    return reasons


def check_ai_rules(transaction, model, scaler, is_trained, kaggle_mode=False):
    """Apply ML-based anomaly detection using Isolation Forest.

    Args:
        transaction: dict with keys amount, _unix_timestamp
        model: trained IsolationForest instance
        scaler: fitted StandardScaler instance
        is_trained: bool indicating if model is ready
        kaggle_mode: bool indicating if model was trained on Kaggle (30 features)

    Returns:
        list of reason strings (empty if no anomaly or model not trained)
    """
    if not is_trained:
        return []

    unix_ts = transaction.get('_unix_timestamp', time.time())

    if kaggle_mode:
        # Kaggle-trained model expects 30 features (Amount, Time, V1-V28)
        feature_vector = np.zeros((1, 30))
        feature_vector[0, 0] = transaction.get('amount', 0)
        feature_vector[0, 1] = unix_ts % 86400
        feature_vector_scaled = scaler.transform(feature_vector)
    else:
        # Synthetic-trained model expects 2 features
        features = pd.DataFrame([{
            'amount': transaction.get('amount', 0),
            'time_of_day': (unix_ts % 86400) / 3600
        }])
        feature_vector_scaled = scaler.transform(features)

    prediction = model.predict(feature_vector_scaled)[0]
    score = model.decision_function(feature_vector_scaled)[0]

    if prediction == -1:
        return [f"AI Anomaly Detected: Unusual pattern (score: {score:.4f})"]
    return []


def train_on_kaggle_dataset(model, scaler, csv_path=None):
    """Train the Isolation Forest on the Kaggle credit card fraud dataset.

    Args:
        model: IsolationForest instance (will be fitted in-place)
        scaler: StandardScaler instance (will be fitted in-place)
        csv_path: path to creditcard.csv

    Returns:
        dict with keys: success, precision, recall, f1, train_duration, total_records, fraud_count
    """
    if csv_path is None:
        csv_path = DEFAULT_CONFIG['kaggle_csv_path']

    if not os.path.exists(csv_path):
        return {'success': False, 'error': f'Dataset not found at {csv_path}'}

    df = pd.read_csv(csv_path)
    total_records = len(df)
    fraud_count = int(df['Class'].sum())

    feature_cols = ['Amount', 'Time'] + [f'V{i}' for i in range(1, 29)]
    X = df[feature_cols].copy()
    y = df['Class'].copy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    start_time = time.time()
    model.fit(X_train_scaled)
    train_duration = time.time() - start_time

    y_pred = model.predict(X_test_scaled)
    y_pred_labels = [1 if p == -1 else 0 for p in y_pred]

    precision = precision_score(y_test, y_pred_labels, zero_division=0)
    recall = recall_score(y_test, y_pred_labels, zero_division=0)
    f1 = f1_score(y_test, y_pred_labels, zero_division=0)

    return {
        'success': True,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'train_duration': train_duration,
        'total_records': total_records,
        'fraud_count': fraud_count,
        'train_size': len(X_train),
        'test_size': len(X_test),
    }


def train_on_synthetic(model, scaler, data_points):
    """Fallback: train on collected synthetic transactions.

    Args:
        model: IsolationForest instance
        scaler: StandardScaler instance
        data_points: list of dicts with keys amount, time_of_day

    Returns:
        True if training succeeded
    """
    if len(data_points) == 0:
        return False

    df = pd.DataFrame(data_points)
    scaled = scaler.fit_transform(df)
    model.fit(scaled)
    return True


def build_alert(transaction, reasons):
    """Build a clean alert dict from a transaction and its fraud reasons.

    Strips internal fields (starting with _) and adds reasons.

    Args:
        transaction: raw transaction dict
        reasons: list of reason strings

    Returns:
        dict suitable for sending as a fraud alert
    """
    alert = {k: v for k, v in transaction.items() if not k.startswith('_')}
    alert['reasons'] = reasons
    return alert