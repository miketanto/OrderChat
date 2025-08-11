import sqlite3
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_NAME = 'restaurant_bot.db'


def get_conn():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE,
            messages TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            items TEXT, -- JSON array of {name, quantity, unit_price}
            total REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS order_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE,
            draft TEXT, -- JSON of {items:[], total}
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    conn.commit()
    conn.close()


# Conversation helpers

def get_conversation_history(phone_number: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT messages FROM conversations WHERE phone_number = ?', (phone_number,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except Exception:
            return []
    return []


def save_conversation_message(phone_number: str, role: str, content: str):
    history = get_conversation_history(phone_number)
    history.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
    if len(history) > 10:
        history = history[-10:]

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT OR REPLACE INTO conversations (phone_number, messages, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)''',
        (phone_number, json.dumps(history))
    )
    conn.commit()
    conn.close()


# Orders helpers

def save_order(phone_number: str, items: list, total: float) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO orders (phone_number, items, total, status) VALUES (?, ?, ?, ?)''',
        (phone_number, json.dumps(items), float(total), 'pending')
    )
    oid = cursor.lastrowid
    conn.commit()
    conn.close()
    return oid


def list_orders():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, phone_number, items, total, status, created_at FROM orders ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            items = json.loads(r[2]) if r[2] else []
        except Exception:
            items = []
        out.append({
            'id': r[0],
            'phone_number': r[1],
            'items': items,
            'total': r[3],
            'status': r[4],
            'created_at': r[5]
        })
    return out


# Draft helpers

def set_order_draft(phone_number: str, draft: Dict[str, Any]):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT OR REPLACE INTO order_drafts (phone_number, draft, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)''',
        (phone_number, json.dumps(draft))
    )
    conn.commit()
    conn.close()


def get_order_draft(phone_number: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT draft FROM order_drafts WHERE phone_number = ?', (phone_number,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except Exception:
            return None
    return None


def clear_order_draft(phone_number: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM order_drafts WHERE phone_number = ?', (phone_number,))
    conn.commit()
    conn.close()
