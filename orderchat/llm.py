import json
import re
import anthropic
from typing import Dict, Any, Optional
from .config import MENU

claude_client = anthropic.Anthropic()


def _strip_code_fences(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"^\s*```(?:json)?\s*", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"```\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _extract_first_json_object(s: str) -> str:
    brace_stack = 0
    start = None
    for i, ch in enumerate(s):
        if ch == '{':
            if brace_stack == 0:
                start = i
            brace_stack += 1
        elif ch == '}':
            if brace_stack > 0:
                brace_stack -= 1
                if brace_stack == 0 and start is not None:
                    return s[start:i+1]
    return s


def extract_order_with_claude(user_message: str) -> Optional[Dict[str, Any]]:
    try:
        system_prompt = (
            "You extract restaurant orders from customer messages. "
            "Return JSON only with this shape: {\n"
            "  \"items\": [ { \"name\": string, \"quantity\": number, \"unit_price\": number } ]\n"
            "}. Use only these menu items and prices: "
            + ", ".join([f"{name} - ${price}" for name, price in MENU.items()]) + ". "
            "If no order present, return {\"items\": []}."
        )
        msg = [{"role": "user", "content": user_message}]
        resp = claude_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=200,
            system=system_prompt,
            messages=msg
        )
        raw = resp.content[0].text if resp and resp.content else ""
        text = _strip_code_fences(raw)
        json_str = _extract_first_json_object(text)
        data = json.loads(json_str)
        items = data.get("items", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []
        normalized_menu = {k.lower(): v for k, v in MENU.items()}
        validated_items = []
        total = 0.0
        for it in items:
            try:
                name = str(it.get("name", "")).strip().lower()
                qty = int(it.get("quantity", 1))
                if qty <= 0:
                    continue
                if name in normalized_menu:
                    price = float(normalized_menu[name])
                    validated_items.append({
                        "name": name.title(),
                        "quantity": qty,
                        "unit_price": price,
                        "line_total": round(price * qty, 2),
                    })
                    total += price * qty
            except Exception:
                continue
        total = round(total, 2)
        if validated_items and total > 0:
            return {"items": validated_items, "total": total}
        return None
    except Exception:
        return None
