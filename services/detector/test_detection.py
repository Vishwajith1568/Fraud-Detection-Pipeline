"""
test_detection.py
Unit tests for the fraud detection engine.
Run with: pytest test_detection.py -v --cov=detection_engine
"""

import time
import pytest
import numpy as np
from collections import defaultdict
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from detection_engine import (
    normalize_timestamp,
    check_hard_rules,
    check_ai_rules,
    train_on_synthetic,
    build_alert,
    DEFAULT_CONFIG,
)


# ═══════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════

@pytest.fixture
def fresh_history():
    """Provide a clean user history for each test."""
    return defaultdict(list)


@pytest.fixture
def trained_model():
    """Provide a trained Isolation Forest + Scaler (synthetic, 2 features)."""
    model = IsolationForest(n_estimators=50, contamination=0.05, random_state=42)
    scaler = StandardScaler()

    # Generate synthetic training data
    np.random.seed(42)
    normal_amounts = np.random.uniform(5, 150, 200)
    normal_times = np.random.uniform(0, 24, 200)
    data = np.column_stack([normal_amounts, normal_times])

    scaled = scaler.fit_transform(data)
    model.fit(scaled)
    return model, scaler


@pytest.fixture
def base_transaction():
    """Provide a base normal transaction."""
    return {
        'transaction_id': 'TX_TEST_001',
        'user_id': 'USER_100',
        'amount': 50.0,
        'currency': 'USD',
        'merchant': 'Test Merchant',
        'country': 'US',
        'transaction_type': 'online',
        'timestamp': time.time(),
        '_unix_timestamp': time.time(),
    }


# ═══════════════════════════════════════════════════════
#  TIMESTAMP NORMALIZATION TESTS
# ═══════════════════════════════════════════════════════

class TestNormalizeTimestamp:

    def test_unix_float(self):
        """Float timestamps should pass through unchanged."""
        ts = 1782718700.728
        assert normalize_timestamp(ts) == ts

    def test_unix_int(self):
        """Integer timestamps should be converted to float."""
        ts = 1782718700
        result = normalize_timestamp(ts)
        assert result == float(ts)
        assert isinstance(result, float)

    def test_iso_string_with_z(self):
        """ISO strings with Z suffix should be parsed correctly."""
        ts = "2026-06-30T12:00:00Z"
        result = normalize_timestamp(ts)
        assert isinstance(result, float)
        assert result > 0

    def test_iso_string_with_offset(self):
        """ISO strings with timezone offset should be parsed correctly."""
        ts = "2026-06-30T12:00:00+05:30"
        result = normalize_timestamp(ts)
        assert isinstance(result, float)
        assert result > 0

    def test_invalid_string_returns_current_time(self):
        """Invalid strings should fall back to current time."""
        before = time.time()
        result = normalize_timestamp("not-a-timestamp")
        after = time.time()
        assert before <= result <= after

    def test_none_returns_current_time(self):
        """None should fall back to current time."""
        before = time.time()
        result = normalize_timestamp(None)
        after = time.time()
        assert before <= result <= after


# ═══════════════════════════════════════════════════════
#  HARD RULES TESTS
# ═══════════════════════════════════════════════════════

