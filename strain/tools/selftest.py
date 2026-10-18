#!/usr/bin/env python3
"""Self-test for the strain driver. Host-independent: every hook is driven by feeding it
the JSON payload a host would send, in a throwaway state directory.

    python3 tools/selftest.py            run everything
    python3 tools/selftest.py -v         print each check
    python3 tools/selftest.py --only 0.10.0 --tmp <folder>   (or --only 0.11.0)
                                         0.10.0's section alone, in a new folder under <folder>; it deletes
                                         nothing and prints the folder (QA, second round)
    python3 tools/selftest.py --keep     the whole run without the final cleanup (section 0.8.3 still
                                         removes two of its own fixture files)

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
HOST_VARS = ("STRAIN_SESSION", "STRAIN_AGENT", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_ENV_FILE",
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
    run("_strain_sign.py", None, ["--decline-instructions", "--session", sg1],
        {"STRAIN_STATE_DIR": gdir})                                   # 0.8.3: prefs.json
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
            if rel in ("ledgers.json.lock", "models.json.lock", "prefs.json.lock"):
                continue
            if rel == "prefs.json":
                if not all(k in ("Claude Code", "Cowork", "Codex") and isinstance(v, dict)
                           for k, v in json.load(open(full)).items()):
                    bad.append(rel + " (an entry not keyed by its host)")
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

def section_082(tmp):
    """0.8.2: found live the night 0.8.1 shipped."""
    def dec(out):
        try:
            return json.loads(out)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return out

    # ---- a big line (a pasted screenshot) after the last usage line --------------------
    # The reader looked at the last 256 KB only; one ~256 KB line right after the newest
    # usage line pushed it out of reach, and the tick fell back to a whole-file estimate
    # (1.2M of 200k = 620%).
    rdir = os.path.join(tmp, "r082")
    sr = U(200)
    tp = cc_transcript(tmp, sr, 300000)
    with open(tp, "a") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "image", "source": {"data": "A" * 400000}}]}}) + "\n")
        f.write(json.dumps({"type": "user", "toolUseResult": "ok"}) + "\n")
    tick(rdir, sr, n=1, transcript=tp)
    c = state_of(rdir, sr).get("ctx") or {}
    check("0.8.2: a big line after the newest usage line does not hide it (reads further back)",
          c.get("mode") == "measured" and c.get("tokens") == 300002, c)

    # ---- a session that HAD a real reading never falls back to a whole-file estimate ------
    sk = U(201)
    tk = cc_transcript(tmp, sk, 300000)
    tick(rdir, sk, n=1, transcript=tk)
    with open(tk, "w") as f:                    # same log, no usage line left in it at all
        for _ in range(3000):
            f.write(json.dumps({"type": "user", "message": {"role": "user"}}) + "\n")
    out, _, _ = tick(rdir, sk, n=1, transcript=tk)
    c = state_of(rdir, sk).get("ctx") or {}
    check("0.8.2: with no usage line found, a session's last real reading is kept, and says so",
          c.get("mode") == "measured" and c.get("tokens") == 300002 and c.get("kept")
          and "kept" in dec(out), (c, dec(out)[:300]))

    # ---- refused for permission: the hint is a numbered procedure -------------------------
    pdir = os.path.join(tmp, "p082")
    sp = U(202)
    tick(pdir, sp, n=1000)
    os.chmod(os.path.join(pdir, "sessions", sp + ".json"), 0o444)
    os.chmod(os.path.join(pdir, "sessions"), 0o555)
    try:
        _, err, rc = run("_strain_level.py", None, ["Mid", "--session", sp], {"STRAIN_STATE_DIR": pdir})
    finally:
        os.chmod(os.path.join(pdir, "sessions"), 0o755)
        os.chmod(os.path.join(pdir, "sessions", sp + ".json"), 0o644)
    check("0.8.2: a record refused for permission prints numbered steps: raise the host's"
          " permission prompt, re-run once allowed, check the receipt",
          rc == 1 and "1)" in err and "2)" in err and "3)" in err and "permission prompt" in err
          and "--receipt" in err and "do not approve it yourself" in err, err)

    # ---- an unsigned session is told, once, to sign ---------------------------------------
    udir = os.path.join(tmp, "u082")
    su = U(203)
    o1, _, _ = tick(udir, su, n=1)
    o2, _, _ = tick(udir, su, n=1)
    check("0.8.2: the first strain check of an unsigned session says how to sign, once",
          "not signed" in dec(o1) and "strain-sign.sh" in dec(o1) and "not signed" not in dec(o2),
          (dec(o1)[-700:], dec(o2)[-300:]))
    sv = U(204)
    run("_strain_sign.py", None, ["--agent", "ana", "--session", sv], {"STRAIN_STATE_DIR": udir})
    o3, _, _ = tick(udir, sv, n=1)
    check("0.8.2: a signed session is not told to sign", "not signed" not in dec(o3), dec(o3)[-300:])

    # ---- agent-facing rules are steps, not principles -------------------------------------
    skill = open(os.path.join(os.path.dirname(HERE), "skills", "strain", "SKILL.md")).read()
    readme = open(os.path.join(os.path.dirname(HERE), "README.md")).read()
    check("0.8.2: no rule an agent can read as 'never ask for permission'",
          "escalat" not in skill and "escalating on your own" not in readme, "")
    check("0.8.2: SKILL carries numbered procedures for start, permission, refusal and wrap",
          all(h in skill for h in ("## At the start of a session", "## When a record command is refused",
                                   "## When the tick fires", "## At the wrap"))
          and "permission prompt" in skill, "")


def section_083(tmp):
    """0.8.3: every session signs in at the start, asks properly, and never nags. Found
    live on Codex (2026-09-30): a new session never signed, because the skill's description
    said "not for short one-pass tasks" and nothing at the start said otherwise; a
    permission prompt closed when the agent ended its turn; two sessions signed under two
    names, so the second could not find the first."""
    import re as _re
    ROOT = os.path.dirname(HERE)
    LANG = "in the user's language"

    def dec(out):
        try:
            return json.loads(out)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return out

    def boot(sdir, sid, cwd="/tmp/proj", host="claude-code", source="startup", env=None):
        payload = {"session_id": sid, "cwd": cwd, "source": source,
                   "hook_event_name": "SessionStart"}
        e = {"STRAIN_STATE_DIR": sdir, "STRAIN_SUBSTRATE": host}
        e.update(env or {})
        return dec(run("_strain_reset.py", payload, [], e)[0])

    def sign(sdir, args, env=None):
        e = {"STRAIN_STATE_DIR": sdir}
        e.update(env or {})
        return run("_strain_sign.py", None, list(args), e)

    def front(path):
        try:
            txt = open(path).read()
        except Exception:
            return "", ""
        m = _re.match(r"^---\n(.*?)\n---\n(.*)$", txt, _re.S)
        return (m.group(1), m.group(2)) if m else ("", txt)

    def flat(s):
        """A phrase check must not depend on where a markdown line happens to wrap."""
        return " ".join(s.split())

    # ---- C1 · a skill whose name and description are about the session start ------------
    fm, body = front(os.path.join(ROOT, "skills", "start", "SKILL.md"))
    fm = flat(fm)
    check("0.8.3 C1: a strain:start skill exists, triggered at the START of every session",
          "name: start" in fm and "START of every session" in fm and "short sessions too" in fm, fm)
    sfm, sbody = front(os.path.join(ROOT, "skills", "strain", "SKILL.md"))
    sfm = flat(sfm)
    check("0.8.3 C1: the strain skill no longer tells agents to skip short sessions",
          bool(sfm) and "Not for short" not in sfm and "strain:start" in sfm, sfm)

    # ---- C2 · the start line carries the start steps while unsigned ---------------------
    d = os.path.join(tmp, "c083")
    s1 = U(300)
    b1 = boot(d, s1)
    check("0.8.3 C2: an unsigned session's start line carries numbered start steps with the"
          " filled sign command",
          "not signed" in b1 and "1)" in b1 and "2)" in b1 and "3)" in b1
          and ("STRAIN_SESSION=%s" % s1) in b1 and "strain-sign.sh" in b1, b1)
    check("0.8.3 C2: the start steps say to keep the host's prompt open, and what a refusal means",
          "do not end your turn" in b1 and "Refused" in b1, b1)
    sign(d, ["--agent", "ana", "--session", s1])
    b1r = boot(d, s1, source="resume")
    check("0.8.3 C2 (guard): a signed session's start line carries no start steps",
          "not signed" not in b1r and "strain-sign.sh" not in b1r, b1r)

    # ---- C3 · the receipt says whether the session is signed ----------------------------
    s3 = U(301)
    boot(d, s3)
    _, e1, _ = sign(d, ["--receipt", "--session", s3])
    sign(d, ["--agent", "ana", "--session", s3])
    _, e2, _ = sign(d, ["--receipt", "--session", s3])
    check("0.8.3 C3: the receipt says 'not signed', then 'signed as <name>'",
          "not signed" in e1 and "signed as ana" in e2 and "not signed" not in e2, (e1, e2))

    # ---- C4 · a stable default name -----------------------------------------------------
    s4 = U(302)
    boot(d, s4, cwd="/tmp/work/my-app")
    o4, e4, r4 = sign(d, ["--session", s4])
    check("0.8.3 C4: a sign with no --agent signs as '<host> · <project folder>'",
          r4 == 0 and "Owner: Claude Code · my-app — signed" in o4
          and state_of(d, s4).get("agent") == "Claude Code · my-app", (r4, o4, e4))
    s5 = U(303)
    boot(d, s5, cwd="/private/var/empty", host="cowork")
    o5, _, r5 = sign(d, ["--session", s5])
    check("0.8.3 C4: where the folder names nothing (local Cowork), the host name alone",
          r5 == 0 and state_of(d, s5).get("agent") == "Cowork", (r5, o5))
    s6 = U(304)
    boot(d, s6, cwd="/tmp/work/my-app")
    sign(d, ["--agent", "Jo", "--session", s6])
    check("0.8.3 C4 (guard): a name the user gave wins", state_of(d, s6).get("agent") == "Jo",
          state_of(d, s6))

    # ---- C5 · after a refusal, no nagging -----------------------------------------------
    s7 = U(305)
    t7 = dec(tick(d, s7, n=1)[0])
    check("0.8.3 C5: the tick's steps say what to do after a refusal -- no records, the tier in"
          " chat", "refused" in t7 and "only report the tier in chat" in t7, t7[-900:])
    check("0.8.3 C4: the printed sign command runs as is (no name to fill in)",
          "<your name>" not in b1 and "<your name>" not in t7 and "strain-sign.sh" in t7,
          t7[-600:])

    # ---- C6 · offer the instruction file, global first; a decline is final --------------
    home = os.path.join(tmp, "home083")
    proj = os.path.join(tmp, "proj083")
    os.makedirs(home, exist_ok=True)
    os.makedirs(proj, exist_ok=True)
    HENV = {"HOME": home}
    gfile = os.path.join(home, ".claude", "CLAUDE.md")
    s8 = U(306)
    boot(d, s8, cwd=proj, env=HENV)
    o8, e8, r8 = sign(d, ["--instructions", "--session", s8], HENV)
    check("0.8.3 C6: --instructions prints the block with its version marker and says the"
          " global file lacks it",
          r8 == 0 and "<!-- strain:start-steps" in o8 and "<!-- /strain:start-steps -->" in o8
          and gfile in e8 and "absent" in e8, (r8, o8, e8))
    os.makedirs(os.path.dirname(gfile), exist_ok=True)
    with open(gfile, "w") as f:
        f.write("# mine\n\n" + o8)
    _, e9, _ = sign(d, ["--instructions", "--session", s8], HENV)
    check("0.8.3 C6: ... and finds it once it is there", "present" in e9, e9)
    b9 = boot(d, U(307), cwd=proj, env=HENV)
    os.remove(gfile)
    s10 = U(308)
    b10 = boot(d, s10, cwd=proj, env=HENV)
    check("0.8.3 C6: the start line offers the instruction file, global first, only while the"
          " block is absent", "instruction file" in b10 and gfile in b10
          and "instruction file" not in b9, (b9[-400:], b10[-700:]))
    pfile = os.path.join(proj, "CLAUDE.md")
    with open(pfile, "w") as f:
        f.write(o8)
    b10p = boot(d, U(311), cwd=proj, env=HENV)
    os.remove(pfile)
    check("0.8.3 C6: a block in the project's own file counts too",
          "instruction file" not in b10p, b10p[-400:])
    sign(d, ["--decline-instructions", "--session", s10], HENV)
    b11 = boot(d, U(309), cwd=proj, env=HENV)
    prefs = jl(os.path.join(d, "prefs.json"), {})
    check("0.8.3 C6: a decline is stored per host and the offer never comes back",
          "instruction file" not in b11
          and (prefs.get("Claude Code") or {}).get("instructions") == "declined", (b11[-400:], prefs))
    cxh = os.path.join(tmp, "codex-home083")
    CENV = {"HOME": home, "CODEX_HOME": cxh}
    s12 = U(310)
    boot(d, s12, cwd=proj, host="codex", env=CENV)
    _, e12, _ = sign(d, ["--instructions", "--session", s12], CENV)
    check("0.8.3 C6: on Codex the global file is AGENTS.md in its home",
          os.path.join(cxh, "AGENTS.md") in e12, e12)

    # ---- C7 / C8 · the docs carry the flow and its limits -------------------------------
    readme = flat(open(os.path.join(ROOT, "README.md")).read())
    check("0.8.3 C7: strain:start has numbered steps for the start AND the wrap, prompt kept open",
          "## At the start" in body and "## At the wrap" in body and "\n1. " in body
          and "keep the prompt open" in flat(body) and "do not end your turn" in flat(body),
          body[:300])
    check("0.8.3 C8: README states the start flow and the limits the host controls",
          "## Starting and wrapping a session" in readme and "keep the prompt open" in readme
          and "the host decides when its prompt closes" in readme and "never wraps" in readme, "")

    # ---- C9 · the approval box shows the agent's sentence: make it the user's ------------
    pdir = os.path.join(tmp, "p083")
    sp = U(312)
    tick(pdir, sp, n=1000)
    os.chmod(os.path.join(pdir, "sessions", sp + ".json"), 0o444)
    os.chmod(os.path.join(pdir, "sessions"), 0o555)
    try:
        _, herr, _ = run("_strain_level.py", None, ["Mid", "--session", sp], {"STRAIN_STATE_DIR": pdir})
    finally:
        os.chmod(os.path.join(pdir, "sessions"), 0o755)
        os.chmod(os.path.join(pdir, "sessions", sp + ".json"), 0o644)
    t_signed = dec(tick(d, s1, n=1)[0])
    check("0.8.3 C9: every place that has the agent run a strain command says to describe it"
          " in the user's language",
          all(LANG in flat(x) for x in (b1, t7, t_signed, herr, body, sbody)),
          [i for i, x in enumerate((b1, t7, t_signed, herr, body, sbody)) if LANG not in flat(x)])
    check("0.8.3 B2: prefs.json is keyed per host",
          bool(prefs) and all(k in ("Claude Code", "Cowork", "Codex") and isinstance(v, dict)
                              for k, v in prefs.items()), prefs)


def section_084(tmp):
    """0.8.4: strain stays out of a sub-agent's way, and an unattended run is never stopped by
    the sign-in. Found live (2026-10-08): (1) five read-only sub-agents each got the strain
    check in their tool results, asking them to run strain commands, and their tool calls
    were counted into the parent session (its count rose 190 -> 390 while they ran) -- the
    host sends a sub-agent's hook calls with the parent's session_id and an agent_id;
    (2) a headless `claude -p` run read the start steps, asked for the sign-in approval that
    nobody could give, ended its turn and did none of its task."""

    def tk(sdir, sid, agent_id=None, n=1):
        payload = {"session_id": sid, "cwd": "/tmp/proj", "hook_event_name": "PostToolUse"}
        if agent_id is not None:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "Explore"
        return run("_strain_tick.py", payload, ["--n", str(n)], {"STRAIN_STATE_DIR": sdir})

    def boot(sdir, sid, entry=None, extra=None):
        payload = {"session_id": sid, "cwd": "/tmp/proj", "source": "startup",
                   "hook_event_name": "SessionStart"}
        e = {"STRAIN_STATE_DIR": sdir, "STRAIN_SUBSTRATE": "claude-code"}
        if entry is not None:
            e["CLAUDE_CODE_ENTRYPOINT"] = entry
        e.update(extra or {})
        out = run("_strain_reset.py", payload, [], e)[0]
        try:
            return json.loads(out)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return out

    # ---- a sub-agent's tool call is neither counted nor spoken to ------------------
    sdir = os.path.join(tmp, "s084a")
    tk(sdir, "sess-P", n=100)
    before = state_of(sdir, "sess-P").get("tick")
    outs = [tk(sdir, "sess-P", agent_id="a76a31904c612ca62", n=1)[0] for _ in range(3)]
    after = state_of(sdir, "sess-P").get("tick")
    check("0.8.4 S1: a sub-agent's tool call is not counted into the parent session",
          before == 1 and after == 1, (before, after))
    check("0.8.4 S1: a sub-agent's tool call gets no strain check, even when the count is due",
          outs == ["", "", ""], outs)
    tk(sdir, "sess-Q", agent_id="a1", n=100)
    check("0.8.4 S1: a sub-agent's tool call creates no session file of its own",
          not os.path.isfile(os.path.join(sdir, "sessions", "sess-Q.json")))
    o = tk(sdir, "sess-P", agent_id="", n=1)[0]
    check("0.8.4 S1: an empty agent_id is the main session -- counted, and the check fires",
          state_of(sdir, "sess-P").get("tick") == 2 and "STRAIN TICK" in o,
          (state_of(sdir, "sess-P").get("tick"), o[:80]))

    # ---- an unattended run is not asked to sign in --------------------------------
    sdir = os.path.join(tmp, "s084b")
    head = boot(sdir, "sess-H", entry="sdk-cli")
    check("0.8.4 S2: a headless claude -p run gets no sign-in steps to wait on",
          "end your turn" not in head and "STEPS" not in head, head[:200])
    check("0.8.4 S2: the headless run is told to carry on with its task, unsigned",
          "unattended" in head and "carry on" in head, head[:200])
    check("0.8.4 S2: the headless run is still counted",
          tk(sdir, "sess-H", n=100) is not None and state_of(sdir, "sess-H").get("tick") == 1,
          state_of(sdir, "sess-H"))
    for entry in ("remote_trigger", "remote_cowork_trigger", "github-action"):
        h = boot(os.path.join(tmp, "s084c-" + entry), "sess-T", entry=entry)
        check("0.8.4 S2: %s is unattended" % entry, "unattended" in h and "STEPS" not in h, h[:120])
    for entry in ("claude-desktop", "cli", "claude-vscode", "sdk-ts", None):
        h = boot(os.path.join(tmp, "s084d-%s" % entry), "sess-I", entry=entry)
        check("0.8.4 S2: %s keeps the normal sign-in steps" % entry,
              "STRAIN START -- this session is not signed in yet" in h and "unattended" not in h,
              h[:120])
    h = boot(os.path.join(tmp, "s084e"), "sess-O", entry="claude-desktop",
             extra={"STRAIN_UNATTENDED": "1"})
    check("0.8.4 S2: STRAIN_UNATTENDED=1 marks any run unattended", "unattended" in h, h[:120])
    h = boot(os.path.join(tmp, "s084f"), "sess-O", entry="sdk-cli",
             extra={"STRAIN_UNATTENDED": "0"})
    check("0.8.4 S2: STRAIN_UNATTENDED=0 keeps the sign-in steps on a headless run",
          "STRAIN START -- this session is not signed in yet" in h, h[:120])


def section_090(tmp):
    """0.9.0: a session gets its number when it signs in, not when it wraps. Found live: two
    chats of one agent both called themselves session 8 -- each took "the highest number in
    the finished reports + 1" at its wrap, and a chat still running has no report yet. The
    number now comes from the agent's book at the sign, under one lock on the book."""
    sys.path.insert(0, SCRIPTS)
    import _strain_common as C

    def sg(agent, sid, n=None, **kw):
        r = {"type": "boot-sign", "ts": "2026-10-11T22:00:00-0700", "session": sid, "agent": agent}
        if n is not None:
            r["n"] = n
        r.update(kw)
        return r

    sn = getattr(C, "session_number", None)
    check("0.9.0 N1: session_number exists (pure: book rows in, number out)", callable(sn))
    if callable(sn):
        check("0.9.0 N2: an empty book gives session 1", sn([], "ana", "s1") == (1, "new"), sn([], "ana", "s1"))
        rows = [sg("ana", "s1", 1), sg("ana", "s2", 2), sg("bo", "t1", 9)]
        check("0.9.0 N3: the next number is the agent's highest + 1 -- another agent's rows never count",
              sn(rows, "ana", "s3") == (3, "new"), sn(rows, "ana", "s3"))
        check("0.9.0 N4: the same session signing again keeps its number (resume, re-sign)",
              sn(rows, "ana", "s1") == (1, "same"), sn(rows, "ana", "s1"))
        check("0.9.0 N5: --continue takes over the number of the session it continues",
              sn(rows, "ana", "s9", cont="s2") == (2, "continue"), sn(rows, "ana", "s9", cont="s2"))
        old = [sg("ana", "o1"), sg("ana", "o2")]
        check("0.9.0 N6: a book with older unnumbered signs and no seed gives NO number (a guess could clash)",
              sn(old, "ana", "s3") == (None, "unseeded"), sn(old, "ana", "s3"))
        seeded = old + [{"type": "seed", "ts": "2026-10-11T22:00:00-0700", "agent": "ana", "next": 67}]
        check("0.9.0 N7: a seed sets the next number", sn(seeded, "ana", "s3") == (67, "new"), sn(seeded, "ana", "s3"))
        check("0.9.0 N8: after the seed, numbers follow the highest given",
              sn(seeded + [sg("ana", "s3", 67)], "ana", "s4") == (68, "new"))

    dn = getattr(C, "duplicate_numbers", None)
    check("0.9.0 N9: duplicate_numbers exists", callable(dn))
    if callable(dn):
        clash = [sg("ana", "s1", 8), sg("ana", "s2", 8), sg("bo", "t1", 8)]
        check("0.9.0 N10: two sessions of one agent on one number are named; another agent's 8 is not a clash",
              dn(clash) == {("ana", 8): ["s1", "s2"]}, dn(clash))
        cont = [sg("ana", "s1", 8), sg("ana", "s2", 8, continues="s1"), sg("ana", "s1", 8)]
        check("0.9.0 N11: a continuing session and a re-sign are not clashes", dn(cont) == {}, dn(cont))

    # ---- the command: the number in the book row and in the receipt ----------------------
    sdir = os.path.join(tmp, "n090")
    os.makedirs(sdir, exist_ok=True)
    book = os.path.join(tmp, "n090-book", "Log.strain")
    os.makedirs(os.path.dirname(book), exist_ok=True)
    env = {"STRAIN_STATE_DIR": sdir}

    def sign(args):
        return run("_strain_sign.py", None, list(args), env)

    def rows_of(path):
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]

    o1, e1, r1 = sign(["--agent", "ana", "--session", "n-a", "--ledger", book])
    o2, e2, r2 = sign(["--agent", "ana", "--session", "n-b", "--ledger", book])
    o3, e3, r3 = sign(["--agent", "ana", "--session", "n-a", "--ledger", book])
    check("0.9.0 N12: the receipt names the number -- first session S1, second S2, the first again S1",
          r1 == r2 == r3 == 0 and "Owner: ana · S1 — signed" in o1 and "Owner: ana · S2 — signed" in o2
          and "Owner: ana · S1 — signed" in o3, (o1, o2, o3, e1))
    bk = [r for r in rows_of(book) if r.get("type") == "boot-sign"]
    check("0.9.0 N13: each boot-sign row carries its number", [r.get("n") for r in bk] == [1, 2, 1], bk)

    o4, e4, r4 = sign(["--agent", "ana", "--session", "n-c", "--ledger", book, "--continue", "n-b"])
    last = rows_of(book)[-1]
    check("0.9.0 N14: --continue books the continued number and names the session it continues",
          r4 == 0 and "Owner: ana · S2 — signed" in o4 and last.get("n") == 2 and last.get("continues") == "n-b",
          (o4, last))

    oldbook = os.path.join(tmp, "n090-old", "Log.strain")
    os.makedirs(os.path.dirname(oldbook), exist_ok=True)
    with open(oldbook, "w") as f:
        f.write(json.dumps(sg("eve", "o1")) + "\n" + json.dumps(sg("eve", "o2")) + "\n")
    o5, e5, r5 = sign(["--agent", "eve", "--session", "n-e", "--ledger", oldbook])
    check("0.9.0 N15: an unseeded old book signs without a number and says how to seed it (not on stdout)",
          r5 == 0 and " · S" not in o5 and "--seed" in e5 and "--seed" not in o5, (o5, e5))
    o6, e6, r6 = sign(["--agent", "eve", "--session", "n-f", "--ledger", oldbook, "--seed", "67"])
    o7, e7, r7 = sign(["--agent", "eve", "--session", "n-g", "--ledger", oldbook])
    check("0.9.0 N16: --seed sets the next number once; the next session follows it",
          r6 == r7 == 0 and "Owner: eve · S67 — signed" in o6 and "Owner: eve · S68 — signed" in o7, (o6, o7, e6))
    n_before = len(rows_of(oldbook))
    o8, e8, r8 = sign(["--agent", "eve", "--session", "n-h", "--ledger", oldbook, "--seed", "10"])
    check("0.9.0 N17: a seed at or below a number already given is refused, and nothing is booked",
          r8 != 0 and len(rows_of(oldbook)) == n_before and "seed" in e8, (r8, e8))

    # ---- found by the first real-data run: the number's "how" overwrote the session's -------
    import re as _re
    def via(err):   # the LAST details line -- the one printed after the book is signed
        m = _re.findall(r"details: session \S+ \(via ([^)]*)\)", err)
        return m[-1] if m else None
    _, ev1, _ = sign(["--agent", "vic", "--session", "n-v"])                    # no book anywhere
    _, ev2, _ = sign(["--agent", "wes", "--session", "n-w", "--ledger", book])  # a book, numbered
    check("0.9.0 N21: the receipt still says where the session id came from, book or no book",
          via(ev1) is not None and via(ev1) == via(ev2), (via(ev1), via(ev2)))

    # ---- the lock, proven directly: the sign must read the book INSIDE the lock ------------
    # (eight parallel signs rarely overlap in the read-to-append moment, so the race check
    # below stays green even with no lock -- seen on a copy. This one cannot.)
    import fcntl, time
    lbook = os.path.join(tmp, "n090-lock", "Log.strain")
    os.makedirs(os.path.dirname(lbook), exist_ok=True)
    open(lbook, "a").close()
    le = dict(CLEAN_ENV)
    le.update(env)
    le.setdefault("CODEX_HOME", os.path.join(tempfile.gettempdir(), "strain-selftest-no-codex"))
    holder = open(lbook, "a+")
    fcntl.flock(holder, fcntl.LOCK_EX)
    p = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "_strain_sign.py"), "--agent", "zed",
                          "--session", "lock-b", "--ledger", lbook],
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=le)
    time.sleep(1.0)
    waited = rows_of(lbook) == []
    holder.write(json.dumps(sg("zed", "lock-a", 1)) + "\n")   # another session took 1 while it waited
    holder.flush()
    fcntl.flock(holder, fcntl.LOCK_UN)
    holder.close()
    p.communicate()
    got = [r.get("n") for r in rows_of(lbook) if r.get("session") == "lock-b"]
    check("0.9.0 N20: the sign waits for the book's lock and reads the book inside it -- a number taken "
          "while it waited is seen (lock-b gets 2, not 1)", waited and got == [2], (waited, got))

    # ---- the S8 case: sessions signing at the same moment never share a number -----------
    rbook = os.path.join(tmp, "n090-race", "Log.strain")
    os.makedirs(os.path.dirname(rbook), exist_ok=True)
    e = dict(CLEAN_ENV)
    e.update(env)
    e.setdefault("CODEX_HOME", os.path.join(tempfile.gettempdir(), "strain-selftest-no-codex"))
    procs = [subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "_strain_sign.py"), "--agent", "rae",
                               "--session", "race-%d" % i, "--ledger", rbook],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e)
             for i in range(8)]
    for p in procs:
        p.communicate()
    nums = sorted(r.get("n") or 0 for r in rows_of(rbook) if r.get("type") == "boot-sign")
    check("0.9.0 N18: eight sessions signing at once get eight different numbers, 1..8",
          nums == list(range(1, 9)), nums)

    with open(rbook, "a") as f:
        f.write(json.dumps(sg("rae", "planted", 3)) + "\n")
    o9, e9, r9 = sign(["--agent", "rae", "--session", "race-0", "--ledger", rbook])
    check("0.9.0 N19: a book where two sessions share a number is named at the sign, in plain words",
          r9 == 0 and "S3" in o9 and "share" in o9 and "/" not in o9.split("share", 1)[-1].split("\n")[0], o9)


