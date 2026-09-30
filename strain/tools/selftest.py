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
        check("directive carries the recorded tier", "carried: High" in nxt, nxt[:300])
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
        out, err, rc = run("_strain_calibrate.py", None,
                           ["--state-dir", dcal, "--product", "Codex CLI",
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
                         ["--state-dir", dcal, "--product", "X", "--window", "100",
                          "--basis", "nominal"])
        check("0.6.0: an unsourced capacity is REFUSED (stale ruler doctrine)",
              rc == 2 and "source" in err, (rc, err[:200]))
        _, err, rc = run("_strain_calibrate.py", None,
                         ["--state-dir", dcal, "--product", "X", "--window", "100",
                          "--source", "s"])
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
            subprocess.run(["bash", "-c", cmd.replace("<Healthy|Mid|High|Warning|Danger>", "Mid")],
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
