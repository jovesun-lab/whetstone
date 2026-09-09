#!/usr/bin/env python3
"""PostToolUse hook -- the driver that makes the strain check fire on its own.

Counts tool calls for this session and, every N calls, returns a directive telling the
agent to run the strain check now. The host inserts that directive next to the tool
result, which is the entire point: a check the agent is merely asked to remember is
crowded out by the work, and decays to silence. The one that fires from outside does not.

Emits nothing on the other N-1 calls.

Mechanism: PostToolUse honours `hookSpecificOutput.additionalContext`, which the host
wraps in a reminder and shows to the agent. Plain stdout would not work here -- for
PostToolUse it goes to the debug log and the agent never sees it.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (TIERS, state_dir, session_path, load, save, blank, now_iso,
                            touch_index, read_payload, log_model, floor_tier,
                            signals_of, signal_floor, pattern_note)
import _strain_context as ctxmod

DEFAULT_N = 10          # tool calls between ticks


def propose_tier(st, ctx):
    """The tier v2 proposes, computed here rather than left to the agent's mood.

    Fill is PRIMARY: the band the window sits in. Floors are the only other inputs --
    escaped hard signals (absolute) and compactions (objective length). One composite:
    fill already past the Warning band plus at least one escaped signal justifies
    Danger even before the top band. Nothing else escalates; in particular the NUMBER
    OF TICKS never does -- v1's "continuing past Warning => Danger" ratcheted on the
    10-call treadmill and pinned Danger at a measured 33%% fill, three fixtures running.
    Returns (tier, basis) where basis says where the number came from.
    """
    fill = ctxmod.fill_tier(ctx)
    tier = fill or "Healthy"
    basis = ("fill %s%%" % ctx.get("pct")) if fill else "no fill measurement"
    sfloor = signal_floor(st)
    if sfloor:
        tier = floor_tier(tier, sfloor)
        basis += " + escaped-signal floor %s" % sfloor
    comp = int(st.get("compactions", 0))
    if comp:
        cfloor = "Warning" if comp >= 2 else "High"
        tier = floor_tier(tier, cfloor)
        basis += " + compaction floor %s" % cfloor
    escaped = sum(1 for s in signals_of(st) if s.get("escaped"))
    if escaped >= 1 and fill in ("Warning", "Danger"):
        tier = "Danger"
        basis += " + escaped signal past the Warning band"
    return tier, basis


def build_directive(n, st, ctx, substrate=""):
    bits = []
    ctx_line = ctxmod.describe(ctx)
    if ctx_line:
        bits.append(" MEASURED: %s." % ctx_line)
    else:
        bits.append(" No context measurement on this host -- count behaviour, and say so"
                    " rather than quoting a number you did not measure.")
    if int(st.get("compactions", 0)) > 0:
        bits.append(" Context has been COMPACTED %d time(s) this session -- an objective"
                    " sign of length, floored into the proposal." % int(st["compactions"]))
    note = pattern_note(st)
    if note:
        bits.append(" " + note)
    proposed, basis = propose_tier(st, ctx)
    carried = st.get("last", "Healthy")
    decay = ""
    try:
        if TIERS.index(proposed) < TIERS.index(carried):
            decay = (" The proposal is LOWER than the carried tier -- that is allowed:"
                     " strain decays when the load does; record the lower tier unless"
                     " something the counters cannot see says otherwise.")
    except ValueError:
        pass
    return (
        "\U0001FA7A STRAIN TICK (%d tool calls since the last check)."
        " PROPOSED TIER: %s (%s); carried: %s.%s%s"
        " Confirm or adjust, then record it:"
        " `bash \"$CLAUDE_PLUGIN_ROOT/scripts/strain-level.sh\" <Healthy|Mid|High|Warning|Danger>`."
        " Adjust UP only for a NEW hard signal the state file has not seen -- record it"
        " first (`strain-signal.sh <kind> --caught|--escaped`): an error that ESCAPED to"
        " the user floors the tier; one you caught and fixed pre-delivery is a working"
        " immune system and moves nothing (say so, don't tier on it). Never escalate"
        " because ticks accumulated or because the previous check was high -- fill and"
        " fresh signals are the only ladders. An unrecorded tier is how this reading"
        " silently stays at its first value. [%s]"
        % (n, proposed, basis, carried, decay, "".join(bits),
           ctxmod.calibration_line(ctx, substrate or st.get("substrate", "")))
    )


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--state-dir", default=None)
    args, _ = ap.parse_known_args()

    N = args.n if args.n is not None else int(os.environ.get("STRAIN_N", DEFAULT_N))
    sdir = state_dir(args.state_dir)

    payload = read_payload(sys.stdin)
    sid = str(payload.get("session_id", "") or "")
    cwd = str(payload.get("cwd", "") or "")

    path = session_path(sdir, sid)
    st = load(path) or blank(sid, cwd)
    st["sid"] = sid or st.get("sid", "")
    if cwd:
        st["cwd"] = cwd
    st["tick"] = int(st.get("tick", 0)) + 1

    # Context is re-read every tick (a bounded tail scan); the baseline is read once and
    # then carried, because what the boot cost cannot change later in the session.
    prev_ctx = st.get("ctx") if isinstance(st.get("ctx"), dict) else {}
    ctx = ctxmod.measure(payload, sid, known_baseline=prev_ctx.get("baseline"))
    st["ctx"] = ctx
    if not st.get("substrate"):
        st["substrate"] = ctxmod.detect_substrate(payload, cwd)

    # The model comes from the transcript tail, not the hook payload -- SessionStart
    # fires before the transcript exists and its payload usually omits the model, so the
    # tick is the first moment "which model is this" is actually observable. Log on
    # change only: the first observation gets a row, and so does a mid-session /model
    # switch; the other N-1 ticks stay silent.
    observed = str(ctx.get("model") or "")
    if observed and observed != str(st.get("model") or ""):
        st["model"] = observed
        log_model(sdir, sid, "observed", observed, cwd)

    st["updated"] = now_iso()
    save(path, st)
    touch_index(sdir, sid, cwd)

    if N > 0 and st["tick"] % N == 0:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": build_directive(N, st, ctx, st.get("substrate", "")),
        }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # a strain counter must never fail a tool call
