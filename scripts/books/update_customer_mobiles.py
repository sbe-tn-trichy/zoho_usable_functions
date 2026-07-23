import os
import sys
import argparse
import time
import pandas as pd
from typing import Dict, Any, List

# Insert project src directory to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_books_client, fetch_access_tokens
from zoho_usable_functions.core.customers import normalize_phone_number

def main():
    parser = argparse.ArgumentParser(description="Update customer mobile numbers to standard format '+91-XXXXXXXXXX'.")
    parser.add_argument("--execute", action="store_true", help="Perform the actual updates in Zoho Books.")
    args = parser.parse_args()

    csv_path = "output/books/incorrect_phone_customers.csv"
    if not os.path.exists(csv_path):
        print(f"❌ Target list file does not exist: {csv_path}")
        print("Please run scripts/books/fetch_active_customers.py first.")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("✅ No incorrect customers to process in CSV.")
        return

    print(f"Loaded {len(df)} target incorrect customers from: {csv_path}")
    
    try:
        tokens = fetch_access_tokens()
        client = get_books_client(token=tokens["books"])

        print("Fetching all contact persons to resolve primary contact person IDs...")
        all_persons = []
        page = 1
        while True:
            res = client.request('GET', 'contacts/contactpersons', params={'page': page, 'per_page': 200})
            persons = res.get('contact_persons', [])
            all_persons.extend(persons)
            if not res.get('page_context', {}).get('has_more_page', False):
                break
            page += 1
        print(f"Retrieved {len(all_persons)} total contact persons.")

        # Build map: contact_id -> primary contact_person_id
        primary_person_map = {}
        for p in all_persons:
            c_id = p.get("contact_id")
            cp_id = p.get("contact_person_id")
            if c_id and cp_id and p.get("is_primary_contact"):
                primary_person_map[c_id] = cp_id

        print("\nAnalyzing mobile numbers for updates...")
        to_update = []
        for _, row in df.iterrows():
            c_id = str(row["contact_id"])
            c_name = row["contact_name"]
            mobile_raw = str(row["mobile"]) if pd.notna(row["mobile"]) else ""
            
            if not mobile_raw or mobile_raw.strip() == "" or mobile_raw.strip() == "nan":
                continue

            normalized = normalize_phone_number(mobile_raw)
            # Verify if it was normalized to standard format
            import re
            if re.match(r"^\+91-\d{10}$", normalized):
                cp_id = primary_person_map.get(c_id)
                if cp_id:
                    to_update.append({
                        "contact_id": c_id,
                        "contact_name": c_name,
                        "contact_person_id": cp_id,
                        "mobile_raw": mobile_raw,
                        "mobile_new": normalized
                    })
                else:
                    print(f"⚠️ Primary contact person not found for contact: {c_name} (ID: {c_id})")
            else:
                print(f"ℹ️ Skipping (cannot normalize): {c_name} -> Mobile: '{mobile_raw}'")

        print(f"\nFound {len(to_update)} normalizable customer mobile updates out of {len(df)} total incorrect rows.")

        if not to_update:
            print("Nothing to update.")
            return

        if not args.execute:
            print("\n*** DRY RUN MODE ***")
            print("Run with --execute to perform actual updates in Zoho Books.")
            for item in to_update[:15]:
                print(f"  - Would update '{item['contact_name']}' mobile: '{item['mobile_raw']}' -> '{item['mobile_new']}'")
            if len(to_update) > 15:
                print(f"  ... and {len(to_update) - 15} more.")
            return

        print("\n*** PRODUCTION EXECUTION MODE ***")
        success_count = 0
        error_count = 0

        for i, item in enumerate(to_update, 1):
            c_name = item["contact_name"]
            cp_id = item["contact_person_id"]
            mobile_new = item["mobile_new"]
            
            print(f"[{i}/{len(to_update)}] Updating '{c_name}'...")
            try:
                endpoint = f"contacts/contactpersons/{cp_id}"
                client.request('PUT', endpoint, json={"mobile": mobile_new})
                print(f"  ✅ Updated successfully to: {mobile_new}")
                success_count += 1
            except Exception as ex:
                print(f"  ❌ Error: {ex}")
                error_count += 1

            # Request pacing to satisfy API limits
            time.sleep(1.0)

        print(f"\nExecution complete: {success_count} updated successfully, {error_count} errors.")
        
        # Delete local customer cache file so that next fetch retrieves fresh updated data
        cache_path = "output/books/raw_contacts_cache.json"
        if os.path.exists(cache_path):
            os.remove(cache_path)
            print("Deleted local cache file to force fresh sync on next run.")

    except Exception as e:
        print(f"❌ Error during update execution: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
