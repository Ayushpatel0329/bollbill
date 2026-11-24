"""Udhaar Agent & Inbox module (Feature 6 in PRD/TRD).
Identifies overdue credit bills, drafts respectful reminder messages (tone levels 1-3),
enforces human-in-the-loop approvals, handles customer promises and replies.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

TONE_LEVEL_1_HINDI = "नमस्ते {customer_name} जी, आपकी {shop_name} से ₹{amount} की उधारी {days} दिनों से बाकी है। कृपया सुविधानुसार भुगतान कर दें। धन्यवाद!"
TONE_LEVEL_1_ENGLISH = "Hello {customer_name}, your balance of ₹{amount} at {shop_name} has been pending for {days} days. Please clear it at your earliest convenience. Thank you!"
TONE_LEVEL_1_HINGLISH = "Namaste {customer_name} ji, aapka {shop_name} par ₹{amount} ka udhaar {days} din se baki hai. Kripya time par payment kar dein. Shukriya!"

TONE_LEVEL_2_HINDI = "नमस्ते {customer_name} जी, {shop_name} का ₹{amount} का बकाया अभी तक प्राप्त नहीं हुआ है ({days} दिन overdue)। कृपया भुगतान की तारीख बता दें।"
TONE_LEVEL_2_ENGLISH = "Hello {customer_name}, your payment of ₹{amount} at {shop_name} is now overdue ({days} days). Kindly let us know when we can expect the payment."
TONE_LEVEL_2_HINGLISH = "Namaste {customer_name} ji, {shop_name} ka ₹{amount} payment abhi tak nahi aaya ({days} days overdue). Kripya payment date confirm karein."

TONE_LEVEL_3_HINDI = "{customer_name} जी, {shop_name} का ₹{amount} का बकाया काफी समय से लंबित है। आगे की असुविधा से बचने के लिए कृपया तुरंत भुगतान करें।"
TONE_LEVEL_3_ENGLISH = "Dear {customer_name}, your account balance of ₹{amount} at {shop_name} is seriously overdue. Please clear it immediately to keep your account in good standing."
TONE_LEVEL_3_HINGLISH = "{customer_name} ji, {shop_name} ka ₹{amount} kafi din se pending hai. Kripya immediately clear karein taaki humara account sahi rahe."

def draft_reminder(customer_name: str, shop_name: str, amount: float, days: int, level: int, language: str = "hinglish") -> str:
    """Generate tone-specific compliant reminder text without abusive language or harassment."""
    c_name = customer_name.strip() or "Grahak"
    s_name = shop_name.strip() or "Dukaan"
    amt_str = f"{amount:,.2f}".rstrip("0").rstrip(".") if amount == int(amount) else f"{amount:,.2f}"

    lvl = max(1, min(3, level))
    lang = language.lower().strip()

    if lvl == 1:
        tmpl = TONE_LEVEL_1_HINDI if lang == "hindi" else (TONE_LEVEL_1_ENGLISH if lang == "english" else TONE_LEVEL_1_HINGLISH)
    elif lvl == 2:
        tmpl = TONE_LEVEL_2_HINDI if lang == "hindi" else (TONE_LEVEL_2_ENGLISH if lang == "english" else TONE_LEVEL_2_HINGLISH)
    else:
        tmpl = TONE_LEVEL_3_HINDI if lang == "hindi" else (TONE_LEVEL_3_ENGLISH if lang == "english" else TONE_LEVEL_3_HINGLISH)

    return tmpl.format(customer_name=c_name, shop_name=s_name, amount=amt_str, days=days)

def classify_reply(reply_text: str) -> Dict[str, Any]:
    """Classify incoming customer message into structured intent & escalation flag."""
    text = reply_text.lower().strip()
    
    # 1. Dispute or anger (Escalate to shopkeeper)
    dispute_keywords = ("galat", "wrong", "nahi liya", "already paid", "de diya", "fraud", "police", "court", "chindi", "bakwas")
    if any(k in text for k in dispute_keywords):
        return {
            "intent": "dispute_or_claim",
            "needs_attention": True,
            "confidence": 0.95,
            "suggested_reply": "Aapka message mila. Hum bill check karke aapse sampark karte hain."
        }
    
    # 2. Promise to pay / payment soon
    promise_keywords = ("kal", "parso", "friday", "monday", "sunday", "pay soon", "bhej raha", "sham", "dunga", "kar dunga")
    if any(k in text for k in promise_keywords):
        return {
            "intent": "promise_to_pay",
            "needs_attention": False,
            "confidence": 0.88,
            "suggested_reply": "Dhanyawad batane ke liye! Hum update kar dete hain."
        }

    # 3. Request for QR / UPI / amount
    inquiry_keywords = ("kitna", "amount", "scanner", "qr", "upi", "bhejo")
    if any(k in text for k in inquiry_keywords):
        return {
            "intent": "payment_details_request",
            "needs_attention": False,
            "confidence": 0.90,
            "suggested_reply": "QR code aur bill details bhej rahe hain."
        }

    # Unclear - escalate
    return {
        "intent": "unclear",
        "needs_attention": True,
        "confidence": 0.60,
        "suggested_reply": "Aapka message mil gaya hai. Dukandaar aapse jaldi baat karenge."
    }

def find_overdue_bills(bills: List[Dict[str, Any]], settings: Dict[str, Any], flags: Dict[str, Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Scan bills for unpaid Udhaar older than remind_after_days."""
    remind_after = settings.get("remind_after_days", 7)
    candidates = []

    for b in bills:
        if b.get("pay_method") != "Udhaar" or b.get("paid"):
            continue

        billed_at_str = b.get("billed_at")
        if not billed_at_str:
            continue
        try:
            billed_at = datetime.fromisoformat(billed_at_str.replace("Z", "+00:00"))
        except Exception:
            continue

        days_past = (now - billed_at).days
        if days_past < remind_after:
            continue

        cust_phone = b.get("customer_phone") or b.get("cust_phone") or ""
        cust_name = b.get("customer_name") or b.get("cust_name") or "Grahak"
        
        # Check flags: opt-out or active promise
        if cust_phone and cust_phone in flags:
            f = flags[cust_phone]
            if f.get("do_not_remind"):
                continue
            promise_date_str = f.get("promise_date")
            if promise_date_str:
                try:
                    p_date = datetime.fromisoformat(promise_date_str.replace("Z", "+00:00"))
                    if p_date > now:
                        continue # Still within promise window
                except Exception:
                    pass

        candidates.append({
            "udhaar_id": b["id"],
            "bill_no": b.get("bill_no"),
            "customer_name": cust_name,
            "customer_phone": cust_phone,
            "amount_due": float(b.get("total") or 0.0),
            "days_overdue": days_past
        })

    return candidates
