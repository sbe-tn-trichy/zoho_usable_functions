from unittest.mock import MagicMock

from zoho_usable_functions import find_customers_with_unused_credits


def test_find_customers_with_unused_credits_filters_and_sorts():
    books_client = MagicMock()
    books_client.contacts.list_all.return_value = [
        {
            "contact_id": "cust_1",
            "contact_number": "C001",
            "contact_name": "Alpha Traders",
            "company_name": "Alpha Traders Pvt Ltd",
            "contact_type": "customer",
            "status": "active",
            "phone": "111",
            "mobile": "9999999999",
            "email": "alpha@example.com",
            "gst_no": "GST1",
            "pan_no": "PAN1",
            "place_of_contact": "India",
            "place_of_contact_formatted": "India",
            "outstanding_receivable_amount": "1000.00",
            "unused_credits_receivable_amount": "250.50",
            "cf_district": "District A",
            "cf_b_name": "Branch A",
            "cf_jurisdiction": "Jurisdiction A",
        },
        {
            "contact_id": "cust_2",
            "contact_number": "C002",
            "contact_name": "Beta Supplies",
            "company_name": "Beta Supplies LLP",
            "contact_type": "customer",
            "status": "active",
            "phone": "222",
            "mobile": "8888888888",
            "email": "beta@example.com",
            "gst_no": "GST2",
            "pan_no": "PAN2",
            "place_of_contact": "India",
            "place_of_contact_formatted": "India",
            "outstanding_receivable_amount": 500,
            "unused_credits_receivable_amount": 0,
            "cf_district": "District B",
            "cf_b_name": "Branch B",
            "cf_jurisdiction": "Jurisdiction B",
        },
        {
            "contact_id": "cust_3",
            "contact_number": "C003",
            "contact_name": "Gamma Retail",
            "company_name": "Gamma Retail",
            "contact_type": "customer",
            "status": "active",
            "phone": "333",
            "mobile": "7777777777",
            "email": "gamma@example.com",
            "gst_no": "GST3",
            "pan_no": "PAN3",
            "place_of_contact": "India",
            "place_of_contact_formatted": "India",
            "outstanding_receivable_amount": "1500.00",
            "unused_credits_receivable_amount": "1,000.00",
            "cf_district": "District C",
            "cf_b_name": "Branch C",
            "cf_jurisdiction": "Jurisdiction C",
        },
    ]

    results = find_customers_with_unused_credits(books_client)

    assert results["summary"]["total_customers_checked"] == 3
    assert results["summary"]["customers_with_unused_credits"] == 2
    assert results["summary"]["total_unused_credit_amount"] == 1250.5
    assert [row["contact_id"] for row in results["customers"]] == ["cust_3", "cust_1"]
    assert results["customers"][0]["unused_credits_receivable_amount"] == 1000.0
    books_client.contacts.list_all.assert_called_once_with(params={"status": "active"})


def test_find_customers_with_unused_credits_min_threshold():
    books_client = MagicMock()
    books_client.contacts.list_all.return_value = [
        {
            "contact_id": "cust_1",
            "contact_name": "Small Credit",
            "company_name": "",
            "contact_type": "customer",
            "status": "active",
            "outstanding_receivable_amount": 0,
            "unused_credits_receivable_amount": 25,
        },
        {
            "contact_id": "cust_2",
            "contact_name": "Large Credit",
            "company_name": "",
            "contact_type": "customer",
            "status": "active",
            "outstanding_receivable_amount": 0,
            "unused_credits_receivable_amount": 100,
        },
    ]

    results = find_customers_with_unused_credits(books_client, min_unused_credit_amount=50)

    assert results["summary"]["customers_with_unused_credits"] == 1
    assert results["customers"][0]["contact_id"] == "cust_2"
