from flask import Blueprint, request, jsonify
import requests
import logging
from .config import VERIFY_TOKEN, WHATSAPP_TOKEN, PHONE_NUMBER_ID, MENU, menu_text, detect_ambiguous_terms, list_category_examples, MENU_CATEGORIES
from .db import (
    save_order,
    set_order_draft,
    get_order_draft,
    clear_order_draft,
)
from .rules import HeuristicGate
from .llm import extract_order_with_claude

bot_bp = Blueprint('bot', __name__)
log = logging.getLogger(__name__)


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

            if draft is None:
                if gate.wants_to_start(message_text):
                    set_order_draft(customer_phone, {"items": [], "total": 0.0})
                    send_whatsapp_message(
                        customer_phone,
                        "Ordering session started. Send items and quantities (e.g. '2 Pizza Margherita, 1 Tiramisu').\n" + menu_text() + "When finished, reply 'confirm' or 'cancel'."
                    )
                else:
                    send_whatsapp_message(customer_phone, "Welcome! Reply with 'start' to begin ordering.\n" + menu_text())
                return jsonify({"status": "ok"})

            if gate.wants_to_cancel(message_text):
                clear_order_draft(customer_phone)
                send_whatsapp_message(customer_phone, "Order canceled. Reply 'start' to begin again.")
                return jsonify({"status": "ok"})

            if gate.wants_to_confirm(message_text):
                if draft.get('items'):
                    order_id = save_order(customer_phone, draft['items'], draft.get('total', 0.0))
                    clear_order_draft(customer_phone)
                    send_whatsapp_message(customer_phone, f"Thanks! Your order #{order_id} has been placed. LLM session closed.")
                else:
                    send_whatsapp_message(customer_phone, "Your cart is empty. Add some items before confirming.")
                return jsonify({"status": "ok"})

            # LLM extraction handles ambiguity & fuzzy corrections
            extracted = extract_order_with_claude(message_text)
            if extracted and extracted.get('need_clarification'):
                prompts = []
                for cat in extracted['need_clarification']:
                    examples = list_category_examples(cat)
                    singular = cat[:-1] if cat.endswith('s') else cat
                    prompts.append(f"Which {singular} would you like? e.g. {examples}")
                send_whatsapp_message(customer_phone, "Need clarification: " + " | ".join(prompts))
                return jsonify({"status": "ok"})

            if extracted and extracted.get('items'):
                current = draft.get('items', [])
                merged = {}
                for it in current:
                    key = it['name'].lower()
                    merged[key] = {
                        'name': it['name'],
                        'quantity': it['quantity'],
                        'unit_price': it['unit_price'],
                        'line_total': it.get('line_total', it['unit_price'] * it['quantity'])
                    }
                for it in extracted['items']:
                    key = it['name'].lower()
                    if key in merged:
                        merged[key]['quantity'] += it['quantity']
                        merged[key]['line_total'] = round(merged[key]['unit_price'] * merged[key]['quantity'], 2)
                    else:
                        merged[key] = it
                new_items = list(merged.values())
                new_total = round(sum(i['line_total'] for i in new_items), 2)
                set_order_draft(customer_phone, {"items": new_items, "total": new_total})
                summary = "\n".join([f"- {i['quantity']} x {i['name']} = ${i['line_total']}" for i in new_items])
                send_whatsapp_message(
                    customer_phone,
                    f"Cart updated. Total ${new_total}:\n{summary}\n\nAdd more items, or 'confirm' / 'cancel'."
                )
                return jsonify({"status": "ok"})

            send_whatsapp_message(customer_phone, "No valid or specific items detected. Please specify exact menu item names, or 'confirm' / 'cancel'.")
            return jsonify({"status": "ok"})

    except KeyError as e:
        log.error(f"Error parsing webhook data: {e}")
    except Exception as e:
        log.error(f"General error: {e}")

    return jsonify({"status": "received"}), 200
