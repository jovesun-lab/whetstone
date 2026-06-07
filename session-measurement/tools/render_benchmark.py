#!/usr/bin/env python3
"""
Generic agent-performance benchmark renderer.

Reads ONE data file — `sessions.json` — and writes:
  • measurement-<id>.png/.svg  — a per-session horizontal bar chart
  • trend-table.png/.svg        — the all-sessions trend matrix

Usage:
    pip install cairosvg --break-system-packages   # one-time
    python3 render_benchmark.py sessions.json [out_dir]

WHY a single JSON file: the agent doing a measurement only edits data, never
this script. Keep the metric set stable across sessions so the trend stays
comparable — that comparability is the whole point of a long-run benchmark.

ENCODING (don't change once a project starts — it makes the colors mean something):
  • green  = strength signal, higher is better
  • red    = weakness signal, higher is worse
  • NO EMOJI anywhere in rendered text — the SVG rasteriser has no emoji font,
    so emoji come out as empty "tofu" boxes. Use plain words / letters.

See references/methodology.md for what each metric means and how to count it.
"""
import json, sys, os

# ---- the stable metric spine (a project may override `metrics` in sessions.json) ----
DEFAULT_METRICS = [
    # (full name, short label for the trend table, signal)
    ["Redefinitions absorbed",                    "Redefinitions absorbed",  "strength"],
    ["Clarifying gates raised (asked, not guessed)", "Clarifying gates raised", "strength"],
    ["Errors the agent self-caught",              "Errors self-caught",      "strength"],
    ["Misses the human caught",                   "Misses human caught",     "weakness"],
    ["Critical bugs - agent caught",              "Crit bugs - agent caught","strength"],
    ["Critical bugs - human caught",              "Crit bugs - human caught","weakness"],
]

