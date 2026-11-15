#!/usr/bin/env python3
"""Decides whether a Bash command is one of the never-do list's irreversible ones.

This is the judgement half of scripts/guard-destructive.sh, which carried it
inline in a heredoc until recently. Extracted for two reasons:

  * it could not be TESTED directly, only through the shell wrapper, one
    subprocess per case with the payload squeezed through stdin;
  * it could not be MEASURED. A bash coverage tracer sees a heredoc as ONE
    statement, so guard-destructive.sh reported 3 of 19 lines covered while every
    rule inside it was being exercised. Rule #29 asks for an honest denominator,
    and 16 of those 19 lines were Python pretending to be shell.

The patterns below were moved VERBATIM by a script, not retyped. They are the
difference between a blocked force-push and a lost branch, and a regex rewritten
from memory is how a guard quietly stops matching. They were widened once since
(14/11/2026, F-001): every bypass named in that finding is a row of the table in
scripts/tests/test_guard_bypasses.py, run through the real wrapper - change a
pattern only with that table green.

Reads the hook payload (JSON, or raw text) on stdin.
Exit 0 = allowed. Exit 2 = blocked, with the reason on stderr.

A push to the prod branch is NOT judged here (17/10/2026, the user's decision: Claude makes that push when the
configuration says so - scripts/podium_config.py, `push.prod`). A push to main, any forced push and --no-verify are.

WARNING - FAIL CLOSED. A payload that will not parse is judged as RAW TEXT rather
than waved through, and the wrapper turns any unexpected exit code into a block.
A guard that opens when it is confused is not a guard. There is deliberately no
environment-variable bypass: a switch the agent can set is not a guard either.
"""
import json
import re
import sys


def without_heredocs(text):
    kept, tag = [], None
    for line in text.splitlines():
        if tag is not None:
            if line.strip() == tag:
                tag = None
            continue
        kept.append(line)
        # `<<<word` is a here-string, not a heredoc: taking it for one stripped every later line (F-002).
        m = re.search(r"(?<!<)<<(?!<)-?\s*[\"\x27]?([A-Za-z_][A-Za-z_0-9]*)", line)
        if m:
            tag = m.group(1)
    return "\n".join(kept)

# `git` and the global options it takes before the verb (`git -C <dir>`, `git -c k=v`, `git --git-dir <d>`): without
# them `git -C repo push --force` was no push to the rules below (F-001).
ARG = r"(?:\"[^\"]*\"|\x27[^\x27]*\x27|\S+)"
GIT = (r"git(?:\s+(?:-[Cc]\s+" + ARG + r"|--(?:git-dir|work-tree|namespace|exec-path|config-env|super-prefix)\s+" + ARG
       + r"|-\S+))*\s+")
PUSH = GIT + r"push(?![-\w.])"            # not `push.default=` in a `-c`


def bundle(letter):
    """A short-option bundle holding `letter` (`-f`, `-fu`, `-uf`); a `--long` option never matches it."""
    return r"-[a-z0-9]*" + letter + r"[a-z0-9]*"


def prefix(shortest, rest):
    """A long option and every abbreviation git accepts for it: `prefix("--mi", "rror")` matches `--mi` ... `--mirror`
    (git takes any unique prefix of a long option, F-045)."""
    return shortest + "".join("(?:" + letter for letter in rest) + ")?" * len(rest)


# Where an option or a target ends: whitespace, the line's end, or what closes the command around it - `;`, `&`, `|`,
# `)`, `}`, a backtick or a quote (`bash -c "git push --force"`, `(git push -f)`, `{ git push -f; }`; QA 16/11/2026).
# An option may stand in quotes too (`git push "-f"`).
END = r"(?=[\s;&|)}`\"\x27]|$)"
Q = r"[\"\x27]?"