def section_0100(tmp):
    """0.10.0: a wrap's start (strain-wrap.sh --start / --cancel) and an agent's names (strain-sign.sh --aka).
    Asked for so a board can show the wrap as started, and so the name tag knows the user's other names for
    an agent. Written first, before the code.
    """
    import importlib
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    common = importlib.import_module("_strain_common")

    def rows_of(path):
        try:
            with open(path) as f:
                return [json.loads(l) for l in f if l.strip()]
        except Exception:
            return []

    def text_of(path):
        with open(path) as f:
            return f.read()

    # ---- A: the wrap's start -------------------------------------------------------------
    sdir = os.path.join(tmp, "w0100")
    book = os.path.join(tmp, "w0100-book", "Log.strain")
    os.makedirs(os.path.dirname(book), exist_ok=True)
    env = {"STRAIN_STATE_DIR": sdir}

    def sign(args):
        return run("_strain_sign.py", None, list(args), env)

    def wrap(args):
        return run("_strain_wrap.py", None, list(args), env)

    tick(sdir, "w-a")
    sign(["--agent", "ana", "--session", "w-a", "--ledger", book])
    o, e, r = wrap(["--start", "--session", "w-a"])
    st = state_of(sdir, "w-a")
    check("0.10.0 W1: --start marks the wrap's start, not its end",
          r == 0 and bool(st.get("wrapStartedAt")) and not st.get("wrappedAt") and "wrapStartTick" in st, (r, o, e, st))
    check("0.10.0 W2: --start says so in plain words, no path on stdout",
          "Owner: ana — wrap started" in o and "/" not in o, o)
    last = (rows_of(book) or [{}])[-1]
    check("0.10.0 W3: a signed session books a wrap-start row",
          last.get("type") == "wrap-start" and last.get("session") == "w-a" and last.get("agent") == "ana", last)
    o, e, r = wrap(["--status", "--session", "w-a"])
    try:
        shown = json.loads(o).get("wrapStartedAt")
    except Exception:
        shown = None
    check("0.10.0 W4: --status shows the start", r == 0 and bool(shown) and shown == st.get("wrapStartedAt"), o)
    o, e, r = wrap(["--session", "w-a"])
    st2 = state_of(sdir, "w-a")
    check("0.10.0 W5: the stamp after a start keeps the start as history",
          r == 0 and bool(st2.get("wrappedAt")) and bool(st2.get("wrapStartedAt"))
          and st2.get("wrapStartedAt") == st.get("wrapStartedAt"), st2)

    tick(sdir, "w-b")
    sign(["--agent", "ana", "--session", "w-b", "--ledger", book])
    wrap(["--start", "--session", "w-b"])
    o, e, r = wrap(["--cancel", "--session", "w-b"])
    st = state_of(sdir, "w-b")
    check("0.10.0 W6: --cancel (the user says go on) removes the start and books wrap-cancel, in plain words",
          r == 0 and "wrapStartedAt" not in st and "wrapStartTick" not in st and not st.get("wrappedAt")
          and (rows_of(book) or [{}])[-1].get("type") == "wrap-cancel" and "wrap called off" in o, (r, o, e, st))
    before, stb = text_of(book), state_of(sdir, "w-b")
    o, e, r = wrap(["--cancel", "--session", "w-b"])
    check("0.10.0 W7: --cancel with no start -> exit 2, nothing written",
          r == 2 and text_of(book) == before and state_of(sdir, "w-b") == stb, (r, o, e))
    # W8 on a session WITH a start, so a missing guard would call it off (a break stayed green on a session without one)
    wrap(["--start", "--session", "w-b"])
    before, stb = text_of(book), state_of(sdir, "w-b")
    o, e, r = wrap(["--start", "--cancel", "--session", "w-b"])
    check("0.10.0 W8: --start with --cancel -> exit 2, nothing written",
          r == 2 and text_of(book) == before and state_of(sdir, "w-b") == stb and bool(stb.get("wrapStartedAt")), (r, o, e))

    # ---- B: names, the pure resolver ----------------------------------------------------
    cn = getattr(common, "canonical_name", None)
    check("0.10.0 N1: canonical_name exists (pure: the typed name, the registry, the book's rows in -> the name out)", callable(cn))
    if callable(cn):
        reg = {"Orion": {"ledger": "/b", "aka": ["Ori", "小猎"]}, "Vega": {"ledger": "/c", "aka": ["Vee"]}}
        check("0.10.0 N2: another name resolves to its agent's one name",
              cn("小猎", reg, [])[0] == "Orion" and cn("Vee", reg, [])[0] == "Vega", (cn("小猎", reg, []), cn("Vee", reg, [])))
        check("0.10.0 N3: another name matches ignoring case", cn("ori", reg, [])[0] == "Orion", cn("ori", reg, []))
        check("0.10.0 N4: an agent's own name resolves to itself; an unknown name stays as typed, with no warning",
              cn("Orion", reg, []) == ("Orion", "") and cn("ana", reg, []) == ("ana", ""), (cn("Orion", reg, []), cn("ana", reg, [])))
        two = cn("x", {"A": {"aka": ["x"]}, "B": {"aka": ["X"]}}, [])
        check("0.10.0 N5: a name two agents claim stays as typed, with a reason -- never a guess", two[0] == "x" and bool(two[1]), two)
        check("0.10.0 N6: the book's names rows resolve too (a machine with no registry)",
              cn("小琴", {}, [{"type": "names", "agent": "Lyra", "aka": ["小琴"]}])[0] == "Lyra")

    # ---- B: names, the commands ----------------------------------------------------------
    sdir = os.path.join(tmp, "n0100")
    book = os.path.join(tmp, "n0100-book", "Log.strain")
    os.makedirs(os.path.dirname(book), exist_ok=True)
    env = {"STRAIN_STATE_DIR": sdir}

    def sign(args, e=None):
        return run("_strain_sign.py", None, list(args), e or env)

    def reg_of(d):
        try:
            with open(os.path.join(d, "ledgers.json")) as f:
                return json.load(f)
        except Exception:
            return {}

    o1, e1, r1 = sign(["--agent", "Orion", "--aka", "Ori", "--aka", "小猎", "--session", "h-1", "--ledger", book])
    names = [r for r in rows_of(book) if r.get("type") == "names"]
    check("0.10.0 N7: --aka keeps the other names in the registry and once in the book",
          r1 == 0 and sorted(reg_of(sdir).get("Orion", {}).get("aka", [])) == sorted(["Ori", "小猎"])
          and len(names) == 1 and names[0].get("agent") == "Orion" and sorted(names[0].get("aka", [])) == sorted(["Ori", "小猎"]),
          (o1, e1, reg_of(sdir), names))
    check("0.10.0 N8: the agent's own name signs as before -- no 'signed as' in the receipt",
          "Owner: Orion · S1 — signed · booked" in o1 and "signed as" not in o1, o1)
    o2, e2, r2 = sign(["--agent", "小猎", "--session", "h-2"])
    bs = [r for r in rows_of(book) if r.get("type") == "boot-sign"]
    st = state_of(sdir, "h-2")
    check("0.10.0 N9: a sign under another name gets the agent's book and next number, both names in the receipt",
          r2 == 0 and "Owner: Orion (signed as 小猎) · S2 — signed · booked" in o2, (o2, e2))
    check("0.10.0 N10: the boot-sign row and the session carry the agent's name, and the typed one beside it",
          bs and bs[-1].get("agent") == "Orion" and bs[-1].get("as") == "小猎" and bs[-1].get("n") == 2
          and st.get("agent") == "Orion" and st.get("signedAs") == "小猎", (bs[-1:], st.get("agent"), st.get("signedAs")))
    check("0.10.0 N17: a sign without --aka keeps the other names the registry holds",
          sorted(reg_of(sdir).get("Orion", {}).get("aka", [])) == sorted(["Ori", "小猎"]), reg_of(sdir).get("Orion"))
    check("0.10.0 N11: the previous-session report reads the agent's chain under its one name",
          "previous session (Orion · h-1" in o2, o2)
    sign(["--agent", "Orion", "--aka", "ori", "--session", "h-1"])
    check("0.10.0 N12: declaring a name already kept (any case) adds no second names row",
          len([r for r in rows_of(book) if r.get("type") == "names"]) == 1, [r for r in rows_of(book) if r.get("type") == "names"])

    bbook = os.path.join(tmp, "n0100-bbook", "Log.strain")
    os.makedirs(os.path.dirname(bbook), exist_ok=True)
    sign(["--agent", "Vega", "--aka", "Vee", "--session", "b-1", "--ledger", bbook])
    before = reg_of(sdir).get("Orion", {}).get("aka", [])
    o3, e3, r3 = sign(["--agent", "Orion", "--aka", "Vega", "--aka", "vee", "--session", "h-1"])
    check("0.10.0 N13: another agent's name, or another agent's other name, is refused with a reason and not kept",
          r3 == 0 and sorted(reg_of(sdir).get("Orion", {}).get("aka", [])) == sorted(before)
          and "Vega" in e3 and "vee" in e3, (e3, reg_of(sdir).get("Orion")))

    tdir = os.path.join(tmp, "n0100-two")
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, "ledgers.json"), "w") as f:
        json.dump({"A": {"ledger": "", "aka": ["x"]}, "B": {"ledger": "", "aka": ["x"]}}, f)
    o4, e4, r4 = sign(["--agent", "x", "--session", "t-1"], {"STRAIN_STATE_DIR": tdir})
    check("0.10.0 N14: a name two agents claim signs as typed, with a warning for the agent (stderr)",
          r4 == 0 and "Owner: x — signed" in o4 and "signed as" not in o4 and "A" in e4 and "B" in e4, (o4, e4))

    o5, e5, r5 = run("_strain_wrap.py", None, ["--agent", "小猎", "--session", "h-2"], env)
    wr = [r for r in rows_of(book) if r.get("type") == "wrap"]
    check("0.10.0 N15: a wrap under another name books the agent's one name",
          r5 == 0 and wr and wr[-1].get("agent") == "Orion" and "Owner: Orion" in o5, (o5, wr[-1:]))

    fdir = os.path.join(tmp, "n0100-fresh")
    o6, e6, r6 = sign(["--agent", "小猎", "--session", "h-9", "--ledger", book], {"STRAIN_STATE_DIR": fdir})
    check("0.10.0 N16: with --ledger on a machine with no registry, the book's names row resolves the name",
          r6 == 0 and "Owner: Orion (signed as 小猎) · S3 — signed · booked" in o6, (o6, e6))

    # ---- QA, first round (written first) ----------------
    o7, e7, r7 = sign(["--agent", "小猎", "--session", "h-10"], {"STRAIN_STATE_DIR": fdir})
    check("0.10.0 N18 (F2): the names recovered from the book are kept in the registry - a second fresh session with no --ledger still resolves",
          r7 == 0 and "Owner: Orion (signed as 小猎) · S4 — signed · booked" in o7, (o7, e7))
    if callable(cn):
        reg = {"Vega": {"ledger": "/c", "aka": ["Vee"]}, "Other": {"ledger": "/o", "aka": ["VEGA"]}}
        check("0.10.0 N19 (F1): an agent's own name matches ignoring case, and before any other name",
              cn("vega", reg, [])[0] == "Vega" and cn("VEGA", reg, [])[0] == "Vega",
              (cn("vega", reg, []), cn("VEGA", reg, [])))
        two = cn("ANA", {"ana": {"ledger": ""}, "Ana": {"ledger": ""}}, [])
        check("0.10.0 N20 (F1): a name that matches two agents' own names by case stays as typed, with a reason; the exact one still resolves",
              two[0] == "ANA" and bool(two[1]) and cn("Ana", {"ana": {}, "Ana": {}}, []) == ("Ana", ""), two)
    dn = getattr(common, "declare_names", None)
    check("0.10.0 N21 (F3): declare_names exists - the claim check and the save under one registry lock", callable(dn))
    if callable(dn):
        cdir = os.path.join(tmp, "n0100-claims")
        os.makedirs(cdir, exist_ok=True)
        with open(os.path.join(cdir, "ledgers.json"), "w") as f:
            json.dump({"B": {"ledger": "", "aka": ["x"]}}, f)
        kept, refused, ok = dn(cdir, "A", "", ["x", "y"], [])
        reg = reg_of(cdir)
        check("0.10.0 N22 (F3): a name another agent holds in the registry on disk is refused at the save; the free one is kept",
              ok and kept == ["y"] and [n for n, _ in refused] == ["x"] and reg.get("A", {}).get("aka") == ["y"]
              and reg.get("B", {}).get("aka") == ["x"], (kept, refused, ok, reg))

    # QA, second round: a registry that cannot be written loses the names - the sign says so (stderr), still books
    xdir = os.path.join(tmp, "n0100-unwritable")
    os.makedirs(os.path.join(xdir, "ledgers.json"), exist_ok=True)      # a folder where the registry file should be
    xbook = os.path.join(tmp, "n0100-xbook", "Log.strain")
    os.makedirs(os.path.dirname(xbook), exist_ok=True)
    o8, e8, r8 = sign(["--agent", "Ana", "--aka", "Annie", "--session", "x-1", "--ledger", xbook], {"STRAIN_STATE_DIR": xdir})
    check("0.10.0 N23: a registry that cannot be written - the other names are reported as not kept; the sign still books",
          r8 == 0 and "not kept" in e8 and "Owner: Ana · S1 — signed · booked" in o8, (o8, e8))


