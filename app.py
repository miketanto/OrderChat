from flask import Flask, request, jsonify
import json
import os
import requests
import sqlite3
from datetime import datetime
import anthropic

app = Flask(__name__)

# Environment variables
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Initialize Claude client (fixed initialization)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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
            send_whatsapp_message(customer_phone, claude_response)
            
    except KeyError as e:
        app.logger.error(f"Error parsing webhook data: {e}")
    except Exception as e:
        app.logger.error(f"General error: {e}")
    
    return jsonify({"status": "received"}), 200

# Initialize database on startup
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)