import time
import random
import json
from datetime import datetime
from faker import Faker
from kafka import KafkaProducer

fake = Faker()

# CLOUD ROUTE: Connects to Docker's Kafka
producer = KafkaProducer(
    bootstrap_servers=['kafka:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

TOPIC_NAME = 'transactions'

EXCHANGE_RATES = {"USD": 1.0, "EUR": 0.92, "INR": 83.50}


def generate_base_transaction(user_id=None):
    base_usd = random.uniform(5.0, 150.0)
    currency = random.choice(list(EXCHANGE_RATES.keys()))
    amount = round(base_usd * EXCHANGE_RATES[currency], 2)

    return {
        "transaction_id": fake.uuid4(),
        "user_id": user_id if user_id else f"USER_{random.randint(100, 999)}",
        "amount": amount,
        "currency": currency,
        "merchant": fake.company(),
        "country": random.choice(["US", "UK", "IN", "CA", "JP", "BR"]),
        "transaction_type": random.choice(["online", "card_present"]),
        "timestamp": time.time(),
        "is_fraud_scenario": False
    }


def generate_velocity_attack():
    victim_user = f"USER_{random.randint(100, 999)}"
    print(f"\nSCENARIO INITIATED: Velocity Attack on {victim_user}")

    for i in range(3):
        tx = generate_base_transaction(user_id=victim_user)
        tx["is_fraud_scenario"] = True

        producer.send(TOPIC_NAME, tx)
        print(f"  -> Sent rapid transaction {i+1}: ${tx['amount']} at {tx['merchant']}")
        time.sleep(0.5)
    print("Velocity Attack Complete\n")


def run_generator():
    print(f"Starting Data Generator... Sending to topic: {TOPIC_NAME}")

    try:
        while True:
            scenario_roll = random.randint(1, 100)

            if scenario_roll <= 10:
                generate_velocity_attack()
            else:
                tx = generate_base_transaction()
                producer.send(TOPIC_NAME, tx)
                print(f"Sent normal transaction: {tx['transaction_id']} | ${tx['amount']}")

            time.sleep(random.uniform(1.0, 3.0))

    except KeyboardInterrupt:
        print("\nStopping Data Generator.")
    finally:
        producer.close()


if __name__ == "__main__":
    run_generator()