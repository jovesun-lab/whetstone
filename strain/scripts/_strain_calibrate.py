#!/usr/bin/env python3
"""Record a context window for one <product> · <model> -- sourced, dated, and typed.

    strain-calibrate.sh --product "Example Host" --model ex-model-1 --window 258400 \
                        --basis runtime --source "host runtime log, session settings pane"
    strain-calibrate.sh --show

Why this exists (first cross-model field report, 2026-09-22): a session on a
non-Claude host had its runtime window ON SCREEN -- 258,400 tokens, reported by the
host itself -- and strain still ran blind, because the transcript reader knows one
host's shape and there was no front door for handing the number over.

0.8.0: a record belongs to ONE <product> · <model> (models.json, one entry per key).
0.6.0/0.7.0 kept one record per machine and every session on the machine divided by it:
a Codex session's 258,400 became the window of every Claude Code session next to it.
Now the model must match always, the product too on a host strain recognises, and a
window the host reports live beats any record. calibration.json is no longer written;
an old one is read as one more entry and, if it names no model, never applied.

The record is deliberately opinionated:
  --product and --model are REQUIRED -- together they are the key.
  --source is REQUIRED -- an unsourced capacity is a stale ruler waiting to happen.
  --basis is REQUIRED -- `nominal` (published capacity) or `runtime` (what the host
    reports live, e.g. a post-compaction window). A runtime reading mistaken for the
    model's nominal size corrupts every percentage that follows.
  checkedAt is stamped today and the record EXPIRES (default 30 days) -- a stale
    record falls back to the engine's own conservative behaviour, it never silently
    keeps ruling.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, load, session_path, resolve_sid, calibration_valid,
                            registry_entries, lookup_window, save_model, model_key,
                            canon_product, models_path, PRODUCT_OF_SUBSTRATE)


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--product", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--window", type=int, default=None)
    ap.add_argument("--basis", default=None, choices=["nominal", "runtime"])
    ap.add_argument("--source", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--show", action="store_true")
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    # Reading this session (to name its model, or say which record rules it) is a READ:
    # it may guess, and says so.
    sid, how = resolve_sid(sdir, args.session)
    st = load(session_path(sdir, sid)) if sid else {}

    if args.show:
        entries = []
        for key, rec, origin in registry_entries(sdir):
            ok, why = calibration_valid(rec)
            if not key:
                ok, why = False, "names no model -- never applied (re-record with --model)"
            entries.append({"key": key or None, "origin": origin, "record": rec,
                            "valid": ok, "why": why})
        this = None
        if sid:
            look = lookup_window(sdir, st.get("substrate", ""), st.get("model", ""))
            this = {"session": sid, "resolvedBy": how,
                    "host": PRODUCT_OF_SUBSTRATE.get(str(st.get("substrate") or ""))
                    or "unrecognised", "model": st.get("model") or None,
                    "uses": look.get("key") or None,
                    "why": ("this record matches" if look.get("key") else
                            (look.get("note") or "no record matches -- the window comes "
                             "from the host, a model hint or the default"))}
        sys.stdout.write(json.dumps({"registry": models_path(sdir), "entries": entries,
                                     "thisSession": this}, indent=1) + "\n")
        return 0

    if not args.product:
        sys.stderr.write("--product is required (e.g. 'Claude Code', 'Codex')\n")
        return 2
    if not (args.model or "").strip():
        seen = str(st.get("model") or "")
        sys.stderr.write("--model is required: a window belongs to one product AND one model"
                         "%s\n" % ((" (this session runs %s)" % seen) if seen else ""))
        return 2
    if not args.window or args.window <= 0:
        sys.stderr.write("--window must be a positive integer (tokens)\n")
        return 2
    if not args.basis:
        sys.stderr.write("--basis is required: 'nominal' (published capacity) or "
                         "'runtime' (what the host reports live)\n")
        return 2
    if not (args.source or "").strip():
        sys.stderr.write("--source is required: say where the number was read -- an "
                         "unsourced capacity is a stale ruler waiting to happen\n")
        return 2

    rec = {"product": canon_product(args.product), "model": args.model.strip().lower(),
           "window": int(args.window), "basis": args.basis,
           "source": args.source.strip(),
           "checkedAt": time.strftime("%Y-%m-%d")}
    why = save_model(sdir, rec)
    if why:
        sys.stderr.write("could not record: %s\n" % why)
        return 1
    key = model_key(rec["product"], rec["model"])
    # USER-SURFACE (plain words, no paths); AGENT-DIRECTED detail on stderr.
    sys.stdout.write("Strain calibrated: %s %s window, %s tokens — expires in %s days\n"
                     % (key, args.basis, "{:,}".format(int(args.window)),
                        os.environ.get("STRAIN_CALIBRATION_MAX_DAYS", "30")))
    sys.stderr.write("registry: %s · source: %s\n" % (models_path(sdir), rec["source"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
