from flask import Flask, request, jsonify
import json
import os
import requests
import sqlite3
from datetime import datetime
import logging
import anthropic
import re

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Environment variables
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Initialize Claude client (fixed initialization)
claude_client = anthropic.Anthropic()

# Define menu for validation and pricing
MENU = {
    "pizza margherita": 12.0,
    "chicken caesar salad": 8.0,
    "spaghetti carbonara": 10.0,
    "chocolate cake": 6.0,
}

# Database setup
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('restaurant_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE,
            messages TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # New orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            items TEXT, -- JSON array of {name, quantity, unit_price}
            total REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def get_conversation_history(phone_number):
    """Get conversation history for a phone number"""
    conn = sqlite3.connect('restaurant_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT messages FROM conversations WHERE phone_number = ?
    ''', (phone_number,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return json.loads(result[0])
    else:
        return []

def save_conversation_message(phone_number, role, content):
    """Save a message to conversation history"""
    conn = sqlite3.connect('restaurant_bot.db')
    cursor = conn.cursor()
    
    history = get_conversation_history(phone_number)
    
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    
    if len(history) > 10:
        history = history[-10:]
    
    cursor.execute('''
        INSERT OR REPLACE INTO conversations (phone_number, messages, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (phone_number, json.dumps(history)))
    
    conn.commit()
    conn.close()

# --- Orders helpers ---

def save_order(phone_number: str, items: list, total: float) -> int:
    """Persist an order and return the new order id."""
    conn = sqlite3.connect('restaurant_bot.db')
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO orders (phone_number, items, total, status) VALUES (?, ?, ?, ?)''',
        (phone_number, json.dumps(items), float(total), 'pending')
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    app.logger.info(f"Saved order #{order_id} for {phone_number} | total=${total}")
    return order_id


def list_orders():
    """Fetch all orders as list of dicts."""
    conn = sqlite3.connect('restaurant_bot.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT id, phone_number, items, total, status, created_at FROM orders ORDER BY created_at DESC''')
    rows = cursor.fetchall()
    conn.close()
    orders = []
    for r in rows:
        items = []
        try:
            items = json.loads(r[2]) if r[2] else []
        except Exception:
            items = []
        orders.append({
            "id": r[0],
            "phone_number": r[1],
            "items": items,
            "total": r[3],
            "status": r[4],
            "created_at": r[5]
        })
    return orders


def _strip_code_fences(s: str) -> str:
    if not isinstance(s, str):
        return ""
    # Remove ```json ... ``` or ``` ... ``` fences
    s = re.sub(r"^\s*```(?:json)?\s*", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"```\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _extract_first_json_object(s: str) -> str:
    """Try to extract the first top-level JSON object substring from s."""
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


def extract_order_with_claude(user_message: str) -> dict | None:
    """Use Claude to extract order JSON from the user's message. Returns dict with items and total or None."""
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
        # Validate against menu and compute totals
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
    except Exception as e:
        app.logger.warning(f"Order extraction failed: {e}")
        return None


def detect_and_save_order(message_text: str, customer_phone: str) -> int | None:
    """Try to detect an order from the user's message and save it. Returns order id or None."""
    extracted = extract_order_with_claude(message_text)
    if extracted:
        try:
            order_id = save_order(customer_phone, extracted["items"], extracted["total"])
            return order_id
        except Exception as e:
            app.logger.error(f"Failed to save order: {e}")
    return None

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "whatsapp-restaurant-bot"}), 200

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Webhook verification for WhatsApp"""
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if token == VERIFY_TOKEN:
        app.logger.info("Webhook verified successfully!")
        return challenge
    else:
        app.logger.error("Webhook verification failed!")
        return "Verification failed", 403

def send_whatsapp_message(to_phone_number, message_text):
    """Send message back to WhatsApp user"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": to_phone_number,
        "text": {"body": message_text}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        app.logger.info(f"WhatsApp API Response: {response.status_code}")
        return response
    except Exception as e:
        app.logger.error(f"WhatsApp send error: {e}")
        return None

