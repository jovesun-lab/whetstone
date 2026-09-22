#!/usr/bin/env python3
"""Record this environment's context window -- sourced, dated, and typed.

    strain-calibrate.sh --product "Codex CLI" --window 258400 --basis runtime \
                        --source "host runtime log, session settings pane"
    strain-calibrate.sh --show

Why this exists (first cross-model field report, 2026-09-22): a session on a
non-Claude host had its runtime window ON SCREEN -- 258,400 tokens, reported by the
host itself -- and strain still ran blind, because the transcript reader knows one
host's shape and there was no front door for handing the number over. The record this
writes becomes the fill denominator (see apply_calibration) until it goes stale.

The record is deliberately opinionated:
  --source is REQUIRED -- an unsourced capacity is a stale ruler waiting to happen.
  --basis is REQUIRED -- `nominal` (published capacity) or `runtime` (what the host
    reports live, e.g. a post-compaction window). A runtime reading mistaken for the
    model's nominal size corrupts every percentage that follows.
  checkedAt is stamped today and the record EXPIRES (default 30 days) -- a shouted
    stale record falls back to the engine's own conservative behaviour, it never
    silently keeps ruling.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, load, save, calibration_path, calibration_valid)


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--product", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--window", type=int, default=None)
    ap.add_argument("--basis", default=None, choices=["nominal", "runtime"])
    ap.add_argument("--source", default=None)
    ap.add_argument("--show", action="store_true")
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    CAL = calibration_path(sdir)

    if args.show:
        cal = load(CAL)
        ok, why = calibration_valid(cal)
        sys.stdout.write(json.dumps({"path": CAL, "record": cal or None,
                                     "valid": ok, "why": why}, indent=1) + "\n")
        return 0

    if not args.product:
        sys.stderr.write("--product is required (e.g. 'Claude Code', 'Codex CLI')\n")
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

    rec = {"product": args.product, "model": args.model or "",
           "window": int(args.window), "basis": args.basis,
           "source": args.source.strip(),
           "checkedAt": time.strftime("%Y-%m-%d")}
    if not save(CAL, rec):
        sys.stderr.write("could not write %s\n" % CAL)
        return 1
    # USER-SURFACE (plain words, no paths); AGENT-DIRECTED detail on stderr.
    sys.stdout.write("Strain calibrated: %s %s window, %s tokens — expires in %s days\n"
                     % (args.product, args.basis, "{:,}".format(int(args.window)),
                        os.environ.get("STRAIN_CALIBRATION_MAX_DAYS", "30")))
    sys.stderr.write("record: %s · source: %s\n" % (CAL, rec["source"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
