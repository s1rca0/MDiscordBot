# metrics_aggregator.py (enhanced)
import json, sys, csv, pathlib, collections, time, gzip, tempfile, os

def iter_events(src):
    p = pathlib.Path(src)
    if p.is_dir():
        for path in sorted(p.glob("*.jsonl*")):
            yield from _read_jsonl(path)
    else:
        yield from _read_jsonl(p)

def _read_jsonl(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except json.JSONDecodeError:
                # keep going; log a synthetic event so we can see noise
                yield {"event": "parse_error", "file": str(path), "line": idx}

def summarize(events):
    counts = collections.Counter()
    true_alerts = 0
    for e in events:
        evt = e.get("event", "unknown")
        counts[evt] += 1
        if evt == "hud_alert" and not e.get("false_alarm"):
            true_alerts += 1
    return counts, true_alerts

def _atomic_write_text(path: pathlib.Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        tmp.write(text)
        tmp_path = pathlib.Path(tmp.name)
    os.replace(tmp_path, path)

def _atomic_write_csv(path: pathlib.Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", newline="", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        w = csv.writer(tmp)
        w.writerow(["event", "count"])
        for k, v in rows:
            w.writerow([k, v])
        tmp_path = pathlib.Path(tmp.name)
    os.replace(tmp_path, path)

def write_reports(events, outdir):
    out = pathlib.Path(outdir)
    counts, true_alerts = summarize(events)
    ordered = sorted(counts.items())

    csv_path = out / "continuity_summary.csv"
    md_path  = out / "continuity_summary.md"

    _atomic_write_csv(csv_path, ordered)

    md = [f"# Continuity Summary ({time.ctime()})", ""]
    for k, v in ordered:
        md.append(f"- **{k}**: {v}")
    md.append(f"\nAlerts (true): **{true_alerts}**\n")
    _atomic_write_text(md_path, "\n".join(md))

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python metrics_aggregator.py <log_path_or_dir> <out_dir>")
        sys.exit(2)
    src, outdir = sys.argv[1], sys.argv[2]
    evts = list(iter_events(src))
    write_reports(evts, outdir)
    print("Wrote CSV + Markdown to", outdir)
    # non-zero exit if any parse errors to surface noisy logs in CI
    bad = any(e.get("event") == "parse_error" for e in evts)
    sys.exit(1 if bad else 0)