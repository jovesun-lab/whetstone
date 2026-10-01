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
import argparse, json, os, shlex, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (TIERS, state_dir, session_path, load, save, blank, now_iso,
                            touch_index, read_payload, log_model, floor_tier,
                            signals_of, signal_floor, pattern_note, state_lock,
                            settle_window, k_tokens, why_unsaved, unsaved_marker,
                            user_messages_on, receipt)
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

    Synthesis: each line scores SEPARATELY, then ONE alarm comes out of max() plus a
    single COMBINATION term -- the composite: fill already inside the Warning/Danger
    caps AND escaped >= 3 -> Danger, printed loudly whenever it fires. The two lines
    answer different questions (is the window full? / is work escaping wrong?); the
    composite does not weight or multiply them -- it names the one compound state
    ("running on a full window AND repeatedly shipping errors") that is more dangerous
    than either line says alone, and it needs BOTH preconditions. Errors inside the
    throttle zone are still ANNOTATED as likely capacity-induced, never
    auto-escalated. The cruder v2 composite ("escaped signal past the Warning band =>
    Danger" -- no capacity precondition) stays deleted; this is the owner's original
    two-condition design (from an internal pre-release iteration, never a formal
    release of this plugin), restored 2026-09-13 after review found the deletion had
    shipped unratified. Tick count never escalates anything -- v1's tick-ratchet
    pinned Danger at a measured 33%% fill, three fixtures running, and stays deleted.
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
    if mode not in ("measured", "estimated", "agent-fed") or pct is None:
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
                    % (line_a, pct, {"estimated": ", estimated",
                                     "agent-fed": ", agent-fed"}.get(mode, "")))
    line_b = signal_floor(st) or "Healthy"
    escaped = sum(1 for s in signals_of(st) if s.get("escaped"))
    logs.append("Line B %s (escaped %d)" % (line_b, escaped))
    # 0.7.0: a compaction is STATED, never a tier floor. It says the context was cut, not
    # that the session is loaded -- the fill after it is what measures the load.
    comp = int(st.get("compactions", 0))
    if comp:
        logs.append("compaction #%d this session (stated, never a floor)" % comp)
        directives.append("RECOVERY DIRECTIVE: context was cut unfiltered (%d time%s)"
                          " -- re-read the goal anchor and the handoff."
                          % (comp, "s" if comp > 1 else ""))
    # The combination alarm: both preconditions, loud print, no weighting.
    line_d = "Healthy"
    if a_scored and line_a in ("Warning", "Danger") and escaped >= 3:
        line_d = "Danger"
        logs.append("composite: fill already %s AND escaped %d >= 3 -> Danger"
                    % (line_a, escaped))
    val_a = TIERS.index(line_a) if a_scored else 0
    val_b = TIERS.index(line_b)
    val_d = TIERS.index(line_d)
    final = max(val_a, val_b, val_d)
    tier = TIERS[final]
    if val_b > val_a and val_b == final:
        logs.append("tier clamped by Line B (escaped conduct)")
    # 0.7.0: nothing measured AND nothing else to say is UNMEASURED -- never "Healthy".
    # (A Codex session read 140% of a wrong window and the proposal said Healthy.)
    if not a_scored and final == 0:
        tier = "UNMEASURED"
    if a_scored and float(pct) >= throttle and escaped > 0:
        logs.append("observation: throttle zone (>=%g%%) -- errors likely"
                    " capacity-induced" % throttle)
    return tier, " | ".join(logs), directives


def caps_calibration_line(ctx, substrate=""):
    """Shadows the engine's calibration_line: prints the Line-A cap ladder ACTUALLY IN
    FORCE (_caps), not the legacy bands -- the display must match the ladder the
    proposal used, or a mis-calibration hides behind an honest-looking line."""
    mid, high, warning, danger, _throttle, invalid = _caps()
    ctx = ctx or {}
    lim, src = ctx.get("limit"), ctx.get("limitSource")
    if not lim or not src:
        lim, src = ctxmod.limit_and_source(ctx.get("model") or "")
    mode = ctx.get("mode") or "pending"
    # 0.8.0 B1: the window names where it came from -- host-reported, calibrated (and
    # which record), model hint, default, or an env override. A record ruling the wrong
    # host would have been visible on its first wrong tick with this one parenthesis.
    line = ("strain calibration: %s · window %s (%s) · fill caps %g/%g/%g/%g%% -> "
            "Mid/High/Warning/Danger (danger derived) · signal mode %s"
            % (substrate or "unknown", k_tokens(lim), src, mid, high, warning, danger, mode))
    if invalid:
        line += " · CONFIG INVALID: built-in defaults in force"
    return line