def section_0110(tmp):
    """0.11.0: a line from an optional lines file, printed once when the fill crosses it, and a backup mark
    (strain-wrap.sh --backup). Asked for so that an agent is told at a fill line by the program, not by a
    person; the words are the user's own file, strain only prints them. Written first, before the code.
    """
    import importlib
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    try:
        lines = importlib.import_module("_strain_lines")
    except Exception:
        lines = None
    check("0.11.0 L0: the lines module exists (_strain_lines.py)", lines is not None)

    SAY50 = "fifty: save a checkpoint"
    SAY70 = "seventy: begin the hand-off"
    GOOD = {"strain_lines": 1, "lines": [{"at": 70, "say": SAY70, "mark": "wrap-start"},
                                         {"at": 50, "say": SAY50, "mark": "backup"}]}
    LIM = {"STRAIN_CONTEXT_LIMIT": "100000"}

    def write(path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))
        return path

    def fill(path, tokens):
        make_transcript(path, [(2, 10000, 0), (2, tokens, 0)])
        return path

    def said(out):
        try:
            return json.loads(out)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return ""

    def rows_of(path):
        try:
            with open(path) as f:
                return [json.loads(l) for l in f if l.strip()]
        except Exception:
            return []

    def as_list(x):          # a wrong answer must FAIL a check, not abort the section
        return list(x) if isinstance(x, (list, tuple)) else ["<not a list: %r>" % (x,)]

    def at_of(x):
        return x.get("at") if isinstance(x, dict) else None

    def pair(r):
        return tuple(r) if isinstance(r, (list, tuple)) and len(r) == 2 else (None, None)

    def load(path):
        try:
            return pair(lines.load_lines(path))
        except Exception as ex:
            return ("<raised %s>" % ex.__class__.__name__, None)

    # ---- L · the pure module -------------------------------------------------------------
    d = os.path.join(tmp, "l0110")
    os.makedirs(d, exist_ok=True)
    good = write(os.path.join(d, "good.json"), GOOD)
    if lines is not None:
        check("0.11.0 L1: STRAIN_LINES names the file",
              lines.lines_path(d, {"STRAIN_LINES": "/x/y.json"}) == "/x/y.json",
              lines.lines_path(d, {"STRAIN_LINES": "/x/y.json"}))
        check("0.11.0 L2: else the state folder's lines.json",
              lines.lines_path(d, {}) == os.path.join(d, "lines.json"), lines.lines_path(d, {}))
        got, why = pair(lines.load_lines(os.path.join(d, "absent.json")))
        check("0.11.0 L3: no file -> no lines and nothing to say", got == [] and why is None, (got, why))
        got, why = pair(lines.load_lines(good))
        gl = [g for g in as_list(got) if isinstance(g, dict)]
        check("0.11.0 L4: a good file -> its lines, lowest first, with their marks",
              why is None and [at_of(g) for g in gl] == [50, 70] and gl[0].get("say") == SAY50
              and gl[0].get("mark") == "backup" and gl[1].get("mark") == "wrap-start", (got, why))
        one = {"at": 50, "say": SAY50}
        bad = [("not JSON", "{"),
               ("not an object", [1]),
               ("no version", {"lines": [one]}),
               ("another version", {"strain_lines": 2, "lines": [one]}),
               ("no lines", {"strain_lines": 1}),
               ("an empty list", {"strain_lines": 1, "lines": []}),
               ("at 0", {"strain_lines": 1, "lines": [dict(one, at=0)]}),
               ("at over 100", {"strain_lines": 1, "lines": [dict(one, at=101)]}),
               ("at as text", {"strain_lines": 1, "lines": [dict(one, at="50")]}),
               ("at as true", {"strain_lines": 1, "lines": [dict(one, at=True)]}),
               ("the same at twice", {"strain_lines": 1, "lines": [one, dict(one, say="again")]}),
               ("an empty say", {"strain_lines": 1, "lines": [dict(one, say="  ")]}),
               ("a say over two lines", {"strain_lines": 1, "lines": [dict(one, say="a\nb")]}),
               ("a say over 300 characters", {"strain_lines": 1, "lines": [dict(one, say="x" * 301)]}),
               ("a say that is not text", {"strain_lines": 1, "lines": [dict(one, say=5)]}),
               ("an unknown mark", {"strain_lines": 1, "lines": [dict(one, mark="nap")]}),
               ("a mark that is a list (QA round 1, F1)", {"strain_lines": 1, "lines": [dict(one, mark=[])]}),
               ("a mark that is an object (QA round 1, F1)", {"strain_lines": 1, "lines": [dict(one, mark={})]}),
               ("a line that is not an object", {"strain_lines": 1, "lines": ["50"]})]
        for i, (name, obj) in enumerate(bad):
            got, why = load(write(os.path.join(d, "bad-%02d.json" % i), obj))
            check("0.11.0 L5: an unusable file (%s) -> no lines, and a reason" % name,
                  got == [] and isinstance(why, str) and bool(why.strip()), (got, why))
        link = os.path.join(d, "dangling.json")
        os.symlink(os.path.join(d, "gone.json"), link)
        got, why = pair(lines.load_lines(link))
        check("0.11.0 L6: a link to a file that is gone is set up but unreadable -> no lines, and a reason",
              got == [] and isinstance(why, str) and bool(why.strip()), (got, why))
        # the lines as the module should return them -- built here, so these checks do not ride on L4
        L = [{"at": 50, "say": SAY50, "mark": "backup"}, {"at": 70, "say": SAY70, "mark": "wrap-start"}]
        due = lines.due_line
        r = pair(due(L, 49.9, {}))
        check("0.11.0 L7: below every line -> nothing due", r[0] is None and as_list(r[1]) == [], r)
        r = pair(due(L, 50.0, {}))
        check("0.11.0 L8: at the line -> that line, and it is now passed",
              at_of(r[0]) == 50 and as_list(r[1]) == [50], r)
        r = pair(due(L, 55.0, {"50": {}}))
        check("0.11.0 L9: a passed line is not due again", r[0] is None and as_list(r[1]) == [], r)
        r = pair(due(L, 70.5, {"50": {}}))
        check("0.11.0 L10: the next line when its turn comes", at_of(r[0]) == 70 and as_list(r[1]) == [70], r)
        r = pair(due(L, 75.0, {}))
        check("0.11.0 L11: a jump past both -> the highest line only, both passed",
              at_of(r[0]) == 70 and sorted(as_list(r[1]), key=str) == [50, 70], r)
        r = pair(due(L, None, {}))
        check("0.11.0 L12: no trusted fill -> nothing due, nothing passed", r[0] is None and as_list(r[1]) == [], r)
        # QA round 1, F2: a key keeps distinct values distinct; the same value written two ways is one key
        near = {"strain_lines": 1, "lines": [{"at": 50, "say": SAY50}, {"at": 50.00001, "say": "a hair later"}]}
        got, why = load(write(os.path.join(d, "near.json"), near))
        check("0.11.0 L13: 50 and 50.00001 are two lines (QA round 1, F2)",
              why is None and len(as_list(got)) == 2, (got, why))
        ks = [lines.key(50), lines.key(50.0), lines.key(52.5), lines.key(50.00001), lines.key(50.0000001)]
        check("0.11.0 L14: keys - 50 and 50.0 are one, 50.00001 and 50.0000001 their own",
              ks[0] == ks[1] == "50" and ks[2] == "52.5" and len(set(ks)) == 4, ks)
        NL = [{"at": 50, "say": SAY50}, {"at": 50.00001, "say": "a hair later"}]
        r1 = pair(due(NL, 50.000005, {lines.key(50): {}}))
        r2 = pair(due(NL, 50.00002, {lines.key(50): {}}))
        check("0.11.0 L15: the nearer line waits for its own crossing",
              r1[0] is None and at_of(r2[0]) == 50.00001, (r1, r2))

    # ---- T · the hook, on Claude Code ------------------------------------------------------
    sdir = os.path.join(tmp, "t0110")
    write(os.path.join(sdir, "lines.json"), GOOD)          # the default place
    tr = os.path.join(tmp, "t0110-a.jsonl")
    o1, _, _ = tick(sdir, "c-a", n=10, transcript=fill(tr, 40000), extra_env=LIM)
    check("0.11.0 T1: below the line a quiet call stays quiet", o1 == "", o1[:300])
    o2, _, _ = tick(sdir, "c-a", n=10, transcript=fill(tr, 52000), extra_env=LIM)
    c2 = said(o2)
    check("0.11.0 T2: the call that crosses prints the line at once, as context for the agent (not the 10th call)",
          SAY50 in c2 and SAY70 not in c2 and '"hookEventName": "PostToolUse"' in o2, o2[:400])
    check("0.11.0 T3: and the exact command that records its mark, for this session",
          "strain-wrap.sh --backup" in c2 and "STRAIN_SESSION=c-a" in c2, c2[:400])
    check("0.11.0 T3b: the user's words end before strain's step, even with no full stop (found in a real run)",
          (SAY50 + " -- once it is done, record it: `") in c2, c2[:400])
    check("0.11.0 T4: the user is not shown it (no systemMessage)", "systemMessage" not in o2, o2[:300])
    o3, _, _ = tick(sdir, "c-a", n=10, transcript=fill(tr, 53000), extra_env=LIM)
    check("0.11.0 T5: printed once", o3 == "", o3[:300])
    st = state_of(sdir, "c-a")
    cr = (st.get("crossed") or {}).get("50") or {}
    check("0.11.0 T6: the session remembers the line: said, at which fill and call",
          cr.get("said") is True and abs(float(cr.get("pct") or 0) - 52.0) < 0.1 and cr.get("tick") == 2
          and bool(cr.get("ts")), st.get("crossed"))
    o4, _, _ = tick(sdir, "c-a", n=10, transcript=fill(tr, 71000), extra_env=LIM)
    c4 = said(o4)
    check("0.11.0 T7: the 70 line, with the command that marks a wrap's start",
          SAY70 in c4 and SAY50 not in c4 and "strain-wrap.sh --start" in c4, c4[:400])
    tick(sdir, "c-a", n=10, transcript=fill(tr, 20000), extra_env=LIM)
    st = state_of(sdir, "c-a")
    check("0.11.0 T8: the peak fill is kept when the fill falls",
          abs(float(st.get("peakPct") or 0) - 71.0) < 0.1 and bool(st.get("peakAt")), (st.get("peakPct"), st.get("peakAt")))
    o5, _, _ = tick(sdir, "c-a", n=10, transcript=fill(tr, 72000), extra_env=LIM)
    check("0.11.0 T9: a fall and a rise do not print again", o5 == "", o5[:300])

    tr2 = os.path.join(tmp, "t0110-b.jsonl")
    tick(sdir, "c-b", n=10, transcript=fill(tr2, 45000), extra_env=LIM)
    o6, _, _ = tick(sdir, "c-b", n=10, transcript=fill(tr2, 75000), extra_env=LIM)
    c6 = said(o6)
    check("0.11.0 T10: a jump past both prints the 70 line only", SAY70 in c6 and SAY50 not in c6, c6[:400])
    cr = state_of(sdir, "c-b").get("crossed") or {}
    check("0.11.0 T11: the 50 line is remembered as jumped, the 70 line as said",
          (cr.get("50") or {}).get("said") is False and (cr.get("70") or {}).get("said") is True, cr)

    tr3 = os.path.join(tmp, "t0110-c.jsonl")
    tick(sdir, "c-c", n=2, transcript=fill(tr3, 40000), extra_env=LIM)
    o7, _, _ = tick(sdir, "c-c", n=2, transcript=fill(tr3, 52000), extra_env=LIM)
    c7 = said(o7)
    check("0.11.0 T12: on a regular tick the line comes first, then the tick",
          SAY50 in c7 and "STRAIN TICK" in c7 and c7.find(SAY50) < c7.find("STRAIN TICK"), c7[:400])

    sdir0 = os.path.join(tmp, "t0110-none")
    tr4 = os.path.join(tmp, "t0110-d.jsonl")
    tick(sdir0, "c-d", n=10, transcript=fill(tr4, 40000), extra_env=LIM)
    o8, _, _ = tick(sdir0, "c-d", n=10, transcript=fill(tr4, 52000), extra_env=LIM)
    o9, _, _ = tick(sdir0, "c-d", n=1, transcript=fill(tr4, 53000), extra_env=LIM)
    check("0.11.0 T13: no lines file -> the crossing call is quiet and the tick names no line or file (as 0.10.0)",
          o8 == "" and "STRAIN LINE" not in o9 and "lines file" not in o9 and "STRAIN TICK" in o9, (o8[:200], o9[:300]))

    sdirb = os.path.join(tmp, "t0110-bad")
    badp = write(os.path.join(sdirb, "lines.json"), "{")
    tr5 = os.path.join(tmp, "t0110-e.jsonl")
    tick(sdirb, "c-e", n=10, transcript=fill(tr5, 40000), extra_env=LIM)
    oa, _, _ = tick(sdirb, "c-e", n=10, transcript=fill(tr5, 52000), extra_env=LIM)
    ob, _, _ = tick(sdirb, "c-e", n=1, transcript=fill(tr5, 53000), extra_env=LIM)
    oc, _, _ = tick(sdirb, "c-e", n=1, transcript=fill(tr5, 54000), extra_env=LIM)
    check("0.11.0 T14: an unusable file prints no line, and the next regular tick says so, naming the file",
          oa == "" and "lines file" in said(ob) and badp in said(ob) and "STRAIN LINE" not in said(ob), (oa[:200], said(ob)[:500]))
    check("0.11.0 T15: ... once per session", "lines file" not in said(oc) and "STRAIN TICK" in said(oc), said(oc)[:300])

    tr6 = fill(os.path.join(tmp, "t0110-f.jsonl"), 52000)
    e = {"STRAIN_STATE_DIR": sdir}
    e.update(LIM)
    of, _, _ = run("_strain_tick.py", {"session_id": "c-f", "cwd": "/tmp/proj", "hook_event_name": "PostToolUse",
                                       "transcript_path": tr6, "agent_id": "sub-1"}, ["--n", "10"], e)
    check("0.11.0 T16: a sub-agent's call prints nothing and records nothing",
          of == "" and not state_of(sdir, "c-f").get("crossed"), of[:200])

    elsewhere = write(os.path.join(tmp, "t0110-elsewhere", "group.json"), GOOD)
    sdire = os.path.join(tmp, "t0110-env")
    tr7 = os.path.join(tmp, "t0110-g.jsonl")
    env7 = dict(LIM, STRAIN_LINES=elsewhere)
    tick(sdire, "c-g", n=10, transcript=fill(tr7, 40000), extra_env=env7)
    og, _, _ = tick(sdire, "c-g", n=10, transcript=fill(tr7, 52000), extra_env=env7)
    check("0.11.0 T17: STRAIN_LINES points at a file outside the state folder", SAY50 in said(og), og[:300])

    sdirw = os.path.join(tmp, "t0110-ro")
    write(os.path.join(sdirw, "lines.json"), GOOD)
    tr8 = os.path.join(tmp, "t0110-h.jsonl")
    tick(sdirw, "c-h", n=1000, transcript=fill(tr8, 40000), extra_env=LIM)
    sess = os.path.join(sdirw, "sessions")
    os.chmod(sess, 0o555)
    os.chmod(os.path.join(sess, "c-h.json"), 0o444)
    try:
        oh, _, _ = tick(sdirw, "c-h", n=1000, transcript=fill(tr8, 52000), extra_env=LIM)
    finally:
        os.chmod(sess, 0o755)
        os.chmod(os.path.join(sess, "c-h.json"), 0o644)
    oi, _, _ = tick(sdirw, "c-h", n=1000, transcript=fill(tr8, 52500), extra_env=LIM)
    check("0.11.0 T18: a reading that cannot be saved holds the line back; the next saved call prints it",
          SAY50 not in oh and SAY50 in said(oi), (oh[:300], oi[:300]))

    # QA round 1, F1: a mark of [] or {} must not cost the tick its save or its directive
    for i, bad_mark in enumerate(([], {})):
        sdm = os.path.join(tmp, "t0110-mark-%d" % i)
        mp = write(os.path.join(sdm, "lines.json"), {"strain_lines": 1, "lines": [{"at": 50, "say": SAY50, "mark": bad_mark}]})
        trm = os.path.join(tmp, "t0110-mark-%d.jsonl" % i)
        q1, _, _ = tick(sdm, "c-m%d" % i, n=10, transcript=fill(trm, 52000), extra_env=LIM)
        q2, _, _ = tick(sdm, "c-m%d" % i, n=1, transcript=fill(trm, 53000), extra_env=LIM)
        stm = state_of(sdm, "c-m%d" % i)
        check("0.11.0 T19: a mark of %s - the calls are still saved, the tick still comes, with the one note (QA round 1, F1)"
              % json.dumps(bad_mark),
              stm.get("tick") == 2 and q1 == "" and "STRAIN TICK" in said(q2) and "lines file" in said(q2) and mp in said(q2)
              and "mark" in said(q2), (stm.get("tick"), q1[:200], said(q2)[:400]))

    # QA round 1: any failure in the lines step becomes the note -- never a lost save (in-process, the step alone)
    import importlib as _il
    tickmod = _il.import_module("_strain_tick")
    real = tickmod.linesmod.load_lines
    def boom(path):
        raise RuntimeError("test")
    tickmod.linesmod.load_lines = boom
    try:
        stg = {"sid": "g-1", "tick": 3}
        try:
            got = tickmod.crossing_line(stg, 52.0, os.path.join(tmp, "t0110-guard"), {})
            raised = None
        except Exception as ex:
            got, raised = None, ex.__class__.__name__
    finally:
        tickmod.linesmod.load_lines = real
    prob = stg.get("_linesProblem") or ("", "")
    check("0.11.0 T20: an exception in the lines step returns no line and leaves the note's reason",
          raised is None and got == "" and "RuntimeError" in str(prob[1]), (raised, got, stg))

    # QA round 1, F3: the peak is compared on the reading itself, not on a rounded copy
    stp = {"sid": "p-1", "tick": 1}
    tickmod.crossing_line(stp, 71.04, os.path.join(tmp, "t0110-peak"), {})
    stp["peakAt"] = "first"
    tickmod.crossing_line(stp, 71.02, os.path.join(tmp, "t0110-peak"), {})
    check("0.11.0 T21: a slightly lower reading does not move the peak (QA round 1, F3)",
          stp.get("peakPct") == 71.04 and stp.get("peakAt") == "first", stp)

    # ---- X · the hook, on Codex ------------------------------------------------------------
    sdirx = os.path.join(tmp, "x0110")
    write(os.path.join(sdirx, "lines.json"), GOOD)
    sx = U(110)
    p1, home = rollout(tmp, sx, [("model", "gpt-x-test"), ("usage", 100000, 0, 258400)])
    CX = {"CODEX_HOME": home}
    ox1, _, _ = tick(sdirx, sx, n=10, transcript=p1, extra_env=CX)
    p2, _ = rollout(tmp, sx, [("model", "gpt-x-test"), ("usage", 100000, 0, 258400), ("usage", 135000, 0, 258400)])
    ox2, _, _ = tick(sdirx, sx, n=10, transcript=p2, extra_env=CX)
    check("0.11.0 X1: on Codex, quiet below the line and the line at the crossing (135000 of 258400 = 52.2%)",
          ox1 == "" and SAY50 in said(ox2) and state_of(sdirx, sx).get("substrate") == "codex", (ox1[:200], ox2[:300]))

    # ---- B · the backup mark ---------------------------------------------------------------
    wdir = os.path.join(tmp, "b0110")
    book = os.path.join(tmp, "b0110-book", "Log.strain")
    os.makedirs(os.path.dirname(book), exist_ok=True)
    wenv = {"STRAIN_STATE_DIR": wdir}
    wenv.update(LIM)

    def wrap(args):
        return run("_strain_wrap.py", None, list(args), wenv)

    trb = os.path.join(tmp, "b0110.jsonl")
    tick(wdir, "b-a", n=1000, transcript=fill(trb, 52000), extra_env=LIM)
    run("_strain_sign.py", None, ["--agent", "ana", "--session", "b-a", "--ledger", book], wenv)
    o, e, r = wrap(["--backup", "--session", "b-a"])
    st = state_of(wdir, "b-a")
    bk = st.get("backups") or []
    check("0.11.0 B1: --backup records a backup with its fill and call, and is not a wrap",
          r == 0 and len(bk) == 1 and abs(float(bk[0].get("pct") or 0) - 52.0) < 0.1 and bk[0].get("tick") == 1
          and bool(bk[0].get("ts")) and not st.get("wrappedAt") and not st.get("wrapStartedAt"), (r, o, e, st))
    check("0.11.0 B2: it says so in plain words, no path on stdout", "Owner: ana — backup marked" in o and "/" not in o, o)
    last = (rows_of(book) or [{}])[-1]
    check("0.11.0 B3: a signed session books a backup row",
          last.get("type") == "backup" and last.get("session") == "b-a" and last.get("agent") == "ana"
          and abs(float(last.get("pct") or 0) - 52.0) < 0.1, last)
    check("0.11.0 B4: a backup is not a signal (signals are errors)", not st.get("signals"), st.get("signals"))
    before_st, before_book = json.dumps(state_of(wdir, "b-a"), sort_keys=True), rows_of(book)
    for combo in (["--start"], ["--cancel"], ["--with-debt"]):
        o, e, r = wrap(["--backup"] + combo + ["--session", "b-a"])
        check("0.11.0 B5: --backup with %s is refused, nothing written" % combo[0],
              r == 2 and json.dumps(state_of(wdir, "b-a"), sort_keys=True) == before_st and rows_of(book) == before_book,
              (r, o, e))
    o, e, r = wrap(["--backup", "--label", "phase two", "--session", "b-a"])
    bk = state_of(wdir, "b-a").get("backups") or []
    check("0.11.0 B6: a second backup keeps the first, and carries its label",
          r == 0 and len(bk) == 2 and bk[1].get("label") == "phase two" and (rows_of(book) or [{}])[-1].get("label") == "phase two",
          (r, o, e, bk))
    o, e, r = wrap(["--status", "--session", "b-a"])
    try:
        stat = json.loads(o)
    except Exception:
        stat = {}
    check("0.11.0 B7: --status shows the backups and the lines passed",
          r == 0 and stat.get("backups") == 2 and bool(stat.get("lastBackupAt")) and "crossed" in stat, o)


