#!/usr/bin/env python
"""Stdlib-only load smoke against a running StudyAI stack (§53, §75).

Measures p50/p95/p99 latencies for read-heavy scenarios and reports them
against the architecture's engineering targets:
  - non-AI API < 500 ms (p95)
Run:  ../myenv/bin/python scripts/load_test.py --base http://127.0.0.1:8000 \
      --email load@example.com --password s3curePass!x --n 200 --threads 20
"""
import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def timed(fn):
    started = time.perf_counter()
    status = fn()
    return (time.perf_counter() - started) * 1000.0, status


def request(url, *, method="GET", token=None, body=None, content_type="application/json"):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    def do():
        try:
            with urllib.request.urlopen(req) as resp:
                resp.read()
                return resp.status
        except urllib.error.HTTPError as exc:
            exc.read()
            return exc.code

    return do


def run_scenario(name, fn, total: int, threads: int) -> dict:
    latencies = []
    statuses: dict[int, int] = {}

    def worker(i):
        ms, status = timed(fn(i))
        latencies.append(ms)
        statuses[status] = statuses.get(status, 0) + 1

    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(worker, range(total)))

    latencies.sort()

    def pct(p):
        if not latencies:
            return 0.0
        idx = min(len(latencies) - 1, int(round(p / 100 * (len(latencies) - 1))))
        return round(latencies[idx], 1)

    summary = {
        "scenario": name,
        "requests": total,
        "statuses": statuses,
        "p50_ms": pct(50),
        "p95_ms": pct(95),
        "p99_ms": pct(99),
        "max_ms": round(latencies[-1], 1),
    }
    print(json.dumps(summary))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--threads", type=int, default=20)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    results = []

    results.append(run_scenario(
        "healthz",
        lambda i: request(f"{base}/healthz"),
        total=args.n, threads=args.threads,
    ))

    login_status = {}

    def do_login(i):
        def fn():
            return request(f"{base}/api/v1/auth/login", method="POST",
                           body={"email": args.email, "password": args.password})
        return fn

    # single login to obtain token for authenticated scenario
    ms, _ = timed(do_login(0))
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{base}/api/v1/auth/login", method="POST",
                                   data=json.dumps({"email": args.email, "password": args.password}).encode(),
                                   headers={"Content-Type": "application/json"})
        ) as resp:
            token = json.loads(resp.read())["access"]
    except urllib.error.HTTPError as exc:
        print("login failed:", exc.code); raise SystemExit(1)

    results.append(run_scenario(
        "auth.login",
        lambda i: request(f"{base}/api/v1/auth/login", method="POST",
                          body={"email": args.email, "password": args.password}),
        total=min(args.n, 50), threads=max(1, args.threads // 2),  # throttled endpoint — keep modest
    ))

    results.append(run_scenario(
        "documents.list (authenticated)",
        lambda i: request(f"{base}/api/v1/documents", token=token),
        total=args.n, threads=args.threads,
    ))

    results.append(run_scenario(
        "revision.overview (authenticated)",
        lambda i: request(f"{base}/api/v1/revision/overview", token=token),
        total=args.n, threads=args.threads,
    ))

    print("\n=== Summary vs §75 targets (non-AI API p95 < 500 ms) ===")
    failures = []
    for r in results:
        verdict = "OK" if r["p95_ms"] < 500 else "OVER TARGET"
        print(f"{r['scenario']:36s} p50={r['p50_ms']:>8} p95={r['p95_ms']:>8} max={r['max_ms']:>9} {verdict}")
        if r["p95_ms"] >= 500 and "auth" not in r["scenario"]:
            failures.append(r["scenario"])
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