def describe_ctx(ctx):
    """The MEASURED line; 0.7.0 adds the agent-fed reading (source, and what was added
    since the feed from transcript growth)."""
    ctx = ctx or {}
    if ctx.get("mode") == "agent-fed" and ctx.get("tokens") is not None:
        k = lambda n: ("%gM" % (n / 1000000.0)) if n >= 1000000 else ("%.0fk" % (n / 1000.0))
        line = ("context %s/%s (%.0f%%), AGENT-FED: %s tokens read from %s"
                % (k(ctx["tokens"]), k(ctx.get("limit") or ctxmod.limit()),
                   ctx.get("pct") or 0, "{:,}".format(int(ctx.get("fedTokens") or 0)),
                   ctx.get("source") or "an unnamed source"))
        if ctx.get("deltaTokens"):
            line += (" + %s estimated since (transcript bytes appended after the feed, /4)"
                     % "{:,}".format(int(ctx["deltaTokens"])))
        return line + " -- feed a fresh reading whenever the host shows one"
    return ctxmod.describe(ctx)


def carry_feed(fed, fresh, st):
    """0.7.0 -- the reading when the last one was FED and this call's own is not a real
    measurement. A fed reading stands until a measured one or a newer feed replaces it
    (0.6.0 overwrote it on the very next call). It is the ANCHOR: only transcript bytes
    appended AFTER it are added (/4), never the whole file (a whole-file estimate read a
    124K/258K session as 150%). A compaction or a model switch after the feed VOIDS it:
    the context it measured is gone, so the answer is UNMEASURED, not a stale number."""
    void = ""
    if int(st.get("compactions", 0) or 0) > int(fed.get("fedCompactions", 0) or 0):
        void = "a compaction since the feed voided it"
    elif fed.get("fedModel") and fresh.get("model") and fresh.get("model") != fed.get("fedModel"):
        void = "a model switch since the feed voided it (%s -> %s)" % (fed.get("fedModel"),
                                                                    fresh.get("model"))
    if void:
        return {"mode": "unmeasured", "voided": True, "fedVoid": True, "kind": "stale",
                "tokens": None, "pct": None, "source": "agent-fed",
                "why": void + " -- feed a new reading", "limit": fresh.get("limit"),
                "model": fresh.get("model") or "", "transcript": fresh.get("transcript") or ""}
    out = dict(fed)
    tp = fresh.get("transcript") or fed.get("transcript") or ""
    try:
        size = os.path.getsize(tp) if tp else None
    except Exception:
        size = None
    if out.get("anchorBytes") is None and size is not None:
        out["anchorBytes"] = size
    delta = 0
    if size is not None and out.get("anchorBytes") is not None:
        delta = max(0, size - int(out["anchorBytes"])) // 4
    out["tokens"] = int(out.get("fedTokens") or 0) + delta
    out["deltaTokens"] = delta
    out["transcript"] = tp
    lim = out.get("limit") or fresh.get("limit")
    out["pct"] = round(100.0 * out["tokens"] / float(lim), 1) if lim else None
    return out


TIER_SLOT = "<Healthy|Mid|High|Warning|Danger|UNMEASURED>"


