# webhook.py
from flask import Flask, request, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
DB_NAME = "dadu.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def update_saldo(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET saldo = saldo + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

@app.route('/webhook/pakasir', methods=['POST'])
def pakasir_webhook():
    try:
        data = request.get_json()
        print("📥 Webhook:", json.dumps(data, indent=2))
        order_id = data.get('order_id')
        status = data.get('status')
        amount = data.get('amount')
        if status == 'completed' and order_id:
            user_id = int(order_id.split('_')[1])
            update_saldo(user_id, amount)
            print(f"✅ Saldo user {user_id} +{amount}")
            return "OK", 200
        return "Ignored", 200
    except Exception as e:
        print("❌ Error:", e)
        return "Error", 500

@app.route('/ping', methods=['GET'])
def ping():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