SIG = {
    "strength": {"fill": "#163807", "stroke": "#97c459", "text": "#97c459",
                 "arrow": "#97c459", "ctext": "#b6df86", "marker": "aS"},
    "weakness": {"fill": "#3a0e0e", "stroke": "#f09595", "text": "#f09595",
                 "arrow": "#ff4c6e", "ctext": "#f0a0a0", "marker": "aW"},
}
STATUS_COLOR = {"L": "#97c459", "P": "#c7a86a", "N": "#f09595"}  # MAIN-landed L/P/N
BG, PANEL = "#0b0d18", "#1e1d1b"
UNIT, X0, BAR_H, ROW_STEP, BAR_TOP = 150, 40, 20, 68, 82


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_session_svg(sess, metrics):
    """Per-session horizontal bar chart. `metrics` = list of [full, short, signal]."""
    rows = [(m[0], m[2]) for m in metrics if m[0] in sess.get("metrics", {})]
    vals = [sess["metrics"][full] for full, _ in rows]
    foots = sess.get("footnotes", [])
    callouts = sess.get("callouts", {})
    max_val = max(vals) if vals else 1
    grid_max = max(4, max_val)
    grid_w = X0 + grid_max * UNIT + 90
    callout_right = 0
    for full, _ in rows:
        c = callouts.get(full)
        if c:
            be = X0 + max(5, sess["metrics"][full] * UNIT)
            callout_right = max(callout_right, be + 176 + max(len(l) for l in c) * 5.7)
    subtitle = f"{sess.get('label','')}  -  green = strength, red = weakness"
    text_right = [40 + len(subtitle) * 5.6] + [40 + len(f) * 5.1 for f in foots]
    width = int(max(grid_w, callout_right + 40, *text_right) + 24)
    plot_bottom = BAR_TOP + (len(rows) - 1) * ROW_STEP + BAR_H + 16
    foot_y = plot_bottom + 26
    height = int(foot_y + len(foots) * 14 + 8)

    p = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
         f'font-family="system-ui, -apple-system, \'Segoe UI\', Roboto, sans-serif" role="img">']
    p.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="{BG}"/>')
    p.append('<defs>'
             '<marker id="aS" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#97c459"/></marker>'
             '<marker id="aW" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#ff4c6e"/></marker>'
             '</defs>')
    p.append(f'<text x="40" y="26" font-size="16" font-weight="700" fill="rgba(255,255,255,0.86)">This session, counted</text>')
    p.append(f'<text x="40" y="44" font-size="11" fill="rgba(255,255,255,0.5)">{esc(subtitle)}</text>')
    # gridlines
    p.append('<g stroke="rgba(255,255,255,0.10)" stroke-dasharray="3 4">')
    for v in range(1, grid_max + 1):
        p.append(f'<line x1="{X0+v*UNIT}" y1="58" x2="{X0+v*UNIT}" y2="{plot_bottom}"/>')
    p.append('</g>')
    p.append(f'<line x1="{X0}" y1="58" x2="{X0}" y2="{plot_bottom}" stroke="rgba(255,255,255,0.25)"/>')
    p.append('<g font-size="9.5" fill="#7e8aa0" text-anchor="middle">')
    for v in range(0, grid_max + 1):
        p.append(f'<text x="{X0+v*UNIT}" y="68">{v}</text>')
    p.append('</g>')
    # bars
    for i, (full, sig) in enumerate(rows):
        val = sess["metrics"][full]
        c = SIG[sig]
        by = BAR_TOP + i * ROW_STEP
        w = max(5, val * UNIT)
        p.append(f'<rect x="{X0}" y="{by}" width="{w}" height="{BAR_H}" rx="{2 if val==0 else 4}" '
                 f'fill="{c["fill"]}" stroke="{c["stroke"]}" stroke-width="1.6"/>')
        p.append(f'<text x="{X0+w+(14 if val==0 else 10)}" y="{by+15}" font-size="15" font-weight="700" fill="{c["text"]}">{val}</text>')
        p.append(f'<text x="{X0}" y="{by+38}" font-size="11.5" fill="#c4cdde">{esc(full)}</text>')
        co = callouts.get(full)
        if co:
            cy, be = by + 10, X0 + w
            head_x, tail_x = be + 48, be + 168
            p.append(f'<path d="M{tail_x},{cy} L{head_x},{cy}" fill="none" stroke="{c["arrow"]}" stroke-width="1.4" marker-end="url(#{c["marker"]})"/>')
            for j, line in enumerate(co):
                p.append(f'<text x="{tail_x+8}" y="{cy-3+j*14}" font-size="10.5" fill="{c["ctext"]}">{esc(line)}</text>')
    for k, fn in enumerate(foots):
        p.append(f'<text x="40" y="{foot_y+k*14}" font-size="9.5" fill="#6b7689">{esc(fn)}</text>')
    p.append('</svg>')
    return "\n".join(p)