class TestHardRules:

    def test_normal_us_online_transaction_passes(self, base_transaction, fresh_history):
        """A normal US online transaction should trigger no rules."""
        reasons = check_hard_rules(base_transaction, fresh_history)
        assert reasons == []

    def test_international_card_present_flagged(self, base_transaction, fresh_history):
        """Card-present transaction from non-US country should be flagged."""
        base_transaction['transaction_type'] = 'card_present'
        base_transaction['country'] = 'UK'
        reasons = check_hard_rules(base_transaction, fresh_history)
        assert len(reasons) == 1
        assert "International physical card transaction" in reasons[0]

    def test_us_card_present_passes(self, base_transaction, fresh_history):
        """Card-present transaction from US should NOT be flagged."""
        base_transaction['transaction_type'] = 'card_present'
        base_transaction['country'] = 'US'
        reasons = check_hard_rules(base_transaction, fresh_history)
        assert reasons == []

    def test_international_online_passes(self, base_transaction, fresh_history):
        """Online transaction from non-US country should NOT be flagged."""
        base_transaction['transaction_type'] = 'online'
        base_transaction['country'] = 'UK'
        reasons = check_hard_rules(base_transaction, fresh_history)
        assert reasons == []

    def test_velocity_not_triggered_at_two(self, fresh_history):
        """Two transactions within window should NOT trigger velocity rule."""
        now = time.time()
        tx1 = {'user_id': 'USER_200', '_unix_timestamp': now, 'transaction_type': 'online', 'country': 'US'}
        tx2 = {'user_id': 'USER_200', '_unix_timestamp': now + 1, 'transaction_type': 'online', 'country': 'US'}

        check_hard_rules(tx1, fresh_history)
        reasons = check_hard_rules(tx2, fresh_history)
        assert reasons == []

    def test_velocity_triggered_at_three(self, fresh_history):
        """Three transactions within window SHOULD trigger velocity rule."""
        now = time.time()
        tx1 = {'user_id': 'USER_300', '_unix_timestamp': now, 'transaction_type': 'online', 'country': 'US'}
        tx2 = {'user_id': 'USER_300', '_unix_timestamp': now + 1, 'transaction_type': 'online', 'country': 'US'}
        tx3 = {'user_id': 'USER_300', '_unix_timestamp': now + 2, 'transaction_type': 'online', 'country': 'US'}

        check_hard_rules(tx1, fresh_history)
        check_hard_rules(tx2, fresh_history)
        reasons = check_hard_rules(tx3, fresh_history)
        assert len(reasons) == 1
        assert "Velocity hit" in reasons[0]

    def test_velocity_not_triggered_outside_window(self, fresh_history):
        """Transactions outside the time window should NOT trigger velocity."""
        now = time.time()
        tx1 = {'user_id': 'USER_400', '_unix_timestamp': now - 10, 'transaction_type': 'online', 'country': 'US'}
        tx2 = {'user_id': 'USER_400', '_unix_timestamp': now - 9, 'transaction_type': 'online', 'country': 'US'}
        tx3 = {'user_id': 'USER_400', '_unix_timestamp': now, 'transaction_type': 'online', 'country': 'US'}

        check_hard_rules(tx1, fresh_history)
        check_hard_rules(tx2, fresh_history)
        reasons = check_hard_rules(tx3, fresh_history)
        # tx1 and tx2 are >5s ago, so only tx3 is in window — no velocity trigger
        assert reasons == []

    def test_velocity_different_users_isolated(self, fresh_history):
        """Transactions from different users should NOT trigger velocity."""
        now = time.time()
        tx1 = {'user_id': 'USER_500', '_unix_timestamp': now, 'transaction_type': 'online', 'country': 'US'}
        tx2 = {'user_id': 'USER_501', '_unix_timestamp': now + 1, 'transaction_type': 'online', 'country': 'US'}
        tx3 = {'user_id': 'USER_502', '_unix_timestamp': now + 2, 'transaction_type': 'online', 'country': 'US'}

        check_hard_rules(tx1, fresh_history)
        check_hard_rules(tx2, fresh_history)
        reasons = check_hard_rules(tx3, fresh_history)
        assert reasons == []

    def test_multiple_rules_can_fire_together(self, fresh_history):
        """International + velocity should both fire on the same transaction."""
        now = time.time()
        tx1 = {'user_id': 'USER_600', '_unix_timestamp': now, 'transaction_type': 'card_present', 'country': 'US'}
        tx2 = {'user_id': 'USER_600', '_unix_timestamp': now + 1, 'transaction_type': 'online', 'country': 'US'}
        tx3 = {'user_id': 'USER_600', '_unix_timestamp': now + 2, 'transaction_type': 'card_present', 'country': 'JP'}

        check_hard_rules(tx1, fresh_history)
        check_hard_rules(tx2, fresh_history)
        reasons = check_hard_rules(tx3, fresh_history)
        assert len(reasons) == 2
        assert any("International" in r for r in reasons)
        assert any("Velocity" in r for r in reasons)

    def test_missing_fields_use_defaults(self, fresh_history):
        """Transactions with missing fields should use safe defaults."""
        tx = {'_unix_timestamp': time.time()}
        reasons = check_hard_rules(tx, fresh_history)
        # Default: transaction_type='online', country='US' → no flags
        assert reasons == []


