"""Purchase File Import module (Feature 2 in PRD/TRD).
Supports CSV and TSV (Excel .xlsx to CSV conversion) with column detection,
fuzzy & alias matching, stock update/replace, and undo tracking.
"""
import csv
import io
import re
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

def normalize_name(s: str) -> str:
    """Lowercase, trim, collapse spaces, strip punctuation."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r'[\s_,\.\-\(\)\[\]/]+', ' ', s)
    return s.strip()

def normalize_unit(unit: str) -> str:
    u = unit.lower().strip()
    if u in ("kg", "kgs", "kilogram", "kilo", "किलो"):
        return "kg"
    if u in ("g", "gm", "gms", "gram"):
        return "g"
    if u in ("l", "ltr", "litre", "liter"):
        return "litre"
    if u in ("ml", "milli"):
        return "ml"
    if u in ("pcs", "pc", "piece", "pieces", "pkt", "packet", "नग"):
        return "piece"
    return u or "piece"

def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()

def detect_columns(headers: List[str]) -> Dict[str, Optional[int]]:
    """Auto-detect columns: name, qty, purchase_price, unit, selling_price, hsn."""
    mapping = {
        "name": None,
        "qty": None,
        "purchase_price": None,
        "unit": None,
        "selling_price": None,
        "hsn": None
    }
    
    for idx, h in enumerate(headers):
        hl = h.lower().strip()
        if mapping["name"] is None and any(k in hl for k in ("item", "name", "product", "description", "naam", "saman")):
            mapping["name"] = idx
        elif mapping["qty"] is None and any(k in hl for k in ("qty", "quantity", "stock", "count", "nag", "matra")):
            mapping["qty"] = idx
        elif mapping["purchase_price"] is None and any(k in hl for k in ("purchase", "cost", "buy", "rate", "cp")):
            mapping["purchase_price"] = idx
        elif mapping["selling_price"] is None and any(k in hl for k in ("sell", "mrp", "sp", "price")):
            mapping["selling_price"] = idx
        elif mapping["unit"] is None and any(k in hl for k in ("unit", "uom", "type")):
            mapping["unit"] = idx
        elif mapping["hsn"] is None and any(k in hl for k in ("hsn", "sac", "code")):
            mapping["hsn"] = idx

    # Fallbacks if purchase_price not explicitly named purchase
    if mapping["purchase_price"] is None and mapping["selling_price"] is not None:
        mapping["purchase_price"] = mapping["selling_price"]
        mapping["selling_price"] = None

    return mapping

def parse_csv_content(content_str: str) -> Tuple[List[str], List[List[str]]]:
    """Parse CSV text safely, preventing formula execution by stripping prefixing =+-@."""
    reader = csv.reader(io.StringIO(content_str))
    rows = []
    for r in reader:
        if not r or all(not cell.strip() for cell in r):
            continue
        cleaned = [cell.strip().lstrip("=+-@") for cell in r]
        rows.append(cleaned)
    if not rows:
        return [], []
    headers = rows[0]
    data_rows = rows[1:]
    return headers, data_rows

def match_and_preview(
    rows: List[List[str]],
    col_map: Dict[str, Optional[int]],
    existing_items: List[Dict[str, Any]],
    aliases: List[Dict[str, Any]],
    margin_pct: float = 0.0
) -> List[Dict[str, Any]]:
    """Match each row against existing items and aliases with preview status."""
    
    # lookup index
    item_by_name = {normalize_name(item["name"]): item for item in existing_items}
    alias_to_item = {}
    for a in aliases:
        alias_to_item[a["normalized_alias"]] = a["item_id"]
    item_by_id = {item["id"]: item for item in existing_items}

    preview_rows = []
    seen_in_file: Dict[str, int] = {}

    for row_idx, r in enumerate(rows):
        def get_val(key):
            idx = col_map.get(key)
            if idx is not None and idx < len(r):
                return r[idx].strip()
            return ""

        raw_name = get_val("name")
        if not raw_name:
            continue

        raw_qty = get_val("qty")
        raw_price = get_val("purchase_price")
        raw_unit = get_val("unit")
        raw_selling = get_val("selling_price")
        raw_hsn = get_val("hsn")

        try:
            qty = float(raw_qty) if raw_qty else 0.0
        except ValueError:
            qty = 0.0

        try:
            purchase_price = float(raw_price) if raw_price else 0.0
        except ValueError:
            purchase_price = 0.0

        unit = normalize_unit(raw_unit) if raw_unit else "piece"
        
        # Suggested selling price
        if raw_selling:
            try:
                selling_price = float(raw_selling)
            except ValueError:
                selling_price = purchase_price * (1 + margin_pct / 100) if margin_pct > 0 else purchase_price
        else:
            selling_price = round(purchase_price * (1 + margin_pct / 100), 2) if margin_pct > 0 else 0.0

        norm_name = normalize_name(raw_name)

        # Merge duplicate rows in same file
        if norm_name in seen_in_file:
            existing_idx = seen_in_file[norm_name]
            preview_rows[existing_idx]["qty"] += qty
            continue

        # Match strategy:
        # 1. Exact alias
        matched_item = None
        match_type = "new"
        confidence = 0.0

        if norm_name in alias_to_item:
            matched_item = item_by_id.get(alias_to_item[norm_name])
            match_type = "alias_exact"
            confidence = 1.0
        elif norm_name in item_by_name:
            matched_item = item_by_name[norm_name]
            match_type = "name_exact"
            confidence = 1.0
        else:
            # Fuzzy match
            best_match = None
            best_score = 0.0
            for ex in existing_items:
                score = fuzzy_ratio(norm_name, ex["name"])
                if score > best_score:
                    best_score = score
                    best_match = ex
            if best_match and best_score >= 0.88:
                matched_item = best_match
                match_type = "fuzzy_high"
                confidence = round(best_score, 2)
            elif best_match and best_score >= 0.65:
                matched_item = best_match
                match_type = "needs_review"
                confidence = round(best_score, 2)

        status = "update" if (matched_item and match_type != "needs_review") else (
            "needs_review" if (matched_item and match_type == "needs_review") else "new"
        )

        entry = {
            "row_index": row_idx,
            "name": raw_name,
            "norm_name": norm_name,
            "qty": qty,
            "purchase_price": purchase_price,
            "selling_price": selling_price,
            "unit": unit,
            "hsn": raw_hsn,
            "status": status,
            "matched_item_id": matched_item["id"] if matched_item else None,
            "matched_item_name": matched_item["name"] if matched_item else None,
            "current_stock": float(matched_item.get("stock") or 0.0) if matched_item else 0.0,
            "current_price": float(matched_item.get("price") or 0.0) if matched_item else 0.0,
            "confidence": confidence
        }

        seen_in_file[norm_name] = len(preview_rows)
        preview_rows.append(entry)

    return preview_rows
