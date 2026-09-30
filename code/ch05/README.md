# Chapter 5: Workflow, nodes and executions

Independent loopback-only teaching lab. It analyzes a synthetic text fixture,
never a personal file. Requirements: Docker Compose v2 and Python 3.12+ on the
host. n8n 2.40.7 and PostgreSQL 17.11 run in containers. No paid n8n feature
or API key is required.

1. From this directory run `python3 init_env.py`, then
   `docker compose config --quiet` and
   `docker compose up -d --build --wait`.
2. Open `http://127.0.0.1:15679`. Create the local owner account
   if prompted. Open the imported workflow
   **CH05 - file analysis: manual and webhook**. If it is not shown after
   owner setup, use the editor's **Import from file** with
   `n8n/workflows/ch05-file-analysis.json`; keep the imported
   workflow unpublished for the first comparison.
3. Click **Execute workflow**. The manual trigger fetches the synthetic
   fixture; **Analyze Document** should return `verdict: review`,
   four lines and a SHA-256 digest. Pin **Load Synthetic Fixture** in the
   editor, then run again to see that manual execution can reuse that output.
   Unpin after the exercise.
4. Before publication, this command must fail with HTTP 404:

   `python3 send_file.py --url http://127.0.0.1:15679/webhook/ch05-file-analysis`

5. In the editor **Publish** the workflow. Allow a few seconds for webhook
   registration, then run the same command again. It should return HTTP 200
   and the JSON analysis. The production execution appears in
   **Executions**, not as live data on the editor canvas. It uses the
   request body, never pinned editor data.
6. For a test webhook instead, click **Listen for test event** in the Webhook
   node and, within the short registration window, run:

   `python3 send_file.py --url http://127.0.0.1:15679/webhook-test/ch05-file-analysis`

Automated checks: `python3 -m unittest discover -s tests -v`.
The analyzer itself can be checked at `http://127.0.0.1:18055/health`.
If you changed the host ports in `.env`, adjust the URLs.

Stop safely with `docker compose down`. This retains volumes and
the local, Git-ignored `.env`. Do not use `down --volumes`
unless you deliberately want to destroy this lab's database and n8n state.
On a repeat visit, the workflow may already be published; unpublish it in
the editor if you want to repeat the initial 404 exercise.
The Python HTTP analyzer has no authentication and is not a production
service. Its host port is bound to loopback; do not expose this stack publicly.
