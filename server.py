import threading
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Discord Bot is running!"

@app.route('/health')
def health():
    return {"status": "healthy"}

def run():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

def start_server():
    server_thread = threading.Thread(target=run)
    server_thread.daemon = True
    server_thread.start()
