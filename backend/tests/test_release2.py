"""Test suite for Release 2 Features:
- Purchase File Importer (Feature 2)
- Udhaar Agent & Reminder logic (Feature 6)
"""
import unittest
from datetime import datetime, timezone, timedelta
from app.importer import (
    normalize_name,
    normalize_unit,
    detect_columns,
    parse_csv_content,
    match_and_preview,
    fuzzy_ratio
)
from app.udhaar_agent import (
    draft_reminder,
    classify_reply,
    find_overdue_bills
)

class TestRelease2(unittest.TestCase):

    def test_normalize_name(self):
        self.assertEqual(normalize_name("  Tata Salt 1kg  "), "tata salt 1kg")
        self.assertEqual(normalize_name("Fortune Oil (1L)"), "fortune oil 1l")
        self.assertEqual(normalize_name("Sugar / Cheeni"), "sugar cheeni")

    def test_normalize_unit(self):
        self.assertEqual(normalize_unit("Kgs"), "kg")
        self.assertEqual(normalize_unit("किलो"), "kg")
        self.assertEqual(normalize_unit("Pkt"), "piece")
        self.assertEqual(normalize_unit("Ltr"), "litre")

    def test_column_detection(self):
        headers = ["Item Name", "Quantity", "Purchase Rate", "Unit", "MRP"]
        cols = detect_columns(headers)
        self.assertEqual(cols["name"], 0)
        self.assertEqual(cols["qty"], 1)
        self.assertEqual(cols["purchase_price"], 2)
        self.assertEqual(cols["unit"], 3)
        self.assertEqual(cols["selling_price"], 4)

    def test_csv_parser_formula_injection_guard(self):
        csv_data = "=cmd|' /C calc'!A0,10,50\n+Sugar,5,40"
        headers, data = parse_csv_content(csv_data)
        # Verify formula prefixes stripped
        self.assertFalse(data[0][0].startswith("="))
        self.assertFalse(data[0][1].startswith("+"))

    def test_import_matching_existing_and_new(self):
        existing = [
            {"id": "item-1", "name": "Sugar", "price": 44, "stock": 10, "unit": "kg"},
            {"id": "item-2", "name": "Basmati Rice", "price": 90, "stock": 25, "unit": "kg"}
        ]
        aliases = [
            {"id": "a-1", "item_id": "item-1", "normalized_alias": "cheeni"}
        ]
        rows = [
            ["Cheeni", "20", "38", "kg", "45"],          # Matches alias -> item-1
            ["basmati rice", "10", "75", "kg", "95"],     # Exact match -> item-2
            ["Toor Dal", "15", "120", "kg", "140"]        # New item
        ]
        col_map = {"name": 0, "qty": 1, "purchase_price": 2, "unit": 3, "selling_price": 4}
        preview = match_and_preview(rows, col_map, existing, aliases)

        self.assertEqual(len(preview), 3)
        self.assertEqual(preview[0]["status"], "update")
        self.assertEqual(preview[0]["matched_item_id"], "item-1")
        self.assertEqual(preview[1]["status"], "update")
        self.assertEqual(preview[1]["matched_item_id"], "item-2")
        self.assertEqual(preview[2]["status"], "new")

    def test_udhaar_draft_tones(self):
        # Tone 1
        t1 = draft_reminder("Ramesh", "Gupta Store", 1250, 7, level=1, language="hinglish")
        self.assertIn("Ramesh", t1)
        self.assertIn("1,250", t1)
        self.assertIn("Gupta Store", t1)

        # Tone 2
        t2 = draft_reminder("Suresh", "Mittal Store", 500, 14, level=2, language="english")
        self.assertIn("overdue", t2.lower())

        # Tone 3
        t3 = draft_reminder("Mohan", "Sharma Store", 2000, 21, level=3, language="hindi")
        self.assertIn("तुरंत", t3)

    def test_reply_classification(self):
        # Dispute
        r1 = classify_reply("Mera hisaab galat hai, maine de diya tha")
        self.assertTrue(r1["needs_attention"])
        self.assertEqual(r1["intent"], "dispute_or_claim")

        # Promise
        r2 = classify_reply("Haan bhai kal sham tak bhej dunga")
        self.assertFalse(r2["needs_attention"])
        self.assertEqual(r2["intent"], "promise_to_pay")

    def test_overdue_scan_logic(self):
        now = datetime.now(timezone.utc)
        bills = [
            {"id": "b-1", "pay_method": "Udhaar", "paid": False, "total": 1000, "billed_at": (now - timedelta(days=10)).isoformat(), "cust_name": "Raju"},
            {"id": "b-2", "pay_method": "Udhaar", "paid": False, "total": 500, "billed_at": (now - timedelta(days=2)).isoformat(), "cust_name": "Sonu"}, # Not overdue yet
            {"id": "b-3", "pay_method": "Cash", "paid": True, "total": 300, "billed_at": (now - timedelta(days=12)).isoformat(), "cust_name": "Monu"} # Cash
        ]
        settings = {"remind_after_days": 7}
        overdue = find_overdue_bills(bills, settings, {}, now)
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]["udhaar_id"], "b-1")

if __name__ == "__main__":
    unittest.main()