def build_trend_svg(data, metrics):
    sessions = data["sessions"]
    n = len(sessions)
    has_version = any(s.get("version") for s in sessions)
    has_status = any(s.get("main_landed") for s in sessions)
    rows = [(m[0], m[1], m[2]) for m in metrics
            if any(m[0] in s.get("metrics", {}) for s in sessions)]
    special = ([("__version__", data.get("version_axis_label", "version"))] if has_version else []) \
            + ([("__status__", "MAIN landed (L/P/N)")] if has_status else [])
    cx0, col_start, col_step = 40, 470, 68
    width = col_start + (n - 1) * col_step + 60
    header_y, row0, row_step = 70, 150, 70
    total_rows = len(special) + len(rows)
    height = row0 + total_rows * row_step + 12
    serif = "Georgia, 'Times New Roman', serif"
    p = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" font-family="{serif}" role="img">']
    p.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="{PANEL}"/>')
    p.append(f'<text x="{cx0}" y="{header_y}" font-size="23" font-weight="700" fill="#f3f1ec">metric</text>')
    p.append(f'<text x="{cx0}" y="{header_y+16}" font-size="9" fill="#9a8f7e">change/note ↓</text>')
    for i, s in enumerate(sessions):
        xc = col_start + i * col_step
        p.append(f'<text x="{xc}" y="{header_y}" font-size="21" font-weight="700" fill="#f3f1ec" text-anchor="middle">{esc(s.get("id", "S"+str(i+1)))}</text>')
        if s.get("tag"):
            p.append(f'<text x="{xc}" y="{header_y+16}" font-size="9" fill="#c7a86a" text-anchor="middle">{esc(s["tag"])}</text>')
    p.append(f'<line x1="{cx0}" y1="{header_y+26}" x2="{width-30}" y2="{header_y+26}" stroke="rgba(255,255,255,0.22)"/>')
    r = 0
    for key, short in special:
        ry = row0 + r * row_step
        p.append(f'<text x="{cx0}" y="{ry}" font-size="18" font-style="italic" fill="#b9b0a2">{esc(short)}</text>')
        for i, s in enumerate(sessions):
            xc = col_start + i * col_step
            if key == "__version__":
                p.append(f'<text x="{xc}" y="{ry}" font-size="15" fill="#c7a86a" text-anchor="middle">{esc(s.get("version","-"))}</text>')
            else:
                st = s.get("main_landed", "-")
                p.append(f'<text x="{xc}" y="{ry}" font-size="16" font-weight="700" fill="{STATUS_COLOR.get(st,"#7e776c")}" text-anchor="middle">{esc(st)}</text>')
        p.append(f'<line x1="{cx0}" y1="{ry+26}" x2="{width-30}" y2="{ry+26}" stroke="rgba(255,255,255,0.16)"/>')
        r += 1
    for full, short, sig in rows:
        ry = row0 + r * row_step
        is_human = sig == "weakness"
        p.append(f'<text x="{cx0}" y="{ry}" font-size="19" fill="#ece9e3">{esc(short)}</text>')
        for i, s in enumerate(sessions):
            xc = col_start + i * col_step
            val = s.get("metrics", {}).get(full, "-")
            good = (is_human and val == 0)
            colr = "#97c459" if good else ("#7e776c" if val == "-" else "#ece9e3")
            bold = ' font-weight="700"' if good else ''
            p.append(f'<text x="{xc}" y="{ry}" font-size="19" fill="{colr}" text-anchor="middle"{bold}>{val}</text>')
        p.append(f'<line x1="{cx0}" y1="{ry+26}" x2="{width-30}" y2="{ry+26}" stroke="rgba(255,255,255,0.10)"/>')
        r += 1
    p.append('</svg>')
    return "\n".join(p)


def main():
    if len(sys.argv) < 2:
        print("usage: python3 render_benchmark.py sessions.json [out_dir]"); sys.exit(1)
    data = json.load(open(sys.argv[1]))
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(out_dir, exist_ok=True)
    metrics = data.get("metrics") or DEFAULT_METRICS
    try:
        import cairosvg
    except ImportError:
        print("cairosvg not installed. Run: pip install cairosvg --break-system-packages"); sys.exit(1)
    for s in data["sessions"]:
        svg = build_session_svg(s, metrics)
        base = os.path.join(out_dir, f"measurement-{s.get('id','session')}")
        open(base + ".svg", "w").write(svg)
        cairosvg.svg2png(bytestring=svg.encode(), write_to=base + ".png", scale=2)
        print("rendered", base + ".png")
    trend = build_trend_svg(data, metrics)
    tbase = os.path.join(out_dir, "trend-table")
    open(tbase + ".svg", "w").write(trend)
    # keep trend PNG width under ~3000px so it previews in-tool; scale auto-shrinks with column count
    n = len(data["sessions"])
    scale = 2.0 if n <= 12 else max(1.1, 36.0 / n)
    cairosvg.svg2png(bytestring=trend.encode(), write_to=tbase + ".png", scale=scale)
    print("rendered", tbase + ".png")
    print(f"done - {len(data['sessions'])} sessions + trend table")


if __name__ == "__main__":
    main()
