# language: Python 3.11, file: health.py
import os, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a): pass

def start_health():
    port = int(os.getenv("PORT", "8080"))
    srv = HTTPServer(("0.0.0.0", port), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
