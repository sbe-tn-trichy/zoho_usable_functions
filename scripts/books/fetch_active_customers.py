import os
import sys
import json
import argparse
import pandas as pd
from typing import Dict, Any, List

# Insert project src directory to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_books_client, fetch_access_tokens
from zoho_usable_functions import fetch_active_customers

def main():
    parser = argparse.ArgumentParser(description="Fetch and filter active customers by mobile format.")
    parser.add_argument("--refresh", action="store_true", help="Force refresh of customer data from Zoho Books API, bypassing local cache.")
    args = parser.parse_args()

    os.makedirs("output/books", exist_ok=True)
    cache_path = "output/books/raw_contacts_cache.json"
    customers = []

    try:
        # Check if local cache exists and we aren't forcing a refresh
        if os.path.exists(cache_path) and not args.refresh:
            print(f"🔄 Loading raw active customers from local cache: {cache_path}")
            with open(cache_path, "r", encoding="utf-8") as f:
                customers = json.load(f)
            print(f"Loaded {len(customers)} customers from cache.")
        else:
            print("Initiating Zoho Books Active Customers Fetch from API...")
            tokens = fetch_access_tokens()
            client = get_books_client(token=tokens["books"])
            
            # Fetch raw customers (do NOT normalize at this step)
            customers = fetch_active_customers(client, normalize=False)
            print(f"Retrieved {len(customers)} active customers from Zoho API.")
            
            # Save raw customers to cache
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(customers, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved raw customers to cache file: {cache_path}")

        if not customers:
            print("No active customers found.")
            return

        # Prepare records for classification
        records = []
        for c in customers:
            records.append({
                "contact_id": c.get("contact_id"),
                "contact_number": c.get("contact_number"),
                "contact_name": c.get("contact_name"),
                "company_name": c.get("company_name"),
                "status": c.get("status"),
                "phone": c.get("phone"),
                "mobile": c.get("mobile"),
                "email": c.get("email"),
                "gst_no": c.get("gst_no"),
                "pan_no": c.get("pan_no"),
                "place_of_contact": c.get("place_of_contact"),
                "place_of_contact_formatted": c.get("place_of_contact_formatted"),
                "outstanding_receivable_amount": c.get("outstanding_receivable_amount"),
                "unused_credits_receivable_amount": c.get("unused_credits_receivable_amount"),
                "district": c.get("cf_district"),
                "branch": c.get("cf_b_name"),
                "jurisdiction": c.get("cf_jurisdiction")
            })

        # Filter strictly on raw mobile format "+91-XXXXXXXXXX"
        import re
        pattern = re.compile(r"^\+91-\d{10}$")
        
        def is_valid_mobile(val):
            if not val or str(val).strip() == "" or str(val).strip() == "nan":
                return True
            return bool(pattern.match(str(val).strip()))

        valid_records = []
        incorrect_records = []

        for r in records:
            m = r["mobile"]
            if is_valid_mobile(m):
                valid_records.append(r)
            else:
                incorrect_records.append(r)

        # Write Valid to CSV
        valid_csv_path = "output/books/active_customers.csv"
        df_valid = pd.DataFrame(valid_records)
        df_valid.to_csv(valid_csv_path, index=False)
        print(f"✅ Exported {len(valid_records)} valid active customers to: {valid_csv_path}")

        # Write Incorrect to CSV
        incorrect_csv_path = "output/books/incorrect_phone_customers.csv"
        df_incorrect = pd.DataFrame(incorrect_records)
        df_incorrect.to_csv(incorrect_csv_path, index=False)
        print(f"⚠️ Exported {len(incorrect_records)} customers with incorrect mobile format to: {incorrect_csv_path}")
        
    except Exception as e:
        print(f"❌ Error processing active customers: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
