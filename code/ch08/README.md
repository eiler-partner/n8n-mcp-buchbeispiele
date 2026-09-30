# Chapter 8: APIs, signed webhooks and idempotency

Independent lab with n8n 2.40.7, PostgreSQL 17.11 and a Python 3.12.11
service. Data is synthetic. Only loopback host ports are published. The
teaching API returns three pages of 3, 3 and 1 record; the order endpoint
accepts only a signed delivery and stores each event in one SQLite
transaction. No paid n8n feature or external provider is required.

Requirements: Docker Compose v2 and Python 3.9+ on the host.

1. In code/ch08/, run python3 init_env.py, docker compose config --quiet,
   and docker compose up -d --build --wait. The private .env is created
   with mode 0600 and never overwritten. n8n is at
   http://127.0.0.1:15682; the teaching API is at 127.0.0.1:18068.
2. Run python3 -m unittest discover -s tests -v and then
   python3 verify_live.py. The latter publishes the webhook, runs the
   paginated HTTP Request in real n8n, sends valid, duplicate, modified,
   stale and conflicting deliveries to the production webhook URL, and
   checks the persistent order count.
3. In the editor, create a local owner account if asked. If the two
   pre-imported CH08 workflows are not visible, import both JSON files from
   n8n/workflows/. Publish CH08 - signed webhook and idempotent order before
   manually calling its production URL.

The signature format is specific to this teaching service, not a GitHub,
Stripe or n8n protocol:

    X-Lab-Timestamp: decimal Unix seconds
    X-Lab-Delivery: stable delivery ID
    X-Lab-Signature: v1=<HMAC-SHA256(secret, timestamp + "." + delivery_id + "." + raw_body)>

The sender signs the exact UTF-8 bytes; the n8n Webhook uses Raw Body and
forwards those bytes without JSON reserialization. The Python service checks
a five-minute timestamp window, constant-time signature comparison, event
schema and an atomic unique event ID. Same ID and body returns 200 with
duplicate: true; same ID with changed body returns 409. The first valid
delivery returns 201. Authentication failures return 401 and invalid
business payloads return 400. The n8n Webhook's built-in Basic/Header/JWT
authentication is not HMAC signature verification.

Expected live output:

    PASS: n8n fetched pages 3 + 3 + 1 and seven distinct IDs
    PASS: signed delivery accepted once, duplicate acknowledged without another order
    PASS: tampering and stale replay rejected; conflicting event rejected; count +1

The GET /throttle endpoint always answers 429 with Retry-After: 2 so the
backoff signal can be inspected without waiting for a real provider. It is
not auto-retried by the workflow. A production retry loop must bound both
attempt count and elapsed time and must not blindly retry non-idempotent
writes. The read-only paginated endpoint has no auth only because this is
synthetic, loopback-only teaching data. Never publish this stack to the
internet or use real orders/secrets.

Stop with docker compose down. Named volumes and .env remain; subsequent
verification runs use a new event ID and expect the order count to rise by
exactly one. --volumes is intentionally not part of cleanup.
