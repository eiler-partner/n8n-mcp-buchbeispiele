"""Read-only, synthetic API and reference table for chapter 6."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os

ORDERS = [
    {"order_id": "A-101", "customer_id": "C-10", "amount": "12.50",
     "created_at": "2026-09-27T08:15:00+02:00"},
    {"order_id": "A-102", "customer_id": None, "amount": "9.00",
     "created_at": "2026-09-27T08:30:00+02:00"},
    {"order_id": "A-103", "customer_id": "C-20", "amount": "0",
     "created_at": "2026-09-27T07:00:00Z"},
]
CUSTOMERS = {
    "C-10": {"customer_id": "C-10", "name": "Aster GmbH", "tier": "standard"},
    "C-20": {"customer_id": "C-20", "name": "Birke KG", "tier": "plus"},
}


def response_for(path: str) -> tuple[int, object]:
    if path == "/health":
        return 200, {"status": "ok"}
    if path == "/orders":
        return 200, ORDERS
    if path == "/customers":
        return 200, list(CUSTOMERS.values())
    if path.startswith("/customers/"):
        customer_id = path.removeprefix("/customers/")
        if customer_id in CUSTOMERS:
            return 200, CUSTOMERS[customer_id]
    return 404, {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status, payload = response_for(self.path)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8066"))), Handler).serve_forever()
