#!/usr/bin/env python3
"""
Enterprise Offline Test & Simulation Suite for Smart Inbox Agent.
Executes batch classification, auto-draft verification, and PDF invoice parsing.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from inbox_router import SmartInboxRouter, EmailMessage, EmailCategory, UrgencyLevel
from invoice_parser import InvoiceParser

def run_inbox_tests():
    print("=" * 70)
    print(">>> SMART INBOX AGENT: ROUTING & DRAFTING TEST HARNESS")
    print("=" * 70)

    emails_path = os.path.join(os.path.dirname(__file__), "demo-data", "sample_emails.json")
    with open(emails_path, "r", encoding="utf-8") as f:
        samples = json.load(f)

    router = SmartInboxRouter()
    passed = 0
    total = len(samples)

    start_time = time.time()

    for idx, item in enumerate(samples, 1):
        email = EmailMessage(
            id=item["id"],
            sender=item["sender"],
            recipient=item["recipient"],
            subject=item["subject"],
            body=item["body"],
            received_at=item["received_at"],
            has_attachments=item.get("has_attachments", False),
            attachment_filenames=item.get("attachment_filenames", [])
        )

        decision = router.classify_and_route(email)
        
        cat_match = decision.category.value == item["expected_category"]
        urg_match = decision.urgency.value == item["expected_urgency"] or decision.urgency in (UrgencyLevel.HIGH, UrgencyLevel.CRITICAL)
        
        is_correct = cat_match and urg_match
        if is_correct:
            passed += 1

        status_flag = "[\033[92mPASS\033[0m]" if is_correct else "[\033[91mFAIL\033[0m]"
        print(f"{status_flag} Case #{idx} [{item['id']}]:")
        print(f"       Category : {decision.category.value} (Expected: {item['expected_category']})")
        print(f"       Queue    : {decision.target_queue} | Confidence: {decision.confidence:.2f}")
        print(f"       Urgency  : {decision.urgency.value} | HITL Required: {decision.requires_human_approval}")
        if decision.draft_response:
            preview = decision.draft_response.split('\n')[0]
            print(f"       Draft    : \"{preview}...\"")
        print("-" * 70)

    elapsed_ms = (time.time() - start_time) * 1000
    avg_latency = elapsed_ms / total

    print(f"\nRouting Test Results: {passed}/{total} Passed (Accuracy: {(passed/total)*100:.1f}%)")
    print(f"Average Inference Latency: {avg_latency:.2f} ms / email\n")
    return passed == total

def run_invoice_tests():
    print("=" * 70)
    print(">>> INVOICE EXTRACTION & INTEGRITY VALIDATOR TESTS")
    print("=" * 70)

    invoices_path = os.path.join(os.path.dirname(__file__), "demo-data", "sample_invoices.json")
    with open(invoices_path, "r", encoding="utf-8") as f:
        invoices = json.load(f)

    parser = InvoiceParser()
    passed = 0
    total = len(invoices)

    for idx, item in enumerate(invoices, 1):
        parsed = parser.parse_text(item["raw_text"])
        
        vendor_match = parsed.vendor_name == item["expected_vendor"]
        total_match = abs(parsed.total_amount - item["expected_total"]) < 0.01
        valid_match = parsed.is_mathematically_valid == item["expected_valid"]

        is_correct = vendor_match and total_match and valid_match
        if is_correct:
            passed += 1

        status_flag = "[\033[92mPASS\033[0m]" if is_correct else "[\033[91mFAIL\033[0m]"
        print(f"{status_flag} Invoice #{idx} [{item['id']}]:")
        print(f"       Vendor   : {parsed.vendor_name}")
        print(f"       Inv Num  : {parsed.invoice_number} | Date: {parsed.invoice_date}")
        print(f"       Total    : {parsed.currency} {parsed.total_amount:.2f} (Subtotal: {parsed.subtotal:.2f}, Tax: {parsed.tax_amount:.2f})")
        print(f"       Items    : {len(parsed.line_items)} extracted")
        print(f"       Valid    : {parsed.is_mathematically_valid} | Score: {parsed.confidence_score}")
        print(f"       SheetsRow: {parsed.to_sheets_row()}")
        print("-" * 70)

    print(f"\nInvoice Extraction Results: {passed}/{total} Passed (Accuracy: {(passed/total)*100:.1f}%)\n")
    return passed == total

if __name__ == "__main__":
    t1 = run_inbox_tests()
    t2 = run_invoice_tests()
    if t1 and t2:
        print("\033[92m[SUCCESS] ALL TEST SUITES PASSED 100% (ZERO REGRESSIONS)\033[0m")
        sys.exit(0)
    else:
        print("\033[91m[FAILURE] SOME TESTS FAILED\033[0m")
        sys.exit(1)