def reading_state(ctx):
    """(kind, why) of a reading that is NOT a usable number, or ("", "") when it is.
    0.8.0 B3: three kinds, each with its own next step --
      no source  no log strain can read on this host (and no adapter for it)
      unusable   a source was read and gave no usable number (no usage lines, a fill
                 at or past 100%, a window of 0, a log that names another session)
      stale      a reading voided by a compaction or a model switch"""
    ctx = ctx or {}
    mode, pct = ctx.get("mode"), ctx.get("pct")
    if mode in ("measured", "estimated", "agent-fed") and pct is not None:
        try:
            p = float(pct)
        except Exception:
            p = -1.0
        if 0.0 <= p <= 100.0:
            return "", ""
        # F6b: a fill past 100% is a broken denominator or a broken count, never a
        # reading; the used count is still a true LOWER bound.
        return "unusable", (
            "fill %s%% is impossible -- at least %s tokens are in use (a lower bound); "
            "check: the model · the effective window · double counting · the compaction "
            "boundary" % (pct, "{:,}".format(int(ctx.get("tokens") or 0))))
    kind = str(ctx.get("kind") or "") or ("stale" if ctx.get("voided") else "no source")
    return kind, str(ctx.get("why") or "")


def procedure(kind, why, st, ctx, sdir):
    """The next step for an UNMEASURED reading, per kind -- a procedure that ends in a
    record, not a hint. Host-neutral: no host-only terms."""
    feed = act_command("strain-level.sh", st, sdir,
                       "<tier> --ctx-used <tokens> --ctx-source '<where you read it>'"
                       " --ctx-provenance host-reported|agent-estimated")
    report = act_command("strain-report.sh", st, sdir, "--note '<what you saw, no paths>'")
    if kind == "no source":
        ns = st.get("noSource") if isinstance(st.get("noSource"), dict) else {}
        if ns.get("checked"):
            return (" No context measurement on this host (no source; checked: %s). Counting"
                    " behaviour only -- feed a number if the host starts showing one: `%s`."
                    % (ns["checked"], feed))
        return (" No context measurement on this host -- UNMEASURED · no source (%s). UNMEASURED"
                " is not Healthy. Look for the number your host keeps: a session or usage log,"
                " a status or usage command, a usage API, the host's settings or status pane."
                " Then end with ONE record: a feed `%s`, or `%s`. This line repeats until one"
                " exists." % (why or "no log strain can read",
                              feed, act_command("strain-level.sh", st, sdir,
                                                "UNMEASURED --no-source --checked"
                                                " '<the places you looked>'")))
    if kind == "unusable":
        if why.startswith("fill "):
            return (" NOT MEASURED -- UNMEASURED · unusable: %s. A fill past 100%% means"
                    " strain's arithmetic is off, not your session: tell the user, and offer"
                    " a bug report they send by hand (nothing is sent automatically): `%s`."
                    " Meanwhile feed the host's own number if it shows one: `%s`."
                    % (why, report, feed))
        return (" NOT MEASURED -- UNMEASURED · unusable: %s. Read the number from your host's"
                " own interfaces (a status or usage command, its usage pane, its log) and"
                " feed it with its provenance: `%s`. If the number lives in a durable log,"
                " draft an adapter proposal -- where the log is, which fields carry the"
                " usage, one redacted sample line -- with `%s`; never edit the installed"
                " plugin." % (why, feed, report))
    if kind == "stale":
        if ctx.get("fedVoid") or ctx.get("source") == "agent-fed":
            return (" NOT MEASURED -- UNMEASURED · stale: %s: `%s`." % (why, feed))
        if ctx.get("source") in ("codex-rollout", "claude-transcript"):
            return (" NOT MEASURED -- UNMEASURED · stale: %s. Nothing to do: this host"
                    " measures itself, and the next request brings a fresh reading." % why)
        return " NOT MEASURED -- UNMEASURED · stale: %s." % why
    return ""


def act_command(script, st, sdir, args):
    """0.7.0: a command the AGENT can run from its own shell. $CLAUDE_PLUGIN_ROOT exists
    only inside the hook process, so the old printed form always failed there. This one
    names the running copy's absolute path, this session and this state dir."""
    sid = str(st.get("sid") or "")
    pre = ("STRAIN_SESSION=%s " % shlex.quote(sid)) if sid else ""
    return "%sSTRAIN_STATE_DIR=%s bash %s %s" % (
        pre, shlex.quote(sdir), shlex.quote(os.path.join(os.path.dirname(
            os.path.abspath(__file__)), script)), args)


