from datetime import date, datetime
from unittest.mock import MagicMock
import pytest

from zoho_usable_functions import find_same_day_payment_anomalies

def test_find_same_day_payment_anomalies_no_anomalies():
    # Arrange
    books_client = MagicMock()
    # Mock list_all to return payments on different days
    books_client.customer_payments.list_all.return_value = [
        {
            "payment_id": "p1",
            "customer_id": "cust_1",
            "customer_name": "Customer One",
            "date": "2026-07-01",
            "amount": 100.0,
            "payment_number": "CP001",
            "payment_mode": "Cash",
            "reference_number": "REF001"
        },
        {
            "payment_id": "p2",
            "customer_id": "cust_1",
            "customer_name": "Customer One",
            "date": "2026-07-02",
            "amount": 150.0,
            "payment_number": "CP002",
            "payment_mode": "Card",
            "reference_number": "REF002"
        },
        {
            "payment_id": "p3",
            "customer_id": "cust_2",
            "customer_name": "Customer Two",
            "date": "2026-07-01",
            "amount": 200.0,
            "payment_number": "CP003",
            "payment_mode": "Cheque",
            "reference_number": "REF003"
        }
    ]

    # Act
    results = find_same_day_payment_anomalies(books_client)

    # Assert
    assert len(results["anomalies"]) == 0
    assert results["summary"]["total_payments_checked"] == 3
    assert results["summary"]["total_anomalies_found"] == 0
    books_client.customer_payments.list_all.assert_called_once_with(params={})

def test_find_same_day_payment_anomalies_detected():
    # Arrange
    books_client = MagicMock()
    # Mock list_all to return multiple payments on same day for cust_1
    books_client.customer_payments.list_all.return_value = [
        {
            "payment_id": "p1",
            "customer_id": "cust_1",
            "customer_name": "Customer One",
            "date": "2026-07-01",
            "amount": 100.0,
            "payment_number": "CP001",
            "payment_mode": "Cash",
            "reference_number": "REF001"
        },
        {
            "payment_id": "p2",
            "customer_id": "cust_1",
            "customer_name": "Customer One",
            "date": "2026-07-01",
            "amount": 150.0,
            "payment_number": "CP002",
            "payment_mode": "Card",
            "reference_number": "REF002"
        },
        {
            "payment_id": "p3",
            "customer_id": "cust_2",
            "customer_name": "Customer Two",
            "date": "2026-07-01",
            "amount": 200.0,
            "payment_number": "CP003",
            "payment_mode": "Cheque",
            "reference_number": "REF003"
        }
    ]

    # Act
    results = find_same_day_payment_anomalies(books_client)

    # Assert
    assert len(results["anomalies"]) == 1
    anomaly = results["anomalies"][0]
    assert anomaly["customer_id"] == "cust_1"
    assert anomaly["customer_name"] == "Customer One"
    assert anomaly["date"] == "2026-07-01"
    assert anomaly["payment_count"] == 2
    assert len(anomaly["payments"]) == 2
    assert anomaly["payments"][0]["payment_id"] == "p1"
    assert anomaly["payments"][1]["payment_id"] == "p2"
    assert results["summary"]["total_payments_checked"] == 3
    assert results["summary"]["total_anomalies_found"] == 1

def test_find_same_day_payment_anomalies_filters():
    # Arrange
    books_client = MagicMock()
    books_client.customer_payments.list_all.return_value = []

    # Act
    find_same_day_payment_anomalies(
        books_client,
        start_date=date(2026, 7, 1),
        end_date=datetime(2026, 7, 6, 12, 0),
        customer_id="cust_abc"
    )

    # Assert
    books_client.customer_payments.list_all.assert_called_once_with(
        params={
            "date_start": "2026-07-01",
            "date_end": "2026-07-06",
            "customer_id": "cust_abc"
        }
    )
