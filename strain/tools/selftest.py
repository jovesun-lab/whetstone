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


def run(script, payload=None, args=(), env=None):
    """Run a hook or CLI script; return (stdout, stderr, returncode)."""
    e = dict(os.environ)
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
        check("directive carries the recorded tier", "carried into this check: High" in nxt, nxt[:200])
        check("level reports which session it wrote", "sess-D" in err, err)

        # resolution by cwd, with no explicit session
        out, err, rc = run("_strain_level.py", None, ["Mid"],
                           {"STRAIN_STATE_DIR": sdir, "PWD": "/tmp/projD"})
        # resolve_sid uses os.getcwd(); the index also stores a most-recent fallback
        check("level resolves a session without being told", rc == 0 and out == "Mid",
              (rc, out, err))

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
        check("wrap marker resets", state_of(sdir, "sess-E").get("tick") == 0,
              state_of(sdir, "sess-E"))
        for _ in range(2):
            tick(sdir, "sess-E")
        start(sdir, "sess-E", source="resume")
        check("a wrap resets once, not forever",
              state_of(sdir, "sess-E").get("tick") == 2, state_of(sdir, "sess-E"))

        # ---- compaction is escalation, one way ---------------------------------------
        sdir = os.path.join(tmp, "s5")
        tick(sdir, "sess-F")
        start(sdir, "sess-F", source="compact")
        st = state_of(sdir, "sess-F")
        check("compaction counted", st.get("compactions") == 1, st)
        check("compaction floors the tier", st.get("last") == "High", st)
        check("compaction preserves the count", st.get("tick") == 1, st)
        start(sdir, "sess-F", source="compact")
        st = state_of(sdir, "sess-F")
        check("second compaction escalates", st.get("last") == "Warning", st)
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

        # thresholds
        big = os.path.join(tmp, "big.jsonl")
        make_transcript(big, [(2, 10000, 0), (2, 160000, 0)])
        out, _, _ = tick(sdir, "sess-J", n=1, transcript=big)
        check("a full window raises the floor", "at least High" in out, out[:300])
        out, _, _ = tick(sdir, "sess-K", n=1, transcript=big,
                         extra_env={"STRAIN_CONTEXT_LIMIT": "1000000"})
        check("the window size is configurable", "at least" not in out, out[:300])

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
        check("a 1M window is not reported as nearly full", "at least" not in out,
              out[:300])
        make_transcript(lpath, [(2, 10000, 0), (2, 160000, 0)],
                        model="claude-sonnet-4-5[1m]")
        tick(ldir, "sess-L2", n=1, transcript=lpath)
        check("an explicit [1m] variant gets a 1M denominator",
              state_of(ldir, "sess-L2").get("ctx", {}).get("limit") == 1000000,
              state_of(ldir, "sess-L2").get("ctx"))
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

        # ---- no absolute paths baked into the shipped config ---------------------------
        hooks = os.path.join(os.path.dirname(HERE), "hooks", "hooks.json")
        with open(hooks) as f:
            raw = f.read()
        check("hooks.json hardcodes no home directory", "/Users/" not in raw and
              "/home/" not in raw, raw[:200])
        check("hooks.json goes through the plugin root", "CLAUDE_PLUGIN_ROOT" in raw)

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