def wrap_line(st):
    """0.7.0: whether this session has wrapped (strain-wrap.sh), and what ran since."""
    tick = int(st.get("tick", 0) or 0)
    wrapped = str(st.get("wrappedAt", "") or "")
    if not wrapped:
        return " This session: %d tool call%s, not wrapped yet." % (tick, "" if tick == 1 else "s")
    since = tick - int(st.get("wrapTick", 0) or 0)
    line = " This session: %d tool call%s, wrapped at %s" % (tick, "" if tick == 1 else "s",
                                                           wrapped[11:16])
    if since > 0:
        line += (", %d call%s since the wrap -- re-run strain-wrap.sh if you hand off again"
                 % (since, "" if since == 1 else "s"))
    return line + "."


def build_directive(n, st, ctx, substrate="", sdir=""):
    bits = []
    ctx_line = describe_ctx(ctx)
    kind, why = reading_state(ctx)
    if ctx_line:
        bits.append(" MEASURED: %s." % ctx_line)
    if int(st.get("compactions", 0)) > 0:
        bits.append(" Context has been COMPACTED: compaction #%d this session -- stated,"
                    " never a tier floor." % int(st["compactions"]))
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
    if kind:
        bits.append(procedure(kind, why, st, ctx, sdir))
    if st.pop("_legacyNote", None):
        bits.append(" NOTE: an old calibration record (calibration.json) has no model, so it"
                    " rules no session -- re-record the window per product and model:"
                    " strain-calibrate.sh --product <product> --model <model> --window <tokens>"
                    " --basis nominal|runtime --source <where>.")
    slot = proposed
    if proposed == "UNMEASURED" and kind:
        slot = "UNMEASURED · %s" % kind
    carried = st.get("last", "Healthy")
    decay = ""
    try:
        if TIERS.index(proposed) < TIERS.index(carried):
            decay = (" The proposal is LOWER than the carried tier -- that is allowed:"
                     " strain decays when the load does; record the lower tier unless"
                     " something the counters cannot see says otherwise.")
    except ValueError:
        pass
    # Drift glance (0.4.1): conditional, generic, NON-FLOORING. A one-sentence ask to
    # glance whatever task track the agent keeps; goal drift is self-reported evidence
    # and is never a tier input. STRAIN_DRIFT_GLANCE=off drops the sentence.
    glance = ""
    if os.environ.get("STRAIN_DRIFT_GLANCE", "on").strip().lower() not in (
            "off", "0", "no"):
        glance = (
            " ALSO glance your task track if you keep one (a list with one marked"
            " MAIN goal, e.g. throughline's convention): a side task ballooning past"
            " the MAIN is GOAL DRIFT -- surface it as a note in your reply; it never"
            " moves the tier (self-reported evidence does not floor)."
            " STRAIN_DRIFT_GLANCE=off drops this line.")
    st["_proposed"] = proposed
    st["_kind"], st["_why"] = kind, why
    return (
        "\U0001FA7A STRAIN TICK (host-fired every %d tool call%s)."
        " PROPOSED TIER: %s (%s); carried: %s.%s%s%s"
        " Confirm or adjust, then record it:"
        " `%s`."
        " Adjust UP only for a NEW hard signal the state file has not seen -- record it"
        " first (`%s`): an error that ESCAPED to"
        " the user floors the tier; one you caught and fixed pre-delivery is a working"
        " immune system and moves nothing (say so, don't tier on it). Never escalate"
        " because ticks accumulated or because the previous check was high -- fill and"
        " fresh signals are the only ladders. An unrecorded tier is how this reading"
        " silently stays at its first value.%s [%s]"
        % (n, "" if n == 1 else "s", slot, basis, carried, decay, "".join(bits),
           wrap_line(st),
           act_command("strain-level.sh", st, sdir, TIER_SLOT),
           act_command("strain-signal.sh", st, sdir, "<kind> --caught|--escaped"), glance,
           caps_calibration_line(ctx, substrate or st.get("substrate", "")))
    )


