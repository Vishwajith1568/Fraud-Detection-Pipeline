import json
import time
from collections import defaultdict
from kafka import KafkaConsumer

TOPIC_NAME = 'transactions'

print(f"Connecting to Kafka broker to listen for '{TOPIC_NAME}'...")

consumer = KafkaConsumer(
    TOPIC_NAME,
    bootstrap_servers=['localhost:29092'],
    auto_offset_reset='latest',
    enable_auto_commit=True,
    group_id='fraud-detection-group',
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

print("Consumer connected! Rule engine active...")

# Memory for our Velocity Rule: {user_id: [timestamp1, timestamp2]}
user_history = defaultdict(list)
VELOCITY_TIME_WINDOW = 5.0  # seconds
VELOCITY_MAX_TRANSACTIONS = 2  # More than 2 swipes in 5 seconds is fraud

try:
    for message in consumer:
        tx = message.value
        user = tx.get('user_id')
        amount = tx.get('amount')
        merchant = tx.get('merchant_category')
        
        current_time = time.time()
        
        # --- RULE 1: HIGH AMOUNT ---
        is_high_amount = amount > 2500
        
        # --- RULE 2: VELOCITY SPIKE (Sliding Window) ---
        # First, clean up old memory (remove timestamps older than 5 seconds)
        user_history[user] = [t for t in user_history[user] if current_time - t < VELOCITY_TIME_WINDOW]
        
        # Add the current transaction's timestamp
        user_history[user].append(current_time)
        
        # Check if they exceeded the limit
        is_velocity_spike = len(user_history[user]) > VELOCITY_MAX_TRANSACTIONS
        
        # --- DECISION ENGINE ---
        if is_high_amount or is_velocity_spike:
            reason = []
            if is_high_amount: reason.append(f"HIGH AMOUNT (${amount})")
            if is_velocity_spike: reason.append("VELOCITY SPIKE")
            
            print(f"🚨 FRAUD BLOCKED [{', '.join(reason)}] -> User: {user} | Merchant: {merchant}")
        else:
            print(f"✅ Approved -> User: {user} | Amount: ${amount}")

except KeyboardInterrupt:
    print("\nClosing consumer connection...")
    consumer.close()