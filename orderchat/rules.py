from __future__ import annotations
from typing import Literal, Dict, Any, List, Tuple
import re

StartState = Literal['idle', 'awaiting_confirm', 'ordering']

START_KEYWORDS = {"start", "order", "menu"}
CONFIRM_KEYWORDS = {"confirm", "yes", "y", "place order"}
CANCEL_KEYWORDS = {"cancel", "no", "n", "abort"}


NUM_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}


class HeuristicGate:
    """Simple text heuristics to decide when to engage LLM or workflow steps."""

    def __init__(self):
        pass

    def normalize(self, s: str) -> str:
        return re.sub(r"\s+", " ", s or "").strip().lower()

    def wants_to_start(self, text: str) -> bool:
        t = self.normalize(text)
        return any(k in t.split() for k in START_KEYWORDS)

    def wants_to_confirm(self, text: str) -> bool:
        t = self.normalize(text)
        return t in CONFIRM_KEYWORDS or any(t.startswith(k) for k in {"confirm"})

    def wants_to_cancel(self, text: str) -> bool:
        t = self.normalize(text)
        return t in CANCEL_KEYWORDS

    def looks_like_order(self, text: str) -> bool:
        # Very light signal that there may be items/quantities
        t = self.normalize(text)
        has_qty = bool(re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", t))
        has_food_words = any(w in t for w in ["pizza", "salad", "spaghetti", "cake"])
        return has_food_words or has_qty


def parse_simple_order(text: str, menu: Dict[str, float]) -> Tuple[List[Dict[str, Any]], float]:
    """A minimal parser for patterns like '2 pizza margherita and 1 cake'.
    Returns (items, total). items as [{name, quantity, unit_price, line_total}].
    """
    t = re.sub(r"\s+", " ", text or "").strip().lower()
    items: List[Dict[str, Any]] = []
    total = 0.0

    # Try detect each menu item by substring, then find quantity preceding it
    for item_name, price in menu.items():
        if item_name in t:
            # Look behind for a qty e.g., '2 pizza margherita' or 'two pizza'
            # Capture last number word or digit within 3 words before the item
            pattern = rf"((?:\b\d+\b|\b({'|'.join(NUM_WORDS.keys())})\b))?\s*(?:\b\w+\b\s*){{0,3}}{re.escape(item_name)}"
            m = re.search(pattern, t)
            qty = 1
            if m and m.group(1):
                val = m.group(1)
                if val.isdigit():
                    qty = int(val)
                else:
                    qty = NUM_WORDS.get(val, 1)
            line_total = round(price * qty, 2)
            items.append({
                'name': item_name.title(),
                'quantity': qty,
                'unit_price': float(price),
                'line_total': line_total
            })
            total += line_total

    return items, round(total, 2)
