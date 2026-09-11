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


def _caps():
    """The Line-A cap ladder for the v3 two-line model.

    Mid/High/Warn come from env with mechanism-grounded defaults; Danger is DERIVED =
    THROTTLE_ONSET - WRAP_BUDGET, so a mandated wrap can COMPLETE before the model
    enters its degraded zone. What each number means, and ⚠️ WHAT YOU MUST FILL IN
    FOR YOUR OWN PROJECT:

      STRAIN_THROTTLE_ONSET (default 80.0) -- the fill %% where your platform's model
        visibly degrades (hidden reasoning, shorter replies, acting without narrating).
        The default is an observed value on one platform, 2026-09. ⚠️ RE-VERIFY ON
        YOURS, and re-verify again when the platform or model changes -- this is a
        physical constant of your environment, not a preference.
      STRAIN_WRAP_BUDGET (default 6.0) -- the context cost of a full session wrap
        (handover artifacts + closing checks). ⚠️ The default is an UNMEASURED
        estimate (5-8%% bracket). Measure YOUR wrap once -- context %% before vs after
        a real wrap -- then pin the number.
      STRAIN_CAP_WARN (70.0) -- where host auto-compaction risk begins.
      STRAIN_CAP_HIGH (60.0) -- where lost-in-the-middle attention dilution shows.
      STRAIN_CAP_MID  (50.0) -- start of deliberate token accounting.

    N1 guard: a broken CONFIG is not a broken MEASUREMENT. If the ladder inverts
    (e.g. a raised WRAP_BUDGET slides derived Danger below WARN), env overrides are
    IGNORED loudly and the built-in defaults stay in force -- a 90%%-full session must
    never sail unwarned because one env var was mistyped. Over-report beats under.
    Returns (mid, high, warn, danger, throttle, invalid)."""
    def f(name, default):
        try:
            return float(os.environ.get(name, default))
        except Exception:
            return default
    throttle = f("STRAIN_THROTTLE_ONSET", 80.0)
    budget = f("STRAIN_WRAP_BUDGET", 6.0)
    warn = f("STRAIN_CAP_WARN", 70.0)
    high = f("STRAIN_CAP_HIGH", 60.0)
    mid = f("STRAIN_CAP_MID", 50.0)
    danger = throttle - budget
    invalid = not (danger >= warn >= high >= mid)
    if invalid:
        throttle, budget, warn, high, mid = 80.0, 6.0, 70.0, 60.0, 50.0
        danger = throttle - budget
    return mid, high, warn, danger, throttle, invalid


