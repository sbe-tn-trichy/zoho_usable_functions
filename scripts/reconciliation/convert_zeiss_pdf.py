#!/usr/bin/env python3
"""
Parse Carl Zeiss ledger PDFs in input_files/zeiss/ledgers/ and consolidate them into a CSV file.

Usage:
    uv run python scripts/reconciliation/convert_zeiss_pdf.py
"""
import os
import sys
import logging

# Inject src directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from zoho_usable_functions.reconciliation.zeiss_pdf import consolidate_zeiss_statements

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("convert_zeiss_pdf")

def main():
    workspace_dir = "/Users/vak/Documents/workspace/zoho_usable_functions"
    ledgers_dir = os.path.join(workspace_dir, "input_files/zeiss/ledgers")
    output_path = os.path.join(workspace_dir, "input_files/zeiss/Consolidated_Zeiss_Statements_2024_2025.csv")
    
    try:
        deduped_rows = consolidate_zeiss_statements(ledgers_dir, output_path)
        logger.info(f"Consolidated CSV created with {len(deduped_rows)} transactions at: {output_path}")
    except Exception as e:
        logger.error(f"Error during consolidation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