def _arg(flag):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv and sys.argv.index(flag) + 1 < len(sys.argv) else None


def main():
    only, base = _arg("--only"), _arg("--tmp")
    tmp = tempfile.mkdtemp(prefix="strain-selftest-", dir=base)
    if only is not None:
        # QA, second round: one section, nothing deleted (section 0.10.0 removes no file; the scripts it runs
        # write by temp file + rename), the folder named for the caller
        sections = {"0.10.0": section_0100, "0.11.0": section_0110}
        if only not in sections:
            print("--only knows %s only" % " and ".join(sorted(sections)))
            return 2
        sections[only](tmp)
        print("kept: " + tmp)
        print("\n%d/%d checks passed (section %s only)" % (len(PASS), len(PASS) + len(FAIL), only))
        if FAIL:
            print("failed: " + ", ".join(FAIL))
            return 1
        return 0
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

        def pt(fill, mode="measured", escaped=0, compactions=0, env=None, at=None):
            old = {}
            for kk, vv in (env or {}).items():
                old[kk] = os.environ.get(kk)
                os.environ[kk] = vv
            try:
                stx = {"compactions": compactions,
                       "signals": [dict({"kind": "k%d" % i, "escaped": True},
                                        **({"pct": at[i]} if at else {}))
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

        # ---- 0.8.5 Line B: only escaped errors made past 50% fill count ----------------
        # The owner's ruling (2026-10-09): errors before 50% fill are recorded, never tiered;
        # five made past 50% are High, and Danger once the fill is at 70%.
        t_, b_, d_ = pt(55.0, escaped=5, at=[51, 52, 53, 54, 55])
        check("0.8.5 B1: fill 55 + 5 escaped made past 50% -> High (Line B High)",
              t_ == "High" and "Line B High" in b_, (t_, b_))
        t_, b_, d_ = pt(72.0, escaped=5, at=[55, 60, 65, 70, 72])
        check("0.8.5 B2: fill 72 + 5 escaped made past 50% -> Danger (Line B Danger)",
              t_ == "Danger" and "Line B Danger" in b_, (t_, b_))
        t_, b_, d_ = pt(55.0, escaped=6, at=[10, 20, 30, 40, 45, 49.9])
        check("0.8.5 B3: six escaped all made before 50% move nothing (tier = Line A Mid)",
              t_ == "Mid" and "Line B Healthy" in b_, (t_, b_))
        t_, b_, d_ = pt(60.0, escaped=7, at=[20, 30, 40, 51, 52, 53, 54])
        check("0.8.5 B4: four past 50% (+3 before) stay under five -> Line B quiet",
              "Line B Healthy" in b_ and "after 50%: 4" in b_, (t_, b_))
        t_, b_, d_ = pt(72.0, escaped=3, at=[60, 65, 70])
        check("0.8.5 B5: the old composite is gone -- fill 72 + 3 escaped = Warning, not Danger",
              t_ == "Warning" and "composite" not in b_, (t_, b_))
        t_, b_, d_ = pt(55.0, escaped=5)
        check("0.8.5 B6: escaped signals with no recorded fill (made before 0.8.5) are not counted",
              t_ == "Mid" and "Line B Healthy" in b_, (t_, b_))
        t_, b_, d_ = pt(None, mode="inferred", escaped=3)
        check("0.8.5 B7: fill not measurable -> today's ladder stays (3 escaped -> Mid), said so",
              t_ == "Mid" and "fill unknown" in b_, (t_, b_))
        t_, b_, d_ = pt(None, mode="inferred", escaped=5)
        check("0.8.5 B8: fill not measurable, 5 escaped -> Warning (today's ladder)",
              t_ == "Warning", (t_, b_))
        t_, b_, d_ = pt(50.0, escaped=5, at=[50.0, 50.0, 50.0, 50.0, 50.0])
        check("0.8.5 B9: errors made at exactly 50% count (the line is inclusive)",
              t_ == "High" and "Line B High" in b_, (t_, b_))
        t_, b_, d_ = pt(70.0, escaped=5, at=[55, 60, 65, 68, 70])
        check("0.8.5 B10: five past 50% with the fill at exactly 70% -> Danger",
              t_ == "Danger" and "Line B Danger" in b_, (t_, b_))
        stc = {"signals": [{"kind": "c%d" % i, "escaped": False, "pct": 60.0} for i in range(6)]}
        t_, b_, d_ = tickmod.propose_tier(stc, {"mode": "measured", "pct": 60.0, "limit": 200000})
        check("0.8.5 B11: caught errors past 50% never count (six caught -> Line B quiet)",
              "Line B Healthy" in b_ and "after 50%: 0" in b_, (t_, b_))

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

        # ---- escaped signals carry the fill they were made at; below 50% they are kept,
        # never tiered (0.8.5, the owner's ruling of 2026-10-09) -----------------------
        gdir = os.path.join(tmp, "s9")
        tick(gdir, "sess-P", n=0, transcript=npath)          # 33% fill on a 1M window
        out, _, rc = run("_strain_signal.py", None,
                         ["regression", "--escaped", "--session", "sess-P"],
                         {"STRAIN_STATE_DIR": gdir})
        sig0 = (state_of(gdir, "sess-P").get("signals") or [{}])[0]
        check("0.8.5: a signal records the fill it was made at",
              rc == 0 and abs(float(sig0.get("pct", -1)) - 33.0) < 1.0, (rc, sig0))
        for kk in ("stale-read", "third-class", "fourth-class", "fifth-class"):
            run("_strain_signal.py", None, [kk, "--escaped", "--session", "sess-P"],
                {"STRAIN_STATE_DIR": gdir})
        check("0.8.5: five escaped at 33% fill move nothing -- recorded and kept, not tiered",
              state_of(gdir, "sess-P").get("last") == "Healthy"
              and len(state_of(gdir, "sess-P").get("signals") or []) == 5,
              state_of(gdir, "sess-P"))
        out, _, _ = tick(gdir, "sess-P", n=1, transcript=npath)
        check("0.8.5: the next tick proposes Healthy and names 0 counted",
              "PROPOSED TIER: Healthy" in out and "after 50%: 0" in out, out[:400])
        udir = os.path.join(tmp, "s9u")                      # no tick: the fill is unknown
        for kk in ("u1", "u2", "u3"):
            run("_strain_signal.py", None, [kk, "--escaped", "--session", "sess-U"],
                {"STRAIN_STATE_DIR": udir})
        check("0.8.5: fill unknown -- the third escaped still floors Mid (today's ladder)",
              state_of(udir, "sess-U").get("last") == "Mid"
              and "pct" not in ((state_of(udir, "sess-U").get("signals") or [{}])[0]),
              state_of(udir, "sess-U"))
        # v4 COMBINATION ALARM (owner's two-condition composite, restored 2026-09-13):
        # Warning-cap fill (72%, below the derived Danger cap 74) AND >=3 escaped ->
        # Danger, with a loud basis line naming both conditions. Below either
        # precondition the lines stay independent (max only); the throttle-zone note
        # still annotates and never tiers.
        # 0.8.5: that composite is gone -- the owner's 2026-10-09 ruling: Danger needs five
        # escaped made past 50% fill AND the fill at 70%, said by Line B.
        wdir = os.path.join(tmp, "s9b")
        wpath = os.path.join(tmp, "warnfill.jsonl")
        make_transcript(wpath, [(2, 10000, 0), (2, 144000, 0)])   # 72% of 200k
        tick(wdir, "sess-Q", n=0, transcript=wpath)               # measured first: signals carry 72%
        for kk in ("k1", "k2", "k3"):
            run("_strain_signal.py", None, [kk, "--escaped", "--session", "sess-Q"],
                {"STRAIN_STATE_DIR": wdir})
        out, _, _ = tick(wdir, "sess-Q", n=1, transcript=wpath)
        check("0.8.5: Warning fill + 3 escaped past 50% -> Warning (the old composite is gone)",
              "PROPOSED TIER: Warning" in out and "composite" not in out, out[:400])
        for kk in ("k4", "k5"):
            run("_strain_signal.py", None, [kk, "--escaped", "--session", "sess-Q"],
                {"STRAIN_STATE_DIR": wdir})
        out, _, _ = tick(wdir, "sess-Q", n=1, transcript=wpath)
        check("0.8.5: the fifth escaped past 50% at 72% fill -> Danger, said by Line B",
              "PROPOSED TIER: Danger" in out and "Line B Danger" in out, out[:600])
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
        section_082(tmp)
        section_083(tmp)
        section_084(tmp)
        section_090(tmp)
        section_0100(tmp)
        section_0110(tmp)

    finally:
        # 0.10.0 (QA, first round): --keep deletes nothing and names the folder it used
        if "--keep" in sys.argv:
            print("kept: " + tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    total = len(PASS) + len(FAIL)
    print("\n%d/%d checks passed" % (len(PASS), total))
    if FAIL:
        print("failed: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
