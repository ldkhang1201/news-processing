"""Measure collector latency and throughput.

Self-contained driver. Clone the repo, then on the target machine:

    uv sync
    docker compose up -d
    uv run python scripts/measure.py --fresh --runs 96 --interval 900 --skip-first

That runs 96 collector cycles 15 min apart (~24 h), then prints latency,
throughput, and article-size stats. Drop `--fresh` if you want to keep the
existing dedup state and topic contents.

The script:
    1. Pre-flight: verifies redpanda is reachable; creates the Kafka topic
       if missing.
    2. (with --fresh) Resets dedup.sqlite and the Kafka topic.
    3. Loops `uv run python main.py`, sleeping INTERVAL between runs.
       Collector logs append to --log-file.
    4. Parses the log to compute wall-time and article-count stats.
    5. Samples N messages from Kafka and computes body-size stats.
    6. Prints a report. Ctrl-C at any point prints a report from runs done so far.

To re-analyse a previous session:

    uv run python scripts/measure.py --analyze-only --skip-first --log-file runs/24h.log
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _rpk(*args: str, check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "redpanda", "rpk", *args],
        cwd=ROOT,
        capture_output=capture,
        text=True,
        check=check,
    )


def preflight(topic: str) -> None:
    """Bail with a clear message if Kafka is unreachable; create topic if missing."""
    try:
        r = _rpk("cluster", "health")
    except FileNotFoundError:
        print("ERROR: `docker` not on PATH. Install Docker / Docker Desktop.", file=sys.stderr)
        sys.exit(2)
    if r.returncode != 0:
        print("ERROR: redpanda not reachable. Is the container up?", file=sys.stderr)
        print("       Try: docker compose up -d", file=sys.stderr)
        if r.stderr:
            print(f"       rpk: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    if "Healthy:" in r.stdout and "true" not in r.stdout.split("Healthy:", 1)[1].split("\n", 1)[0]:
        print(f"WARN: redpanda not healthy:\n{r.stdout}", file=sys.stderr)

    listing = _rpk("topic", "list")
    if topic not in listing.stdout:
        print(f"[setup] creating topic {topic!r}", flush=True)
        _rpk("topic", "create", topic, "-p", "3", "-r", "1", check=True)


def reset_state(topic: str, dedup_path: Path) -> None:
    print(f"[reset] removing {dedup_path}", flush=True)
    dedup_path.unlink(missing_ok=True)
    print(f"[reset] recreating topic {topic!r}", flush=True)
    _rpk("topic", "delete", topic)
    _rpk("topic", "create", topic, "-p", "3", "-r", "1", check=True)


def run_loop(runs: int, interval: int, log_path: Path) -> int:
    """Run collector `runs` times, sleeping `interval` between. Returns runs completed."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as logf:
        logf.write(f"\n# === measurement session start: {datetime.now().isoformat()} ===\n")

    completed = 0
    for i in range(1, runs + 1):
        print(f"[run {i}/{runs}] starting", flush=True)
        t0 = time.monotonic()
        with log_path.open("a") as logf:
            r = subprocess.run(
                ["uv", "run", "python", "main.py"],
                cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT,
            )
        dt = time.monotonic() - t0
        completed = i
        print(f"[run {i}/{runs}] exit={r.returncode} elapsed={dt:.2f}s", flush=True)
        if i < runs:
            print(f"[sleep] {interval}s before next run", flush=True)
            time.sleep(interval)
    return completed


def parse_log(log_path: Path, skip_first: bool) -> list[dict]:
    """Return per-run dicts: start, end, wall, total_new, warnings."""
    runs: list[dict] = []
    current: dict | None = None
    warnings_in_current = 0
    if not log_path.exists():
        return runs
    for line in log_path.read_text().splitlines():
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = r.get("event")
        ts = r.get("timestamp")
        if ev == "starting" and ts:
            current = {"start": datetime.fromisoformat(ts)}
            warnings_in_current = 0
        elif r.get("level") == "warning" and current is not None:
            warnings_in_current += 1
        elif ev == "run_complete" and current is not None and ts:
            current["end"] = datetime.fromisoformat(ts)
            current["wall"] = (current["end"] - current["start"]).total_seconds()
            current["total_new"] = r.get("total_new", 0)
            current["warnings"] = warnings_in_current
            runs.append(current)
            current = None
            warnings_in_current = 0
    if skip_first and runs:
        runs = runs[1:]
    return runs