def get_claude_response(user_message, customer_phone):
    """Get response from Claude with conversation context"""
    
    system_prompt = """You are a helpful restaurant ordering assistant. 
    Help customers browse the menu and place orders. Be friendly and conversational.
    
    Our menu:
    - Pizza Margherita - $12
    - Chicken Caesar Salad - $8  
    - Spaghetti Carbonara - $10
    - Chocolate Cake - $6
    
    Keep responses concise for WhatsApp messaging."""
    
    try:
        history = get_conversation_history(customer_phone)
        
        claude_messages = []
        for msg in history:
            if msg['role'] in ['user', 'assistant']:
                claude_messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
        
        claude_messages.append({
            "role": "user",
            "content": user_message
        })
        
        response = claude_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=150,
            system=system_prompt,
            messages=claude_messages
        )
        
        claude_reply = response.content[0].text
        
        save_conversation_message(customer_phone, "user", user_message)
        save_conversation_message(customer_phone, "assistant", claude_reply)
        
        return claude_reply
    
    except Exception as e:
        app.logger.error(f"Claude API error: {e}")
        return "Sorry, I'm having trouble right now. Please try again!"

@app.route('/webhook', methods=['POST'])
def handle_message():
    """Handle incoming WhatsApp messages"""
    data = request.get_json()
    
    try:
        entry = data['entry'][0]
        changes = entry['changes'][0]
        value = changes['value']
        
        if 'messages' in value:
            message = value['messages'][0]
            customer_phone = message['from']
            message_text = message['text']['body']
            
            app.logger.info(f"Message from {customer_phone}: {message_text}")
            
            claude_response = get_claude_response(message_text, customer_phone)

            # Attempt to detect and save an order from the user's message
            order_id = detect_and_save_order(message_text, customer_phone)
            if order_id:
                app.logger.info(f"Order #{order_id} captured for {customer_phone}")
                # Optionally, append a confirmation note to user
                try:
                    send_whatsapp_message(customer_phone, f"Thanks! I captured your order (#{order_id}). You can view it at /orders.")
                except Exception:
                    pass

            # Send Claude's main response as usual
            send_whatsapp_message(customer_phone, claude_response)
            
    except KeyError as e:
        app.logger.error(f"Error parsing webhook data: {e}")
    except Exception as e:
        app.logger.error(f"General error: {e}")
    
    return jsonify({"status": "received"}), 200

# --- Orders viewing endpoints ---

@app.route('/api/orders', methods=['GET'])
def api_orders():
    return jsonify({"orders": list_orders()})


@app.route('/orders', methods=['GET'])
def orders_page():
    orders = list_orders()
    # Simple HTML table view
    rows = []
    for o in orders:
        items_html = "<ul>" + "".join([f"<li>{i['quantity']} x {i['name']} @ ${i['unit_price']} = ${i.get('line_total', round(i['unit_price']*i['quantity'],2))}</li>" for i in o.get('items', [])]) + "</ul>"
        rows.append(
            f"<tr>"
            f"<td>{o['id']}</td>"
            f"<td>{o['phone_number']}</td>"
            f"<td>{items_html}</td>"
            f"<td>${o['total']}</td>"
            f"<td>{o['status']}</td>"
            f"<td>{o['created_at']}</td>"
            f"</tr>"
        )
    html = (
        "<!doctype html>\n"
        "<html lang='en'>\n<head>\n<meta charset='utf-8'/>\n<title>Orders</title>\n"
        "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Inter,Arial,sans-serif;padding:24px;background:#f8fafc;color:#0f172a}"
        "table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.06);border-radius:8px;overflow:hidden}"
        "th,td{padding:12px 14px;border-bottom:1px solid #e2e8f0;vertical-align:top}"
        "th{background:#f1f5f9;text-align:left;font-weight:600;color:#334155}"
        "h1{margin:0 0 16px;font-size:24px}"
        "ul{margin:0;padding-left:18px}" 
        "</style>\n</head>\n<body>\n"
        "<h1>Customer Orders</h1>\n"
        "<table>\n<thead><tr><th>ID</th><th>Phone</th><th>Items</th><th>Total</th><th>Status</th><th>Created</th></tr></thead>\n"
        f"<tbody>{''.join(rows) or '<tr><td colspan=6 style=\'text-align:center;padding:24px\'>No orders yet.</td></tr>'}</tbody>\n"
        "</table>\n"
        "</body></html>"
    )
    return html

# Initialize database on startup
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)