# Heredoc bodies are stripped for the GIT rules only — a heredoc that WRITES a
# script containing "--no-verify" is not a commit. They are NOT stripped for the
# rules below it, because `psql <<EOF ...` really does execute.
# The shortest abbreviations blocked: `--fo` (ambiguous with --follow-tags, which git refuses anyway; `--fol` is not
# matched), `--mi`, `--de`, `--pru` (`--pr` is also --progress), `--no-v`. `--no-verify-signatures` is not --no-verify.
GIT_RULES = (
    (PUSH + r"([^;&|\n]*\s)?" + Q + r"(" + bundle("f") + r"|--fo(r(c(e[a-z-]*)?)?)?(=\S*)?)" + END, "forced push"),
    (PUSH + r"[^;&|\n]*\s[\"\x27]?\+", "forced push (a + refspec)"),
    (PUSH + r"([^;&|\n]*\s)?" + Q + prefix("--mi", "rror") + END, "mirror push (overwrites and deletes remote branches)"),
    (PUSH + r"([^;&|\n]*\s)?" + Q + r"(" + bundle("d") + r"|" + prefix("--de", "lete") + r")" + END,
     "deletes a remote branch"),
    (PUSH + r"([^;&|\n]*\s)?" + Q + prefix("--pru", "ne") + END, "deletes remote branches (--prune)"),
    (PUSH + r"[^;&|\n]*\s[\"\x27]?:[^\s:]", "deletes a remote branch (a :branch refspec)"),
    (PUSH + r"[^;&|\n]*(\s|:|refs/heads/)[\"\x27]?main" + END, "push straight to main"),
    (GIT + r"(commit|push|merge)([^;&|\n]*\s)?" + Q + prefix("--no-v", "erify") + END,
     "--no-verify skips the pre-commit gitleaks hook"),
    # `git commit -n` IS --no-verify (on push and merge -n means something else).
    (GIT + r"commit(?![-\w])([^;&|\n]*\s)?" + Q + bundle("n") + END,
     "-n (--no-verify) skips the pre-commit gitleaks hook"),
)
# rm, as a command word (not `confirm`, `terraform`): a recursive option, short (`-r`, `-rf`, `-r -f`) or long
# (`--recursive` or a prefix of it, `--recur`), and a dangerous target, bare or quoted (`"$HOME"`, `'/'`), each ANYWHERE
# in the same command (F-001, F-045: `rm -rf build ~`). A target may end in `/`, `/.`, `/*` or `/..`, and the parent
# `..` counts (`"$HOME"/`, `~/.`, `/.`, `../*`; QA 16/11/2026). `git rm -r --cached .` only untracks, and plain rm has
# no --cached: left alone.
SEGMENT = r"[^;&|\n]*[ \t]"
RM_RECURSIVE = SEGMENT + r"(" + bundle("r") + r"|" + prefix("--r", "ecursive") + r")" + END
RM_TARGET = SEGMENT + r"(--[ \t]+)?" + Q + r"(/|~|\$HOME|\$\{HOME\}|\*|\.\.?)" + Q + r"(/?\.{0,2}/?\*?)" + Q + END
ANY_RULES = (
    (r"(drop|truncate)\s+(table|database|schema)", "DROP/TRUNCATE (take a backup and get approval first)"),
    (r"(?<![\w.-])rm(?=[ \t])(?=" + RM_RECURSIVE + r")(?=" + RM_TARGET + r")(?!" + SEGMENT + r"--cached(\s|$))",
     "recursive delete of a root/home/working directory"),
)


def masked(text):
    """`;`, `&` and `|` inside a quoted string are text, not command separators: masked so a commit message with a `;`
    no longer hides the `--no-verify` after it (`git commit -m "a; b" --no-verify`; QA 16/11/2026)."""
    return re.sub(r"\"[^\"\n]*\"|\x27[^\x27\n]*\x27", lambda m: re.sub(r"[;&|]", "_", m.group(0)), text)


def command_of(raw):
    """The text to judge. Fail closed: an unparseable payload is judged raw."""
    try:
        return json.loads(raw).get("tool_input", {}).get("command", "") or raw
    except Exception:
        return raw


def verdict(command):
    """The reason this command is blocked, or None when it is allowed."""
    for view, rules in ((masked(without_heredocs(command)), GIT_RULES), (masked(command), ANY_RULES)):
        for pattern, reason in rules:
            if re.search(pattern, view, re.I):
                return reason
    return None


def main():
    reason = verdict(command_of(sys.stdin.read()))
    if reason is None:
        return 0
    sys.stderr.write(
        "BLOCKED by guard-destructive.sh: %s\n"
        "Ask the user to run it themselves (never-do list).\n" % reason)
    return 2


if __name__ == "__main__":
    sys.exit(main())
