#!/usr/bin/env python3
"""Draft a bug report about strain itself -- for the USER to send. Nothing is sent.

    strain-report.sh                                draft from this session's last reading
    strain-report.sh --note "<what you saw>"        add the agent's or user's own words
    strain-report.sh --title "<one line>"           name the problem

When strain's own arithmetic breaks -- a fill past 100%, a window that cannot be right,
a host whose log it cannot read -- the fix belongs upstream, and the person who saw it is
usually the only one who can tell. This writes a short report draft with the facts
strain holds (version, host, model, the reading and its window, where that window came
from) and prints where to file it. The user reads it, edits it, and sends it by hand --
or not at all.

What the draft never carries: file paths, the session id, folder or project names, or any
conversation content. The note is scrubbed mechanically too (the home folder, the
session id and anything shaped like an absolute path are replaced), but the person
sending it is the last check -- the output says so.

The same tool drafts an ADAPTER PROPOSAL when a host keeps its usage in a durable log
strain cannot read yet: describe where the log is, which fields carry the usage, and
one redacted sample line in --note. Never edit the installed plugin instead -- a local
patch is overwritten by the next update and helps nobody else.
"""
import argparse, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, session_path, load, resolve_for_write,
                            PRODUCT_OF_SUBSTRATE, k_tokens)

HERE = os.path.dirname(os.path.abspath(__file__))
PATHLIKE = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][^\s\\/'\"`<>|]+){2,}[\\/]?")


def plugin_meta():
    try:
        with open(os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json")) as f:
            d = json.load(f)
        return str(d.get("version") or "?"), str(d.get("repository") or "")
    except Exception:
        return "?", ""


def scrub(text, sid):
    t = str(text or "")
    if sid:
        t = t.replace(sid, "<session>")
    home = os.path.expanduser("~")
    if home and home != "~":
        t = t.replace(home, "~")
    return PATHLIKE.sub("<path>", t)


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--note", default="")
    ap.add_argument("--title", default="")
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    sid, how, refusal = resolve_for_write(sdir, args.session, "strain-report.sh", argv)
    if refusal:
        sys.stderr.write(refusal)
        return 2
    st = load(session_path(sdir, sid))
    ctx = st.get("ctx") if isinstance(st.get("ctx"), dict) else {}
    import _strain_tick as tickmod
    kind, why = tickmod.reading_state(ctx)
    version, repo = plugin_meta()
    host = PRODUCT_OF_SUBSTRATE.get(str(st.get("substrate") or ""), "") or "unrecognised host"
    title = args.title or ("strain: %s reading on %s" % (("UNMEASURED · " + kind) if kind
                                                       else "a questionable", host))
    lines = [
        "# %s" % scrub(title, sid),
        "",
        "Drafted by `strain-report.sh` -- review before sending; nothing was sent.",
        "",
        "## What strain recorded",
        "",
        "- strain version: %s" % version,
        "- host: %s" % host,
        "- model: %s" % (st.get("model") or ctx.get("model") or "not seen"),
        "- reading: %s%s" % (ctx.get("mode") or "none",
                             (" · " + kind) if kind else ""),
        "- tokens in context: %s" % ("{:,}".format(int(ctx["tokens"]))
                                     if ctx.get("tokens") is not None else "not known"),
        "- window: %s (%s)" % (k_tokens(ctx.get("limit")) if ctx.get("limit") else "not known",
                               ctx.get("limitSource") or "source not recorded"),
        "- fill: %s" % (("%s%%" % ctx["pct"]) if ctx.get("pct") is not None else "not known"),
        "- reading source: %s" % (ctx.get("source") or "none"),
        "- compactions this session: %d" % int(st.get("compactions", 0) or 0),
        "- tool calls this session: %d" % int(st.get("tick", 0) or 0),
    ]
    if why:
        lines += ["", "## Why strain could not use it", "", scrub(why, sid)]
    if args.note:
        lines += ["", "## What the agent or user saw", "", scrub(args.note, sid)]
    lines += ["", "## Not included on purpose", "",
              "File paths, the session id, folder or project names and conversation content."
              " Add only what you are comfortable making public."]
    body = "\n".join(lines) + "\n"

    d = os.path.join(sdir, "reports")
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "strain-report-%s-%s.md"
                            % (re.sub(r"[^0-9a-f]", "", sid.lower())[:8] or "unknown",
                               time.strftime("%Y%m%d-%H%M%S")))
        with open(path, "w") as f:
            f.write(body)
    except Exception as e:
        sys.stderr.write("could not write the draft (%s)\n" % type(e).__name__)
        return 1
    # USER-SURFACE: plain words; the path and the link go to stderr for the agent.
    sys.stdout.write("Strain · bug report drafted — nothing was sent. Read it, edit it, and file"
                     " it yourself if you want it fixed.\n")
    sys.stderr.write("draft: %s\nfile it at: %s\n" % (path, (repo.rstrip("/") + "/issues/new")
                                                     if repo else "the strain repository"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
