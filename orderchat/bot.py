from flask import Blueprint, request, jsonify
import requests
import logging
from .config import VERIFY_TOKEN, WHATSAPP_TOKEN, PHONE_NUMBER_ID, MENU, menu_text
from .db import (
    get_conversation_history,
    save_conversation_message,
    save_order,
    set_order_draft,
    get_order_draft,
    clear_order_draft,
)
from .rules import HeuristicGate, parse_simple_order
from .llm import extract_order_with_claude
from .embeddings import IntentGate

bot_bp = Blueprint('bot', __name__)
log = logging.getLogger(__name__)
intent_gate = IntentGate()


def send_whatsapp_message(to_phone_number, message_text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_phone_number, "text": {"body": message_text}}
    try:
        response = requests.post(url, headers=headers, json=data)
        log.info(f"WhatsApp API Response: {response.status_code}")
        return response
    except Exception as e:
        log.error(f"WhatsApp send error: {e}")
        return None


@bot_bp.get('/webhook')
def verify_webhook():
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if token == VERIFY_TOKEN:
        log.info("Webhook verified successfully!")
        return challenge
    else:
        log.error("Webhook verification failed!")
        return "Verification failed", 403


@bot_bp.post('/webhook')
def handle_message():
    data = request.get_json()
    try:
        entry = data['entry'][0]
        changes = entry['changes'][0]
        value = changes['value']
        if 'messages' in value:
            message = value['messages'][0]
            customer_phone = message['from']
            message_text = message['text']['body']
            log.info(f"Message from {customer_phone}: {message_text}")

            gate = HeuristicGate()
            draft = get_order_draft(customer_phone)

            # Step 0: require keyword to start
            if draft is None:
                if gate.wants_to_start(message_text):
                    set_order_draft(customer_phone, {"items": [], "total": 0.0})
                    send_whatsapp_message(
                        customer_phone,
                        "Great! Let's start your order. You can say things like '2 Pizza Margherita and 1 Chocolate Cake'.\n" + menu_text()
                    )
                    save_conversation_message(customer_phone, 'system', 'ordering_started')
                else:
                    send_whatsapp_message(customer_phone, "Welcome! Reply with 'start' to begin ordering, or ask about our menu.\n" + menu_text())
                return jsonify({"status": "ok"})

            # Handle cancel
            if gate.wants_to_cancel(message_text):
                clear_order_draft(customer_phone)
                send_whatsapp_message(customer_phone, "Order canceled. Reply 'start' to begin again.")
                return jsonify({"status": "ok"})

            # Handle confirm -> persist to orders table
            if gate.wants_to_confirm(message_text):
                if draft.get('items'):
                    order_id = save_order(customer_phone, draft['items'], draft.get('total', 0.0))
                    clear_order_draft(customer_phone)
                    send_whatsapp_message(customer_phone, f"Thanks! Your order #{order_id} has been placed.")
                else:
                    send_whatsapp_message(customer_phone, "Your cart is empty. Add some items before confirming.")
                return jsonify({"status": "ok"})

            # Try simple parser first
            items, total = parse_simple_order(message_text, MENU)
            used_llm = False
            if items:
                pass
            else:
                # If classifier says this doesn't look like an order intent strongly, avoid LLM
                if intent_gate.should_gate_llm(message_text):
                    send_whatsapp_message(customer_phone, "I'm here to help with ordering. Try: '2 Pizza Margherita'.")
                    return jsonify({"status": "ok"})
                # Fallback to LLM extraction
                extracted = extract_order_with_claude(message_text)
                if extracted:
                    items = extracted['items']
                    total = extracted['total']
                    used_llm = True

            if items:
                new_items = draft.get('items', []) + items
                new_total = round(sum(i.get('line_total', i['unit_price'] * i['quantity']) for i in new_items), 2)
                set_order_draft(customer_phone, {"items": new_items, "total": new_total})
                summary = "\n".join([f"- {i['quantity']} x {i['name']} = ${i.get('line_total', i['unit_price']*i['quantity'])}" for i in new_items])
                suffix = " (via LLM)" if used_llm else ""
                send_whatsapp_message(
                    customer_phone,
                    f"Added to cart{suffix}. Current total ${new_total}:\n{summary}\n\nReply 'confirm' to place the order, or add more items."
                )
                return jsonify({"status": "ok"})

            # Not an order-like message
            send_whatsapp_message(customer_phone, "I can add items to your cart. For example: '2 Pizza Margherita'. When ready, reply 'confirm'.")
            return jsonify({"status": "ok"})

    except KeyError as e:
        log.error(f"Error parsing webhook data: {e}")
    except Exception as e:
        log.error(f"General error: {e}")

    return jsonify({"status": "received"}), 200