def user_message(st, ctx, path, fire):
    """0.8.0 B4: the line the HOST shows the user (Claude Code `systemMessage`), or "".
    The receipt once per session; a reading that has just become UNMEASURED."""
    if not fire or not user_messages_on(st.get("substrate")):
        return ""
    out = []
    if not st.get("receiptShown"):
        out.append(receipt(st, "", path, "ledger joined" if st.get("ledger") else "no ledger"))
        st["receiptShown"] = now_iso()
    proposed = st.get("_proposed")
    if proposed == "UNMEASURED" and st.get("lastProposal") != "UNMEASURED":
        out.append("Strain: this session's context is not measured right now (%s%s)."
                   % (st.get("_kind") or "no reading",
                      (": " + st["_why"]) if st.get("_why") else ""))
    if proposed:
        st["lastProposal"] = proposed
    return " ".join(out)


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
    lock = state_lock(path)
    lock.__enter__()
    st = load(path) or blank(sid, cwd)
    st["sid"] = sid or st.get("sid", "")
    if cwd:
        st["cwd"] = cwd
    st["tick"] = int(st.get("tick", 0)) + 1
    # 0.8.0: "unknown" is re-asked -- a session that began before its host had an
    # adapter (a Codex session started on 0.7.0) is recognised once the adapter exists.
    if not st.get("substrate") or st.get("substrate") == "unknown":
        st["substrate"] = ctxmod.detect_substrate(payload, cwd)

    # Context is re-read every tick (a bounded tail scan); the baseline is read once and
    # then carried, because what the boot cost cannot change later in the session.
    prev_ctx = st.get("ctx") if isinstance(st.get("ctx"), dict) else {}
    ctx = ctxmod.measure(payload, sid, known_baseline=prev_ctx.get("baseline"), prev=prev_ctx)
    # 0.7.0: measured > agent-fed (+ delta since its anchor) > byte estimate. A fed
    # reading stands until a real measurement or a newer feed replaces it; a fed reading
    # that a compaction voided stays voided until a new feed (0.8.0: only a FED void is
    # carried -- a host that measures itself re-measures on its own).
    if ctx.get("mode") != "measured":
        if prev_ctx.get("mode") == "agent-fed":
            ctx = carry_feed(prev_ctx, ctx, st)
        elif prev_ctx.get("mode") == "unmeasured" and prev_ctx.get("fedVoid"):
            ctx = dict(prev_ctx)
    # 0.8.0 A1: ONE denominator decision, after measuring (the model is known by now).
    ctx, look = settle_window(ctx, sdir, st.get("substrate", ""))
    st["ctx"] = ctx
    if look.get("legacyNoModel") and not st.get("legacyNoted"):
        st["legacyNoted"] = now_iso()
        st["_legacyNote"] = True

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
    directive = build_directive(N, st, ctx, st.get("substrate", ""), sdir) if fire else None
    if st.get("_legacyNote") and not fire:
        st.pop("legacyNoted", None)        # not said yet -- say it at the next firing tick
    st.pop("_legacyNote", None)
    shown = user_message(st, ctx, path, fire)
    for k in ("_proposed", "_kind", "_why"):
        st.pop(k, None)
    saved = save(path, st)
    lock.__exit__()

    # 0.8.0 A4: a save that fails is SAID -- once, on stderr and to the agent (and to the
    # user where the host shows hook messages); the regular directive is held back,
    # because a counter that cannot be saved is frozen and would fire on every call.
    marker = unsaved_marker(sdir, sid)
    if not saved:
        why = why_unsaved(path)
        sys.stderr.write("strain: this reading could not be saved (%s)\n" % why)
        first = not os.path.exists(marker)
        try:
            with open(marker, "w") as f:
                f.write(why)
        except Exception:
            pass
        if first:
            out = {"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "\U0001FA7A STRAIN STATE NOT SAVED -- this reading could"
                " not be saved (%s); nothing is recorded for this session until it can be."
                " Tell the user." % why}}
            if user_messages_on(st.get("substrate")):
                out["systemMessage"] = "Strain: state write FAILED -- %s." % why
            sys.stdout.write(json.dumps(out))
        return 0

    touch_index(sdir, sid, cwd)
    if fire:
        if os.path.exists(marker):
            try:
                with open(marker) as f:
                    gap = f.read().strip()
                os.remove(marker)
            except Exception:
                gap = ""
            directive += (" NOTE: earlier readings could not be saved (%s); the counts"
                          " above miss them." % (gap or "reason not recorded"))
        out = {"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": directive,
        }}
        if shown:
            out["systemMessage"] = shown
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # a strain counter must never fail a tool call
