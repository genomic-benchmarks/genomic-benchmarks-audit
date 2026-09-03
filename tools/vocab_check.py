#!/usr/bin/env python3
"""Scan prose for terms the vocabulary convention restricts.

The convention is VOCABULARY.md; the machine-checkable part of it is
tools/vocabulary.toml. This script is the part that runs.

Only prose is scanned. Fenced code blocks, inline code spans, link
destinations, bare URLs and HTML comments are blanked out before matching, so
`overall_verdict` and combined_classes_results.csv never trip a rule: an
identifier is not a claim.

Roughly half the rules are literal string matches and are reported as errors.
The rest -- bias, shortcut, artefact, clean -- are words whose acceptability
depends on the sentence, and are reported as warnings for a human to judge.

Suppress a rule on one line with an HTML comment carrying a reason:

    <!-- vocab-ok: golden-set # quoting the name this project replaced -->

Alone on its own line, the comment applies to the next non-blank line;
trailing on a line of prose, it applies to that line. The reason is required,
and a suppression that stops matching anything is reported, so the allowlist
cannot quietly outlive the sentence that needed it.

Usage:
    tools/vocab_check.py                 # the paths in vocabulary.toml
    tools/vocab_check.py docs/rules.md   # specific files or directories
    tools/vocab_check.py --strict        # warnings fail too
    tools/vocab_check.py --list-rules
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES = Path(__file__).resolve().parent / "vocabulary.toml"

SUPPRESS_RE = re.compile(
    r"<!--\s*vocab-ok\s*:\s*(?P<ids>[^#>]*?)\s*(?:#\s*(?P<reason>[^>]*?))?\s*-->",
    re.S,
)

# Regions that are not prose. Order matters: comments go first so a suppression
# reason can name the term it excuses, fences before inline spans so a code
# block's backticks cannot open a span.
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FENCE_OPEN_RE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"(?P<ticks>`+).+?(?P=ticks)", re.S)
# HTML code regions. The plan documents are HTML, and there a field name is
# <code>au_roc</code> rather than `au_roc` — without this the checker reports
# every code reference in them as prose.
HTML_CODE_RE = re.compile(
    r"<(?P<tag>code|pre|kbd|samp|script|style)\b[^>]*>.*?</(?P=tag)\s*>",
    re.S | re.I)
LINK_DEST_RE = re.compile(r"\]\((?P<dest>[^)]*)\)")
LINK_REF_RE = re.compile(r"^[ \t]*\[[^\]]+\]:[ \t]*(?P<dest>\S+)", re.M)
AUTOLINK_RE = re.compile(r"<(?P<dest>[a-z][a-z0-9+.-]*://[^>\s]+)>", re.I)
BARE_URL_RE = re.compile(r"(?P<dest>[a-z][a-z0-9+.-]*://\S+)", re.I)

TEXT_SUFFIXES = {".md", ".markdown", ".html", ".txt"}


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern
    severity: str
    message: str


@dataclass(frozen=True)
class Hit:
    path: Path
    line: int
    col: int
    rule: str
    severity: str
    message: str
    matched: str
    line_text: str


@dataclass
class Suppression:
    path: Path
    line: int          # the line it governs
    declared_on: int   # the line the comment sits on
    ids: tuple
    reason: str
    used: bool = field(default=False)


@dataclass
class Settings:
    paths: tuple = ("docs",)
    exclude: tuple = ()


# --------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------

def load_rules(path: Path) -> tuple[list[Rule], Settings]:
    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    settings = Settings(
        paths=tuple(raw.get("settings", {}).get("paths", ["docs"])),
        exclude=tuple(raw.get("settings", {}).get("exclude", [])),
    )

    rules, seen = [], set()
    for entry in raw.get("rule", []):
        for key in ("id", "pattern", "severity", "message"):
            if key not in entry:
                raise ValueError(f"{path}: rule is missing '{key}': {entry!r}")
        rid = entry["id"]
        if rid in seen:
            raise ValueError(f"{path}: duplicate rule id {rid!r}")
        seen.add(rid)
        if entry["severity"] not in ("error", "warn"):
            raise ValueError(
                f"{path}: rule {rid!r} has severity {entry['severity']!r}, "
                "expected 'error' or 'warn'"
            )
        flags = re.IGNORECASE if entry.get("ignorecase", True) else 0
        try:
            compiled = re.compile(entry["pattern"], flags)
        except re.error as exc:
            raise ValueError(f"{path}: rule {rid!r} has a bad pattern: {exc}") from exc
        rules.append(Rule(rid, compiled, entry["severity"], entry["message"]))

    if not rules:
        raise ValueError(f"{path}: no rules defined")
    return rules, settings


# --------------------------------------------------------------------------
# masking
# --------------------------------------------------------------------------

def _blank(chars: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if chars[i] != "\n":
            chars[i] = " "


def _mask_fences(chars: list[str], text: str) -> None:
    """Blank fenced code blocks, fence lines included."""
    pos, fence, block_start = 0, None, 0
    for line in text.splitlines(keepends=True):
        end = pos + len(line)
        opener = FENCE_OPEN_RE.match(line)
        if fence is None:
            if opener:
                fence, block_start = opener.group("fence")[0] * 3, pos
        elif opener and opener.group("fence").startswith(fence):
            _blank(chars, block_start, end)
            fence = None
        pos = end
    if fence is not None:          # unterminated fence: mask to end of file
        _blank(chars, block_start, len(text))


def mask_code(text: str) -> str:
    """Blank fenced blocks, HTML code elements and inline spans.

    Offsets are preserved throughout, so a hit's line and column still point
    at the raw file.

    Suppressions are read from this rather than from the raw text, so the
    worked example of a vocab-ok comment in VOCABULARY.md is documentation
    and not a live allowlist entry.
    """
    chars = list(text)
    _mask_fences(chars, text)
    partial = "".join(chars)
    for m in HTML_CODE_RE.finditer(partial):
        _blank(chars, m.start(), m.end())
    partial = "".join(chars)
    for m in INLINE_CODE_RE.finditer(partial):
        _blank(chars, m.start(), m.end())
    return "".join(chars)


def mask_non_prose(text: str) -> str:
    """Return text with every non-prose region blanked, offsets preserved."""
    chars = list(mask_code(text))
    partial = "".join(chars)
    for m in HTML_COMMENT_RE.finditer(partial):
        _blank(chars, m.start(), m.end())
    partial = "".join(chars)
    for regex in (LINK_DEST_RE, LINK_REF_RE, AUTOLINK_RE, BARE_URL_RE):
        for m in regex.finditer(partial):
            _blank(chars, m.start("dest"), m.end("dest"))
    return "".join(chars)


# --------------------------------------------------------------------------
# suppressions
# --------------------------------------------------------------------------

def _line_bounds(text: str) -> list[tuple[int, int]]:
    bounds, pos = [], 0
    for line in text.splitlines(keepends=True):
        bounds.append((pos, pos + len(line)))
        pos += len(line)
    return bounds or [(0, 0)]


def parse_suppressions(path: Path, text: str,
                       known: set) -> tuple[list[Suppression], list[Hit]]:
    """Pull `vocab-ok` comments out of the raw text. Malformed ones are hits."""
    bounds = _line_bounds(text)
    lines = text.splitlines()
    suppressions, problems = [], []
    searchable = mask_code(text)   # a comment shown inside a fence is an example

    def line_of(offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    for m in SUPPRESS_RE.finditer(searchable):
        declared_on = line_of(m.start())
        last = line_of(m.end() - 1)
        ids = tuple(i.strip() for i in m.group("ids").split(",") if i.strip())
        reason = (m.group("reason") or "").strip()

        def problem(msg: str) -> Hit:
            body = lines[declared_on - 1] if declared_on <= len(lines) else ""
            return Hit(path, declared_on, m.start() - bounds[declared_on - 1][0] + 1,
                       "vocab-ok", "error", msg, m.group(0).strip(), body)

        if not ids:
            problems.append(problem("A vocab-ok comment names no rule."))
            continue
        if not reason:
            problems.append(problem(
                "A vocab-ok comment needs a reason: "
                "<!-- vocab-ok: rule-id # why this sentence is allowed -->"))
            continue
        unknown = [i for i in ids if i not in known and i != "*"]
        if unknown:
            problems.append(problem(
                f"A vocab-ok comment names unknown rule(s): {', '.join(unknown)}."))
            continue

        # Alone on its line, it governs the next line with prose on it.
        start, end = bounds[last - 1]
        remainder = (text[start:m.start()] + text[m.end():end]).strip()
        target = last
        if not remainder:
            target = next((n for n in range(last + 1, len(lines) + 1)
                           if lines[n - 1].strip()), last)
        suppressions.append(Suppression(path, target, declared_on, ids, reason))

    return suppressions, problems


# --------------------------------------------------------------------------
# scanning
# --------------------------------------------------------------------------

def scan_text(path: Path, text: str, rules: list[Rule]) -> tuple[list[Hit], list[Suppression]]:
    known = {r.id for r in rules}
    suppressions, hits = parse_suppressions(path, text, known)
    prose = mask_non_prose(text)
    bounds = _line_bounds(text)
    lines = text.splitlines()

    by_line: dict[int, list[Suppression]] = {}
    for s in suppressions:
        by_line.setdefault(s.line, []).append(s)

    for rule in rules:
        for m in rule.pattern.finditer(prose):
            line = prose.count("\n", 0, m.start()) + 1
            covering = [s for s in by_line.get(line, [])
                        if rule.id in s.ids or "*" in s.ids]
            if covering:
                for s in covering:
                    s.used = True
                continue
            hits.append(Hit(
                path=path,
                line=line,
                col=m.start() - bounds[line - 1][0] + 1,
                rule=rule.id,
                severity=rule.severity,
                message=rule.message,
                matched=text[m.start():m.end()],
                line_text=lines[line - 1] if line <= len(lines) else "",
            ))

    hits.sort(key=lambda h: (h.line, h.col, h.rule))
    return hits, suppressions


def collect_files(targets, exclude) -> list[Path]:
    excluded = [Path(e) for e in exclude]

    def is_excluded(p: Path) -> bool:
        rel = p.relative_to(REPO_ROOT) if p.is_absolute() and p.is_relative_to(REPO_ROOT) else p
        return any(rel == e or e in rel.parents for e in excluded)

    files: list[Path] = []
    for target in targets:
        p = Path(target)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if p.is_dir():
            files.extend(f for f in sorted(p.rglob("*"))
                         if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES
                         and ".git" not in f.parts and not is_excluded(f))
        elif p.is_file():
            if not is_excluded(p):
                files.append(p)
        # A configured path that does not exist yet is not an error: docs/
        # arrives later than this script does.
    return files


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def report(hits, stale, github: bool, stream=None) -> None:
    # Resolved per call, not as a default: a default is bound at import
    # and would ignore a redirected stdout in the tests.
    stream = sys.stdout if stream is None else stream
    for h in hits:
        if github:
            level = "error" if h.severity == "error" else "warning"
            print(f"::{level} file={rel(h.path)},line={h.line},col={h.col}::"
                  f"{h.rule}: {h.message}", file=stream)
        else:
            print(f"{rel(h.path)}:{h.line}:{h.col}: {h.severity} [{h.rule}] "
                  f"{h.matched!r} -- {h.message}", file=stream)
            if h.line_text.strip():
                print(f"    {h.line_text.strip()}", file=stream)

    for s in stale:
        text = (f"{rel(s.path)}:{s.declared_on}: warn [vocab-ok] suppression for "
                f"{', '.join(s.ids)} matched nothing -- delete it, or the "
                f"allowlist outlives the sentence that needed it")
        if github:
            print(f"::warning file={rel(s.path)},line={s.declared_on}::{text}",
                  file=stream)
        else:
            print(text, file=stream)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan prose for terms the vocabulary convention restricts.")
    parser.add_argument("paths", nargs="*", help="files or directories to scan")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--strict", action="store_true",
                        help="fail on warnings as well as errors")
    parser.add_argument("--github", action="store_true",
                        help="emit GitHub Actions annotations")
    parser.add_argument("--list-rules", action="store_true")
    args = parser.parse_args(argv)

    try:
        rules, settings = load_rules(args.rules)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"vocab_check: {exc}", file=sys.stderr)
        return 2

    if args.list_rules:
        for r in sorted(rules, key=lambda r: (r.severity, r.id)):
            print(f"{r.severity:5}  {r.id:20}  {r.message}")
        return 0

    files = collect_files(args.paths or settings.paths, settings.exclude)
    if not files:
        print("vocab_check: nothing to scan", file=sys.stderr)
        return 0

    all_hits, stale = [], []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"vocab_check: cannot read {rel(path)}: {exc}", file=sys.stderr)
            return 2
        hits, suppressions = scan_text(path, text, rules)
        all_hits.extend(hits)
        stale.extend(s for s in suppressions if not s.used)

    report(all_hits, stale, args.github or bool(os.environ.get("GITHUB_ACTIONS")))

    errors = sum(1 for h in all_hits if h.severity == "error")
    warnings = sum(1 for h in all_hits if h.severity == "warn") + len(stale)
    scanned = f"{len(files)} file{'s' if len(files) != 1 else ''}"
    if errors or warnings:
        print(f"\nvocab_check: {scanned}, {errors} error(s), {warnings} warning(s)")
    else:
        print(f"vocab_check: {scanned}, clear")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
