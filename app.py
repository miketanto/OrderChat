from flask import Flask, jsonify
import logging

from orderchat.db import init_db
from orderchat.views import orders_bp
from orderchat.bot import bot_bp

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)


@app.get('/')
def health_check():
    return jsonify({"status": "healthy", "service": "whatsapp-restaurant-bot"}), 200


# Register blueprints
app.register_blueprint(bot_bp)
app.register_blueprint(orders_bp)


# Initialize database on startup
init_db()


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)