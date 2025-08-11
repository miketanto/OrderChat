from flask import Blueprint, jsonify
from .db import list_orders

orders_bp = Blueprint('orders', __name__)


@orders_bp.get('/api/orders')
def api_orders():
    return jsonify({"orders": list_orders()})


@orders_bp.get('/orders')
def orders_page():
    orders = list_orders()
    rows = []
    for o in orders:
        items_html = "<ul>" + "".join([
            f"<li>{i['quantity']} x {i['name']} @ ${i['unit_price']} = ${i.get('line_total', round(i['unit_price']*i['quantity'],2))}</li>"
            for i in o.get('items', [])
        ]) + "</ul>"
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
