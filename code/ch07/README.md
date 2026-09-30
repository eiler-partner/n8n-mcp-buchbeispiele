# Chapter 7: control flow and data processing

Independent lab with n8n 2.40.7, PostgreSQL 17.11, and a read-only Python
API. Every record is synthetic. No external provider, paid feature, or
credential is required. Host ports are bound to loopback.

Requirements: Docker Compose v2 and Python 3.9+ on the host; the API image
uses Python 3.12.11.

1. In `code/ch07/`, run `python3 init_env.py`, `docker compose config --quiet`,
   and `docker compose up -d --build --wait`. An existing private `.env` is
   preserved. The editor is at `http://127.0.0.1:15681`; the API is at
   `http://127.0.0.1:18067/cases/empty` (also `single`, `large`, `filtered`).
2. Run `python3 -m unittest discover -s tests -v` for the local contract tests.
   Then run `python3 verify_live.py`. It publishes the two workflow versions,
   restarts n8n once to load the publication, runs both n8n workflows through
   the CLI, compares all outputs to the independent Python oracle, and starts
   the editor again in a `finally` block.
3. In n8n, create the local owner account if prompted. Open **CH07 - empty
   single large and filtered cases** and **CH07 - normalize and summarize
   sub-workflow**. If they are not visible after owner setup, import the JSON
   files in `n8n/workflows/` from the editor. Publish the sub-workflow before
   running the parent. The third workflow, **CH07 - explicit batches of
   three**, shows the 3 + 3 + 1 loop sequence.

The parent fetches four envelopes and calls the child once per envelope with
**Wait for Sub-Workflow Completion** enabled. The child uses **Accept all
data** at the trigger and validates the full schema immediately in
**Validate and Normalize**. This avoids an editor-only schema default while
retaining a strict runtime contract. A positive eligible count enters Split
Out, Filter, Remove Duplicates (within current input, by `rows.id`), Sort,
Aggregate, and Summary Contract. Zero eligible rows take an explicit output
path rather than vanishing at Split Out or Filter. The final node always
returns exactly one summary item per envelope.

Expected results:

| Case | Raw | Eligible | Unique | North cents | South cents |
|---|---:|---:|---:|---:|---:|
| empty | 0 | 0 | 0 | 0 | 0 |
| single | 1 | 1 | 1 | 1250 | 0 |
| large | 150 | 133 | 114 | 54000 | 46400 |
| filtered | 2 | 0 | 0 | 0 | 0 |

`python3 verify_live.py` also asserts that the batch body runs with 3, 3, and
1 items and the Done output returns B-1 through B-7. n8n's internal Python
task-runner warning is unrelated: these Code nodes use JavaScript; the
separate input API and reference calculation use Python.

Stop the stack with `docker compose down`. This preserves named volumes and
the private `.env`. Do not add `--volumes` unless you explicitly intend a
fresh-start exercise. The teaching API has no authentication and must never
be exposed beyond loopback.