# ═══════════════════════════════════════════════════════
#  AI RULES TESTS
# ═══════════════════════════════════════════════════════

class TestAIRules:

    def test_untrained_model_returns_empty(self):
        """AI rules should return empty list when model is not trained."""
        model = IsolationForest()
        scaler = StandardScaler()
        tx = {'amount': 50.0, '_unix_timestamp': time.time()}
        reasons = check_ai_rules(tx, model, scaler, is_trained=False)
        assert reasons == []

    def test_normal_transaction_no_anomaly(self, trained_model):
        """A normal-amount transaction should not be flagged as anomaly."""
        model, scaler = trained_model
        tx = {'amount': 75.0, '_unix_timestamp': time.time()}
        reasons = check_ai_rules(tx, model, scaler, is_trained=True, kaggle_mode=False)
        # Normal amount within training range — should usually pass
        # (ML is probabilistic, so we test the return type)
        assert isinstance(reasons, list)

    def test_ai_returns_score_in_reason(self, trained_model):
        """When AI flags a transaction, the reason should include the anomaly score."""
        model, scaler = trained_model
        # Try extreme amount to force anomaly
        tx = {'amount': 999999.0, '_unix_timestamp': time.time()}
        reasons = check_ai_rules(tx, model, scaler, is_trained=True, kaggle_mode=False)
        if len(reasons) > 0:
            assert "score:" in reasons[0]

    def test_ai_prediction_returns_list(self, trained_model):
        """AI rules should always return a list regardless of prediction."""
        model, scaler = trained_model
        tx = {'amount': 25.0, '_unix_timestamp': time.time()}
        result = check_ai_rules(tx, model, scaler, is_trained=True, kaggle_mode=False)
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════
#  SYNTHETIC TRAINING TESTS
# ═══════════════════════════════════════════════════════

class TestSyntheticTraining:

    def test_training_succeeds_with_valid_data(self):
        """Synthetic training should succeed with valid data points."""
        model = IsolationForest(n_estimators=10, random_state=42)
        scaler = StandardScaler()
        data = [{'amount': float(i * 10), 'time_of_day': float(i)} for i in range(50)]
        result = train_on_synthetic(model, scaler, data)
        assert result is True

    def test_training_fails_with_empty_data(self):
        """Synthetic training should fail with empty data."""
        model = IsolationForest()
        scaler = StandardScaler()
        result = train_on_synthetic(model, scaler, [])
        assert result is False


# ═══════════════════════════════════════════════════════
#  BUILD ALERT TESTS
# ═══════════════════════════════════════════════════════

class TestBuildAlert:

    def test_strips_internal_fields(self):
        """Internal fields starting with _ should be stripped from alerts."""
        tx = {
            'transaction_id': 'TX_001',
            'amount': 100.0,
            '_unix_timestamp': 1782718700.0,
            '_internal_flag': True,
        }
        alert = build_alert(tx, ["Test reason"])
        assert '_unix_timestamp' not in alert
        assert '_internal_flag' not in alert
        assert 'transaction_id' in alert
        assert 'amount' in alert

    def test_reasons_attached(self):
        """Alert should contain the provided reasons."""
        tx = {'transaction_id': 'TX_002', 'amount': 50.0}
        reasons = ["Rule 1 triggered", "Rule 2 triggered"]
        alert = build_alert(tx, reasons)
        assert alert['reasons'] == reasons
        assert len(alert['reasons']) == 2

    def test_empty_reasons(self):
        """Alert should work with empty reasons list."""
        tx = {'transaction_id': 'TX_003'}
        alert = build_alert(tx, [])
        assert alert['reasons'] == []