def propose_tier(st, ctx):
    """The v3 TWO-LINE tier model: capacity and conduct, scored separately, max-joined.

    Line A = fill vs the cap ladder (_caps; Danger derived from the throttle onset
    minus the wrap budget). Scores "measured" AND "estimated" fills (an estimate is an
    observation, labelled in the basis); ABSTAINS LOUDLY on anything else and on
    impossible percentages -- a missing measurement is never "Healthy (fill 0%%)".
    Line B = the escaped-signal ladder (signal_floor -- ONE home for the policy).
    Compaction floor rides as a third max() term.

    Synthesis is max() and NOTHING ELSE -- no cross-weighting. Errors inside the
    throttle zone are ANNOTATED as likely capacity-induced, never auto-escalated:
    the two lines answer different questions (is the window full? / is work escaping
    wrong?) and multiplying them manufactures verdicts neither line stated. The v2
    composite ("escaped signal past the Warning band => Danger") is deleted for that
    reason. Tick count never escalates anything -- v1's tick-ratchet pinned Danger at
    a measured 33%% fill, three fixtures running, and stays deleted.
    Returns (tier, basis, directives)."""
    ctx = ctx or {}
    mid, high, warn, danger, throttle, invalid = _caps()
    logs, directives = [], []
    if invalid:
        logs.append("CONFIG INVALID: cap ladder inverted -- env overrides IGNORED,"
                    " built-in defaults in force")
    mode = str(ctx.get("mode") or "")
    pct = ctx.get("pct")
    line_a = "Healthy"
    a_scored = False
    if mode not in ("measured", "estimated") or pct is None:
        logs.append("Line A abstains: no trustworthy fill measurement (mode %s)"
                    % (mode or "none"))
    elif not (0.0 <= float(pct) <= 100.0):
        logs.append("Line A abstains: fill %s%% impossible (denominator/measurement"
                    " broken)" % pct)
    else:
        p = float(pct)
        a_scored = True
        if p >= danger:
            line_a = "Danger"
            directives.append("MANDATORY DIRECTIVE: wrap now (fill %.1f%% >= derived"
                              " danger cap %.1f%% = throttle %.0f%% - wrap budget)."
                              % (p, danger, throttle))
        elif p >= warn:
            line_a = "Warning"
            directives.append("Prepare to wrap. Context entering host compression"
                              " risk zone.")
        elif p >= high:
            line_a = "High"
        elif p >= mid:
            line_a = "Mid"
        logs.append("Line A %s (fill %s%%%s)"
                    % (line_a, pct, ", estimated" if mode == "estimated" else ""))
    line_b = signal_floor(st) or "Healthy"
    escaped = sum(1 for s in signals_of(st) if s.get("escaped"))
    logs.append("Line B %s (escaped %d)" % (line_b, escaped))
    comp = int(st.get("compactions", 0))
    line_c = "Warning" if comp >= 2 else ("High" if comp == 1 else "Healthy")
    if comp:
        logs.append("compaction floor %s (count %d)" % (line_c, comp))
        directives.append("RECOVERY DIRECTIVE: context was cut unfiltered (%d time%s)"
                          " -- re-read the goal anchor and the handoff."
                          % (comp, "s" if comp > 1 else ""))
    val_a = TIERS.index(line_a) if a_scored else 0
    val_b = TIERS.index(line_b)
    val_c = TIERS.index(line_c)
    final = max(val_a, val_b, val_c)
    tier = TIERS[final]
    if val_b > val_a and val_b == final:
        logs.append("tier clamped by Line B (escaped conduct)")
    elif val_c > val_a and val_c > val_b and val_c == final:
        logs.append("tier floored by host compactions")
    if a_scored and float(pct) >= throttle and escaped > 0:
        logs.append("observation: throttle zone (>=%g%%) -- errors likely"
                    " capacity-induced" % throttle)
    return tier, " | ".join(logs), directives


def caps_calibration_line(ctx, substrate=""):
    """Shadows the engine's calibration_line: prints the Line-A cap ladder ACTUALLY IN
    FORCE (_caps), not the legacy bands -- the display must match the ladder the
    proposal used, or a mis-calibration hides behind an honest-looking line."""
    mid, high, warning, danger, _throttle, invalid = _caps()
    lim = (ctx or {}).get("limit") or ctxmod.limit()
    mode = (ctx or {}).get("mode") or "pending"
    def k(n):
        return ("%gM" % (n / 1000000.0)) if n >= 1000000 else ("%.0fk" % (n / 1000.0))
    line = ("strain calibrated: %s · window %s · fill caps %g/%g/%g/%g%% -> "
            "Mid/High/Warning/Danger (danger derived) · signal mode %s"
            % (substrate or "unknown", k(lim), mid, high, warning, danger, mode))
    if invalid:
        line += " · CONFIG INVALID: built-in defaults in force"
    return line


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
    proposed, basis, directives = propose_tier(st, ctx)
    # The recovery directive prints ONCE PER EVENT (keyed on the compaction count),
    # not on every tick -- caller-side dedup, mutating st; the caller saves st after
    # building the directive so the dedup key persists.
    comp = int(st.get("compactions", 0))
    if comp <= int(st.get("recovery_announced", 0) or 0):
        directives = [d for d in directives if not d.startswith("RECOVERY DIRECTIVE")]
    else:
        st["recovery_announced"] = comp
    if directives:
        bits.append(" " + " ".join(directives))
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
           caps_calibration_line(ctx, substrate or st.get("substrate", "")))
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
    # Build the directive BEFORE saving -- build_directive dedups the recovery
    # directive by mutating st (recovery_announced), and that mutation must persist.
    fire = N > 0 and st["tick"] % N == 0
    directive = build_directive(N, st, ctx, st.get("substrate", "")) if fire else None
    save(path, st)
    touch_index(sdir, sid, cwd)

    if fire:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": directive,
        }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # a strain counter must never fail a tool call
