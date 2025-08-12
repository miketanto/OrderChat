import os
from typing import Dict, List
import re

# Environment variables
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Expanded structured menu
MENU_CATEGORIES: Dict[str, Dict[str, float]] = {
    'pizzas': {
        'pizza margherita': 12.0,
        'pizza pepperoni': 13.5,
        'pizza quattro formaggi': 14.0,
        'pizza vegetarian': 13.0,
        'pizza bbq chicken': 14.5,
    },
    'pastas': {
        'spaghetti carbonara': 11.0,
        'penne arrabbiata': 10.0,
        'fettuccine alfredo': 12.5,
        'lasagna bolognese': 13.5,
        'gnocchi pesto': 12.0,
    },
    'salads': {
        'chicken caesar salad': 9.0,
        'greek salad': 8.5,
        'garden salad': 7.5,
        'caprese salad': 9.5,
        'kale quinoa salad': 10.0,
    },
    'desserts': {
        'chocolate cake': 6.0,
        'tiramisu': 6.5,
        'panna cotta': 6.0,
        'gelato trio': 5.5,
        'cheesecake': 6.5,
    }
}

# Flattened menu for pricing lookups
MENU: Dict[str, float] = {item: price for cat in MENU_CATEGORIES.values() for item, price in cat.items()}

# Generic category terms mapping to categories for ambiguity detection
GENERIC_TERMS: Dict[str, str] = {
    'pizza': 'pizzas',
    'pizzas': 'pizzas',
    'pasta': 'pastas',
    'pastas': 'pastas',
    'salad': 'salads',
    'salads': 'salads',
    'dessert': 'desserts',
    'desserts': 'desserts',
    'cake': 'desserts'
}


def list_category_examples(cat_key: str, limit: int = 3) -> str:
    items = list(MENU_CATEGORIES.get(cat_key, {}).keys())[:limit]
    return ", ".join([i.title() for i in items])


def menu_text() -> str:
    lines: List[str] = ["Our menu:"]
    for cat, items in MENU_CATEGORIES.items():
        lines.append(f"  {cat.title()}:")
        for name, price in items.items():
            lines.append(f"    - {name.title()} - ${price}")
    return "\n".join(lines) + "\n"


def detect_ambiguous_terms(message: str) -> List[str]:
    """Return list of generic category words present without specific item names."""
    msg = message.lower()
    ambiguous = []
    for term, cat in GENERIC_TERMS.items():
        if re_search_word(term, msg):
            # Check if any specific item from that category is also present
            if not any(re_search_word(item, msg) for item in MENU_CATEGORIES[cat].keys()):
                ambiguous.append(cat)
    return sorted(set(ambiguous))


def re_search_word(word: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None
