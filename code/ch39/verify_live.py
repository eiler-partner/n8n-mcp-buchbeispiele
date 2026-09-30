"""Bounded real n8n queue-mode integration test with isolated cleanup."""
from __future__ import annotations

import concurrent.futures
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBHOOK = "http://127.0.0.1:15739/webhook/ch39-job"


def command(*args: str, env: dict[str, str], capture: bool = False) -> str:
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, check=True,
                            capture_output=capture, timeout=300)
    return result.stdout if capture else ""


def compose(env: dict[str, str], *args: str, capture: bool = False) -> str:
    return command("docker", "compose", *args, env=env, capture=capture)


def generate_secrets(folder: Path) -> list[str]:
    values = []
    for name, size in (("db_password", 40), ("n8n_key", 48), ("runner_token", 48)):
        value = secrets.token_urlsafe(size)
        descriptor = os.open(folder / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
        (folder / name).chmod(0o644)  # private parent remains mode 0700
        values.append(value)
    return values


def fixture(env: dict[str, str], action: str) -> dict:
    script = (
        "import json,urllib.request;"
        f"r=urllib.request.Request('http://127.0.0.1:8139/{action}',"
        f"method={'POST' if action == 'reset' else 'GET'!r});"
        "print(json.dumps(json.load(urllib.request.urlopen(r,timeout=5))))"
    )
    raw = compose(env, "exec", "-T", "workload", "python", "-c", script, capture=True)
    return json.loads(raw)


def waiting_jobs(env: dict[str, str]) -> int | None:
    # Diagnostics only. Redis/Bull key names are implementation details, not a public API.
    lua = "local n=0; for _,k in ipairs(redis.call('keys','*:wait')) do n=n+redis.call('llen',k) end; return n"
    try:
        raw = compose(env, "exec", "-T", "redis", "redis-cli", "--raw", "EVAL", lua, "0",
                      capture=True).strip()
        return int(raw)
    except (subprocess.CalledProcessError, ValueError):
        return None


def request_job(job_id: str, delay_ms: int = 450) -> dict:
    data = json.dumps({"id": job_id, "delay_ms": delay_ms}).encode()
    request = urllib.request.Request(WEBHOOK, data=data,
                                     headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.load(response)
            return {"id": job_id, "status": response.status, "body": body,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1)}
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        return {"id": job_id, "error": str(exc),
                "latency_ms": round((time.monotonic() - started) * 1000, 1)}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5)))
    return ordered[index]


def burst(env: dict[str, str], prefix: str, count: int) -> dict:
    fixture(env, "reset")
    stop_sample = threading.Event()
    samples: list[int] = []

    def sampler() -> None:
        while not stop_sample.wait(0.15):
            value = waiting_jobs(env)
            if value is not None:
                samples.append(value)

    monitor = threading.Thread(target=sampler, daemon=True)
    monitor.start()
    began = time.monotonic()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(request_job, f"{prefix}-{i:02d}") for i in range(count)]
            results = [future.result() for future in futures]
    finally:
        stop_sample.set()
        monitor.join(timeout=5)
    elapsed = time.monotonic() - began
    stats = fixture(env, "stats")
    failures = [item for item in results if item.get("status") != 200 or
                item.get("body") != {"id": item["id"], "ok": True, "runner": "external-python"}]
    assert not failures, f"workflow errors: {failures[:3]}"
    assert stats["completed"] == count, stats
    assert stats["active"] == 0, stats
    assert sorted(stats["ids"]) == sorted(item["id"] for item in results), stats
    latencies = [item["latency_ms"] for item in results]
    return {"requests": count, "errors": len(failures),
            "error_rate": 0.0, "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
            "elapsed_s": round(elapsed, 3), "throughput_rps": round(count / elapsed, 2),
            "fixture_max_active": stats["max_active"],
            "redis_wait_list_peak_if_visible": max(samples) if samples else None}


def main() -> None:
    private = Path(tempfile.mkdtemp(prefix="buch-ch39-", dir="/private/tmp"))
    private.chmod(0o700)
    env = dict(os.environ, CH39_SECRET_DIR=str(private),
               COMPOSE_PROJECT_NAME=f"buch-ch39-check-{secrets.token_hex(4)}")
    values = generate_secrets(private)
    started = False
    try:
        rendered = compose(env, "--profile", "scale", "config", "--format", "json", capture=True)
        config = json.loads(rendered)
        assert all(value not in rendered for value in values)
        assert {str(entry["published"]) for name in ("webhook", "main")
                for entry in config["services"][name]["ports"]} == {"15739", "15740"}
        started = True
        try:
            compose(env, "up", "-d", "--wait")
        except subprocess.CalledProcessError:
            subprocess.run(("docker", "compose", "logs", "--tail", "60"),
                           cwd=ROOT, env=env, text=True, check=False, timeout=30)
            raise

        last_error = None
        for _ in range(35):
            try:
                warmup = request_job("warmup-0", 100)
                if warmup.get("body") == {"id": "warmup-0", "ok": True,
                                           "runner": "external-python"}:
                    break
                last_error = warmup
            except Exception as exc:
                last_error = str(exc)
            time.sleep(1)
        else:
            raise AssertionError(f"queue/runner warmup failed: {last_error}")

        one = burst(env, "one", 18)
        assert 1 <= one["fixture_max_active"] <= 5, one
        # Add only the new pair; re-running bootstrap while main is active
        # would import/publish the same workflow again unnecessarily.
        compose(env, "--profile", "scale", "up", "-d", "--wait", "--no-deps", "worker2")
        compose(env, "--profile", "scale", "up", "-d", "--wait", "--no-deps", "runner2")
        two = burst(env, "two", 18)
        assert 1 <= two["fixture_max_active"] <= 10, two
        compose(env, "stop", "worker1", "runner1")
        failover = burst(env, "survivor", 8)
        assert 1 <= failover["fixture_max_active"] <= 5, failover

        for service in ("main", "webhook", "worker1", "worker2", "runner1", "runner2",
                        "postgres", "redis", "workload"):
            container_id = compose(env, "--profile", "scale", "ps", "-a", "-q", service,
                                   capture=True).strip()
            inspect = command("docker", "inspect", container_id, env=env, capture=True)
            assert all(value not in inspect for value in values), service

        report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                  "images": {"n8n": "n8nio/n8n:2.40.7", "runner": "n8nio/runners:2.40.7"},
                  "fixture_delay_ms": 450, "worker_concurrency": 5,
                  "one_worker": one, "two_workers": two,
                  "worker1_stopped_worker2_survives": failover,
                  "notes": ["Local synthetic I/O only; not a throughput guarantee.",
                            "Redis wait-list sample is diagnostic, not a supported queue API.",
                            "Main remains a single point of failure without licensed multi-main."]}
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports/live-observation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("PASS chapter 39 live: queue, bounded load, two worker/runner pairs, worker loss")
    except Exception:
        if started:
            subprocess.run(("docker", "compose", "--profile", "scale", "logs", "--tail", "70"),
                           cwd=ROOT, env=env, text=True, check=False, timeout=30)
        raise
    finally:
        try:
            if started:
                compose(env, "--profile", "scale", "down", "-v")
        finally:
            shutil.rmtree(private)


if __name__ == "__main__":
    main()
