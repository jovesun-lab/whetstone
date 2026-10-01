#!/usr/bin/env python3
"""Self-test for the strain driver. Host-independent: every hook is driven by feeding it
the JSON payload a host would send, in a throwaway state directory.

    python3 tools/selftest.py            run everything
    python3 tools/selftest.py -v         print each check

The checks that matter most are the ones for failures this tool has actually shipped
before: two sessions sharing one counter, a recorded tier landing in a file the reader
never opens, and a context probe that reads an empty transcript and concludes the whole
capability is impossible.
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
VERBOSE = "-v" in sys.argv

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    if VERBOSE or not cond:
        print("  %s %s%s" % ("ok  " if cond else "FAIL", name,
                             "" if cond else ("  <- " + str(detail))))


# 0.8.0: the host variables that name a session are stripped from every child run, so a
# check never depends on the shell the selftest happens to run in (a Claude Code or Codex
# shell carries its own session id, and 0.8.0 treats those as identity sources).
HOST_VARS = ("STRAIN_SESSION", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_ENV_FILE",
             "STRAIN_SUBSTRATE", "CLAUDE_CODE_ENTRYPOINT", "STRAIN_CONTEXT_LIMIT",
             "STRAIN_STATE_DIR", "XDG_STATE_HOME", "CODEX_HOME")
CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in HOST_VARS}
for _k in HOST_VARS:
    os.environ.pop(_k, None)     # the in-process engine calls see the same clean env


def run(script, payload=None, args=(), env=None):
    """Run a hook or CLI script; return (stdout, stderr, returncode)."""
    e = dict(CLEAN_ENV)
    e.setdefault("CODEX_HOME", os.path.join(tempfile.gettempdir(), "strain-selftest-no-codex"))
    e.update(env or {})
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args),
                       input=(json.dumps(payload) if payload is not None else ""),
                       capture_output=True, text=True, env=e)
    return p.stdout, p.stderr, p.returncode


def state_of(sdir, sid):
    path = os.path.join(sdir, "sessions", sid + ".json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def tick(sdir, sid, cwd="/tmp/proj", n=10, transcript=None, extra_env=None):
    payload = {"session_id": sid, "cwd": cwd, "hook_event_name": "PostToolUse"}
    if transcript:
        payload["transcript_path"] = transcript
    env = {"STRAIN_STATE_DIR": sdir}
    env.update(extra_env or {})
    return run("_strain_tick.py", payload, ["--n", str(n)], env)


def start(sdir, sid, source="startup", cwd="/tmp/proj", model=""):
    payload = {"session_id": sid, "cwd": cwd, "source": source,
               "model": model, "hook_event_name": "SessionStart"}
    return run("_strain_reset.py", payload, [], {"STRAIN_STATE_DIR": sdir})


def make_transcript(path, rows, model=""):
    """rows: (input, cache_read, cache_creation) or (input, cache_read, cache_creation,
    model) for successive assistant turns; `model` is the default for 3-tuples."""
    with open(path, "w") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user"}}) + "\n")
        for row in rows:
            (i, cr, cc), m = row[:3], (row[3] if len(row) > 3 else model)
            msg = {"role": "assistant",
                   "usage": {"input_tokens": i, "cache_read_input_tokens": cr,
                             "cache_creation_input_tokens": cc}}
            if m:
                msg["model"] = m
            f.write(json.dumps({"type": "assistant", "message": msg}) + "\n")


def model_log(sdir):
    try:
        with open(os.path.join(sdir, "model-log.jsonl")) as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception:
        return []


# ---- 0.8.0 fixtures --------------------------------------------------------------------
# Ids are uuid-shaped (they are on every host strain reads): the short-id and candidate
# list cut ids, and a fixture like "sess-A" cannot show a cut in the wrong place.

def U(n):
    return "0a8e%04x-0000-4000-8000-%012x" % (n, n)


def cc_transcript(tmp, sid, tokens, model="claude-opus-5-5"):
    """A transcript where Claude Code keeps one: under .../.claude/projects/<project>/."""
    path = os.path.join(tmp, "home", ".claude", "projects", "proj", sid + ".jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    make_transcript(path, [(2, 10000, 0), (2, tokens, 0)], model=model)
    return path


def rollout(tmp, sid, events, meta_id=None, name=None):
    """A Codex rollout log: first line session_meta, then the events, in the shapes
    read from live rollouts (2026-09-30): turn_context.payload.model,
    event_msg/token_count with info.last_token_usage.input_tokens (cache already
    inside) and info.model_context_window, and a `compacted` row."""
    home = os.path.join(tmp, "codex-home")
    d = os.path.join(home, "sessions", "2026", "09", "30")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name or ("rollout-2026-09-30T12-00-00-%s.jsonl" % sid))
    ts = "2026-09-30T12:00:00.000Z"
    rows = [{"timestamp": ts, "type": "session_meta",
             "payload": {"id": meta_id or sid, "session_id": meta_id or sid,
                         "cwd": "/tmp/cx", "originator": "codex"}}]
    for e in events:
        k = e[0]
        if k == "model":
            rows.append({"timestamp": ts, "type": "turn_context", "payload": {"model": e[1]}})
        elif k == "usage":                       # ("usage", input, cached, window[, ts])
            rows.append({"timestamp": e[4] if len(e) > 4 else ts, "type": "event_msg",
                         "payload": {"type": "token_count", "info": {
                             "last_token_usage": {"input_tokens": e[1],
                                                  "cached_input_tokens": e[2],
                                                  "output_tokens": 50,
                                                  "total_tokens": e[1] + 50},
                             "total_token_usage": {"input_tokens": 9999999},
                             "model_context_window": e[3]}}})
        elif k == "compacted":
            rows.append({"timestamp": ts, "type": "compacted", "payload": {"message": ""}})
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path, home


def jl(path, default=None):
    """json.load that a missing or torn file cannot crash (tests must FAIL, not abort)."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def section_080(tmp):
    import re as _re
    import threading
    LVL = os.path.join(SCRIPTS, "strain-level.sh")
    CC = {"STRAIN_SUBSTRATE": "claude-code"}

    tick_raw = globals()["tick"]

    def tick(*a, **k):
        """The hook's text as the agent reads it (JSON-decoded: '·' arrives escaped)."""
        out, err, rc = tick_raw(*a, **k)
        try:
            j = json.loads(out)
            out = j["hookSpecificOutput"]["additionalContext"]
        except Exception:
            pass
        return out, err, rc

    def lvl(sdir, args, env=None):
        return run("_strain_level.py", None, args, dict({"STRAIN_STATE_DIR": sdir}, **(env or {})))

    def ctx_of(sdir, sid):
        return state_of(sdir, sid).get("ctx") or {}

    # ---- A1 · a calibration record rules only its own <product> · <model> (0.8.0) --------
    adir = os.path.join(tmp, "a1")
    os.makedirs(adir, exist_ok=True)
    legacy = os.path.join(adir, "calibration.json")
    with open(legacy, "w") as f:                 # what a Codex session wrote on 0.7.0
        json.dump({"product": "Codex", "model": "gpt-x-test", "window": 258400,
                   "basis": "runtime", "source": "host runtime log",
                   "checkedAt": __import__("time").strftime("%Y-%m-%d")}, f)
    legacy_bytes = open(legacy, "rb").read()
    s1 = U(1)
    out, _, _ = tick(adir, s1, n=1, transcript=cc_transcript(tmp, s1, 104000))
    check("0.8.0 A1: another host's record never rules a Claude Code session",
          ctx_of(adir, s1).get("limit") == 1000000 and "window 1M (model hint)" in out,
          (ctx_of(adir, s1).get("limit"), out[-300:]))
    s2 = U(2)
    _, err, rc = run("_strain_calibrate.py", None,
                     ["--state-dir", adir, "--product", "Claude Code", "--window", "900000",
                      "--basis", "nominal", "--source", "vendor docs", "--session", s1])
    check("0.8.0 A1: --model is required and the refusal names the observed model",
          rc == 2 and "--model" in err and "claude-opus-5-5" in err, (rc, err))
    for spelling in ("claude code", "Claude-Code"):
        _, err, rc = run("_strain_calibrate.py", None,
                         ["--state-dir", adir, "--product", spelling,
                          "--model", "Claude-Opus-5-5", "--window", "900000",
                          "--basis", "nominal", "--source", "vendor docs"])
    reg = jl(os.path.join(adir, "models.json"), {})
    check("0.8.0 A1: product spellings collapse to one key (models.json)",
          rc == 0 and list(reg) == ["Claude Code · claude-opus-5-5"], (rc, err, reg))
    check("0.8.0 A1: calibrate leaves the old calibration.json byte-identical",
          open(legacy, "rb").read() == legacy_bytes)
    out, _, _ = tick(adir, s1, n=1, transcript=cc_transcript(tmp, s1, 104000))
    check("0.8.0 A1/B1: the matching record rules, and the bracket names it",
          ctx_of(adir, s1).get("limit") == 900000
          and "window 900k (calibrated: Claude Code · claude-opus-5-5)" in out,
          (ctx_of(adir, s1), out[-300:]))
    out, err, rc = lvl(adir, ["--session", s1, "--ctx-used", "90000", "--ctx-source", "host pane"])
    check("0.8.0 A1: a feed divides by the matching record, not another host's",
          rc == 0 and "fill 10.0%" in out, (rc, out, err))
    # Cowork's own record (Sonnet 5 compacts at 500K there) never rules Claude Code
    run("_strain_calibrate.py", None,
        ["--state-dir", adir, "--product", "Cowork", "--model", "claude-sonnet-5",
         "--window", "400000", "--basis", "runtime", "--source", "host"])
    s3 = U(3)
    out, _, _ = tick(adir, s3, n=1, transcript=cc_transcript(tmp, s3, 100000, "claude-sonnet-5"))
    check("0.8.0 A1: a Cowork record does not rule a Claude Code session on the same model",
          ctx_of(adir, s3).get("limit") == 500000, ctx_of(adir, s3))
    s4 = U(4)
    cw = os.path.join(tmp, "local-agent-mode-sessions", "x", s4 + ".jsonl")
    os.makedirs(os.path.dirname(cw), exist_ok=True)
    make_transcript(cw, [(2, 10000, 0), (2, 100000, 0)], model="claude-sonnet-5")
    tick(adir, s4, n=1, transcript=cw)
    check("0.8.0 A1: ... and does rule a Cowork session on it",
          ctx_of(adir, s4).get("limit") == 400000, ctx_of(adir, s4))
    # unrecognised hosts: model alone, one candidate only; a known product's record never
    s5 = U(5)
    run("_strain_calibrate.py", None,
        ["--state-dir", adir, "--product", "Example Host", "--model", "ex-model-1",
         "--window", "300000", "--basis", "runtime", "--source", "host"])
    exr = os.path.join(tmp, "ex", s5 + ".jsonl")
    os.makedirs(os.path.dirname(exr), exist_ok=True)
    make_transcript(exr, [(2, 10000, 0), (2, 30000, 0)], model="ex-model-1")
    tick(adir, s5, n=1, transcript=exr)
    check("0.8.0 A1: an unrecognised host on a recorded model gets that record",
          ctx_of(adir, s5).get("limit") == 300000, ctx_of(adir, s5))
    bdir2 = os.path.join(tmp, "a1b")
    for prod in ("Host One", "Host Two"):
        run("_strain_calibrate.py", None,
            ["--state-dir", bdir2, "--product", prod, "--model", "m-" + prod[-3:].lower(),
             "--window", "300000", "--basis", "runtime", "--source", "host"])
    s6 = U(6)
    out, _, _ = tick(bdir2, s6, n=1)
    check("0.8.0 A1: model unknown + two candidates -> none applied, the bracket says why",
          ctx_of(bdir2, s6).get("limit") == 200000 and "2 candidates" in out,
          (ctx_of(bdir2, s6), out[-300:]))
    # a legacy record WITHOUT a model is never applied, and the tick says so once
    ldir = os.path.join(tmp, "a1l")
    os.makedirs(ldir, exist_ok=True)
    with open(os.path.join(ldir, "calibration.json"), "w") as f:
        json.dump({"product": "Some Host", "model": "", "window": 300000, "basis": "runtime",
                   "source": "x", "checkedAt": __import__("time").strftime("%Y-%m-%d")}, f)
    s7 = U(7)
    o1, _, _ = tick(ldir, s7, n=1)
    o2, _, _ = tick(ldir, s7, n=1)
    check("0.8.0 A1: an old record with no model is never applied, said once",
          ctx_of(ldir, s7).get("limit") == 200000 and "has no model" in o1
          and "has no model" not in o2, (o1[-400:], o2[-200:]))
    # parallel calibrations keep both entries
    pdir = os.path.join(tmp, "a1p")
    lost = 0
    for rnd in range(3):
        ps = [subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "_strain_calibrate.py"),
                                "--state-dir", pdir, "--product", "Host %d" % i,
                                "--model", "m%d-%d" % (rnd, i), "--window", "1000",
                                "--basis", "runtime", "--source", "s"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=CLEAN_ENV)
              for i in range(6)]
        [p.wait() for p in ps]
    n_entries = len(jl(os.path.join(pdir, "models.json"), {}))
    check("0.8.0 A1: 18 calibrations in parallel keep 18 entries", n_entries == 18, n_entries)

    # ---- A2 · UNMEASURED is recordable --------------------------------------------------
    udir = os.path.join(tmp, "a2")
    su = U(8)
    out, _, _ = tick(udir, su, n=1)
    check("0.8.0 A2: the record command offers UNMEASURED",
          "UNMEASURED>" in out or "|UNMEASURED" in out, out[-900:])
    _, err, rc = lvl(udir, ["UNMEASURED", "--session", su])
    out, _, _ = tick(udir, su, n=1)
    check("0.8.0 A2: UNMEASURED is recorded and carried",
          rc == 0 and "carried: UNMEASURED" in out, (rc, err, out[:300]))

    # ---- A3 · the hooks.json description ------------------------------------------------
    hj = json.load(open(os.path.join(os.path.dirname(HERE), "hooks", "hooks.json")))
    check("0.8.0 A3: hooks.json no longer calls a compaction an escalation",
          "escalation" not in hj.get("description", "")
          and "never a tier floor" in hj.get("description", ""), hj.get("description"))

    # ---- A4 · a failed save is said, not swallowed ---------------------------------------
    rdir = os.path.join(tmp, "a4")
    sr = U(9)
    tick(rdir, sr, n=1000)
    sess = os.path.join(rdir, "sessions")
    os.chmod(sess, 0o555)
    os.chmod(os.path.join(sess, sr + ".json"), 0o444)
    try:
        o1, e1, rc1 = tick(rdir, sr, n=1)
        o2, e2, rc2 = tick(rdir, sr, n=1)
        ob, _, _ = start(rdir, sr, source="resume")
    finally:
        os.chmod(sess, 0o755)
        os.chmod(os.path.join(sess, sr + ".json"), 0o644)
    check("0.8.0 A4: an unwritable state file is said (directive + stderr), exit 0",
          rc1 == 0 and "could not be saved" in o1 and "could not be saved" in e1, (rc1, o1[:300], e1))
    check("0.8.0 A4: ... once, not on every call", rc2 == 0 and o2 == "", o2[:200])
    check("0.8.0 A4: the boot says it too", "could not be saved" in ob, ob[:300])
    o3, _, _ = tick(rdir, sr, n=1)
    check("0.8.0 A4: the next saved tick notes the gap",
          "earlier readings could not be saved" in o3, o3[:400])

    # ---- A6 · Codex as a known host -----------------------------------------------------
    cdir = os.path.join(tmp, "a6")
    sc = U(10)
    path, home = rollout(tmp, sc, [("model", "gpt-x-test"), ("usage", 120000, 100000, 258400),
                                   ("usage", 129584, 128512, 258400)])
    CX = {"CODEX_HOME": home}
    out, _, _ = tick(cdir, sc, n=1, transcript=path, extra_env=CX)
    c = ctx_of(cdir, sc)
    check("0.8.0 A6: a Codex rollout is MEASURED -- newest receipt, cache not double-counted",
          c.get("mode") == "measured" and c.get("tokens") == 129584 and c.get("limit") == 258400
          and c.get("model") == "gpt-x-test", c)
    check("0.8.0 A6/B1: the host is named and the window says it came from the host",
          state_of(cdir, sc).get("substrate") == "codex"
          and "window 258k (host-reported · Codex)" in out, (state_of(cdir, sc).get("substrate"), out[-300:]))
    sc2 = U(11)
    p2, _ = rollout(tmp, sc2, [("model", "gpt-x-test"), ("usage", 50000, 0, 258400)])
    tick(cdir, sc2, n=1, extra_env=CX)           # no transcript_path: found by id under CODEX_HOME
    check("0.8.0 A6: found by its session id when the hook names no file",
          ctx_of(cdir, sc2).get("tokens") == 50000, ctx_of(cdir, sc2))
    sc3 = U(12)
    p3, _ = rollout(tmp, sc3, [("usage", 50000, 0, 258400)], meta_id=U(99),
                    name="rollout-2026-09-30T12-00-00-other.jsonl")
    tick(cdir, sc3, n=1, transcript=p3, extra_env=CX)
    check("0.8.0 A6: a log that belongs to another session is never read as this one",
          ctx_of(cdir, sc3).get("mode") != "measured", ctx_of(cdir, sc3))
    sc4 = U(13)
    p4, _ = rollout(tmp, sc4, [("model", "gpt-x-test"), ("usage", 238739, 0, 258400), ("compacted",)])
    out, _, _ = tick(cdir, sc4, n=1, transcript=p4, extra_env=CX)
    check("0.8.0 A6/B3: a compaction voids the receipt -> UNMEASURED · stale, host re-measures",
          "PROPOSED TIER: UNMEASURED · stale" in out and "next request" in out, out[:500])
    p4, _ = rollout(tmp, sc4, [("model", "gpt-x-test"), ("usage", 238739, 0, 258400), ("compacted",),
                               ("usage", 0, 0, 258400), ("usage", 47766, 0, 258400)])
    tick(cdir, sc4, n=1, transcript=p4, extra_env=CX)
    check("0.8.0 A6: a receipt after the compaction re-measures (a zero receipt is skipped)",
          ctx_of(cdir, sc4).get("tokens") == 47766, ctx_of(cdir, sc4))
    sc5 = U(14)
    p5, _ = rollout(tmp, sc5, [("model", "gpt-x-test"), ("usage", 90000, 0, 258400),
                               ("model", "gpt-x-mini")])
    out, _, _ = tick(cdir, sc5, n=1, transcript=p5, extra_env=CX)
    check("0.8.0 A6: a model switch voids the receipt", "UNMEASURED · stale" in out
          and "model" in out.split("UNMEASURED · stale", 1)[1][:200], out[:400])
    sc6 = U(15)
    p6, _ = rollout(tmp, sc6, [("model", "gpt-x-test"), ("usage", 90000, 0, 0)])
    out, _, _ = tick(cdir, sc6, n=1, transcript=p6, extra_env=CX)
    check("0.8.0 A6: window 0 -> UNMEASURED · unusable", "UNMEASURED · unusable" in out, out[:400])
    sc7 = U(16)
    p7, _ = rollout(tmp, sc7, [("model", "gpt-x-test"),
                               ("usage", 77000, 0, 258400, "2026-09-30T08:00:00.000Z")])
    with open(p7, "a") as f:
        f.write('{"timestamp":"2026-09-30T12:00:01.000Z","type":"event_msg","payload":{"type":"tok')
    run("_strain_calibrate.py", None, ["--state-dir", cdir, "--product", "Codex",
                                        "--model", "gpt-x-test", "--window", "1000000",
                                        "--basis", "nominal", "--source", "x"])
    tick(cdir, sc7, n=1, transcript=p7, extra_env=CX)
    c = ctx_of(cdir, sc7)
    check("0.8.0 A6: no clock (an old receipt still reads), a torn last line is ignored",
          c.get("mode") == "measured" and c.get("tokens") == 77000, c)
    check("0.8.0 D4: the host-reported window beats a calibration record",
          c.get("limit") == 258400, c)

    # ---- A7 · identity is handed over by the host, never guessed -------------------------
    idir = os.path.join(tmp, "a7")
    sa, sb = U(20), U(21)
    tick(idir, sa, cwd="/tmp/a7-claude")
    tick(idir, sb, cwd="/tmp/a7-codex")          # newer, another folder
    for script, args in (("_strain_level.py", ["High"]), ("_strain_signal.py", ["k", "--escaped"]),
                         ("_strain_sign.py", ["--agent", "ana"]), ("_strain_wrap.py", [])):
        _, err, rc = run(script, None, args, {"STRAIN_STATE_DIR": idir})
        check("0.8.0 A7: %s without a key refuses (exit 2) and lists ready commands" % script,
              rc == 2 and "no session key" in err and "STRAIN_SESSION=" in err, (rc, err[:400]))
    check("0.8.0 A7: ... and nothing landed in either session",
          state_of(idir, sa).get("last") == "Healthy" and not state_of(idir, sb).get("signals")
          and not state_of(idir, sa).get("agent"), (state_of(idir, sa), state_of(idir, sb)))
    out, err, rc = lvl(idir, ["--get"])
    check("0.8.0 A7: a read may guess, and says it guessed", rc == 0 and "guessed" in err, (rc, err))
    _, err, rc = lvl(idir, ["High"], {"STRAIN_SESSION": sa, "CLAUDE_CODE_SESSION_ID": sb})
    check("0.8.0 A7: sources that disagree -> refuse, naming both",
          rc == 2 and "disagree" in err and sa in err and sb in err, (rc, err))
    _, err, rc = lvl(idir, ["High"], {"CLAUDE_CODE_SESSION_ID": sa})
    check("0.8.0 D6: the undocumented host id alone is a cross-check, not a key -- but it ranks"
          " its session first", rc == 2 and err.find(sa) != -1
          and (err.find(sb) == -1 or err.find(sa) < err.find(sb)), (rc, err))
    _, err, rc = lvl(idir, ["Mid"], {"CODEX_THREAD_ID": sb})
    check("0.8.0 A7: Codex hands its thread id to the shell -- that is a key",
          rc == 0 and state_of(idir, sb).get("last") == "Mid", (rc, err))
    envf = os.path.join(tmp, "a7-env.sh")
    open(envf, "w").close()
    start(idir, sa)
    run("_strain_reset.py", {"session_id": sa, "cwd": "/tmp/a7-claude", "source": "startup",
                             "hook_event_name": "SessionStart"}, [],
        {"STRAIN_STATE_DIR": idir, "CLAUDE_ENV_FILE": envf})
    check("0.8.0 A7: SessionStart hands the id to the agent's shell (CLAUDE_ENV_FILE)",
          open(envf).read() == "export STRAIN_SESSION=%s\n" % sa, open(envf).read())

    # ---- B3 · UNMEASURED says which kind, and the next step is a procedure ------------------
    bdir = os.path.join(tmp, "b3")
    sn = U(30)
    out, _, _ = tick(bdir, sn, n=1)
    check("0.8.0 B3: no source -> a checklist ending in one of two records",
          "PROPOSED TIER: UNMEASURED · no source" in out and "--no-source --checked" in out
          and "--ctx-used" in out, out[:900])
    _, err, rc = lvl(bdir, ["--session", sn, "--no-source", "--checked", "status command, settings"])
    out, _, _ = tick(bdir, sn, n=1)
    check("0.8.0 B3: once recorded, the checklist stops and the record is shown",
          rc == 0 and "checked: status command, settings" in out and "--no-source --checked" not in out,
          (rc, err, out[:600]))
    so = U(31)
    out, _, _ = tick(bdir, so, n=1, transcript=cc_transcript(tmp, so, 300000),
                     extra_env={"STRAIN_CONTEXT_LIMIT": "200000"})
    check("0.8.0 B3/S1: fill over 100% -> unusable, a lower bound, what to check, a report offer",
          "UNMEASURED · unusable" in out and "lower bound" in out and "strain-report.sh" in out,
          out[:900])
    sf = U(32)
    tick(bdir, sf, n=1)
    lvl(bdir, ["--session", sf, "--ctx-used", "50000", "--ctx-source", "host pane",
               "--ctx-provenance", "host-reported"])
    check("0.8.0 B3: a feed keeps its provenance",
          ctx_of(bdir, sf).get("provenance") == "host-reported", ctx_of(bdir, sf))
    start(bdir, sf, source="compact")
    out, _, _ = tick(bdir, sf, n=1)
    check("0.8.0 B3: a stale FED reading asks for a new feed",
          "UNMEASURED · stale" in out and "feed a new reading" in out, out[:600])

    # ---- D5 · the byte estimate counts only what follows the last compaction ---------------
    ddir = os.path.join(tmp, "d5")
    sd = U(40)
    dp = os.path.join(tmp, "d5.jsonl")
    with open(dp, "w") as f:
        f.write(("x" * 99 + "\n") * 400)                                  # 40,000 bytes
        f.write(json.dumps({"type": "system", "subtype": "compact_boundary"}) + "\n")
        f.write(("y" * 99 + "\n") * 40)                                   # 4,000 bytes
    tick(ddir, sd, n=1, transcript=dp)
    check("0.8.0 D5: the estimate counts bytes after the last compaction marker (4000/4)",
          ctx_of(ddir, sd).get("mode") == "estimated" and ctx_of(ddir, sd).get("tokens") == 1000,
          ctx_of(ddir, sd))

    # ---- B4 · the receipt (0.8.1: one plain sentence for the user; details for the agent) ---
    TECH = ("window", "transcript", "model", "ledger", "state", "hint", "·", "host", "token")

    def plain_ok(line):
        return bool(line) and not any(w in line for w in TECH)

    def user_line(out):
        return next((l for l in out.splitlines() if l.startswith("Strain ")
                     and not l.startswith("Strain ·") and not l.startswith("Strain receipt")), "")

    rcd = os.path.join(tmp, "b4")
    sr2 = U(50)
    tick(rcd, sr2, n=1000, transcript=cc_transcript(tmp, sr2, 104000))
    out, err, rc = run("_strain_sign.py", None, ["--agent", "ana", "--session", sr2],
                       {"STRAIN_STATE_DIR": rcd})
    ul = user_line(out)
    check("0.8.1 (was 0.8.0 B4: the receipt line on stdout): the first sign tells the user one"
          " plain sentence", rc == 0 and ul.startswith("Strain is on. This conversation is 10% full")
          and plain_ok(ul) and "Strain receipt" not in out, (rc, out))
    check("0.8.1: ... and the details go to the agent (stderr)",
          "Strain receipt" in err and "host Claude Code" in err and "session %s" % sr2[:8] in err
          and "reading Claude transcript" in err and "window 1M (model hint)" in err
          and "hooks saving" in err, err)
    out2, _, _ = run("_strain_sign.py", None, ["--agent", "ana", "--session", sr2],
                     {"STRAIN_STATE_DIR": rcd})
    out3, err3, rc3 = run("_strain_sign.py", None, ["--receipt", "--session", sr2],
                          {"STRAIN_STATE_DIR": rcd})
    check("0.8.0 B4: a re-sign does not repeat it; --receipt reprints it any time",
          not user_line(out2) and rc3 == 0 and user_line(out3).startswith("Strain is on.")
          and "Strain receipt" in err3, (out2, out3, err3))
    os.chmod(os.path.join(rcd, "sessions", sr2 + ".json"), 0o444)
    os.chmod(os.path.join(rcd, "sessions"), 0o555)
    try:
        out4, err4, _ = run("_strain_sign.py", None, ["--receipt", "--session", sr2],
                            {"STRAIN_STATE_DIR": rcd})
        _, err5, rc5 = lvl(rcd, ["Mid", "--session", sr2])
    finally:
        os.chmod(os.path.join(rcd, "sessions"), 0o755)
        os.chmod(os.path.join(rcd, "sessions", sr2 + ".json"), 0o644)
    check("0.8.1 (was 0.8.0 B4: an unwritable state file shows as FAILED): a shell that cannot"
          " write is not 'strain cannot save' -- the hooks still save",
          user_line(out4).startswith("Strain is on.") and "can't save" not in out4
          and "hooks saving" in err4 and "this shell cannot write" in err4, (out4, err4))
    check("0.8.1: a record refused for permission says to ask the user, and that the hooks are"
          " not affected", rc5 == 1 and "ask the user" in err5 and "hooks" in err5, (rc5, err5))
    sm = U(51)
    tp = cc_transcript(tmp, sm, 104000)
    o1, _, _ = tick_raw(rcd, sm, n=1, transcript=tp, extra_env=CC)
    o2, _, _ = tick_raw(rcd, sm, n=1, transcript=tp, extra_env=CC)
    try:
        m1, m2 = json.loads(o1).get("systemMessage", ""), json.loads(o2).get("systemMessage", "")
    except Exception:
        m1 = m2 = ""
    check("0.8.1 (was 0.8.0 B4: the hook shows the receipt line): the hook shows the user one"
          " plain sentence, once", m1.startswith("Strain is on. This conversation is 10% full")
          and plain_ok(m1) and not m2, (m1, m2))
    sm2 = U(52)
    plain = os.path.join(tmp, "plain", sm2 + ".jsonl")
    os.makedirs(os.path.dirname(plain), exist_ok=True)
    make_transcript(plain, [(2, 10000, 0), (2, 104000, 0)], model="claude-opus-5-5")
    o3, _, _ = tick_raw(rcd, sm2, n=1, transcript=plain)
    check("0.8.0 B4: a host strain cannot vouch for gets no user message",
          "systemMessage" not in o3, o3[:200])
    open(tp, "w").close()                        # the reading disappears -> a NEW UNMEASURED
    o4, _, _ = tick_raw(rcd, sm, n=1, transcript=tp, extra_env=CC)
    try:
        m4 = json.loads(o4).get("systemMessage", "")
    except Exception:
        m4 = ""
    check("0.8.1 (was 0.8.0 B4: 'not measured' + the kind): a new UNMEASURED is told in plain words",
          m4 == "Strain can't tell how full this conversation is right now, so it's only counting"
          " the agent's work and mistakes.", m4)
    sm3 = U(53)
    tp3 = cc_transcript(tmp, sm3, 104000)
    tick_raw(rcd, sm3, n=1000, transcript=tp3, extra_env=CC)
    os.chmod(os.path.join(rcd, "sessions"), 0o555)
    try:
        o5, _, _ = tick_raw(rcd, sm3, n=1, transcript=tp3, extra_env=CC)
    finally:
        os.chmod(os.path.join(rcd, "sessions"), 0o755)
    try:
        m5 = json.loads(o5).get("systemMessage", "")
    except Exception:
        m5 = ""
    check("0.8.1: a hook that cannot save tells the user in plain words",
          m5 == "Strain can't save on this computer, so it isn't keeping track of this"
          " conversation. Your agent has the details.", m5)

    # ---- S1 · a bug report the user sends by hand -----------------------------------------
    rp = os.path.join(tmp, "s1")
    sx = U(60)
    tick(rp, sx, n=1, transcript=cc_transcript(tmp, sx, 300000),
         extra_env={"STRAIN_CONTEXT_LIMIT": "200000"})
    out, err, rc = run("_strain_report.py", None,
                       ["--session", sx, "--note", "seen in %s while session %s ran" % (tmp, sx)],
                       {"STRAIN_STATE_DIR": rp})
    reps = [os.path.join(rp, "reports", f) for f in (os.listdir(os.path.join(rp, "reports"))
                                                     if os.path.isdir(os.path.join(rp, "reports")) else [])]
    body = open(reps[0]).read() if reps else ""
    check("0.8.0 S1: strain-report.sh drafts a report and sends nothing",
          rc == 0 and "nothing was sent" in out and len(reps) == 1 and "/issues/new" in err, (rc, out, err))
    check("0.8.0 S1: the draft carries the facts and no path or session id",
          "unusable" in body and "300" in body and tmp not in body and sx not in body
          and os.path.expanduser("~") not in body, body[:600])

    # ---- S5 · signing takes the session lock ------------------------------------------------
    kdir = os.path.join(tmp, "s5")
    sk = U(70)
    tick(kdir, sk, n=1000)
    for rnd in range(3):
        ps = [subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "_strain_tick.py"), "--n", "1000"],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, env=dict(CLEAN_ENV, STRAIN_STATE_DIR=kdir),
                               text=True) for _ in range(12)]
        sg = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "_strain_sign.py"),
                               "--agent", "a%d" % rnd, "--session", sk],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              env=dict(CLEAN_ENV, STRAIN_STATE_DIR=kdir))
        for p in ps:
            p.stdin.write(json.dumps({"session_id": sk, "cwd": "/tmp/proj"}))
            p.stdin.close()
        [p.wait() for p in ps]
        sg.wait()
    check("0.8.0 S5 (guard): parallel ticks and a sign lose no count",
          state_of(kdir, sk).get("tick") == 37 and state_of(kdir, sk).get("agent") == "a2",
          state_of(kdir, sk))

    # ---- B2 · the shared-file guard -------------------------------------------------------
    # A full scenario; then EVERY file strain wrote must be per-session, or keyed per entry
    # by session / agent / product · model. A new unkeyed file fails here (the class of the 0.8.0 shared-record bug).
    gdir = os.path.join(tmp, "b2")
    sg1, sg2 = U(80), U(81)
    book = os.path.join(tmp, "b2-proj", "Log.strain")
    os.makedirs(os.path.dirname(book), exist_ok=True)
    start(gdir, sg1, model="claude-opus-5-5")
    tick(gdir, sg1, n=1, transcript=cc_transcript(tmp, sg1, 104000))
    tick(gdir, sg2, n=1, cwd="/tmp/b2-other")
    run("_strain_sign.py", None, ["--agent", "ana", "--session", sg1, "--ledger", book],
        {"STRAIN_STATE_DIR": gdir})
    lvl(gdir, ["Mid", "--session", sg1])
    run("_strain_signal.py", None, ["k", "--caught", "--session", sg1], {"STRAIN_STATE_DIR": gdir})
    run("_strain_calibrate.py", None, ["--state-dir", gdir, "--product", "Claude Code",
                                        "--model", "claude-opus-5-5", "--window", "1000000",
                                        "--basis", "nominal", "--source", "x"])
    lvl(gdir, ["--session", sg2, "--ctx-used", "1000", "--ctx-source", "x"])
    run("_strain_wrap.py", None, ["--session", sg1], {"STRAIN_STATE_DIR": gdir})
    run("_strain_report.py", None, ["--session", sg1], {"STRAIN_STATE_DIR": gdir})
    bad = []
    for root, _dirs, files in os.walk(gdir):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), gdir)
            full = os.path.join(root, fn)
            m = _re.match(r"^sessions/([0-9a-f-]+)\.json(\.lock)?$", rel)
            if m:
                if not m.group(2) and json.load(open(full)).get("sid") != m.group(1):
                    bad.append(rel + " (sid inside differs from its name)")
                continue
            if _re.match(r"^reports/strain-report-[0-9a-f]{8}-\d{8}-\d{6}\.md$", rel):
                continue
            if rel in ("ledgers.json.lock", "models.json.lock"):
                continue
            if rel == "index.json":
                ix = json.load(open(full))
                if not all(isinstance(v, dict) and v.get("sid") for v in
                           list((ix.get("by_cwd") or {}).values()) + [ix.get("last") or {}]):
                    bad.append(rel + " (an entry without its session)")
                continue
            if rel == "model-log.jsonl":
                if not all(json.loads(l).get("session_id") for l in open(full) if l.strip()):
                    bad.append(rel + " (a row without its session)")
                continue
            if rel == "ledgers.json":
                if not all(isinstance(v, dict) and v.get("ledger") for v in json.load(open(full)).values()):
                    bad.append(rel + " (an entry without its agent's ledger)")
                continue
            if rel == "models.json":
                for k, v in json.load(open(full)).items():
                    if k != "%s · %s" % (v.get("product"), v.get("model")):
                        bad.append(rel + " (entry %r not keyed by its product · model)" % k)
                continue
            bad.append(rel + " (not in the declared table -- unkeyed shared file?)")
    if os.path.isfile(book):
        for l in open(book):
            r = json.loads(l)
            if not (r.get("session") and r.get("agent")):
                bad.append("Log.strain row without session/agent: %r" % r)
    check("0.8.0 B2: every file strain writes is per-session or keyed per entry", not bad, bad)

    # ---- S2 / A5 · docs ---------------------------------------------------------------------
    skill = open(os.path.join(os.path.dirname(HERE), "skills", "strain", "SKILL.md")).read()
    readme = open(os.path.join(os.path.dirname(HERE), "README.md")).read()
    check("0.8.0 S2: SKILL says look before saying strain is missing -- host-neutral",
          "before saying strain is missing" in skill and "--receipt" in skill, "")
    check("0.8.0 A5: README says where strain writes, per host",
          "## Where strain writes" in readme and "STRAIN_STATE_DIR" in readme, "")
    check("0.8.0 A2: SKILL lists UNMEASURED as a recordable tier",
          "strain-level.sh UNMEASURED" in skill, "")
    check("0.8.1: the state-folder advice keeps hooks and records in ONE folder",
          "or set `STRAIN_STATE_DIR` to a folder inside the project for that host" not in readme
          and "`STRAIN_STATE_DIR` to a folder inside the project." not in skill
          and "only if the host's hooks get it too" in readme
          and "only if the host's hooks get it too" in skill, "")
    check("0.8.1: README says where the notice shows and to restart after an update",
          "received a notice" in readme and "restart the host" in readme, "")


