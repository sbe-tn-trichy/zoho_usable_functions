import unittest
from unittest.mock import patch, MagicMock
from zoho_usable_functions.credit_memos.processor import (
    parse_polycab_credit_memo,
    resolve_vendor_id,
    resolve_account_id,
    create_vendor_credit_from_pdf,
    upload_vendor_credit_attachment,
    upload_to_workdrive
)

class TestCreditMemoProcessor(unittest.TestCase):
    @patch("os.path.exists")
    @patch("pdfplumber.open")
    def test_parse_polycab_credit_memo(self, mock_plumber_open, mock_exists):
        mock_exists.return_value = True
        
        # Mock pdfplumber structures
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_plumber_open.return_value.__enter__.return_value = mock_pdf
        mock_pdf.pages = [mock_page]
        
        mock_page.extract_text.return_value = """
        POLYCAB INDIA LIMITED
        Credit Note
        Buyer's details / Place of Supply: Code Customer PO Number : Credit Note No :
        BHARATH DISTRIBUTORS Customer PO Date : Credit Note Date : 03-MAR-26
        Consignee's details / Place of Delivery: AR Invoice Number : 2603211538
        BHARATH DISTRIBUTORS Code Invoice Date : 03-MAR-2026
        Sr. CGST
        HSN/SAC Item Code Description UOM Rate/ Unit Qty Freight Amount Rs. CGST Amnt SGST Rate SGST Amnt Total Value
        1 94054900 LDO0115087 Scintillate Slim Integral LED Downlight 5W 6500K NOS 64.91 1 0 64.91 9.00 5.84 9% 5.84 76.59
        TOTAL 108896.82
        (Rupees One Lakh Eight Thousand Eight Hundred Ninety Six and paise Eighty Two only) For POLYCAB INDIA LIMITED
        """
        
        details = parse_polycab_credit_memo("dummy_memo.pdf")
        
        self.assertEqual(details["vendor_credit_number"], "2603211538")
        self.assertEqual(details["date"], "2026-03-03")
        self.assertEqual(details["amount"], 108896.82)
        self.assertTrue("Scintillate Slim Integral" in details["description"])

    def test_resolve_vendor_id(self):
        books_client = MagicMock()
        books_client.contacts.list.return_value = {
            "contacts": [{"contact_id": "resolved_vendor_999"}]
        }
        
        vendor_id = resolve_vendor_id(books_client, "Polycab")
        self.assertEqual(vendor_id, "resolved_vendor_999")
        books_client.contacts.list.assert_called_once_with(params={"contact_name": "Polycab"})

    def test_resolve_account_id(self):
        books_client = MagicMock()
        books_client.chart_of_accounts.list.return_value = {
            "chartofaccounts": [
                {"account_id": "acc_01", "account_name": "Office Supplies"},
                {"account_id": "acc_02", "account_name": "Polycab Scheme - Expense"}
            ]
        }
        
        account_id = resolve_account_id(books_client, "Polycab Scheme - Expense")
        self.assertEqual(account_id, "acc_02")

    @patch("zoho_usable_functions.credit_memos.processor.resolve_bill_id_by_number")
    @patch("zoho_usable_functions.credit_memos.processor.parse_polycab_credit_memo")
    @patch("zoho_usable_functions.credit_memos.processor.resolve_vendor_id")
    @patch("zoho_usable_functions.credit_memos.processor.resolve_item_id")
    def test_create_vendor_credit_from_pdf(self, mock_resolve_item, mock_resolve_vend, mock_parse, mock_resolve_bill):
        books_client = MagicMock()
        mock_parse.return_value = {
            "vendor_name": "Polycab India Limited",
            "vendor_credit_number": "2603233393",
            "date": "2026-03-31",
            "amount": 810.31,
            "description": "SG/SPECIAL SCHEME",
            "raw_text": "Original Tax Inv. No. : \n"
        }
        mock_resolve_vend.return_value = "vendor_99"
        mock_resolve_item.return_value = "item_123"
        books_client.request.return_value = {
            "vendorcredit": {"vendor_credit_id": "vc_100"}
        }
        
        # Test Case 1: No bill number in PDF (registered type and out of scope tax)
        res = create_vendor_credit_from_pdf(books_client, "dummy.pdf")
        self.assertEqual(res["vendor_credit_id"], "vc_100")
        
        books_client.request.assert_called_once()
        call_args = books_client.request.call_args
        payload = call_args[1]['json']
        self.assertEqual(payload["vendor_id"], "vendor_99")
        self.assertEqual(payload["vendor_credit_number"], "2603233393")
        self.assertEqual(payload["reference_invoice_type"], "registered")
        self.assertNotIn("bill_id", payload)
        self.assertEqual(payload["line_items"][0]["item_id"], "item_123")
        self.assertEqual(payload["line_items"][0]["rate"], 810.31)
        self.assertEqual(payload["line_items"][0]["gst_treatment_code"], "out_of_scope")
        self.assertNotIn("tax_id", payload["line_items"][0])
        
        # Test Case 2: Bill number explicitly in PDF
        books_client.request.reset_mock()
        mock_parse.return_value["raw_text"] = "Original Tax Inv. No. : BILL999\n"
        mock_resolve_bill.return_value = "bill_777"
        
        res = create_vendor_credit_from_pdf(books_client, "dummy.pdf")
        books_client.request.assert_called_once()
        mock_resolve_bill.assert_called_once_with(books_client, "vendor_99", "BILL999")
        payload = books_client.request.call_args[1]['json']
        self.assertEqual(payload["bill_id"], "bill_777")
        self.assertNotIn("reference_invoice_type", payload)

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_upload_vendor_credit_attachment(self, mock_open, mock_exists):
        mock_exists.return_value = True
        books_client = MagicMock()
        books_client.request.return_value = {"status": "success"}
        
        res = upload_vendor_credit_attachment(books_client, "vc_100", "dummy.pdf")
        self.assertEqual(res["status"], "success")
        books_client.request.assert_called_once()

    def test_upload_to_workdrive(self):
        wd_client = MagicMock()
        wd_client.files.upload.return_value = {"data": [{"id": "wd_file_111"}]}
        
        res = upload_to_workdrive(wd_client, "folder_123", "dummy.pdf")
        self.assertEqual(res["data"][0]["id"], "wd_file_111")
        wd_client.files.upload.assert_called_once_with("folder_123", "dummy.pdf")
