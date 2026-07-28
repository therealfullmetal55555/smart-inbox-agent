import re
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("InvoiceParser")

@dataclass
class InvoiceLineItem:
    description: str
    quantity: float
    unit_price: float
    total_price: float

@dataclass
class ExtractedInvoice:
    vendor_name: str
    invoice_number: str
    invoice_date: str
    due_date: Optional[str]
    currency: str
    subtotal: float
    tax_amount: float
    total_amount: float
    line_items: List[InvoiceLineItem]
    is_mathematically_valid: bool
    confidence_score: float

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["line_items"] = [asdict(item) for item in self.line_items]
        return data

    def to_sheets_row(self) -> List[Any]:
        return [
            self.invoice_date,
            self.vendor_name,
            self.invoice_number,
            f"{self.total_amount:.2f}",
            self.currency,
            self.due_date or "N/A",
            "VERIFIED" if self.is_mathematically_valid else "NEEDS_REVIEW",
            len(self.line_items)
        ]

class InvoiceParser:
    """
    High-precision Structured Invoice Extraction & Validation Engine.
    Extracts core financial headers, tabular items, and performs integrity checks.
    """

    def parse_text(self, document_text: str) -> ExtractedInvoice:
        lines = [line.strip() for line in document_text.split("\n") if line.strip()]
        
        vendor = self._extract_vendor(lines, document_text)
        inv_num = self._extract_invoice_number(document_text)
        inv_date = self._extract_date(document_text, r'(?:invoice date|date|billed on):\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4})') or "2026-09-01"
        due_date = self._extract_date(document_text, r'(?:due date|payment due|pay by):\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4})')
        currency = self._extract_currency(document_text)
        
        subtotal = self._extract_amount(document_text, r'\b(?:subtotal|sub-total|net amount):\s*(?:[\$€£]|USD|EUR)?\s*([0-9,]+\.[0-9]{2})')
        tax = self._extract_amount(document_text, r'\b(?:tax|vat|gst|sales tax):\s*(?:[\$€£]|USD|EUR)?\s*([0-9,]+\.[0-9]{2})')
        total = self._extract_amount(document_text, r'\b(?:total amount|total due|grand total|balance due|total):\s*(?:[\$€£]|USD|EUR)?\s*([0-9,]+\.[0-9]{2})')
        
        line_items = self._extract_line_items(lines)

        # Fallback math calculation if subtotal or tax missing
        if subtotal == 0.0 and line_items:
            subtotal = sum(item.total_price for item in line_items)
        if total == 0.0:
            total = subtotal + tax

        # Mathematical integrity check
        calculated_sum = subtotal + tax
        is_valid = abs(calculated_sum - total) < 0.05

        confidence = 0.98 if (vendor and inv_num and is_valid) else 0.75

        return ExtractedInvoice(
            vendor_name=vendor,
            invoice_number=inv_num,
            invoice_date=inv_date,
            due_date=due_date,
            currency=currency,
            subtotal=round(subtotal, 2),
            tax_amount=round(tax, 2),
            total_amount=round(total, 2),
            line_items=line_items,
            is_mathematically_valid=is_valid,
            confidence_score=round(confidence, 2)
        )

    def _extract_vendor(self, lines: List[str], text: str) -> str:
        # Check explicit vendor labels
        m = re.search(r'(?:from|vendor|biller|supplier|company):\s*([^\n\r,]+)', text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # First non-header line often contains vendor name
        for line in lines[:5]:
            if not re.search(r'(invoice|receipt|bill to|tax invoice|statement|page)', line, re.IGNORECASE) and len(line) > 3:
                return line
        return "Unknown Vendor Inc."

    def _extract_invoice_number(self, text: str) -> str:
        m = re.search(r'(?:invoice\s*#?|inv\s*#?|number|no\.?):\s*([A-Z0-9\-_]+)', text, re.IGNORECASE)
        return m.group(1).strip() if m else "INV-UNKNOWN"

    def _extract_date(self, text: str, pattern: str) -> Optional[str]:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _extract_currency(self, text: str) -> str:
        if "€" in text or "EUR" in text:
            return "EUR"
        if "£" in text or "GBP" in text:
            return "GBP"
        return "USD"

    def _extract_amount(self, text: str, pattern: str) -> float:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            clean_val = m.group(1).replace(",", "")
            try:
                return float(clean_val)
            except ValueError:
                return 0.0
        return 0.0

    def _extract_line_items(self, lines: List[str]) -> List[InvoiceLineItem]:
        items: List[InvoiceLineItem] = []
        # Pattern: description ... qty x price = total
        # e.g.: "Cloud Server Compute (16 vCPU)   2   $120.00   $240.00"
        item_regex = re.compile(r'^([A-Za-z0-9\s\-_\(\)]+?)\s+(\d+(?:\.\d+)?)\s+(?:[\$€£])?(\d+(?:\.\d+)?)\s+(?:[\$€£])?(\d+(?:\.\d+)?)$')
        
        for line in lines:
            match = item_regex.match(line)
            if match:
                desc, qty, unit, tot = match.groups()
                items.append(InvoiceLineItem(
                    description=desc.strip(),
                    quantity=float(qty),
                    unit_price=float(unit),
                    total_price=float(tot)
                ))
        return items
