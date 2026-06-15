import unittest
from unittest.mock import patch, MagicMock
from zoho_usable_functions.reconciliation.gstr2b import (
    amt,
    parse_date,
    load_gstr2b_csv,
    parse_gstr2_report,
    reconcile_gstr2b_with_books,
    clean_gstr2b_xlsx
)

class TestGstr2b(unittest.TestCase):
    def test_amt(self):
        self.assertEqual(amt("1,234.50"), 1234.50)
        self.assertEqual(amt(""), 0.0)
        self.assertEqual(amt(None), 0.0)
        self.assertEqual(amt("abc"), 0.0)
        
    def test_parse_date(self):
        self.assertEqual(parse_date("15/04/2025"), "2025-04-15")
        self.assertEqual(parse_date("invalid"), "invalid")
        
    @patch("builtins.open")
    @patch("csv.DictReader")
    @patch("os.path.exists")
    def test_load_gstr2b_csv(self, mock_exists, mock_reader, mock_open):
        mock_exists.return_value = True
        mock_reader.return_value = [
            {
                "GSTIN of supplier": "27AAAAA1111A1Z1",
                "Trade/Legal name": "Supplier A",
                "Document Type": "Invoice",
                "Document Number": "INV-001",
                "Document Date": "15/04/2025",
                "Document Value (₹)": "1,180.00",
                "Taxable Value (₹)": "1,000.00",
                "Integrated Tax(₹)": "180.00",
                "Central Tax(₹)": "0.00",
                "State/UT Tax(₹)": "0.00",
                "ITC Availability": "Yes"
            }
        ]
        
        rows = load_gstr2b_csv("dummy.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(rows[0]["doc_number"], "INV-001")
        self.assertEqual(rows[0]["doc_date"], "2025-04-15")
        self.assertEqual(rows[0]["taxable_value"], 1000.00)
        
    @patch("openpyxl.load_workbook")
    @patch("os.path.exists")
    def test_parse_gstr2_report(self, mock_exists, mock_load_wb):
        mock_exists.return_value = True
        
        mock_wb = MagicMock()
        mock_load_wb.return_value = mock_wb
        mock_wb.sheetnames = ["b2b"]
        
        mock_sheet = MagicMock()
        mock_wb.__getitem__.return_value = mock_sheet
        mock_sheet.max_row = 3
        
        mock_values = {
            (3, 2): "Supplier A",
            (3, 3): "INV-001",
            (3, 5): 1180.00,
            (3, 8): 1000.00,
            (3, 10): 0.00,
            (3, 11): 0.00,
            (3, 12): 180.00
        }
        mock_sheet.cell.side_effect = lambda r, c: MagicMock(value=mock_values.get((r, c)))
        
        docs = parse_gstr2_report("dummy.xlsx")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs["INV-001"]["vendor_name"], "Supplier A")
        self.assertEqual(docs["INV-001"]["sub_total"], 1000.00)
        
    @patch("zoho_usable_functions.reconciliation.gstr2b.load_gstr2b_csv")
    @patch("zoho_usable_functions.reconciliation.gstr2b.parse_gstr2_report")
    @patch("os.path.exists")
    def test_reconcile_gstr2b_with_books(self, mock_exists, mock_parse_report, mock_load_csv):
        mock_exists.return_value = True
        
        mock_load_csv.return_value = [
            {
                "gstin": "27AAAAA1111A1Z1",
                "supplier": "Supplier A",
                "doc_type": "Invoice",
                "doc_number": "INV-001",
                "doc_date": "2025-04-15",
                "doc_value": 1180.00,
                "taxable_value": 1000.00,
                "igst": 180.00,
                "cgst": 0.00,
                "sgst": 0.00,
                "itc": "Yes"
            }
        ]
        
        mock_parse_report.return_value = {
            "INV-001": {
                "vendor_name": "Supplier A",
                "sub_total": 1000.00,
                "tax_total": 180.00,
                "total": 1180.00
            }
        }
        
        books_client = MagicMock()
        books_client.request.return_value = {
            "contacts": [{"contact_id": "vid_abc", "contact_name": "Supplier A"}]
        }
        
        results = reconcile_gstr2b_with_books(
            books_client=books_client,
            gstr2b_csv_path="dummy.csv",
            from_date="2025-04-01",
            to_date="2025-04-30",
            amount_tolerance=1.0,
            temp_xlsx_path="dummy.xlsx"
        )
        
        self.assertEqual(len(results["matched_invoices"]), 1)
        self.assertEqual(results["matched_invoices"][0]["books"]["sub_total"], 1000.00)
        self.assertEqual(results["gst_rows_count"], 1)

    @patch("zoho_usable_functions.reconciliation.gstr2b.load_gstr2b_csv")
    @patch("zoho_usable_functions.reconciliation.gstr2b.parse_gstr2_report")
    @patch("os.path.exists")
    def test_reconcile_gstr2b_with_books_auto_dates(self, mock_exists, mock_parse_report, mock_load_csv):
        mock_exists.return_value = True
        
        mock_load_csv.return_value = [
            {
                "gstin": "27AAAAA1111A1Z1",
                "supplier": "Supplier A",
                "doc_type": "Invoice",
                "doc_number": "INV-001",
                "doc_date": "2025-04-15",
                "doc_value": 1180.00,
                "taxable_value": 1000.00,
                "igst": 180.00,
                "cgst": 0.00,
                "sgst": 0.00,
                "itc": "Yes"
            }
        ]
        
        mock_parse_report.return_value = {
            "INV-001": {
                "vendor_name": "Supplier A",
                "sub_total": 1000.00,
                "tax_total": 180.00,
                "total": 1180.00
            }
        }
        
        books_client = MagicMock()
        books_client.request.return_value = {
            "contacts": [{"contact_id": "vid_abc", "contact_name": "Supplier A"}]
        }
        
        results = reconcile_gstr2b_with_books(
            books_client=books_client,
            gstr2b_csv_path="dummy.csv"
        )
        
        self.assertEqual(len(results["matched_invoices"]), 1)
        self.assertEqual(results["gst_rows_count"], 1)
        
        # Verify that download was triggered with auto-calculated start and end dates
        args, kwargs = books_client.gst.download_gstr_inward_supplies.call_args
        self.assertEqual(kwargs['params']['from_date'], "2025-04-01")
        self.assertEqual(kwargs['params']['to_date'], "2025-04-30")

    @patch("zoho_usable_functions.reconciliation.gstr2b.load_gstr2b_csv")
    @patch("zoho_usable_functions.reconciliation.gstr2b.parse_gstr2_report")
    @patch("os.path.isdir")
    @patch("glob.glob")
    @patch("os.path.exists")
    def test_reconcile_gstr2b_with_books_directory(self, mock_exists, mock_glob, mock_isdir, mock_parse_report, mock_load_csv):
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_glob.return_value = ["dir/file1.csv", "dir/file2.csv"]
        
        mock_load_csv.side_effect = [
            [
                {
                    "gstin": "27AAAAA1111A1Z1",
                    "supplier": "Supplier A",
                    "doc_type": "Invoice",
                    "doc_number": "INV-001",
                    "doc_date": "2025-04-15",
                    "doc_value": 1180.00,
                    "taxable_value": 1000.00,
                    "igst": 180.00,
                    "cgst": 0.00,
                    "sgst": 0.00,
                    "itc": "Yes"
                }
            ],
            [
                {
                    "gstin": "27AAAAA1111A1Z1",
                    "supplier": "Supplier A",
                    "doc_type": "Invoice",
                    "doc_number": "INV-002",
                    "doc_date": "2025-04-20",
                    "doc_value": 2360.00,
                    "taxable_value": 2000.00,
                    "igst": 360.00,
                    "cgst": 0.00,
                    "sgst": 0.00,
                    "itc": "Yes"
                }
            ]
        ]
        
        mock_parse_report.return_value = {
            "INV-001": {
                "vendor_name": "Supplier A",
                "sub_total": 1000.00,
                "tax_total": 180.00,
                "total": 1180.00
            },
            "INV-002": {
                "vendor_name": "Supplier A",
                "sub_total": 2000.00,
                "tax_total": 360.00,
                "total": 2360.00
            }
        }
        
        books_client = MagicMock()
        books_client.request.return_value = {
            "contacts": [{"contact_id": "vid_abc", "contact_name": "Supplier A"}]
        }
        
        results = reconcile_gstr2b_with_books(
            books_client=books_client,
            gstr2b_csv_path="dummy_dir"
        )
        
        self.assertEqual(len(results["matched_invoices"]), 2)
        self.assertEqual(results["gst_rows_count"], 2)
        
        # Verify that download was triggered with auto-calculated start and end dates
        args, kwargs = books_client.gst.download_gstr_inward_supplies.call_args
        self.assertEqual(kwargs['params']['from_date'], "2025-04-01")
        self.assertEqual(kwargs['params']['to_date'], "2025-04-30")

    @patch("openpyxl.load_workbook")
    @patch("builtins.open")
    @patch("os.makedirs")
    def test_clean_gstr2b_xlsx(self, mock_makedirs, mock_open, mock_load_workbook):
        mock_wb = MagicMock()
        mock_load_workbook.return_value = mock_wb
        mock_wb.sheetnames = ["B2B"]
        
        mock_sheet = MagicMock()
        mock_wb.__getitem__.return_value = mock_sheet
        mock_sheet.max_row = 2
        
        # Simulating finding the header row in the first 15 rows
        # Let's say row 1 contains headers
        mock_headers = [
            "GSTIN of supplier", "Trade/Legal name", "Document Type", "Document Number", 
            "Document Date", "Document Value (₹)", "Taxable Value (₹)", "Integrated Tax(₹)", 
            "Central Tax(₹)", "State/UT Tax(₹)", "ITC Availability"
        ]
        
        def cell_val(r, c):
            if r == 1:
                if c <= len(mock_headers):
                    return mock_headers[c-1]
            elif r == 2:
                # Row 2 values
                vals = [
                    "27AAAAA1111A1Z1", "Supplier A", "Invoice", "INV-001", 
                    "15/04/2025", "1180.00", "1000.00", "180.00", "0.00", "0.00", "Y"
                ]
                if c <= len(vals):
                    return vals[c-1]
            return None
            
        mock_sheet.cell.side_effect = lambda r, c: MagicMock(value=cell_val(r, c))
        
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        clean_gstr2b_xlsx("dummy.xlsx", "dummy.csv")
        
        # Verify open and write were called
        mock_open.assert_called_once_with("dummy.csv", "w", newline="", encoding="utf-8")
        mock_makedirs.assert_called_once()
