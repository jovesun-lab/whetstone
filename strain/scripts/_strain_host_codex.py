#!/usr/bin/env python3
"""Host adapter: Codex -- where its conversation log lives and how it is shaped.

WHY THIS FILE EXISTS
    Codex reports its own context usage on every request, and strain could read none of
    it: the engine's reader knows one host's transcript shape, so a Codex session fell
    to a byte estimate of a log that is mostly not context (140% of a wrong window read
    "Healthy" before 0.7.0). This adapter reads the number Codex itself wrote down.

THE SHAPE (read from live Codex logs, 2026-09-30)
    ~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<session id>.jsonl
    line 1      {"type": "session_meta", "payload": {"id": <session id>, ...}}
    per turn    {"type": "turn_context", "payload": {"model": ...}}
    per request {"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "last_token_usage": {"input_tokens": N, "cached_input_tokens": C, ...},
                    "total_token_usage": {...},          <- cumulative, NOT context
                    "model_context_window": W}}}
    compaction  {"type": "compacted", ...}  (followed by a token_count of 0)

THE READING
    tokens  = last_token_usage.input_tokens of the newest receipt (the cache is already
              inside it -- OpenAI usage dialect, see _strain_context.context_tokens)
    window  = model_context_window, reported by the host -- it beats any calibration
              record, because a measurement beats a hand-entered number
    A compaction or a model switch after the newest receipt voids it: the context it
    measured is gone, so the answer is UNMEASURED (stale) until the next request writes
    a new receipt. A zero receipt (written right after a compaction) is not a reading.

    No clock: a receipt is not stale because it is old, only because something changed
    after it. Codex writes the receipt after the tool output, so a hook normally reads
    the previous request -- one request behind is normal, as with the Claude reader.

IDENTITY
    The file is found by the hook's own session id and must say so on its first line
    (session_meta.id == the session id). A log that names another session is never read
    as this one -- "the most recently modified log" is a guess, not an identity.
"""
import glob, json, os

SUBSTRATE = "codex"
PRODUCT = "Codex"
TAIL_BYTES = 1 << 20          # receipts are written every request; 1 MiB holds many
HEAD_PEEK = 512               # session_meta names itself in the first few bytes


def codex_home():
    return os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")


def _meta(path):
    """The session_meta payload of a Codex log, or None if the file is not one."""
    try:
        with open(path, "rb") as f:
            head = f.read(HEAD_PEEK)
            if b'"session_meta"' not in head:
                return None
            f.seek(0)
            row = json.loads(f.readline().decode("utf-8", "replace"))
        if row.get("type") != "session_meta":
            return None
        p = row.get("payload")
        return p if isinstance(p, dict) else None
    except Exception:
        return None


def locate(payload, sid):
    """(path, meta) of this session's Codex log, or ("", None)."""
    tp = str((payload or {}).get("transcript_path") or "")
    if tp:
        if os.path.isfile(tp):
            m = _meta(tp)
            if m is not None:
                return tp, m
        return "", None              # the host named a file, and it is not a Codex log
    if not sid:
        return "", None
    pat = os.path.join(codex_home(), "sessions", "*", "*", "*",
                       "rollout-*-%s.jsonl" % glob.escape(str(sid)))
    for hit in sorted(glob.glob(pat)):
        m = _meta(hit)
        if m is not None:
            return hit, m
    return "", None


def detect(payload, cwd=""):
    path, _m = locate(payload, str((payload or {}).get("session_id") or ""))
    return bool(path)


def _tail_rows(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > TAIL_BYTES:
            f.seek(-TAIL_BYTES, 2)
            lines = f.read().split(b"\n")[1:]          # drop the partial first line
        else:
            lines = f.read().split(b"\n")
    for raw in lines:
        if not (b"token_count" in raw or b"turn_context" in raw or b"compact" in raw):
            continue
        try:
            row = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            continue                                   # a torn last line is not a row
        if isinstance(row, dict):
            yield row


def measure(payload, sid):
    """A reading from this session's Codex log, or None when there is no such log."""
    path, meta = locate(payload, sid)
    if not path:
        return None
    base = {"transcript": path, "source": "codex-rollout", "model": "", "tokens": None,
            "pct": None, "limit": None, "limitSource": "host-reported · %s" % PRODUCT}
    if str(meta.get("id") or "") != str(sid or ""):
        return dict(base, mode="unmeasured", kind="unusable",
                    why="the Codex log the host named belongs to another session")
    import _strain_context as ctxmod
    model, receipt, void = "", None, ""
    try:
        for row in _tail_rows(path):
            t = row.get("type")
            p = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if t == "turn_context":
                m = str(p.get("model") or "")
                if m and model and m != model and receipt is not None:
                    receipt = None
                    void = "the model switched (%s -> %s) after the last reading" % (model, m)
                if m:
                    model = m
            elif t == "compacted" or (t == "event_msg" and p.get("type") == "context_compacted"):
                if receipt is not None:
                    void = "the context was compacted after the last reading"
                receipt = None
            elif t == "event_msg" and p.get("type") == "token_count":
                info = p.get("info") if isinstance(p.get("info"), dict) else {}
                used = ctxmod.context_tokens(info.get("last_token_usage"), model)
                if used:                                # a zero receipt is not a reading
                    receipt = (used, info.get("model_context_window"), row.get("timestamp"))
                    void = ""
    except Exception:
        return dict(base, mode="unmeasured", kind="unusable",
                    why="the Codex log could not be read")
    base["model"] = model
    if receipt is None:
        if void:
            return dict(base, mode="unmeasured", voided=True, kind="stale",
                        why=void + " -- the host re-measures at its next request")
        return dict(base, mode="unmeasured", kind="unusable",
                    why="the Codex log carries no usage receipt yet")
    used, window, ts = receipt
    try:
        window = int(window or 0)
    except Exception:
        window = 0
    if window <= 0:
        return dict(base, mode="unmeasured", kind="unusable", tokens=used,
                    why="the Codex log reports no context window (window 0)")
    return dict(base, mode="measured", tokens=int(used), limit=window,
                pct=round(100.0 * int(used) / window, 1), observedAt=str(ts or ""))
