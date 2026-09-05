"""The joint reading, and the two things it must never be shown without.

The joint AUROC is the one number on this site the audit did not compute, the one
measured somewhere other than the reference split, and the one a stale consumer
would actively misread. So it gets its own file: what it is, where it has to
appear, and the caveat that is not separable from it.
"""

from __future__ import annotations

import re
from pathlib import Path

from gb_audit import audit


def test_every_dataset_the_selection_saw_carries_its_verdicts(run):
    """The two tables cover one corpus, or a dataset page renders an absence.

    `audit.read` already refuses a run where they do not, so this asserts the
    thing that refusal is for rather than the refusal.
    """
    for dataset in run.datasets.values():
        assert set(dataset.gates) == set(audit.GATES), dataset.benchmark_id


def test_only_a_dataset_with_no_held_out_split_lacks_a_joint_reading(run):
    """An absent joint figure means one thing, and the run has to agree it does.

    The site says "no held-out split to score one on" wherever the figure is
    missing. If a joint reading ever went missing for some other reason, that
    sentence would be a claim about the data rather than a description of it.
    """
    for dataset in run.datasets.values():
        if dataset.joint is not None:
            continue
        held_out = [s for s in dataset.splits if s.split != "train"]
        assert not held_out or dataset.reference_split != "train", dataset.benchmark_id


def test_a_lower_bound_always_says_why(run):
    """`lower_bound` and `caveat` travel together in both directions.

    A marked figure with no reason is a mark a reader cannot act on; a reason on
    an unmarked figure is a caveat attached to a number it does not qualify.
    """
    for dataset in run.datasets.values():
        joint = dataset.joint
        if joint is None:
            continue
        assert joint.lower_bound == bool(joint.caveat), dataset.benchmark_id


def test_the_joint_gate_is_the_only_step_admitting_lower_bounds(run):
    """The funnel's note is on the step whose number it qualifies.

    A count of admitted lower bounds under the separability step would be a
    qualification of the wrong cut.
    """
    noted = [gate.criterion for gate in run.gates if gate.note]
    assert noted == ["joint"]


def test_clean_but_joint_is_exactly_what_the_run_recorded(run):
    """No check returned Fail, and the same features together recovered it.

    Read off `excluded_by` rather than from the per-gate columns, because those
    are each criterion taken alone: a dataset removed on leakage can still carry a
    passing separability gate, and testing them directly would count it here.
    """
    found = {d.benchmark_id for d in run.datasets.values() if d.clean_but_joint}
    for benchmark_id in found:
        dataset = run.datasets[benchmark_id]
        assert "Fail" not in dataset.flags.values(), benchmark_id
        assert dataset.joint is not None and dataset.joint.au_roc >= 0.8, benchmark_id
    assert found, "the corpus holds six of these; none is a broken join"


def test_every_dataset_page_states_the_joint_reading(built, committed):
    """The manuscript's own minimum scope for this site.

    "The joint QC-feature AUROC beside the per-check flags on each dataset page,
    because after M27 that is the number Core Set membership turns on and the site
    is where a reader would check it."
    """
    out = Path(built["out"])
    for dataset in committed["datasets"]:
        page = (out / "datasets" / f"{dataset['slug']}.html").read_text()
        assert 'id="joint"' in page, dataset["benchmark_id"]
        joint = dataset["joint"]
        if joint is None:
            # One dataset ships a single split, so there is nothing held out to
            # score a joint model on. It has to say so rather than show a blank.
            assert "no held-out split" in page, dataset["benchmark_id"]
            continue
        assert f'{joint["auroc"]:.3f}' in page, dataset["benchmark_id"]
        assert f'<code>{joint["split"]}</code>' in page, dataset["benchmark_id"]


def test_no_lower_bound_is_ever_printed_bare(built, committed):
    """Where a joint figure is capped, the page that shows it says so.

    The direction is what makes this worth a test: a capped figure can only be too
    low, so a reader comparing one against the 0.80 ceiling and not told it is a
    bound would read it as clearing a line it may not clear.
    """
    out = Path(built["out"])
    for dataset in committed["datasets"]:
        joint = dataset["joint"]
        if joint is None or not joint["lower_bound"]:
            continue
        page = (out / "datasets" / f"{dataset['slug']}.html").read_text()
        assert joint["caveat"] in page, dataset["benchmark_id"]
        assert "lower bound" in page, dataset["benchmark_id"]

    # And on the Core Set page, where members sit in one column against a ceiling.
    core = (out / "core-set.html").read_text()
    for dataset in committed["datasets"]:
        joint = dataset["joint"]
        if not dataset["in_core_set"] or joint is None or not joint["lower_bound"]:
            continue
        assert 'class="lb"' in core, dataset["benchmark_id"]


def test_the_core_set_page_carries_the_finding_no_flag_can_show(built, committed):
    core = (out := Path(built["out"]), (out / "core-set.html").read_text())[1]
    removed = [d for d in committed["datasets"] if d["excluded_by"] == "joint"]
    assert len(removed) == committed["totals"]["n_clean_but_joint"]
    for dataset in removed:
        assert dataset["slug"] in core, dataset["benchmark_id"]
        assert f'{dataset["joint"]["auroc"]:.3f}' in core, dataset["benchmark_id"]
