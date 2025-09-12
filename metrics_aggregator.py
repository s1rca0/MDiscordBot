# metrics_aggregator.py
import json, sys, csv, pathlib, collections, time

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def summarize(events):
    by = collections.Counter()
    alerts = 0
    for e in events:
        by[e["event"]] += 1
        if e["event"] == "hud_alert" and not e.get("false_alarm"):
            alerts += 1
    return by, alerts

def write_reports(events, outdir):
    out = pathlib.Path(outdir); out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "continuity_summary.csv"
    md_path  = out / "continuity_summary.md"

    counts, alerts = summarize(events)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["event","count"])
        for k,v in sorted(counts.items()):
            w.writerow([k,v])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Continuity Summary ({time.ctime()})\n\n")
        for k,v in sorted(counts.items()):
            f.write(f"- **{k}**: {v}\n")
        f.write(f"\nAlerts (true): **{alerts}**\n")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python metrics_aggregator.py <log_path> <out_dir>")
        sys.exit(2)
    events = list(load(sys.argv[1]))
    write_reports(events, sys.argv[2])
    print("Wrote CSV + Markdown to", sys.argv[2])