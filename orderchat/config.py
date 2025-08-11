import os

# Environment variables
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Define menu for validation and pricing
MENU = {
    "pizza margherita": 12.0,
    "chicken caesar salad": 8.0,
    "spaghetti carbonara": 10.0,
    "chocolate cake": 6.0,
}


def menu_text() -> str:
    return (
        "Our menu:\n"
        "- Pizza Margherita - $12\n"
        "- Chicken Caesar Salad - $8\n"
        "- Spaghetti Carbonara - $10\n"
        "- Chocolate Cake - $6\n"
    )
