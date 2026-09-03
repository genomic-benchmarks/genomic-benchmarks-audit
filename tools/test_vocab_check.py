#!/usr/bin/env python3
"""Tests for vocab_check. Runs standalone: python3 tools/test_vocab_check.py

Also collects under pytest, but needs nothing installed to run.
"""

from __future__ import annotations

import io
import sys
import tempfile
import textwrap
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vocab_check as vc  # noqa: E402

RULES, _ = vc.load_rules(vc.DEFAULT_RULES)


def scan(body: str, name: str = "page.md"):
    """Scan a dedented string, returning (hits, suppressions)."""
    return vc.scan_text(Path(name), textwrap.dedent(body).lstrip("\n"), RULES)


def ids(hits):
    return sorted(h.rule for h in hits)


# ----------------------------------------------------------------- masking --

def test_mask_preserves_offsets():
    text = "a `code` b\n```\ngolden set\n```\nend\n"
    masked = vc.mask_non_prose(text)
    assert len(masked) == len(text)
    assert masked.count("\n") == text.count("\n")


def test_code_span_is_not_prose():
    hits, _ = scan("The `golden set` column is documented below.\n")
    assert hits == []


def test_identifier_does_not_trip_a_rule_even_unquoted():
    # `\b` does not fire inside overall_verdict, because underscore is a word
    # character. Column names survive without needing backticks.
    hits, _ = scan("The overall_verdict column keeps its name.\n")
    assert hits == []
    hits, _ = scan("The verdict was recorded.\n")
    assert ids(hits) == ["verdict"]


def test_fenced_block_is_not_prose():
    hits, _ = scan("""
        Before.

        ```python
        golden_set = "gold standard"
        ```

        After.
        """)
    assert hits == []


def test_unterminated_fence_masks_to_end():
    hits, _ = scan("```\ngold standard\nAU-ROC\n")
    assert hits == []


def test_html_code_element_is_not_prose():
    # In an HTML page a field name is <code>au_roc</code>, not `au_roc`.
    hits, _ = scan("<p>The <code>au_roc</code> column is documented below.</p>\n",
                   "page.html")
    assert hits == []


def test_html_pre_block_is_not_prose():
    hits, _ = scan("""
        <p>Before.</p>
        <pre><code>golden_set = "gold standard"
        AU-ROC</code></pre>
        <p>After.</p>
        """, "page.html")
    assert hits == []


def test_html_script_and_style_are_not_prose():
    hits, _ = scan('<style>.trivial { color:red }</style>\n'
                   '<script>var v = "gold standard";</script>\n', "page.html")
    assert hits == []


def test_html_prose_outside_code_is_still_scanned():
    hits, _ = scan("<p>A <code>Pass</code> means the set is high-quality.</p>\n",
                   "page.html")
    assert ids(hits) == ["high-quality"]


def test_html_masking_preserves_offsets():
    text = "<p>ok</p>\n<pre>gold standard\nAU-ROC</pre>\n<p>the trivial case</p>\n"
    masked = vc.mask_non_prose(text)
    assert len(masked) == len(text)
    assert masked.count("\n") == text.count("\n")
    hits, _ = scan(text, "page.html")
    assert ids(hits) == ["trivial"]
    assert hits[0].line == 4


def test_unclosed_html_code_element_stays_prose():
    # Fails open rather than swallowing the rest of the page.
    hits, _ = scan("<p>The <code>gold standard is here.</p>\n", "page.html")
    assert ids(hits) == ["golden-set"]


def test_link_targets_and_urls_are_not_prose():
    hits, _ = scan("See [the set](https://example.org/golden-set) and\n"
                   "https://example.org/AU-ROC for detail.\n")
    assert hits == []


def test_link_text_is_prose():
    hits, _ = scan("See [the golden set](https://example.org/x).\n")
    assert ids(hits) == ["golden-set"]


# -------------------------------------------------------------------- hits --

def test_error_hit_has_position_and_severity():
    hits, _ = scan("Line one.\nThis is the golden set of datasets.\n")
    assert len(hits) == 1
    hit = hits[0]
    assert (hit.rule, hit.severity, hit.line) == ("golden-set", "error", 2)
    assert hit.col == 13
    assert hit.matched == "golden set"


def test_warning_severity():
    hits, _ = scan("The dataset is clean.\n")
    assert [(h.rule, h.severity) for h in hits] == [("clean", "warn")]


def test_lowercase_flag_is_case_sensitive():
    assert ids(scan("Datasets with no fail on any check.\n")[0]) == ["lowercase-flag"]
    assert scan("Datasets with no Fail on any check.\n")[0] == []


def test_split_provenance():
    assert ids(scan("the splits we drew for mRNABench\n")[0]) == ["split-provenance"]
    assert scan("splits generated from the collection's own function\n")[0] == []


