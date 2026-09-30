# Chapter 6: n8n items, expressions, and item linking

Independent teaching lab: n8n 2.40.7, PostgreSQL 17.11, and a Python
read-only API with three synthetic order rows and a two-row customer
reference table. It uses no credentials for external providers and no paid
n8n feature. The Code node contains a small JavaScript transformation because
n8n's item-linking expressions use the JavaScript runtime; the source API
and local tests are Python.

Requirements: Docker Compose v2 and Python 3.12+ on the host.

1. In `code/ch06/` run:

   `python3 init_env.py`
   `docker compose config --quiet`
   `docker compose up -d --build --wait`
   `python3 -m unittest discover -s tests -v`

2. Inspect `http://127.0.0.1:18066/orders` and
   `http://127.0.0.1:18066/customers`. The middle order intentionally
   has a null customer ID; the other two have amount strings and timestamps
   with explicit UTC offsets.
3. Open `http://127.0.0.1:15680` and create the local owner account
   if prompted. Open **CH06 - broken item link**. If imported workflows are
   not visible after owner setup, import the JSON files from
   `n8n/workflows/` using the editor's **Import from file** action.
4. Execute the broken workflow. **Normalize Orders** emits two new items from
   three inputs but omits `pairedItem`. At **Join Result**, the
   expression referencing `$('Fetch Orders').item` should fail
   because the lineage is missing.
5. Open **CH06 - repaired item link** and execute it. Its one material change
   is `pairedItem: { item: i }` on each normalized output. The two
   joined results should contain **A-101/Aster GmbH/1250** and
   **A-103/Birke KG/0**, with UTC timestamps. The middle input is excluded
   explicitly, not silently misassigned.

The lab tests can also run headlessly using n8n's CLI while the n8n service
is stopped:

`docker compose stop n8n`
`docker compose run --rm --no-deps n8n execute --id=ch06BrokenLink`
`docker compose run --rm --no-deps n8n execute --id=ch06FixedLink`
`docker compose up -d --wait n8n`

The first execute command is intentionally expected to fail. The second
should succeed. Do not rely on a command's console exit status alone;
inspect the node result and final item values.

Stop safely with `docker compose down`. Volumes and the local,
Git-ignored `.env` remain. The Python API is unauthenticated and
its host port is bound to loopback only. Never expose this teaching stack
on a public interface.
