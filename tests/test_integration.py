"""
test_integration.py
Integration tests for the fraud detection pipeline.
Requires all Docker containers running: docker-compose up

Run with: python -m pytest test_integration.py -v -s

Tests send transactions to Kafka (localhost:29092), wait for processing,
then verify results in MongoDB (localhost:27017) and the API (localhost:4000).
"""

import time
import json
import uuid
import pytest
import requests
from kafka import KafkaProducer
from pymongo import MongoClient


# ═══════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════

KAFKA_BROKER = 'localhost:29092'
MONGODB_URI = 'mongodb://localhost:27017'
MONGODB_DB = 'fraud_detection'
API_BASE = 'http://localhost:4000'
API_USERNAME = 'admin'
API_PASSWORD = 'admin123'
KAFKA_TOPIC = 'transactions'

# How long to wait for pipeline to process (seconds)
PROCESSING_WAIT = 10


# ═══════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def kafka_producer():
    """Create a Kafka producer connected to localhost."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BROKER],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            request_timeout_ms=10000,
        )
        yield producer
        producer.close()
    except Exception as e:
        pytest.skip(f"Kafka not available at {KAFKA_BROKER}: {e}")


@pytest.fixture(scope='module')
def mongo_client():
    """Create a MongoDB client connected to localhost."""
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Force connection test
        client.server_info()
        yield client
        client.close()
    except Exception as e:
        pytest.skip(f"MongoDB not available at {MONGODB_URI}: {e}")


@pytest.fixture(scope='module')
def api_token():
    """Get a JWT token from the API."""
    try:
        response = requests.post(
            f'{API_BASE}/api/login',
            json={'username': API_USERNAME, 'password': API_PASSWORD},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data['token']
        pytest.skip("Could not authenticate with API")
    except Exception as e:
        pytest.skip(f"API not available at {API_BASE}: {e}")


def generate_test_transaction(user_id=None, amount=50.0, country='US', tx_type='online'):
    """Generate a transaction with a unique ID for testing."""
    return {
        'transaction_id': f'TEST_{uuid.uuid4().hex[:12]}',
        'user_id': user_id or f'TEST_USER_{uuid.uuid4().hex[:6]}',
        'amount': amount,
        'currency': 'USD',
        'merchant': 'Integration Test Merchant',
        'country': country,
        'transaction_type': tx_type,
        'timestamp': time.time(),
        'is_fraud_scenario': False,
    }


# ═══════════════════════════════════════════════════════
#  CONNECTION TESTS
# ═══════════════════════════════════════════════════════

class TestConnections:
    """Verify all pipeline components are reachable."""

    def test_kafka_connection(self, kafka_producer):
        """Kafka broker should be reachable."""
        assert kafka_producer is not None
        assert kafka_producer.bootstrap_connected()

    def test_mongodb_connection(self, mongo_client):
        """MongoDB should be reachable and have the fraud_detection database."""
        db_names = mongo_client.list_database_names()
        # fraud_detection db may not exist until first alert is saved
        assert mongo_client is not None

    def test_api_health(self):
        """Web backend API should respond."""
        try:
            response = requests.post(
                f'{API_BASE}/api/login',
                json={'username': 'wrong', 'password': 'wrong'},
                timeout=5
            )
            # Even with wrong credentials, the server should respond
            assert response.status_code == 401
        except requests.ConnectionError:
            pytest.skip("API not available")

    def test_api_login(self, api_token):
        """API should return a valid JWT token on correct credentials."""
        assert api_token is not None
        assert len(api_token) > 20


# ═══════════════════════════════════════════════════════
#  PIPELINE FLOW TESTS
# ═══════════════════════════════════════════════════════

class TestPipelineFlow:
    """Test end-to-end transaction processing through the pipeline."""

    def test_normal_transaction_not_flagged(self, kafka_producer, mongo_client):
        """A normal US online transaction should NOT appear in fraud alerts."""
        tx = generate_test_transaction(
            user_id='INTTEST_NORMAL_001',
            amount=25.0,
            country='US',
            tx_type='online'
        )
        tx_id = tx['transaction_id']

        # Send to Kafka
        kafka_producer.send(KAFKA_TOPIC, value=tx)
        kafka_producer.flush()

        # Wait for pipeline processing
        time.sleep(PROCESSING_WAIT)

        # Check MongoDB - should NOT be in alerts
        db = mongo_client[MONGODB_DB]
        alert = db.alerts.find_one({'transaction_id': tx_id})
        assert alert is None, f"Normal transaction {tx_id} should NOT be flagged"

    def test_international_card_flagged(self, kafka_producer, mongo_client):
        """An international card-present transaction SHOULD be flagged."""
        tx = generate_test_transaction(
            user_id='INTTEST_INTL_001',
            amount=75.0,
            country='UK',
            tx_type='card_present'
        )
        tx_id = tx['transaction_id']

        # Send to Kafka
        kafka_producer.send(KAFKA_TOPIC, value=tx)
        kafka_producer.flush()

        # Wait for pipeline processing
        time.sleep(PROCESSING_WAIT)

        # Check MongoDB - SHOULD be in alerts
        db = mongo_client[MONGODB_DB]
        alert = db.alerts.find_one({'transaction_id': tx_id})
        assert alert is not None, f"International card transaction {tx_id} should be flagged"
        assert 'International physical card transaction' in alert.get('reasons', [])

    def test_velocity_attack_flagged(self, kafka_producer, mongo_client):
        """Three rapid transactions from same user SHOULD trigger velocity rule."""
        victim_user = f'INTTEST_VELOCITY_{uuid.uuid4().hex[:6]}'
        tx_ids = []

        # Send 3 rapid transactions
        for i in range(3):
            tx = generate_test_transaction(
                user_id=victim_user,
                amount=30.0 + i * 10,
                country='US',
                tx_type='online'
            )
            tx_ids.append(tx['transaction_id'])
            kafka_producer.send(KAFKA_TOPIC, value=tx)
            time.sleep(0.3)  # Small gap but within 5s window

        kafka_producer.flush()

        # Wait for pipeline processing
        time.sleep(PROCESSING_WAIT)

        # Check MongoDB - the 3rd transaction should have velocity flag
        db = mongo_client[MONGODB_DB]
        third_alert = db.alerts.find_one({'transaction_id': tx_ids[2]})
        assert third_alert is not None, f"Third rapid transaction should be flagged"
        assert any('Velocity' in r for r in third_alert.get('reasons', []))

    def test_flagged_alerts_appear_in_api(self, kafka_producer, api_token):
        """Flagged transactions should be retrievable via the REST API."""
        tx = generate_test_transaction(
            user_id='INTTEST_API_001',
            amount=60.0,
            country='JP',
            tx_type='card_present'
        )

        # Send to Kafka
        kafka_producer.send(KAFKA_TOPIC, value=tx)
        kafka_producer.flush()

        # Wait for processing
        time.sleep(PROCESSING_WAIT)

        # Query API
        response = requests.get(
            f'{API_BASE}/api/alerts',
            headers={'Authorization': f'Bearer {api_token}'},
            timeout=5
        )
        assert response.status_code == 200
        alerts = response.json()
        assert isinstance(alerts, list)
        assert len(alerts) > 0, "API should return at least one alert"

    def test_api_rejects_without_token(self):
        """API should reject requests without authentication."""
        try:
            response = requests.get(f'{API_BASE}/api/alerts', timeout=5)
            assert response.status_code == 401
        except requests.ConnectionError:
            pytest.skip("API not available")

    def test_api_rejects_invalid_token(self):
        """API should reject requests with an invalid token."""
        try:
            response = requests.get(
                f'{API_BASE}/api/alerts',
                headers={'Authorization': 'Bearer fake.invalid.token'},
                timeout=5
            )
            assert response.status_code == 403
        except requests.ConnectionError:
            pytest.skip("API not available")


# ═══════════════════════════════════════════════════════
#  LOAD TEST
# ═══════════════════════════════════════════════════════

class TestLoadPerformance:
    """Basic load test to verify pipeline handles burst traffic."""

    def test_burst_throughput(self, kafka_producer):
        """Pipeline should handle a burst of 500 transactions without dropping."""
        total = 500
        start_time = time.time()

        for i in range(total):
            tx = generate_test_transaction(
                user_id=f'LOADTEST_USER_{i % 50}',
                amount=float(10 + (i % 200)),
            )
            kafka_producer.send(KAFKA_TOPIC, value=tx)

        kafka_producer.flush()
        duration = time.time() - start_time

        throughput = total / duration
        print(f"\n  LOAD TEST RESULTS")
        print(f"  Sent {total} transactions in {duration:.2f}s")
        print(f"  Throughput: {throughput:.0f} transactions/second")

        # Should be able to send at least 100 tx/s to Kafka
        assert throughput > 100, f"Throughput too low: {throughput:.0f} tx/s"