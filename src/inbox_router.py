import re
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SmartInboxRouter")

class EmailCategory(str, Enum):
    SALES_INBOUND = "sales_inbound"
    SUPPORT_TECHNICAL = "support_technical"
    BILLING_INVOICE = "billing_invoice"
    PARTNERSHIP = "partnership"
    REFUND_DISPUTE = "refund_dispute"
    SPAM_PROMOTION = "spam_promotion"
    UNKNOWN = "unknown"

class UrgencyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

@dataclass
class EmailMessage:
    id: str
    sender: str
    recipient: str
    subject: str
    body: str
    received_at: str
    has_attachments: bool = False
    attachment_filenames: List[str] = field(default_factory=list)

@dataclass
class RoutingDecision:
    email_id: str
    category: EmailCategory
    confidence: float
    urgency: UrgencyLevel
    target_queue: str
    requires_human_approval: bool
    draft_response: Optional[str]
    suggested_actions: List[str]
    extracted_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["urgency"] = self.urgency.value
        return data

class SmartInboxRouter:
    """
    Production-grade AI Inbox Router & Auto-Drafter.
    Performs zero-shot intent categorization, urgency scoring, entity extraction,
    and automatic draft response generation.
    """

    CATEGORIES = {
        EmailCategory.SALES_INBOUND: {
            "queue": "crm_sales_leads",
            "sla_hours": 2,
            "auto_draft": True
        },
        EmailCategory.SUPPORT_TECHNICAL: {
            "queue": "zendesk_tier1_support",
            "sla_hours": 4,
            "auto_draft": True
        },
        EmailCategory.BILLING_INVOICE: {
            "queue": "finance_erp_pipeline",
            "sla_hours": 24,
            "auto_draft": False
        },
        EmailCategory.PARTNERSHIP: {
            "queue": "bizdev_inbox",
            "sla_hours": 12,
            "auto_draft": True
        },
        EmailCategory.REFUND_DISPUTE: {
            "queue": "executive_escalations",
            "sla_hours": 1,
            "auto_draft": True
        },
        EmailCategory.SPAM_PROMOTION: {
            "queue": "archive_spam",
            "sla_hours": 0,
            "auto_draft": False
        }
    }

    def __init__(self, high_confidence_threshold: float = 0.85):
        self.high_confidence_threshold = high_confidence_threshold

    def classify_and_route(self, email: EmailMessage) -> RoutingDecision:
        """
        Classifies incoming email and computes optimal routing target, SLA, and response draft.
        """
        text = f"{email.subject} {email.body}".lower()

        # Rule & Heuristic Feature Extraction
        category, confidence = self._determine_category(email, text)
        urgency = self._determine_urgency(text, category)
        target_queue = self.CATEGORIES.get(category, {}).get("queue", "general_triage")
        
        # Human in the loop gate
        requires_human = (
            confidence < self.high_confidence_threshold 
            or urgency in (UrgencyLevel.HIGH, UrgencyLevel.CRITICAL)
            or category == EmailCategory.REFUND_DISPUTE
        )

        metadata = self._extract_entities(text, email)
        draft = self._generate_draft(email, category, metadata)
        actions = self._generate_suggested_actions(category, email)

        return RoutingDecision(
            email_id=email.id,
            category=category,
            confidence=round(confidence, 3),
            urgency=urgency,
            target_queue=target_queue,
            requires_human_approval=requires_human,
            draft_response=draft,
            suggested_actions=actions,
            extracted_metadata=metadata
        )

    def _determine_category(self, email: EmailMessage, text: str) -> tuple[EmailCategory, float]:
        # Invoice / Billing check
        has_invoice_attachment = any(
            re.search(r'(invoice|receipt|statement|factura).*\.(pdf|xlsx|csv)', fn, re.IGNORECASE)
            for fn in email.attachment_filenames
        )
        if has_invoice_attachment or re.search(r'\b(invoice|bill|payment receipt|wire transfer|vat no|tax invoice|due date)\b', text):
            return EmailCategory.BILLING_INVOICE, 0.96

        # Refund / Dispute (High escalation)
        if re.search(r'\b(chargeback|refund|dispute|lawyer|sue|unauthorized transaction|fraud|cancel subscription immediately)\b', text):
            return EmailCategory.REFUND_DISPUTE, 0.94

        # Sales / Pricing / Demo
        if re.search(r'\b(pricing|book a demo|request quote|enterprise plan|sales team|schedule a call|procurement|seats|licensing)\b', text):
            return EmailCategory.SALES_INBOUND, 0.92

        # Technical Support
        if re.search(r'\b(error|bug|crash|api exception|500 internal|login issue|downtime|timeout|not working|broken|traceback)\b', text):
            return EmailCategory.SUPPORT_TECHNICAL, 0.91

        # Partnerships
        if re.search(r'\b(partnership|collab|affiliate|co-marketing|integration partner|synergy|joint venture)\b', text):
            return EmailCategory.PARTNERSHIP, 0.88

        # Spam / Cold outreach promo
        if re.search(r'\b(seo services|increase your traffic|crypto investment|earn \$|guest post|backlinks|unsubscribe here)\b', text):
            return EmailCategory.SPAM_PROMOTION, 0.95

        return EmailCategory.UNKNOWN, 0.45

    def _determine_urgency(self, text: str, category: EmailCategory) -> UrgencyLevel:
        if category == EmailCategory.REFUND_DISPUTE or re.search(r'\b(asap|urgent|emergency|critical outage|production down|legal action)\b', text):
            return UrgencyLevel.CRITICAL
        if category == EmailCategory.SUPPORT_TECHNICAL and re.search(r'\b(outage|blocked|cannot access|data loss)\b', text):
            return UrgencyLevel.HIGH
        if category == EmailCategory.SALES_INBOUND:
            return UrgencyLevel.MEDIUM
        if category == EmailCategory.SPAM_PROMOTION:
            return UrgencyLevel.LOW
        return UrgencyLevel.MEDIUM

    def _extract_entities(self, text: str, email: EmailMessage) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        
        # Phone numbers
        phone_match = re.search(r'(\+?[0-9]{1,3}[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}', text)
        if phone_match:
            metadata["phone"] = phone_match.group(0).strip()

        # Budgets / Currency amounts
        amount_match = re.search(r'(\$|€|£|USD|EUR)\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)', email.body, re.IGNORECASE)
        if amount_match:
            metadata["detected_amount"] = amount_match.group(0)

        # Domain / Organization
        sender_domain = email.sender.split("@")[-1] if "@" in email.sender else ""
        metadata["sender_domain"] = sender_domain

        return metadata

    def _generate_draft(self, email: EmailMessage, category: EmailCategory, metadata: Dict[str, Any]) -> Optional[str]:
        sender_name = email.sender.split("<")[0].strip().split("@")[0].capitalize()
        
        if category == EmailCategory.SALES_INBOUND:
            return (
                f"Hi {sender_name},\n\n"
                f"Thank you for reaching out to us regarding our enterprise solutions! We'd love to learn more about your team's requirements.\n\n"
                f"You can choose a convenient time for an executive intro and live demo here: https://cal.com/enterprise-team/30min\n\n"
                f"Best regards,\nEnterprise Solutions Team"
            )
        elif category == EmailCategory.SUPPORT_TECHNICAL:
            return (
                f"Hi {sender_name},\n\n"
                f"Thank you for reporting this issue. Our engineering team has been notified and is currently investigating.\n\n"
                f"Reference Ticket: #{email.id[:8].upper()}\n"
                f"If you have additional logs or reproduction steps, please reply directly to this email.\n\n"
                f"Best regards,\nTechnical Operations"
            )
        elif category == EmailCategory.PARTNERSHIP:
            return (
                f"Hi {sender_name},\n\n"
                f"Thanks for connecting regarding potential partnership opportunities. We review integration and co-marketing proposals weekly.\n\n"
                f"Could you share a brief overview deck or one-pager?\n\n"
                f"Best regards,\nBusiness Development"
            )
        elif category == EmailCategory.REFUND_DISPUTE:
            return (
                f"Hello {sender_name},\n\n"
                f"We take account concerns very seriously. Your inquiry has been escalated directly to our Senior Accounts Resolution Desk.\n\n"
                f"A specialist will review your transaction history and contact you within 60 minutes.\n\n"
                f"Sincerely,\nExecutive Relations Team"
            )
        return None

    def _generate_suggested_actions(self, category: EmailCategory, email: EmailMessage) -> List[str]:
        if category == EmailCategory.SALES_INBOUND:
            return ["create_hubspot_deal", "enrich_clearbit_data", "post_to_slack_sales_channel"]
        elif category == EmailCategory.BILLING_INVOICE:
            return ["parse_pdf_attachment", "match_purchase_order", "export_to_quickbooks"]
        elif category == EmailCategory.SUPPORT_TECHNICAL:
            return ["create_jira_issue", "check_statuspage_metrics", "queue_tier1_response"]
        elif category == EmailCategory.REFUND_DISPUTE:
            return ["flag_stripe_charge", "notify_compliance_officer", "sms_alert_oncall"]
        elif category == EmailCategory.SPAM_PROMOTION:
            return ["apply_spam_label", "archive_thread"]
        return ["manual_triage"]
