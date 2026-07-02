"""
app.py - Fraud Detection Pipeline Main Process
Connects to Kafka, processes transactions, and produces fraud alerts.
Detection logic lives in detection_engine.py for testability.
"""

import time
import json
import os
from collections import defaultdict
from confluent_kafka import Consumer, Producer
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from detection_engine import (
    normalize_timestamp,
    check_hard_rules,
    check_ai_rules,
    train_on_kaggle_dataset,
    train_on_synthetic,
    build_alert,
    DEFAULT_CONFIG,
)

TOPIC_NAME = 'transactions'
KAGGLE_CSV_PATH = '/app/data/creditcard.csv'

# CLOUD ROUTE: Connects to Docker's Kafka using Confluent Syntax
consumer = Consumer({
    'bootstrap.servers': 'kafka:9092',
    'group.id': 'fraud-ai-group',
    'auto.offset.reset': 'earliest'
})

producer = Producer({
    'bootstrap.servers': 'kafka:9092'
})

consumer.subscribe([TOPIC_NAME])

print("=" * 60)
print("  FRAUD DETECTION ENGINE v2.0")
print("  Hard Rules + AI Anomaly Detection (Isolation Forest)")
print("=" * 60)

user_history = defaultdict(list)

ai_model = IsolationForest(
    n_estimators=DEFAULT_CONFIG['n_estimators'],
    contamination=DEFAULT_CONFIG['contamination'],
    random_state=DEFAULT_CONFIG['random_state']
)
scaler = StandardScaler()
is_ai_trained = False
kaggle_mode = False
training_data = []


def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"FRAUD ALERT SENT to topic {msg.topic()}")


# ── STARTUP: Train on Kaggle data if available ──
if os.path.exists(KAGGLE_CSV_PATH):
    print("\n" + "=" * 60)
    print("  TRAINING ON KAGGLE CREDIT CARD FRAUD DATASET")
    print("=" * 60)

    result = train_on_kaggle_dataset(ai_model, scaler, KAGGLE_CSV_PATH)

    if result['success']:
        is_ai_trained = True
        kaggle_mode = True
        print(f"\n[1/5] Loaded {result['total_records']:,} transactions")
        print(f"       Fraud cases: {result['fraud_count']} ({result['fraud_count']/result['total_records']*100:.3f}%)")
        print(f"[2/5] Train: {result['train_size']:,} | Test: {result['test_size']:,}")
        print(f"[3/5] Features scaled with StandardScaler")
        print(f"[4/5] Training completed in {result['train_duration']:.2f} seconds")
        print(f"\n  MODEL EVALUATION RESULTS")
        print(f"  Precision: {result['precision']:.4f}")
        print(f"  Recall:    {result['recall']:.4f}")
        print(f"  F1 Score:  {result['f1']:.4f}")
        print("\nAI Model trained on REAL DATA and ready for inference!")
        print("=" * 60 + "\n")
        print("Waiting for live transactions from Kafka...\n")
    else:
        print(f"[WARNING] {result.get('error', 'Unknown error')}")
        print("Falling back to synthetic training...\n")
else:
    print("\n[INFO] Kaggle dataset not found. Will train on first 50 transactions.\n")

try:
    while True:
        msg = consumer.poll(1.0)

        if msg is None:
            continue
        if msg.error():
            print(f"Consumer error: {msg.error()}")
            continue

        try:
            transaction = json.loads(msg.value().decode('utf-8'))
        except json.JSONDecodeError as e:
            print(f"Skipping malformed message: {e}")
            continue

        transaction['_unix_timestamp'] = normalize_timestamp(transaction.get('timestamp'))

        user_id = transaction.get('user_id', 'UNKNOWN')
        amount = transaction.get('amount', 0)
        tx_id = transaction.get('transaction_id', 'NO_ID')
        print(f"Analyzing: {tx_id} | User: {user_id} | ${amount}")

        # Fallback synthetic training
        if not is_ai_trained:
            unix_ts = transaction['_unix_timestamp']
            training_data.append({
                'amount': amount,
                'time_of_day': (unix_ts % 86400) / 3600
            })
            if len(training_data) >= 50:
                if train_on_synthetic(ai_model, scaler, training_data):
                    is_ai_trained = True
                    print("AI Model trained (synthetic) and active!\n")

        fraud_reasons = check_hard_rules(transaction, user_history)
        ai_reasons = check_ai_rules(transaction, ai_model, scaler, is_ai_trained, kaggle_mode)
        all_reasons = fraud_reasons + ai_reasons

        if all_reasons:
            alert = build_alert(transaction, all_reasons)
            print(f"FRAUD DETECTED: {all_reasons}")

            producer.produce(
                'fraud_alerts',
                key=tx_id.encode('utf-8'),
                value=json.dumps(alert).encode('utf-8'),
                callback=delivery_report
            )
            producer.poll(0)

except KeyboardInterrupt:
    print("Shutting down AI Detector...")
finally:
    consumer.close()
    producer.flush()