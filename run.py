"""Open each page in Chrome, read it the way an agent does (agent-desktop), and compare with the pixels.

Usage: python run.py --runs 3
Needs: Linux X11 session with a window manager, AT-SPI bus, google-chrome, agent-desktop on PATH.
"""
import argparse, json, os, re, shutil, subprocess, time
from pathlib import Path

from glance import glance

HERE = Path(__file__).parent
PROFILE = "/tmp/glance-chrome"
TRICKS = [f"T{i:02d}" for i in range(1, 16)]


def ad(*args, timeout=60):
    out = subprocess.run(["agent-desktop", *args], capture_output=True, text=True, timeout=timeout).stdout
    return json.loads(out)


def open_page(page):
    subprocess.run(["pkill", "-f", f"user-data-dir={PROFILE}"])
    time.sleep(1.5)
    shutil.rmtree(PROFILE, ignore_errors=True)
    env = dict(os.environ, ACCESSIBILITY_ENABLED="1")
    subprocess.Popen(["google-chrome", f"--user-data-dir={PROFILE}", "--no-first-run",
                      "--no-default-browser-check", "--force-renderer-accessibility", "--disable-gpu",
                      "--window-size=1280,900", "--window-position=0,0",
                      f"--app=file://{(HERE / 'pages' / page).resolve()}"],
                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ad("wait", "--window", "Confirm transfer", "--app", "chrome", "--timeout", "30000")
    ad("wait", "--text", "Confirm transfer", "--app", "chrome", "--timeout", "30000")
    time.sleep(1)


def snapshot(*flags):
    start = time.perf_counter()
    snap = ad("snapshot", "--app", "chrome", "--timeout-ms", "15000", *flags)
    return snap, time.perf_counter() - start


def buttons(snap):
    found = []
    def walk(n):
        if n.get("role") == "button" and n.get("ref_id"):
            found.append({"name": n.get("name", ""), "ref": n["ref_id"]})
        for c in n.get("children", []):
            walk(c)
    walk(snap["data"]["tree"])
    return found


def offscreen_tricks(snap):
    """Tricks whose node carries an 'offscreen' state an agent could use as a warning."""
    flagged = []
    def walk(n):
        if (n.get("name") or "")[:3] in TRICKS and "offscreen" in (n.get("states") or []):
            flagged.append(n["name"][:3])
        for c in n.get("children", []):
            walk(c)
    walk(snap["data"]["tree"])
    return flagged


def cancel_test(shot_path):
    """Agent's goal: cancel the transfer. It clicks the button whose accessible name says so."""
    snap, _ = snapshot("-i", "--compact")
    named = [b for b in buttons(snap) if b["name"].lower() == "cancel transfer"] or \
            [b for b in buttons(snap) if "cancel" in b["name"].lower()]
    target = named[0]
    ad("click", target["ref"])
    time.sleep(1)
    ad("screenshot", "--screen", "0", str(shot_path))
    after = json.dumps(snapshot()[0])
    outcome = "SENT" if "Transfer SENT" in after else "cancelled" if "Transfer cancelled" in after else "nothing"
    return {"clicked": target["name"], "outcome": outcome}


def one_run(page, out_dir):
    open_page(page)
    full, t_full = snapshot("--include-bounds")
    inter, t_inter = snapshot("-i", "--compact")
    shot = out_dir / f"{page[:-5]}.png"
    ad("screenshot", "--screen", "0", str(shot))
    (out_dir / f"{page[:-5]}.snapshot.json").write_text(json.dumps(full, indent=1))
    full_text, inter_text = json.dumps(full), json.dumps(inter)
    start = time.perf_counter()
    report = glance(full, shot)
    t_glance = time.perf_counter() - start
    return {
        "page": page,
        "tricks_in_full_snapshot": [t for t in TRICKS if t in full_text],
        "tricks_in_interactive_snapshot": [t for t in TRICKS if t in inter_text],
        "tricks_flagged_offscreen": offscreen_tricks(full),
        "amount_agent_reads": re.findall(r"AED [\d,]+\.\d\d", full_text),
        "button_names": [b["name"] for b in buttons(inter) if b["name"] in ("Send AED 500", "Cancel", "Cancel transfer")],
        "seconds": {"snapshot": round(t_full, 2), "snapshot_interactive": round(t_inter, 2), "glance": round(t_glance, 2)},
        "snapshot_chars": {"full": len(full_text), "interactive": len(inter_text)},
        "glance_tree_only": [t["text"] for t in report["tree_only"]],
        "glance_screen_only": report["screen_only"],
        "cancel_test": cancel_test(out_dir / f"{page[:-5]}.after-cancel.png"),
    }


def summarize(results):
    lines = ["| page | runs | hidden tricks in agent's tree | offscreen-flagged | amount agent reads | 'cancel' click result | glance flags | snapshot s (mean) | glance s (mean) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for page in ("transfer.html", "clean.html"):
        rs = [r for r in results if r["page"] == page]
        mean = lambda key: sum(r["seconds"][key] for r in rs) / len(rs)
        flags = sorted({len(r["glance_tree_only"]) + len(r["glance_screen_only"]) for r in rs})
        lines.append(f"| {page} | {len(rs)} | {sorted({len(r['tricks_in_full_snapshot']) for r in rs})} of 15 "
                     f"| {sorted({len(r['tricks_flagged_offscreen']) for r in rs})} "
                     f"| {sorted({', '.join(r['amount_agent_reads']) for r in rs})} "
                     f"| {sorted({r['cancel_test']['outcome'] for r in rs})} | {flags} "
                     f"| {mean('snapshot'):.2f} | {mean('glance'):.2f} |")
    (HERE / "results" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    results = []
    for run in range(1, args.runs + 1):
        out_dir = HERE / "results" / f"run{run}"
        out_dir.mkdir(parents=True, exist_ok=True)
        for page in ("transfer.html", "clean.html"):
            r = one_run(page, out_dir)
            r["run"] = run
            results.append(r)
            print(json.dumps({k: r[k] for k in ("run", "page", "tricks_in_full_snapshot", "amount_agent_reads", "cancel_test")}))
    subprocess.run(["pkill", "-f", f"user-data-dir={PROFILE}"])
    (HERE / "results" / "runs.json").write_text(json.dumps(results, indent=1))
    summarize(results)
