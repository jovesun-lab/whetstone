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
from _strain_common import (state_dir, session_path, load, save, blank, now_iso,
                            touch_index, read_payload, log_model)
import _strain_context as ctxmod

DEFAULT_N = 10          # tool calls between ticks


def build_directive(n, st, ctx):
    bits = []
    ctx_line = ctxmod.describe(ctx)
    if ctx_line:
        bits.append(" MEASURED: %s." % ctx_line)
    else:
        bits.append(" No context measurement on this host -- count behaviour, and say so"
                    " rather than quoting a number you did not measure.")
    if int(st.get("compactions", 0)) > 0:
        bits.append(" Context has been COMPACTED %d time(s) this session -- that is a hard"
                    " signal of length, not a fresh start." % int(st["compactions"]))
    floor = ctxmod.context_floor(ctx)
    if floor:
        bits.append(" Context occupancy alone justifies at least %s." % floor)
    return (
        "\U0001FA7A STRAIN TICK (%d tool calls since the last check). Run the session-strain"
        " check now, before further work: read the task list (one MAIN goal + how many side"
        " tasks have piled under it), add the hard signals (a factual error caught, a"
        " regression introduced, a self-revert), and report the tier to the user in the"
        " per-tier format -- Healthy: one line; Mid/High: the counts plus a suggestion to"
        " wrap soon; Warning/Danger: the counts, the hard signals, why, and a recommendation"
        " to wrap now.%s Then record it:"
        " `bash \"$CLAUDE_PLUGIN_ROOT/scripts/strain-level.sh\" <Healthy|Mid|High|Warning|Danger>`."
        " An unrecorded tier is how this reading silently stays at its first value."
        " [tier carried into this check: %s]"
        % (n, "".join(bits), st.get("last", "Healthy"))
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
            "additionalContext": build_directive(N, st, ctx),
        }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # a strain counter must never fail a tool call