def test_validator_sense_is_only_a_warning():
    hits, _ = scan("A submission that failed the format check is rejected.\n")
    assert [(h.rule, h.severity) for h in hits] == [("failed-check", "warn")]


def test_clear_page_is_clear():
    hits, sup = scan("""
        Flagged `Fail` on dinucleotide content, at AUROC 0.90.
        The Core Set is the subset no check flagged `Fail`.
        """)
    assert (hits, sup) == ([], [])


# ------------------------------------------------------------ suppressions --

def test_trailing_suppression():
    hits, sup = scan(
        "The golden set was renamed. <!-- vocab-ok: golden-set # quoting the old name -->\n")
    assert hits == []
    assert [s.used for s in sup] == [True]


def test_suppression_on_its_own_line_governs_the_next():
    hits, sup = scan("""
        <!-- vocab-ok: golden-set # quoting the old name -->
        The golden set was renamed.
        """)
    assert hits == []
    assert sup[0].line == 2 and sup[0].used


def test_suppression_skips_blank_lines():
    hits, _ = scan("""
        <!-- vocab-ok: golden-set # quoting the old name -->

        The golden set was renamed.
        """)
    assert hits == []


def test_suppression_does_not_leak_to_other_lines():
    hits, _ = scan("""
        The golden set. <!-- vocab-ok: golden-set # first mention only -->
        The golden set again.
        """)
    assert [(h.rule, h.line) for h in hits] == [("golden-set", 2)]


def test_suppression_is_rule_specific():
    hits, _ = scan("A trivial gold standard. <!-- vocab-ok: trivial # quoting -->\n")
    assert ids(hits) == ["golden-set"]


def test_star_suppresses_everything_on_the_line():
    hits, _ = scan("A trivial gold standard. <!-- vocab-ok: * # this table quotes its own bans -->\n")
    assert hits == []


def test_multiple_ids():
    hits, _ = scan("A trivial gold standard. <!-- vocab-ok: trivial, golden-set # quoting -->\n")
    assert hits == []


def test_reason_is_required():
    hits, _ = scan("The golden set. <!-- vocab-ok: golden-set -->\n")
    assert ids(hits) == ["golden-set", "vocab-ok"]


def test_unknown_rule_id_is_reported():
    hits, _ = scan("Fine sentence. <!-- vocab-ok: no-such-rule # typo -->\n")
    assert ids(hits) == ["vocab-ok"]
    assert "unknown rule" in hits[0].message


def test_suppression_inside_a_fence_is_only_an_example():
    hits, sup = scan("""
        The golden set.

        ```
        <!-- vocab-ok: golden-set # how you would allow it -->
        ```
        """)
    assert ids(hits) == ["golden-set"]
    assert sup == []


def test_stale_suppression_is_reported():
    hits, sup = scan("Nothing to excuse here. <!-- vocab-ok: golden-set # stale -->\n")
    assert hits == []
    assert [s.used for s in sup] == [False]


def test_reason_may_mention_the_banned_term():
    hits, sup = scan(
        "The Core Set. <!-- vocab-ok: golden-set # was called the golden set until 2026-08-27 -->\n")
    assert hits == []
    assert sup == [] or [s.used for s in sup] == [False]


# --------------------------------------------------------------------- CLI --

def run_main(body: str, *args) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.md"
        page.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = vc.main([str(page), *args])
        return code, out.getvalue()


def test_exit_clear():
    code, out = run_main("Flagged `Fail` on GC content.\n")
    assert code == 0 and "clear" in out


def test_exit_on_error():
    code, out = run_main("The golden set.\n")
    assert code == 1 and "golden-set" in out and "1 error" in out


def test_warnings_do_not_fail_by_default():
    code, out = run_main("The dataset is clean.\n")
    assert code == 0 and "1 warning" in out


def test_strict_fails_on_warnings():
    code, _ = run_main("The dataset is clean.\n", "--strict")
    assert code == 1


def test_github_annotations():
    code, out = run_main("The golden set.\n", "--github")
    assert code == 1
    assert out.startswith("::error file=")
    assert ",line=1,col=5::golden-set:" in out


def test_missing_path_is_not_an_error():
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = vc.main(["docs/does-not-exist-yet"])
    assert code == 0


# ------------------------------------------------------------------- rules --

def test_every_rule_is_documented_in_vocabulary_md():
    prose = (vc.REPO_ROOT / "VOCABULARY.md").read_text(encoding="utf-8")
    missing = [r.id for r in RULES
               if not any(w in prose.lower() for w in r.id.split("-"))]
    assert not missing, f"rules with no counterpart in VOCABULARY.md: {missing}"


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failed.append((name, exc))
            print(f"FAIL {name}: {exc}")
        except Exception as exc:                      # noqa: BLE001
            failed.append((name, exc))
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