def main():
    tmp = tempfile.mkdtemp(prefix="strain-selftest-")
    try:
        # ---- counting, per session -------------------------------------------------
        sdir = os.path.join(tmp, "s1")
        for _ in range(3):
            tick(sdir, "sess-A")
        check("tick counts", state_of(sdir, "sess-A").get("tick") == 3,
              state_of(sdir, "sess-A"))

        for _ in range(2):
            tick(sdir, "sess-B", cwd="/tmp/other")
        a, b = state_of(sdir, "sess-A"), state_of(sdir, "sess-B")
        check("two sessions do not merge", a.get("tick") == 3 and b.get("tick") == 2,
              (a.get("tick"), b.get("tick")))
        check("each session has its own file",
              os.path.isfile(os.path.join(sdir, "sessions", "sess-A.json")) and
              os.path.isfile(os.path.join(sdir, "sessions", "sess-B.json")))

        # ---- the directive fires on schedule, and only then -------------------------
        sdir = os.path.join(tmp, "s2")
        outs = [tick(sdir, "sess-C", n=3)[0] for _ in range(3)]
        check("silent before N", outs[0] == "" and outs[1] == "", outs[:2])
        check("directive at N", "STRAIN TICK" in outs[2], outs[2][:120])
        try:
            payload = json.loads(outs[2])
            ctx_ok = payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse" and \
                bool(payload["hookSpecificOutput"]["additionalContext"])
        except Exception as ex:
            ctx_ok = False
        check("directive uses additionalContext", ctx_ok)

        # ---- the writer and the reader share one location ---------------------------
        # The regression this guards: the CLI defaulting to a different state file from
        # the hooks, so recording a tier changed nothing the hooks could see.
        sdir = os.path.join(tmp, "s3")
        tick(sdir, "sess-D", cwd="/tmp/projD")
        out, err, rc = run("_strain_level.py", None, ["High", "--session", "sess-D"],
                           {"STRAIN_STATE_DIR": sdir})
        check("level writes", rc == 0 and out == "High", (rc, out, err))
        check("level lands where the hook reads",
              state_of(sdir, "sess-D").get("last") == "High", state_of(sdir, "sess-D"))
        got, _, _ = run("_strain_level.py", None, ["--get", "--session", "sess-D"],
                        {"STRAIN_STATE_DIR": sdir})
        check("level reads back", got == "High", got)
        nxt, _, _ = tick(sdir, "sess-D", n=1)
        check("directive carries the recorded tier", "carried: High" in nxt, nxt[:300])
        check("level reports which session it wrote", "sess-D" in err, err)

        # no explicit session: a WRITE refuses and lists candidates (0.8.0 A7) -- a
        # folder or most-recent guess is how a record lands in another session's file
        out, err, rc = run("_strain_level.py", None, ["Mid"],
                           {"STRAIN_STATE_DIR": sdir, "PWD": "/tmp/projD"})
        check("0.8.0 A7 (was: level resolves a session without being told): a keyless write"
              " refuses and names the candidate",
              rc == 2 and out == "" and "sess-D" in err
              and state_of(sdir, "sess-D").get("last") == "High", (rc, out, err))

        _, _, rc = run("_strain_level.py", None, ["Sleepy", "--session", "sess-D"],
                       {"STRAIN_STATE_DIR": sdir})
        check("a typo is not a reading", rc == 2, rc)

        # ---- wrap marker resets, once ------------------------------------------------
        sdir = os.path.join(tmp, "s4")
        for _ in range(4):
            tick(sdir, "sess-E")
        start(sdir, "sess-E", source="resume")
        check("no marker means keep counting", state_of(sdir, "sess-E").get("tick") == 4,
              state_of(sdir, "sess-E"))
        run("_strain_wrap.py", None, ["--label", "phase one", "--session", "sess-E"],
            {"STRAIN_STATE_DIR": sdir})
        start(sdir, "sess-E", source="resume")
        check("0.7.0 B2 (was: wrap marker resets): a wrap resets nothing, it records the wrap",
              state_of(sdir, "sess-E").get("tick") == 4
              and bool(state_of(sdir, "sess-E").get("wrappedAt")), state_of(sdir, "sess-E"))
        for _ in range(2):
            tick(sdir, "sess-E")
        start(sdir, "sess-E", source="resume")
        check("0.7.0 B2 (was: a wrap resets once): work after the wrap keeps counting",
              state_of(sdir, "sess-E").get("tick") == 6
              and state_of(sdir, "sess-E").get("wrapTick") == 4, state_of(sdir, "sess-E"))

        # ---- compaction is escalation, one way ---------------------------------------
        sdir = os.path.join(tmp, "s5")
        tick(sdir, "sess-F")
        start(sdir, "sess-F", source="compact")
        st = state_of(sdir, "sess-F")
        check("compaction counted", st.get("compactions") == 1, st)
        check("0.7.0 B1 (was: compaction floors the tier): stated, never a floor",
              st.get("last") == "Healthy", st)
        check("compaction preserves the count", st.get("tick") == 1, st)
        start(sdir, "sess-F", source="compact")
        st = state_of(sdir, "sess-F")
        check("0.7.0 B1 (was: second compaction escalates): counted, still no floor",
              st.get("last") == "Healthy" and st.get("compactions") == 2, st)
        run("_strain_level.py", None, ["Healthy", "--session", "sess-F"],
            {"STRAIN_STATE_DIR": sdir})
        start(sdir, "sess-F", source="resume")
        check("an honest improvement is allowed to be recorded",
              state_of(sdir, "sess-F").get("last") == "Healthy",
              state_of(sdir, "sess-F"))

        # ---- context: measured, inferred, and the timing trap -------------------------
        sdir = os.path.join(tmp, "s6")
        tpath = os.path.join(tmp, "transcript.jsonl")
        make_transcript(tpath, [(2, 30000, 100), (2, 90000, 200)])
        out, _, _ = tick(sdir, "sess-G", n=1, transcript=tpath)
        ctx = state_of(sdir, "sess-G").get("ctx", {})
        check("measured mode when usage exists", ctx.get("mode") == "measured", ctx)
        check("current context is the latest turn", ctx.get("tokens") == 90202, ctx)
        check("baseline is the first turn", ctx.get("baseline") == 30102, ctx)
        check("readout quotes the measurement", "context" in out and "boot" in out, out[:200])

        empty = os.path.join(tmp, "empty.jsonl")
        open(empty, "w").close()
        out, _, _ = tick(sdir, "sess-H", n=1, transcript=empty)
        ctx = state_of(sdir, "sess-H").get("ctx", {})
        check("an empty transcript is inferred, not zero", ctx.get("mode") == "inferred", ctx)
        check("inferred mode says so", "No context measurement" in out, out[:200])

        out, _, _ = tick(sdir, "sess-I", n=1, transcript="/nonexistent/x.jsonl")
        check("a missing transcript degrades quietly",
              state_of(sdir, "sess-I").get("ctx", {}).get("mode") == "inferred")

        # ---- fill bands: the same fixture under two capacities (the v2 calibration) ----
        # 160k tokens = 80% of a 200k window (Warning band) but 16% of a 1M one (Healthy).
        # The tiers must differ with ZERO config edits beyond the detected window.
        big = os.path.join(tmp, "big.jsonl")
        make_transcript(big, [(2, 10000, 0), (2, 160000, 0)])
        out, _, _ = tick(sdir, "sess-J", n=1, transcript=big)
        check("v3: 80% fill proposes Danger (>= derived cap 74) with a MANDATORY wrap",
              "PROPOSED TIER: Danger" in out and "MANDATORY DIRECTIVE" in out,
              out[:400])
        out, _, _ = tick(sdir, "sess-K", n=1, transcript=big,
                         extra_env={"STRAIN_CONTEXT_LIMIT": "1000000"})
        check("same fixture on a 1M window proposes Healthy",
              "PROPOSED TIER: Healthy" in out, out[:300])
        full = os.path.join(tmp, "full.jsonl")
        make_transcript(full, [(2, 10000, 0), (2, 178000, 0)])
        out, _, _ = tick(sdir, "sess-J2", n=1, transcript=full)
        check("89% fill proposes Danger on fill alone",
              "PROPOSED TIER: Danger" in out, out[:300])
        out, _, _ = tick(sdir, "sess-J3", n=1, transcript=big,
                         extra_env={"STRAIN_CAP_WARN": "90", "STRAIN_CAP_HIGH": "75",
                                    "STRAIN_THROTTLE_ONSET": "99",
                                    "STRAIN_WRAP_BUDGET": "1"})
        check("caps are env-tunable (80% under a raised ladder proposes High)",
              "PROPOSED TIER: High" in out, out[:300])

        # ---- model: observed from the transcript tail, logged on change ----------------
        # The SessionStart payload usually omits the model, so the transcript is the
        # source of truth -- and reading the TAIL means a mid-session /model switch is
        # seen, which no start-time reading could ever be.
        mdir = os.path.join(tmp, "s6m")
        mpath = os.path.join(tmp, "modeled.jsonl")
        make_transcript(mpath, [(2, 30000, 100), (2, 60000, 200)], model="model-one")
        tick(mdir, "sess-M", n=10, transcript=mpath)
        check("model observed from the transcript",
              state_of(mdir, "sess-M").get("model") == "model-one",
              state_of(mdir, "sess-M"))
        rows = model_log(mdir)
        check("model observation is logged",
              len(rows) == 1 and rows[0]["model"] == "model-one"
              and rows[0]["source"] == "observed", rows)
        tick(mdir, "sess-M", n=10, transcript=mpath)
        check("an unchanged model is not re-logged", len(model_log(mdir)) == 1,
              model_log(mdir))
        make_transcript(mpath, [(2, 30000, 100, "model-one"), (2, 90000, 0, "model-two")])
        tick(mdir, "sess-M", n=10, transcript=mpath)
        check("a mid-session model switch gets its own row",
              [r["model"] for r in model_log(mdir)] == ["model-one", "model-two"],
              model_log(mdir))
        check("state carries the current model",
              state_of(mdir, "sess-M").get("model") == "model-two",
              state_of(mdir, "sess-M"))
        start(mdir, "sess-M", source="resume")
        check("a start without a model logs no empty row", len(model_log(mdir)) == 2,
              model_log(mdir))
        start(mdir, "sess-M", source="startup", model="model-two")
        check("a start that names a model still logs it", len(model_log(mdir)) == 3,
              model_log(mdir))

        # ---- the denominator follows the model ----------------------------------------
        # 160k tokens is 80% of a 200k window but 16% of a 1M one. The regression this
        # guards: a hardcoded 200k limit reporting a 1M-window session as nearly full.
        ldir = os.path.join(tmp, "s6l")
        lpath = os.path.join(tmp, "longctx.jsonl")
        make_transcript(lpath, [(2, 10000, 0), (2, 160000, 0)], model="claude-fable-5")
        out, _, _ = tick(ldir, "sess-L1", n=1, transcript=lpath)
        ctx = state_of(ldir, "sess-L1").get("ctx", {})
        check("a 1M-window model gets a 1M denominator",
              ctx.get("limit") == 1000000 and ctx.get("pct") == 16.0, ctx)
        check("a 1M window is not reported as nearly full",
              "PROPOSED TIER: Healthy" in out, out[:300])
        make_transcript(lpath, [(2, 10000, 0), (2, 160000, 0)],
                        model="claude-sonnet-4-5[1m]")
        tick(ldir, "sess-L2", n=1, transcript=lpath)
        check("an explicit [1m] variant gets a 1M denominator",
              state_of(ldir, "sess-L2").get("ctx", {}).get("limit") == 1000000,
              state_of(ldir, "sess-L2").get("ctx"))
        make_transcript(lpath, [(2, 10000, 0), (2, 160000, 0)], model="claude-opus-5")
        tick(ldir, "sess-L4", n=1, transcript=lpath)
        check("opus-5 gets a 1M denominator (0.2.1 table refresh)",
              state_of(ldir, "sess-L4").get("ctx", {}).get("limit") == 1000000,
              state_of(ldir, "sess-L4").get("ctx"))
        make_transcript(lpath, [(2, 10000, 0), (2, 160000, 0)], model="claude-sonnet-5")
        tick(ldir, "sess-L5", n=1, transcript=lpath)
        check("sonnet-5 gets the 500K effective ceiling (Cowork compaction bound)",
              state_of(ldir, "sess-L5").get("ctx", {}).get("limit") == 500000,
              state_of(ldir, "sess-L5").get("ctx"))
        out, _, _ = tick(ldir, "sess-L3", n=1, transcript=lpath,
                         extra_env={"STRAIN_CONTEXT_LIMIT": "200000"})
        check("the env override still beats the model hint",
              state_of(ldir, "sess-L3").get("ctx", {}).get("limit") == 200000,
              state_of(ldir, "sess-L3").get("ctx"))

        # baseline is carried, not re-read
        st = state_of(sdir, "sess-G")
        st["ctx"]["baseline"] = 12345
        with open(os.path.join(sdir, "sessions", "sess-G.json"), "w") as f:
            json.dump(st, f)
        tick(sdir, "sess-G", n=99, transcript=tpath)
        check("a known baseline is carried, not recomputed",
              state_of(sdir, "sess-G")["ctx"].get("baseline") == 12345,
              state_of(sdir, "sess-G")["ctx"])

        # ---- v3 two-line model: the acceptance rows, unit level -----------------------
        # Direct calls on propose_tier -- some rows need fills no transcript fixture can
        # produce (an impossible percentage IS the fixture). Each row locks one behaviour
        # of the model; together they are the acceptance sheet for the v3 port.
        sys.path.insert(0, SCRIPTS)
        import _strain_tick as tickmod

        def pt(fill, mode="measured", escaped=0, compactions=0, env=None):
            old = {}
            for kk, vv in (env or {}).items():
                old[kk] = os.environ.get(kk)
                os.environ[kk] = vv
            try:
                stx = {"compactions": compactions,
                       "signals": [{"kind": "k%d" % i, "escaped": True}
                                   for i in range(escaped)]}
                ctxx = {"mode": mode, "pct": fill, "limit": 200000}
                return tickmod.propose_tier(stx, ctxx)
            finally:
                for kk, vv in old.items():
                    if vv is None:
                        os.environ.pop(kk, None)
                    else:
                        os.environ[kk] = vv

        t_, b_, d_ = pt(75.0, escaped=1)
        check("v3-A: fill 75 + 1 escaped = Danger via Line A, MANDATORY directive",
              t_ == "Danger" and any("MANDATORY" in x for x in d_)
              and "Line B Healthy" in b_, (t_, b_, d_))
        t_, b_, d_ = pt(210.0, escaped=4)
        check("v3-B: fill 210 = Line A abstains loudly, High via Line B only",
              t_ == "High" and "impossible" in b_, (t_, b_))
        t_, b_, d_ = pt(46.0, escaped=2)
        check("v3-C: fill 46 + 2 escaped = Healthy (both lines quiet)",
              t_ == "Healthy", (t_, b_))
        t_, b_, d_ = pt(None, mode="inferred")
        check("0.7.0 A2 (was v3-D): unmeasured mode = Line A abstains -> UNMEASURED, never Healthy",
              t_ == "UNMEASURED" and "abstains" in b_ and "fill 0" not in b_, (t_, b_))
        t_, b_, d_ = pt(80.0, env={"STRAIN_WRAP_BUDGET": "12"})
        check("v3-E: a raised WRAP_BUDGET that inverts the ladder shouts CONFIG INVALID",
              "CONFIG INVALID" in b_, b_)
        t_, b_, d_ = pt(82.0, escaped=0)
        check("v3-F: throttle zone with ZERO escaped -> no capacity-induced claim",
              "capacity-induced" not in b_, b_)
        t_, b_, d_ = pt(82.0, escaped=1)
        check("v3-F2: throttle zone WITH an escaped -> observation annotates only",
              "capacity-induced" in b_ and t_ == "Danger", (t_, b_))
        t_, b_, d_ = pt(90.0, env={"STRAIN_WRAP_BUDGET": "15"})
        check("v3-H: inverted ladder + fill 90 -> defaults in force -> Danger",
              t_ == "Danger" and "CONFIG INVALID" in b_, (t_, b_))
        t_, b_, d_ = pt(-5.0)
        check("0.7.0 A2 (was v3-I): pct -5 -> Line A abstains loudly -> UNMEASURED",
              t_ == "UNMEASURED" and "impossible" in b_, (t_, b_))

        # ---- robustness ---------------------------------------------------------------
        sdir = os.path.join(tmp, "s7")
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "_strain_tick.py")],
                           input="not json at all", capture_output=True, text=True,
                           env=dict(os.environ, STRAIN_STATE_DIR=sdir))
        check("a malformed payload never fails a tool call", p.returncode == 0, p.returncode)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "_strain_reset.py")],
                           input="", capture_output=True, text=True,
                           env=dict(os.environ, STRAIN_STATE_DIR=sdir))
        check("an empty payload never fails a session start", p.returncode == 0, p.returncode)
        check("an unknown session gets its own bucket, not someone else's",
              os.path.isfile(os.path.join(sdir, "sessions", "unknown-session.json")))

        # ---- v2 NEGATIVE FIXTURE: the v1 bug, reproduced and now passing ---------------
        # Three real sessions (2026-08-09/12/15) had v1 ratchet to Danger/Mid while the
        # measured fill was 33/28/33%. Reproduce the shape: a carried Warning tier, a long
        # tick history, 33% fill, zero escaped signals -> v2 must propose Healthy, offer
        # decay, and never escalate on tick count.
        ndir = os.path.join(tmp, "s8")
        npath = os.path.join(tmp, "third.jsonl")
        make_transcript(npath, [(2, 74000, 0), (2, 330000, 0)], model="claude-fable-5")
        for _ in range(80):                       # the tick treadmill that ratcheted v1
            tick(ndir, "sess-N", n=0, transcript=npath)
        run("_strain_level.py", None, ["Warning", "--session", "sess-N"],
            {"STRAIN_STATE_DIR": ndir})           # the ratcheted carry v1 left behind
        out, _, _ = tick(ndir, "sess-N", n=1, transcript=npath)
        check("33% fill with no escaped signals proposes Healthy, not Danger",
              "PROPOSED TIER: Healthy" in out, out[:400])
        check("the ratchet text is gone", "escalate to Danger" not in out
              and "Escalate" not in out, out[:400])
        check("a lower proposal names the decay", "LOWER than the carried tier" in out,
              out[:600])
        # caught-and-fixed errors (the third fixture had three, all one class) move nothing
        for _ in range(3):
            run("_strain_signal.py", None,
                ["half-mechanism", "--caught", "--session", "sess-N"],
                {"STRAIN_STATE_DIR": ndir})
        out, _, _ = tick(ndir, "sess-N", n=1, transcript=npath)
        check("caught signals do not move the proposal",
              "PROPOSED TIER: Healthy" in out, out[:400])
        check("a repeated signal class earns a pattern note",
              "Pattern note" in out and "half-mechanism x3" in out, out[:600])

        # ---- hard signals are absolute; escaped ones floor the tier --------------------
        gdir = os.path.join(tmp, "s9")
        tick(gdir, "sess-P", n=0, transcript=npath)          # 33% fill on a 1M window
        out, _, rc = run("_strain_signal.py", None,
                         ["regression", "--escaped", "--session", "sess-P"],
                         {"STRAIN_STATE_DIR": gdir})
        check("v3 ladder: one escaped signal moves NOTHING",
              rc == 0 and state_of(gdir, "sess-P").get("last") == "Healthy", (rc, out))
        run("_strain_signal.py", None, ["stale-read", "--escaped", "--session", "sess-P"],
            {"STRAIN_STATE_DIR": gdir})
        check("v3 ladder: two escaped signals still move nothing",
              state_of(gdir, "sess-P").get("last") == "Healthy",
              state_of(gdir, "sess-P"))
        run("_strain_signal.py", None, ["third-class", "--escaped", "--session", "sess-P"],
            {"STRAIN_STATE_DIR": gdir})
        check("v3 ladder: the third escaped floors Mid",
              state_of(gdir, "sess-P").get("last") == "Mid", state_of(gdir, "sess-P"))
        run("_strain_signal.py", None, ["fourth-class", "--escaped", "--session", "sess-P"],
            {"STRAIN_STATE_DIR": gdir})
        run("_strain_signal.py", None, ["fifth-class", "--escaped", "--session", "sess-P"],
            {"STRAIN_STATE_DIR": gdir})
        check("v3 ladder: the fifth escaped floors Warning",
              state_of(gdir, "sess-P").get("last") == "Warning",
              state_of(gdir, "sess-P"))
        out, _, _ = tick(gdir, "sess-P", n=1, transcript=npath)
        check("escaped floors survive a low-fill tick",
              "PROPOSED TIER: Warning" in out, out[:400])
        # v4 COMBINATION ALARM (owner's two-condition composite, restored 2026-09-13):
        # Warning-cap fill (72%, below the derived Danger cap 74) AND >=3 escaped ->
        # Danger, with a loud basis line naming both conditions. Below either
        # precondition the lines stay independent (max only); the throttle-zone note
        # still annotates and never tiers.
        wdir = os.path.join(tmp, "s9b")
        wpath = os.path.join(tmp, "warnfill.jsonl")
        make_transcript(wpath, [(2, 10000, 0), (2, 144000, 0)])   # 72% of 200k
        for kk in ("k1", "k2", "k3"):
            run("_strain_signal.py", None, [kk, "--escaped", "--session", "sess-Q"],
                {"STRAIN_STATE_DIR": wdir})
        out, _, _ = tick(wdir, "sess-Q", n=1, transcript=wpath)
        check("v4 composite: Warning fill + 3 escaped -> Danger",
              "PROPOSED TIER: Danger" in out and "Line B Mid" in out, out[:400])
        check("v4 composite fires LOUDLY (basis names both conditions)",
              "composite: fill already Warning AND escaped 3 >= 3 -> Danger" in out,
              out[:600])
        # v4 composite NEGATIVE (capacity precondition unmet): High-cap fill (65%)
        # + 3 escaped stays High -- the combination alarm needs Warning+ fill.
        hdir = os.path.join(tmp, "s9c")
        hpath = os.path.join(tmp, "highfill.jsonl")
        make_transcript(hpath, [(2, 10000, 0), (2, 130000, 0)])   # 65% of 200k
        for kk in ("h1", "h2", "h3"):
            run("_strain_signal.py", None, [kk, "--escaped", "--session", "sess-R"],
                {"STRAIN_STATE_DIR": hdir})
        out, _, _ = tick(hdir, "sess-R", n=1, transcript=hpath)
        check("v4 composite precondition: High fill + 3 escaped stays High",
              "PROPOSED TIER: High" in out and "composite" not in out, out[:400])
        # 0.4.1 drift glance: conditional, generic, non-flooring -- present by
        # default, dropped by STRAIN_DRIFT_GLANCE=off, and never a tier input
        # (the proposed tier is identical with and without it).
        out_on, _, _ = tick(hdir, "sess-R", n=1, transcript=hpath)
        check("drift glance rides the tick by default (non-flooring note)",
              "GOAL DRIFT" in out_on and "never" in out_on
              and "PROPOSED TIER: High" in out_on, out_on[:700])
        out_off, _, _ = tick(hdir, "sess-R", n=1, transcript=hpath,
                             extra_env={"STRAIN_DRIFT_GLANCE": "off"})
        check("STRAIN_DRIFT_GLANCE=off drops the glance, tier unchanged",
              "GOAL DRIFT" not in out_off and "PROPOSED TIER: High" in out_off,
              out_off[:400])
        _, err, rc = run("_strain_signal.py", None, ["oops", "--session", "sess-Q"],
                         {"STRAIN_STATE_DIR": wdir})
        check("a signal must say caught or escaped", rc == 2 and "say whether" in err,
              (rc, err))

        # ---- estimated mode: transcript bytes when the host logs no usage --------------
        edir = os.path.join(tmp, "s10")
        bpath = os.path.join(tmp, "nousage.jsonl")
        with open(bpath, "w") as f:
            for _ in range(2000):
                f.write(json.dumps({"type": "assistant",
                                    "message": {"role": "assistant"}}) + "\n")
        out, _, _ = tick(edir, "sess-R", n=1, transcript=bpath)
        ctx = state_of(edir, "sess-R").get("ctx", {})
        check("bytes become an estimated fill, not inferred silence",
              ctx.get("mode") == "estimated" and ctx.get("pct") is not None, ctx)
        check("estimated mode says so out loud", "ESTIMATED from transcript bytes" in out,
              out[:400])

        # ---- calibration is printed at boot, and a wrap reset clears signals -----------
        cdir = os.path.join(tmp, "s11")
        out, _, _ = start(cdir, "sess-S")
        check("0.7.0 A5/A6 (was: boot prints the 40/60/75/85 bands): boot prints the tick's caps",
              "strain calibration:" in out and "50/60/70/74" in out
              and "40/60/75/85" not in out, out[:400])
        run("_strain_signal.py", None, ["regression", "--escaped", "--session", "sess-S"],
            {"STRAIN_STATE_DIR": cdir})
        run("_strain_wrap.py", None, ["--label", "done", "--session", "sess-S"],
            {"STRAIN_STATE_DIR": cdir})
        start(cdir, "sess-S", source="resume")
        st = state_of(cdir, "sess-S")
        check("0.7.0 B2 (was: a wrap reset clears the signal ledger): a wrap keeps the signals",
              len(st.get("signals") or []) == 1, st)

        # ---- 0.5.0: signed wraps + the project ledger ----------------------------------
        # The shipped failure this section locks: two agents, one state dir -- one
        # agent's wrap marker reset the other's LIVE session at its next start.
        wdir = os.path.join(tmp, "signed")
        os.makedirs(wdir, exist_ok=True)
        proj = os.path.join(tmp, "signed-proj")
        os.makedirs(proj, exist_ok=True)
        book = os.path.join(proj, "Log.strain")
        tick(wdir, "sess-A1", cwd="/tmp/proj-a")     # two live sessions, two agents
        tick(wdir, "sess-B1", cwd="/tmp/proj-b")
        tick(wdir, "sess-B1", cwd="/tmp/proj-b")
        out, err, rc = run("_strain_sign.py", None,
                           ["--agent", "ana", "--session", "sess-A1", "--ledger", book],
                           {"STRAIN_STATE_DIR": wdir})
        check("sign records agent + ledger in the session state",
              rc == 0 and state_of(wdir, "sess-A1").get("agent") == "ana"
              and state_of(wdir, "sess-A1").get("ledger") == book
              and "Strain · Owner: ana" in out, (rc, out, state_of(wdir, "sess-A1")))
        with open(book) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        check("sign appends a boot-sign row to the ledger",
              len(rows) == 1 and rows[0].get("type") == "boot-sign"
              and rows[0].get("agent") == "ana"
              and rows[0].get("session") == "sess-A1", rows)
        run("_strain_sign.py", None, ["--agent", "bo", "--session", "sess-B1"],
            {"STRAIN_STATE_DIR": wdir})
        out, err, rc = run("_strain_wrap.py", None,
                           ["--label", "ana done", "--session", "sess-A1"],
                           {"STRAIN_STATE_DIR": wdir})
        check("wrap inherits the wrapping session's signature (no --agent needed)",
              rc == 0 and "Strain · Owner: ana — wrapped" in out, (rc, out))
        with open(book) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        check("a signed session's wrap is booked as a ledger row",
              len(rows) == 2 and rows[1].get("type") == "wrap"
              and rows[1].get("agent") == "ana"
              and rows[1].get("verdict") == "WRAPPED", rows)
        out, _, _ = start(wdir, "sess-B1", source="resume", cwd="/tmp/proj-b")
        stB = state_of(wdir, "sess-B1")
        check("0.7.0 B2 (was: ana's signed marker does NOT reset bo): ana's wrap leaves bo alone",
              stB.get("tick") == 2, (stB, out[:300]))
        out, _, _ = start(wdir, "sess-B1", source="resume", cwd="/tmp/proj-b")
        check("0.7.0 B2 (was: foreign-marker line once): no wrap line reaches another session",
              "signed by ana" not in out and "wrap" not in out.lower(), out[:300])
        out, _, _ = start(wdir, "sess-A1", source="resume", cwd="/tmp/proj-a")
        stA = state_of(wdir, "sess-A1")
        check("0.7.0 B2 (was: same signature resets): the wrapping session keeps its counters",
              stA.get("tick") == 1 and bool(stA.get("wrappedAt")), (stA, out[:300]))
        check("the reset keeps the signature and the ledger binding",
              stA.get("agent") == "ana" and stA.get("ledger") == book, stA)
        # unsigned marker = pre-0.5.0 behaviour, exactly (signing is opt-in)
        tick(wdir, "sess-C1", cwd="/tmp/proj-c")
        run("_strain_wrap.py", None, ["--session", "sess-C1"],
            {"STRAIN_STATE_DIR": wdir})
        start(wdir, "sess-B1", source="resume", cwd="/tmp/proj-b")
        check("0.7.0 B2 (was: an unsigned marker resets everyone): an unsigned wrap touches no one else",
              state_of(wdir, "sess-B1").get("tick") == 2, state_of(wdir, "sess-B1"))
        # an unsigned session facing a signed marker is told how to join in
        tick(wdir, "sess-D1", cwd="/tmp/proj-d")
        run("_strain_wrap.py", None, ["--agent", "ana", "--session", "sess-A1"],
            {"STRAIN_STATE_DIR": wdir})
        out, _, _ = start(wdir, "sess-D1", source="resume", cwd="/tmp/proj-d")
        check("0.7.0 B2 (was: unsigned session vs signed marker + hint): its counters stand",
              state_of(wdir, "sess-D1").get("tick") == 1, (state_of(wdir, "sess-D1"), out[:300]))
        # the ledger survives concurrent writers -- every row lands whole
        import threading
        sys.path.insert(0, SCRIPTS)
        import _strain_common as _C
        cbook = os.path.join(proj, "Concurrent.strain")
        ths = [threading.Thread(target=_C.ledger_append,
                                args=(cbook, {"type": "boot-sign", "i": i}))
               for i in range(20)]
        [t.start() for t in ths]; [t.join() for t in ths]
        got = _C.ledger_rows(cbook)
        check("20 concurrent ledger appends = 20 intact rows (flock)",
              len(got) == 20 and sorted(r.get("i") for r in got) == list(range(20)),
              (len(got), got[:3]))

        # ---- 0.5.1: per-agent ledger registry + user-surface purity -------------------
        out, err, rc = run("_strain_sign.py", None,
                           ["--agent", "ana", "--session", "sess-A9"],
                           {"STRAIN_STATE_DIR": wdir})
        check("0.5.1: a later session resolves its ledger from the registry",
              rc == 0 and "via registry" in err and "booked" in out,
              (rc, out, err[:200]))
        check("0.5.1 USER-SURFACE purity: stdout has no flags/paths/commands",
              "Strain · Owner: ana" in out and "--" not in out and "/" not in out
              and ".sh" not in out, out)
        out, err, rc = run("_strain_sign.py", None,
                           ["--agent", "cleo", "--session", "sess-A10"],
                           {"STRAIN_STATE_DIR": wdir})
        check("0.5.1: the registry never lends across agents (no book for cleo)",
              rc == 0 and "no ledger" in err and "booked" not in out,
              (rc, out, err[:200]))
        # the index guard: an unreadable index refuses the rewrite
        bdir = os.path.join(tmp, "badidx")
        os.makedirs(bdir, exist_ok=True)
        with open(os.path.join(bdir, "index.json"), "w") as f:
            f.write("{corrupt")
        tick(bdir, "sess-X1", cwd="/tmp/proj-x")
        with open(os.path.join(bdir, "index.json")) as f:
            kept = f.read()
        check("an unreadable index refuses the rewrite (rows cannot evaporate)",
              kept == "{corrupt"
              and state_of(bdir, "sess-X1").get("tick") == 1, kept)

        # ---- no absolute paths baked into the shipped config ---------------------------
        hooks = os.path.join(os.path.dirname(HERE), "hooks", "hooks.json")
        with open(hooks) as f:
            raw = f.read()
        check("hooks.json hardcodes no home directory", "/Users/" not in raw and
              "/home/" not in raw, raw[:200])
        check("hooks.json goes through the plugin root", "CLAUDE_PLUGIN_ROOT" in raw)

        # ---- 0.6.0: the FEED DOOR (first cross-model field report, 2026-09-22) --------
        # A host the transcript reader cannot parse may still SHOW its numbers; the
        # agent hands them over -- sourced, typed, never dressed up as measured.
        dcal = os.path.join(tmp, "feed")
        os.makedirs(dcal, exist_ok=True)
        # 0.8.0 rewrite: every record names its model, and the product is a host strain
        # does NOT recognise -- the session below has no transcript (model unknown), the
        # one case where a lone record for an unrecognised host still applies.
        out, err, rc = run("_strain_calibrate.py", None,
                           ["--state-dir", dcal, "--product", "Example Host",
                            "--model", "example-model",
                            "--window", "258400", "--basis", "runtime",
                            "--source", "host runtime log"])
        check("0.6.0: calibrate writes a sourced, typed, dated record",
              rc == 0 and "runtime window" in out and "258,400" in out, (rc, out))
        out, err, rc = run("_strain_calibrate.py", None,
                           ["--state-dir", dcal, "--show"])
        check("0.6.0: --show reads the record back as valid",
              rc == 0 and '"valid": true' in out and '"basis": "runtime"' in out,
              out[:300])
        _, err, rc = run("_strain_calibrate.py", None,
                         ["--state-dir", dcal, "--product", "X", "--model", "m",
                          "--window", "100", "--basis", "nominal"])
        check("0.6.0: an unsourced capacity is REFUSED (stale ruler doctrine)",
              rc == 2 and "source" in err, (rc, err[:200]))
        _, err, rc = run("_strain_calibrate.py", None,
                         ["--state-dir", dcal, "--product", "X", "--model", "m",
                          "--window", "100", "--source", "s"])
        check("0.6.0: a record without nominal/runtime basis is REFUSED",
              rc == 2 and "basis" in err, (rc, err[:200]))
        # denominator flows into a tick with no env override
        tick(dcal, "sess-feed1", n=1)
        stF = state_of(dcal, "sess-feed1")
        check("0.6.0: a valid calibration record sets the tick denominator",
              (stF.get("ctx") or {}).get("limit") == 258400, stF.get("ctx"))
        out, _, rc = tick(dcal, "sess-feed1", n=1,
                          extra_env={"STRAIN_CONTEXT_LIMIT": "999000"})
        check("0.6.0: an explicit env override still beats the calibration record",
              (state_of(dcal, "sess-feed1").get("ctx") or {}).get("limit") == 999000,
              state_of(dcal, "sess-feed1").get("ctx"))
        # the fed numerator, through the recorder
        out, err, rc = run("_strain_level.py", None,
                           ["--state-dir", dcal, "--session", "sess-feed1",
                            "--ctx-used", "65749", "--ctx-source", "host runtime log"])
        stF = state_of(dcal, "sess-feed1")
        check("0.6.0: level --ctx-used computes fill against the calibrated window",
              rc == 0 and "fill 25.4%" in out and "agent-fed" in out
              and (stF.get("ctx") or {}).get("mode") == "agent-fed"
              and (stF.get("ctx") or {}).get("source") == "host runtime log",
              (rc, out, stF.get("ctx")))
        _, err, rc = run("_strain_level.py", None,
                         ["--state-dir", dcal, "--session", "sess-feed1",
                          "--ctx-used", "1000"])
        check("0.6.0: a fed reading WITHOUT a source is REFUSED",
              rc == 2 and "ctx-source" in err, (rc, err[:200]))
        out, err, rc = run("_strain_level.py", None,
                           ["Mid", "--state-dir", dcal, "--session", "sess-feed1",
                            "--ctx-used", "70000", "--ctx-source", "host runtime log"])
        stF = state_of(dcal, "sess-feed1")
        check("0.6.0: feeding and recording a tier in one call does both",
              rc == 0 and stF.get("last") == "Mid"
              and (stF.get("ctx") or {}).get("tokens") == 70000, (rc, stF))

        # ---- 0.7.0 (the internal fixes that apply, ported) ------------------------------
        import re as _re
        LVL = os.path.join(SCRIPTS, "strain-level.sh")
        SIG = os.path.join(SCRIPTS, "strain-signal.sh")
        # A1 -- the tick's record command runs from a plain shell (no $CLAUDE_PLUGIN_ROOT)
        xdir = os.path.join(tmp, "s070")
        for _ in range(10):
            out, _, _ = tick(xdir, "sess-X1")
        check("0.7.0 A1: no $CLAUDE_PLUGIN_ROOT in the tick text",
              "PROPOSED TIER" in out and "CLAUDE_PLUGIN_ROOT" not in out, out[:300])
        m = _re.search(r"record it: `([^`]+)`", out)
        cmd = m.group(1) if m else ""
        check("0.7.0 A1: the record command names this session, its state dir and the running copy",
              "STRAIN_SESSION=sess-X1" in cmd and LVL in cmd and xdir in cmd, cmd)
        check("0.7.0 A1: the signal command is runnable too", SIG in out, out[-900:])
        if cmd:
            plain = {k: v for k, v in os.environ.items()
                     if k not in ("STRAIN_STATE_DIR", "STRAIN_SESSION")}
            # 0.8.0: the tier slot also offers UNMEASURED -- fill whatever placeholder it shows
            subprocess.run(["bash", "-c", _re.sub(r"<[^>]*>", "Mid", cmd)],
                           env=plain, capture_output=True, text=True, cwd=tmp)
        check("0.7.0 A1: run from a plain shell, the printed command records into this session",
              state_of(xdir, "sess-X1").get("last") == "Mid", state_of(xdir, "sess-X1"))
        # A2 -- nothing measured and nothing else to say -> UNMEASURED, with the feed door named
        check("0.7.0 A2: an unmeasured tick proposes UNMEASURED and names the feed",
              "PROPOSED TIER: UNMEASURED" in out and "--ctx-used" in out, out[:500])
        # A6 -- wording
        check("0.7.0 A6: the header names the interval, not a count",
              "host-fired every 10 tool calls" in out and "since the last check" not in out,
              out[:200])
        check("0.7.0 A6: the bracket reads 'strain calibration:'",
              "strain calibration:" in out and "strain calibrated:" not in out, out[-400:])
        # A5 -- the boot line uses the tick's caps (one ruler per session)
        out, _, _ = start(xdir, "sess-X2")
        check("0.7.0 A5: boot line = tick caps (50/60/70/74), never the legacy bands",
              "fill caps 50/60/70/74" in out and "fill bands" not in out, out[:400])

        # A3 -- a fed reading is scored, kept, grows only by bytes after it, voided by compaction
        fdir = os.path.join(tmp, "s070f")
        ftp = os.path.join(tmp, "fed-raw.jsonl")
        with open(ftp, "w") as f:
            f.write("{}\n" * 1000)                       # 3000 bytes, no usage rows
        L = {"STRAIN_CONTEXT_LIMIT": "1000000"}
        tick(fdir, "sess-F7", n=1, transcript=ftp, extra_env=L)
        run("_strain_level.py", None, ["--session", "sess-F7", "--ctx-used", "650000",
                                        "--ctx-source", "host runtime log"],
            dict(L, STRAIN_STATE_DIR=fdir))
        out, _, _ = tick(fdir, "sess-F7", n=1, transcript=ftp, extra_env=L)
        check("0.7.0 A3: the next tick SCORES the fed value (65% -> High, not abstained)",
              "PROPOSED TIER: High" in out, out[:400])
        check("0.7.0 A3: a byte estimate does not overwrite the fed value",
              state_of(fdir, "sess-F7").get("ctx", {}).get("mode") == "agent-fed",
              state_of(fdir, "sess-F7").get("ctx"))
        with open(ftp, "a") as f:
            f.write("x" * 40000)
        tick(fdir, "sess-F7", n=1, transcript=ftp, extra_env=L)
        fctx = state_of(fdir, "sess-F7").get("ctx", {})
        check("0.7.0 A3: only bytes appended AFTER the feed are added (40000 bytes -> +10000)",
              fctx.get("mode") == "agent-fed" and fctx.get("tokens") == 660000, fctx)
        mtp = os.path.join(tmp, "fed-measured.jsonl")
        make_transcript(mtp, [(2, 300000, 0)], model="claude-opus-5")
        tick(fdir, "sess-F7", n=1, transcript=mtp, extra_env=L)
        check("0.7.0 A3: a real measured reading replaces the fed value",
              state_of(fdir, "sess-F7").get("ctx", {}).get("mode") == "measured",
              state_of(fdir, "sess-F7").get("ctx"))
        tick(fdir, "sess-F8", n=1, transcript=ftp, extra_env=L)
        run("_strain_level.py", None, ["--session", "sess-F8", "--ctx-used", "650000",
                                        "--ctx-source", "host runtime log"],
            dict(L, STRAIN_STATE_DIR=fdir))
        start(fdir, "sess-F8", source="compact")
        out, _, _ = tick(fdir, "sess-F8", n=1, transcript=ftp, extra_env=L)
        check("0.7.0 A3: a compaction after the feed voids it -> UNMEASURED",
              "PROPOSED TIER: UNMEASURED" in out, out[:400])

        # A4 -- parallel hooks never wipe the session file
        kdir = os.path.join(tmp, "s070k")
        tick(kdir, "sess-K", n=1000)
        run("_strain_signal.py", None, ["regression", "--escaped", "--session", "sess-K"],
            {"STRAIN_STATE_DIR": kdir})
        wiped, total = 0, 1
        for rnd in range(3):
            ps = [subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "_strain_tick.py"),
                                    "--n", "1000"], stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=dict(os.environ, STRAIN_STATE_DIR=kdir), text=True)
                  for _ in range(24)]
            for pr in ps:
                pr.stdin.write(json.dumps({"session_id": "sess-K", "cwd": "/tmp/proj",
                                           "hook_event_name": "PostToolUse"}))
                pr.stdin.close()
            for pr in ps:
                pr.wait()
            total += 24
            if len(state_of(kdir, "sess-K").get("signals") or []) != 1:
                wiped += 1
        check("0.7.0 A4: 72 parallel ticks keep the escaped signal (3 rounds)", wiped == 0,
              state_of(kdir, "sess-K"))
        check("0.7.0 A4: ... and lose no count", state_of(kdir, "sess-K").get("tick") == total,
              (state_of(kdir, "sess-K").get("tick"), total))

        # A7 -- a ledger that cannot be written says why
        out, err, rc = run("_strain_sign.py", None,
                           ["--agent", "zed", "--session", "sess-X1", "--ledger",
                            os.path.join(tmp, "no-such-folder", "Log.strain")],
                           {"STRAIN_STATE_DIR": xdir})
        check("0.7.0 A7: a failed ledger append names its reason",
              "does not exist" in err, (rc, out, err))

        # B2 -- a wrap writes no marker; --status shows this session's wrap
        bdir = os.path.join(tmp, "s070b")
        for _ in range(3):
            tick(bdir, "sess-W")
        run("_strain_wrap.py", None, ["--label", "phase one", "--session", "sess-W"],
            {"STRAIN_STATE_DIR": bdir})
        check("0.7.0 B2: no shared wrap-marker.json is written",
              not os.path.exists(os.path.join(bdir, "wrap-marker.json")), os.listdir(bdir))
        out, _, rc = run("_strain_wrap.py", None, ["--status", "--session", "sess-W"],
                         {"STRAIN_STATE_DIR": bdir})
        check("0.7.0 B2: --status shows this session's wrap",
              rc == 0 and '"wrapTick": 3' in out, out)
        out, _, _ = tick(bdir, "sess-W", n=1)
        check("0.7.0 B2: the tick says when this session wrapped and what ran since",
              "wrapped at" in out and "1 call since the wrap" in out, out[-700:])

        # B3 -- the sign reports the previous session of the same agent
        pdir = os.path.join(tmp, "s070p")
        pbook = os.path.join(tmp, "s070p-proj", "Log.strain")
        os.makedirs(os.path.dirname(pbook), exist_ok=True)
        out, _, _ = run("_strain_sign.py", None, ["--agent", "ana", "--session", "sess-P1",
                                                   "--ledger", pbook], {"STRAIN_STATE_DIR": pdir})
        check("0.7.0 B3: the first session of an agent says so",
              "no earlier session" in out, out)
        for _ in range(3):
            tick(pdir, "sess-P1")
        run("_strain_wrap.py", None, ["--session", "sess-P1"], {"STRAIN_STATE_DIR": pdir})
        out, _, _ = run("_strain_sign.py", None, ["--agent", "ana", "--session", "sess-P2",
                                                   "--ledger", pbook], {"STRAIN_STATE_DIR": pdir})
        check("0.7.0 B3: the next session's sign reports the previous one",
              "previous session (ana · sess-P1)" in out and "3 tool calls" in out
              and "wrapped" in out, out)
        out, _, _ = run("_strain_sign.py", None, ["--agent", "ana", "--session", "sess-P2"],
                        {"STRAIN_STATE_DIR": pdir})
        check("0.7.0 B3: a re-sign of the same session does not repeat the report",
              "previous session" not in out, out)

        # B4 -- the engine names cloud Cowork and the hostloop shape
        ctxm = tickmod.ctxmod
        saved = os.environ.get("CLAUDE_CODE_ENTRYPOINT")
        os.environ["CLAUDE_CODE_ENTRYPOINT"] = "remote_cowork"
        try:
            got = ctxm.detect_substrate(
                {"transcript_path": "/root/.claude/projects/-home-claude/x.jsonl"}, "/home/claude")
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)
            else:
                os.environ["CLAUDE_CODE_ENTRYPOINT"] = saved
        check("0.7.0 B4: CLAUDE_CODE_ENTRYPOINT=remote_cowork -> cowork-cloud", got == "cowork-cloud", got)
        got = ctxm.detect_substrate({"transcript_path": "/x/claude-hostloop-plugins/ab12/projects/"
                                                        "session/s.jsonl"}, "/private/var/empty")
        check("0.7.0 B4: the hostloop transcript shape -> cowork", got == "cowork", got)

        section_080(tmp)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(PASS) + len(FAIL)
    print("\n%d/%d checks passed" % (len(PASS), total))
    if FAIL:
        print("failed: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
