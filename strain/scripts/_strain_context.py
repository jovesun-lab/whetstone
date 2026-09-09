#!/usr/bin/env python3
"""Context measurement -- the half of strain the host can answer for us.

TWO MODES, NAMED HONESTLY
-------------------------
How full the context window is, is the least arguable strain signal there is: it is a
number the vendor already computes. But only some hosts expose it, so strain runs in one
of two modes and always says which one it is in:

    measured  the host hands us a per-session transcript that carries token usage, so
              the readout quotes real numbers (context used, and what the boot alone
              cost before any work happened)
    inferred  no usage available, so strain falls back to counting behaviour -- tool
              calls, compactions, and whatever the task list shows

`inferred` is not a failure. It is the original design and it works. What would be a
failure is printing a confident number that was never measured, so the mode travels with
every readout.

WHERE THE NUMBER COMES FROM
    Claude Code writes one JSONL transcript per session and passes its path in every hook
    payload as `transcript_path`. Assistant messages carry a `usage` object. The context
    currently occupied is the input side of the most recent one:

        input_tokens + cache_read_input_tokens + cache_creation_input_tokens

    (Cache-read tokens are still context: they are prompt the model saw. Leaving them out
    reports a near-empty window on any cached session, which is every long one.)

    The BASELINE is the same sum on the FIRST assistant message: what the session cost
    before a single instruction was carried out -- system prompt, tool schemas, project
    instructions, skills. That is the floor the session can never get back under.

TIMING MATTERS
    Read this at tool-call time, not at session start. At SessionStart the transcript
    usually does not exist on disk yet, so an earlier version of this probe recorded
    `exists: false` every single time and the capability looked impossible.
"""
import glob, json, os

DEFAULT_LIMIT = 200000          # context window, tokens; override with STRAIN_CONTEXT_LIMIT
TAIL_BYTES = 262144             # how much of the transcript tail to scan for the last usage
HEAD_LINES = 400                # how far into the head to look for the first usage

# Model-name -> window-size hints, checked as substrings of the model id. The host does
# not publish the window anywhere (verified: no context-limit field in the transcript),
# so the denominator is INFERRED from the model observed on the transcript tail. This
# table will age -- that is what STRAIN_CONTEXT_LIMIT is for -- but a stale entry beats
# the previous behaviour, which divided a 1M-window session by 200k and reported 69%
# for a window that was actually 14% full.
MODEL_LIMITS = (
    ("[1m]", 1000000),          # explicit long-context variants, e.g. sonnet-4-5[1m]
    ("fable", 1000000),
)


def limit(model=""):
    """The context window for this session: env override > model hint > default."""
    env = os.environ.get("STRAIN_CONTEXT_LIMIT")
    if env:
        try:
            return max(1, int(env))
        except Exception:
            pass
    m = (model or "").lower()
    for frag, n in MODEL_LIMITS:
        if frag in m:
            return n
    return DEFAULT_LIMIT


def _usage_of(line):
    """(total_input_tokens, model) of one transcript line, or (None, "") if it carries
    no usage. The model rides on the same assistant message as the usage object, so the
    line that answers "how full is the window" also answers "which model is running" --
    including a mid-session /model switch, which the SessionStart payload can never see."""
    try:
        j = json.loads(line)
    except Exception:
        return None, ""
    msg = j.get("message")
    if not isinstance(msg, dict):
        return None, ""
    u = msg.get("usage")
    if not isinstance(u, dict):
        return None, ""
    total = 0
    for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        try:
            total += int(u.get(k) or 0)
        except Exception:
            pass
    if total <= 0:
        return None, ""
    return total, str(msg.get("model") or "")


def locate(payload, sid):
    """The transcript for THIS session, or "" if the host does not publish one.

    Prefers the path the host handed us. Falls back to the documented Claude Code layout
    (~/.claude/projects/<project>/<session-id>.jsonl) for the case where the payload
    omits it -- keyed by session id, so it can never pick up another session's file.
    """
    tp = str((payload or {}).get("transcript_path") or "")
    if tp and os.path.isfile(tp) and os.path.getsize(tp) > 0:
        return tp
    if not sid:
        return ""
    for hit in glob.glob(os.path.expanduser("~/.claude/projects/*/%s.jsonl" % sid)):
        if os.path.isfile(hit) and os.path.getsize(hit) > 0:
            return hit
    return ""