def sample_kafka(topic: str, n: int) -> list[int]:
    """Consume up to n messages, return list of word counts of `content`."""
    out = _rpk("topic", "consume", topic, "-o", "start", "-n", str(n), "--format", "%v\n")
    if out.returncode != 0:
        print(f"[kafka] consume failed: {out.stderr.strip()}", file=sys.stderr)
        return []
    words: list[int] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            a = json.loads(line)
        except json.JSONDecodeError:
            continue
        c = (a.get("content") or "").strip()
        if c:
            words.append(len(c.split()))
    return words


def fmt_lat(values: list[float]) -> str:
    if not values:
        return "(no data)"
    n = len(values)
    parts = [
        f"n={n}",
        f"mean={statistics.mean(values):.2f}s",
        f"p50={statistics.median(values):.2f}s",
        f"min={min(values):.2f}s",
        f"max={max(values):.2f}s",
    ]
    if n >= 10:
        parts.insert(3, f"p90={statistics.quantiles(values, n=10)[8]:.2f}s")
    return " ".join(parts)


def report(runs: list[dict], words: list[int], window_s: float | None, tokens_per_word: float) -> None:
    if not runs:
        print("no runs found in log")
        return

    wall = [r["wall"] for r in runs]
    new = [r["total_new"] for r in runs]
    warn = [r["warnings"] for r in runs]
    actual_window = (runs[-1]["end"] - runs[0]["start"]).total_seconds() if len(runs) >= 2 else None

    print("\n=========== LATENCY ===========")
    print(f"per-run wall: {fmt_lat(wall)}")

    print("\n=========== THROUGHPUT ===========")
    print(f"runs analysed: {len(runs)}")
    print(f"total_new sum: {sum(new)}  (per-run: min={min(new)} max={max(new)} mean={statistics.mean(new):.1f})")
    print(f"warnings (incl. 429): total={sum(warn)} per-run-max={max(warn)}")

    eff_window = actual_window if actual_window else window_s
    if eff_window:
        rate = sum(new) / (eff_window / 3600)
        label = "actual" if actual_window else "planned"
        print(f"window ({label})={eff_window/3600:.2f}h  rate={rate:.1f} articles/hour")

    print("\n=========== ARTICLE SIZE (Kafka sample) ===========")
    if words:
        mean_w = statistics.mean(words)
        p50 = statistics.median(words)
        print(f"n={len(words)}  mean={mean_w:.0f} words  p50={p50:.0f}  max={max(words)}")
        tokens_per_article = mean_w * tokens_per_word
        print(f"tokens/article ≈ {tokens_per_article:.0f}  (assuming {tokens_per_word}× tokens/word)")
        if eff_window:
            rate = sum(new) / (eff_window / 3600)
            tph = rate * tokens_per_article
            print(f"tokens/hour ≈ {tph:.0f}  tokens/min ≈ {tph/60:.0f}  tokens/sec ≈ {tph/3600:.1f}")
    else:
        print("(no Kafka samples — set --samples > 0 and ensure topic has messages)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=18, help="number of runs (default: 18; use 96 for ~24h at 15min)")
    ap.add_argument("--interval", type=int, default=900, help="seconds between runs (default: 900)")
    ap.add_argument("--log-file", type=Path, default=ROOT / "runs/collector.log")
    ap.add_argument("--topic", default="articles")
    ap.add_argument("--dedup-path", type=Path, default=ROOT / "dedup.sqlite")
    ap.add_argument("--samples", type=int, default=200, help="Kafka messages to sample for size")
    ap.add_argument("--tokens-per-word", type=float, default=1.7, help="VN BPE multiplier")
    ap.add_argument("--skip-first", action="store_true", help="drop warmup run from stats")
    ap.add_argument("--fresh", action="store_true", help="reset dedup + topic before running")
    ap.add_argument("--analyze-only", action="store_true", help="skip running, just parse log")
    args = ap.parse_args()

    interrupted = False
    if not args.analyze_only:
        preflight(args.topic)
        if args.fresh:
            reset_state(args.topic, args.dedup_path)
        try:
            run_loop(args.runs, args.interval, args.log_file)
        except KeyboardInterrupt:
            interrupted = True
            print("\n[interrupted] stopping run loop, computing report from runs so far...", flush=True)

    runs = parse_log(args.log_file, skip_first=args.skip_first)
    words = sample_kafka(args.topic, args.samples) if args.samples > 0 else []
    planned_window = (args.runs - 1) * args.interval if args.runs > 1 else None
    report(runs, words, planned_window, args.tokens_per_word)
    if interrupted:
        sys.exit(130)


if __name__ == "__main__":
    main()
