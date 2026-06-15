"""
Check all Polycab vendor credits for any location other than Sri Bharath Electricals.
"""
import sys
import os

# Inject src directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.credit_memos.processor import check_vendor_credits_location

def main():
    setup_logging()

    EXPECTED_LOCATION_ID = Config.EXPECTED_LOCATION_ID
    EXPECTED_LOCATION_NAME = Config.EXPECTED_LOCATION_NAME
    VENDOR_ID = Config.POLYCAB_VENDOR_ID

    try:
        client = get_books_client()
    except Exception as e:
        print(f"Error: Could not initialize Zoho Books client: {e}")
        sys.exit(1)

    print(f"Auditing vendor credits for Polycab (vendor_id={VENDOR_ID})...")
    
    try:
        results = check_vendor_credits_location(
            books_client=client,
            vendor_id=VENDOR_ID,
            expected_location_id=EXPECTED_LOCATION_ID
        )
    except Exception as e:
        print(f"Audit failed with error: {e}")
        sys.exit(1)

    mismatched = results["mismatched"]
    no_location = results["no_location"]
    correct_count = len(results["correct"])
    total_checked = results["total_checked"]

    print(f"\n{'='*70}")
    print(f"LOCATION CHECK RESULTS")
    print(f"{'='*70}")
    print(f"  Expected Location : {EXPECTED_LOCATION_NAME} (ID: {EXPECTED_LOCATION_ID})")
    print(f"  Total VCs checked : {total_checked}")
    print(f"  Correctly located : {correct_count}")
    print(f"  Wrong location    : {len(mismatched)}")
    print(f"  No location set   : {len(no_location)}")

    if mismatched:
        print(f"\n{'='*70}")
        print(f"VCs WITH WRONG LOCATION ({len(mismatched)}):")
        print(f"{'='*70}")
        print(f"  {'VC Number':<25} {'Date':<12} {'Amount':<14} {'Status':<10} {'Location Name':<25} {'Location ID'}")
        print(f"  {'-'*110}")
        for vc in mismatched:
            print(f"  {vc['number']:<25} {vc['date']:<12} {str(vc['amount']):<14} {vc['status']:<10} {vc['location_name']:<25} {vc['location_id']}")
    else:
        print(f"\n✅ All audited vendor credits have the correct location: {EXPECTED_LOCATION_NAME}")

    if no_location:
        print(f"\n{'='*70}")
        print(f"VCs WITH NO LOCATION SET ({len(no_location)}):")
        print(f"{'='*70}")
        print(f"  {'VC Number':<25} {'Date':<12} {'Amount':<14} {'Status'}")
        print(f"  {'-'*70}")
        for vc in no_location:
            print(f"  {vc['number']:<25} {vc['date']:<12} {str(vc['amount']):<14} {vc['status']}")

if __name__ == "__main__":
    main()