def read_usage(path, want_baseline=True):
    """(current_tokens, baseline_tokens, model) from a transcript; numbers possibly None.

    The tail scan is bounded and cheap enough to run on every tool call. The head scan is
    not, on a long transcript -- so callers that already know the baseline pass
    want_baseline=False and keep the cached one. The baseline is fixed for the life of a
    session anyway: it is what the boot cost. The model is whatever the most recent
    assistant turn ran on -- deliberately the tail, not the head, so a /model switch
    mid-session shows up.
    """
    current = baseline = None
    model = ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(-TAIL_BYTES, 2)
                chunk = f.read().decode("utf-8", "replace")
                lines = chunk.split("\n")[1:]      # drop the partial first line
            else:
                lines = f.read().decode("utf-8", "replace").split("\n")
        for line in reversed(lines):
            if not line.strip():
                continue
            got, m = _usage_of(line)
            if got is not None:
                current = got
                model = m
                break
    except Exception:
        return None, None, ""
    if not want_baseline:
        return current, None, model
    try:
        with open(path, "r", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= HEAD_LINES:
                    break
                got, _m = _usage_of(line)
                if got is not None:
                    baseline = got
                    break
    except Exception:
        pass
    return current, baseline, model


def measure(payload, sid, known_baseline=None):
    """The context reading for one session. Never raises; never guesses a number.

    Pass the baseline already stored in the session state to skip re-reading the head of
    a transcript that only ever grows at the other end.
    """
    out = {"mode": "inferred", "tokens": None, "baseline": known_baseline,
           "limit": limit(), "pct": None, "transcript": "", "model": ""}
    try:
        path = locate(payload, sid)
        if not path:
            return out
        current, base, model = read_usage(path, want_baseline=(known_baseline is None))
        if current is None:
            # No usage keys anywhere in the transcript -- a host that logs turns but not
            # tokens. The transcript's SIZE is still a real signal, so estimate: ~4 bytes
            # per token is coarse, and the mode says so ("estimated", never "measured").
            # Estimating beats the v1 behaviour, which fell back to counting tool calls
            # and read a one-third-full window as Danger.
            try:
                size = os.path.getsize(path)
            except Exception:
                return out
            if size <= 0:
                return out
            out["mode"] = "estimated"
            out["tokens"] = size // 4
            out["transcript"] = path
            out["limit"] = limit()
            out["pct"] = round(100.0 * out["tokens"] / out["limit"], 1)
            return out
        out["mode"] = "measured"
        out["tokens"] = current
        out["baseline"] = known_baseline if known_baseline is not None else base
        out["transcript"] = path
        out["model"] = model
        out["limit"] = limit(model)      # the denominator follows the observed model
        out["pct"] = round(100.0 * current / out["limit"], 1)
    except Exception:
        pass
    return out


def bands():
    """The fill bands, lowest first: crossing each one enters Mid/High/Warning/Danger.

    Defaults are the 2026-09-04 ruling (40/60/75/85). Env-overridable per band because
    thresholds are the one number every user should expect to retune -- and whatever they
    are, they are PRINTED at boot and on every tick, so a mis-calibration is visible
    instead of silently wrong.
    """
    def thr(name, default):
        try:
            return float(os.environ.get(name, default))
        except Exception:
            return default
    return (thr("STRAIN_FILL_MID", 40.0), thr("STRAIN_FILL_HIGH", 60.0),
            thr("STRAIN_FILL_WARNING", 75.0), thr("STRAIN_FILL_DANGER", 85.0))


def fill_tier(ctx):
    """The tier the fill percentage justifies on its own -- the PRIMARY signal.

    <mid Healthy · mid-high Mid · high-warning High · warning-danger Warning ·
    >=danger Danger (a window that full is a real constraint by itself; the acceptance
    rule is "no Danger without fill past the top band or fresh hard signals").
    Returns None when nothing was measured or estimated -- never a guessed tier.
    """
    if not ctx or ctx.get("mode") not in ("measured", "estimated") or ctx.get("pct") is None:
        return None
    mid, high, warning, danger = bands()
    pct = ctx["pct"]
    if pct >= danger:
        return "Danger"
    if pct >= warning:
        return "Warning"
    if pct >= high:
        return "High"
    if pct >= mid:
        return "Mid"
    return "Healthy"


def context_floor(ctx):
    """Back-compat name: the floor the fill justifies (None when Healthy/unmeasured)."""
    t = fill_tier(ctx)
    return None if t in (None, "Healthy") else t


def detect_substrate(payload, cwd=""):
    """Which shell this session runs under -- decides nothing by itself, but travels
    with the calibration line so a wrong window is attributable. Env-overridable."""
    env = os.environ.get("STRAIN_SUBSTRATE")
    if env:
        return env
    tp = str((payload or {}).get("transcript_path") or "")
    probe = tp + " " + (cwd or "")
    if "local-agent-mode-sessions" in probe or probe.startswith("/sessions/") \
            or " /sessions/" in probe:
        return "cowork"
    if "/.claude/projects/" in tp:
        return "claude-code"
    return "unknown"


def calibration_line(ctx, substrate=""):
    """One line that proves calibration happened: substrate, window, bands, mode.

    The S255 law -- running is not observing -- applies to the calibrator itself: this
    line is derived from what was actually measured, not from a baked-in table.
    """
    mid, high, warning, danger = bands()
    lim = (ctx or {}).get("limit") or limit()
    mode = (ctx or {}).get("mode") or "pending"
    def k(n):
        return ("%gM" % (n / 1000000.0)) if n >= 1000000 else ("%.0fk" % (n / 1000.0))
    return ("strain calibrated: %s · window %s · fill bands %g/%g/%g/%g%% -> "
            "Mid/High/Warning/Danger · signal mode %s"
            % (substrate or "unknown", k(lim), mid, high, warning, danger, mode))


def describe(ctx):
    """One human line for the readout, or "" when there is nothing measured to say."""
    if not ctx or ctx.get("mode") not in ("measured", "estimated"):
        return ""
    def k(n):
        if n is None:
            return "?"
        if n >= 1000000:
            return ("%g" % (n / 1000000.0)) + "M"
        return "%.0fk" % (n / 1000.0)
    bit = "context %s/%s (%.0f%%)" % (k(ctx.get("tokens")), k(ctx.get("limit")), ctx.get("pct") or 0)
    if ctx.get("mode") == "estimated":
        bit += ", ESTIMATED from transcript bytes (no token usage on this host)"
    elif ctx.get("baseline"):
        bit += ", of which %s was the boot itself" % k(ctx["baseline"])
    return bit
