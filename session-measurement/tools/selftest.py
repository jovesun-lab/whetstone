#!/usr/bin/env python3
"""session-measurement selftest — builds the charts from examples/sessions.example.json in memory.

No files are written and cairosvg is not needed: the checks call the two SVG builders directly and the command line only
for its usage line.

    python3 session-measurement/tools/selftest.py        (from the repo root, or from anywhere)
    exit 0 = every check passed; each failure prints one FAIL line.
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.dont_write_bytecode = True   # no __pycache__ left in the repo
sys.path.insert(0, HERE)
import render_benchmark as rb  # noqa: E402

n = 0
failed = 0


def check(what, ok):
    global n, failed
    n += 1
    if not ok:
        failed += 1
        print(f"FAIL #{n}: {what}")


def parses(svg):
    try:
        ET.fromstring(svg)
        return True
    except ET.ParseError:
        return False


def has_emoji(text):
    # the rasteriser has no emoji font (render_benchmark.py: NO EMOJI) — pictographs and symbol blocks
    return any(0x1F000 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF for c in text)


data = json.load(open(os.path.join(ROOT, "examples", "sessions.example.json")))
metrics = data.get("metrics") or rb.DEFAULT_METRICS

# 1 · the example data is what the renderer expects
check("example: has sessions", len(data["sessions"]) > 0)
check("example: every session has an id and metrics", all(s.get("id") and s.get("metrics") for s in data["sessions"]))
known = {m[0] for m in rb.DEFAULT_METRICS}
check("example: every metric name is a known one", all(k in known for s in data["sessions"] for k in s["metrics"]))
check("default metrics: [full, short, signal], signal is strength or weakness",
      all(len(m) == 3 and m[2] in rb.SIG for m in rb.DEFAULT_METRICS))

# 2 · one chart per session
for s in data["sessions"]:
    svg = rb.build_session_svg(s, metrics)
    sid = s["id"]
    check(f"session {sid}: well-formed SVG", parses(svg))
    check(f"session {sid}: every metric it holds is drawn", all(rb.esc(k) in svg for k in s["metrics"]))
    check(f"session {sid}: its label is shown", rb.esc(s.get("label", "")) in svg)
    check(f"session {sid}: no emoji", not has_emoji(svg))

# 3 · the trend table
trend = rb.build_trend_svg(data, metrics)
check("trend: well-formed SVG", parses(trend))
check("trend: every session id is a column", all(rb.esc(s["id"]) in trend for s in data["sessions"]))
check("trend: the short labels are the rows",
      all(rb.esc(m[1]) in trend for m in metrics if any(m[0] in s["metrics"] for s in data["sessions"])))
check("trend: no emoji", not has_emoji(trend))

# 4 · a project's own metric list is used when the data carries one; text is escaped
own = {"sessions": [{"id": "X1", "label": "a <b> & c", "metrics": {"Tests written first": 3}}],
       "metrics": [["Tests written first", "Tests first", "strength"]]}
svg = rb.build_session_svg(own["sessions"][0], own["metrics"])
check("own metrics: drawn", "Tests written first" in svg and parses(svg))
check("own metrics: the label is escaped", "a &lt;b&gt; &amp; c" in svg)
check("own metrics: trend", "Tests first" in rb.build_trend_svg(own, own["metrics"]))

# 5 · the command line without arguments prints its usage and exits 1
r = subprocess.run([sys.executable, os.path.join(HERE, "render_benchmark.py")], capture_output=True, text=True)
check("cli: no arguments → usage, exit 1", r.returncode == 1 and "usage" in r.stdout)

if failed:
    print("selftest FAILED")
    sys.exit(1)
print(f"selftest: {n}/{n} checks passed")
