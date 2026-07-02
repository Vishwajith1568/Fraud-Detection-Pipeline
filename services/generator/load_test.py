import json
import uuid
import random
import time
from kafka import KafkaProducer
from datetime import datetime

print("🚀 INITIATING BLACK FRIDAY STRESS TEST...")

# Connect to Kafka
try:
    producer = KafkaProducer(
        bootstrap_servers=['localhost:29092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    print("✅ Connected to Kafka Broker")
except Exception as e:
    print(f"❌ Failed to connect to Kafka: {e}")
    exit(1)

USER_IDS = [f"USER_{i}" for i in range(1000, 9999)]
MERCHANTS = ["online_retail", "gas_station", "grocery", "electronics", "restaurant", "luxury_goods"]

def generate_transaction():
    # 5% chance of generating an obvious massive fraud anomaly to test the AI under pressure
    is_fraud = random.random() < 0.05 
    amount = round(random.uniform(5000, 50000), 2) if is_fraud else round(random.uniform(5, 150), 2)
    
    return {
        "transaction_id": str(uuid.uuid4()),
        "user_id": random.choice(USER_IDS),
        "amount": amount,
        "currency": random.choice(["USD", "EUR", "INR"]),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "merchant_category": "luxury_goods" if is_fraud else random.choice(MERCHANTS),
        "location": "N/A"
    }

# --- THE BOMBARDMENT ---
TOTAL_TRANSACTIONS = 5000
start_time = time.time()

print(f"🔥 Blasting {TOTAL_TRANSACTIONS} transactions into the pipeline...")

for i in range(TOTAL_TRANSACTIONS):
    tx = generate_transaction()
    producer.send('transactions', value=tx)
    
    # Print progress every 500 messages so we don't freeze the terminal
    if i % 500 == 0:
        print(f"   -> Sent {i} messages...")

producer.flush()
end_time = time.time()

duration = end_time - start_time
print(f"🏁 STRESS TEST COMPLETE!")
print(f"📊 Sent {TOTAL_TRANSACTIONS} messages in {duration:.2f} seconds.")
print(f"⚡ Throughput: {TOTAL_TRANSACTIONS / duration:.2f} transactions/second.")