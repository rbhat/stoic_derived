"""`repair_records.py --restrip` — re-derive stored `ocr_text` through the
current `_strip_axis_ladders`.

This is a reprocessing operation, not a repair: it asserts nothing about what
the chart shows, so it needs no JPEG ground truth. The record invariant it must
preserve is set by `visual_extract._build_ok_record`:

    ocr_text          the stripped text
    ocr_text_raw      the model's original output, present iff the filter fired
    axis_lines_stripped   how many lines it removed, present iff > 0
    unreadable_lines / ocr_line_count   both derived from the STRIPPED text

Deriving from `ocr_text_raw` rather than from `ocr_text` is what makes it
idempotent, and is the difference between a re-strip and a line deletion.
"""

from __future__ import annotations

import pytest

AXIS = "Nov 11 18 25 Dec 9 16 23 30 2025 13 21 27 Feb 10 18 24 Mar 10 17 24 31 Apr 14 21 28 May"
HEADER = "NASDAQ 100 E-mini Futures · 1W · CME"


@pytest.fixture
def restrip(repair_records):
    return repair_records.restrip_record


def _rec(**kw):
    base = {"id": "v#0001", "ocr_text": "", "unreadable_lines": 0, "ocr_line_count": 0}
    base.update(kw)
    return base


class TestRestrip:
    def test_strips_an_inline_axis_the_original_run_missed(self, restrip):
        rec = _rec(ocr_text=f"{HEADER}\n{AXIS}", ocr_line_count=2)
        rec, change = restrip(dict(rec))
        assert rec["ocr_text"] == HEADER
        assert rec["axis_lines_stripped"] == 1
        assert rec["ocr_line_count"] == 1
        assert change is not None
        assert change["lines_removed"] == 1

    def test_records_the_original_text_as_raw_when_it_first_fires(self, restrip):
        rec = _rec(ocr_text=f"{HEADER}\n{AXIS}", ocr_line_count=2)
        rec, _ = restrip(rec)
        assert rec["ocr_text_raw"] == f"{HEADER}\n{AXIS}"

    def test_re_derives_from_raw_not_from_the_already_stripped_text(self, restrip):
        """The run rule removed 4 price lines at extraction time. The re-strip
        must count 5 removed in total, not 1, and must leave raw untouched."""
        raw = "\n".join([HEADER, "25,900.00", "25,800.00", "25,700.00", "25,600.00", AXIS])
        rec = _rec(ocr_text=f"{HEADER}\n{AXIS}", ocr_text_raw=raw,
                   axis_lines_stripped=4, ocr_line_count=2)
        rec, change = restrip(rec)
        assert rec["ocr_text"] == HEADER
        assert rec["ocr_text_raw"] == raw
        assert rec["axis_lines_stripped"] == 5
        assert change["lines_removed"] == 1  # newly removed, beyond the stored 4

    def test_is_idempotent(self, restrip):
        rec = _rec(ocr_text=f"{HEADER}\n{AXIS}", ocr_line_count=2)
        once, first = restrip(dict(rec))
        twice, second = restrip(dict(once))
        assert first is not None
        assert second is None, "a second pass must report no change"
        assert twice == once

    def test_reports_no_change_when_there_is_nothing_to_strip(self, restrip):
        rec = _rec(ocr_text="PDH\nPDL", ocr_line_count=2)
        out, change = restrip(dict(rec))
        assert change is None
        assert out == rec

    def test_recomputes_unreadable_lines_from_the_stripped_text(self, restrip):
        rec = _rec(ocr_text=f"[unreadable]\n{HEADER}\n{AXIS}", ocr_line_count=3)
        rec, _ = restrip(rec)
        assert rec["unreadable_lines"] == 1
        assert rec["ocr_line_count"] == 2

    def test_keeps_the_before_text_in_the_change_so_it_is_reversible(self, restrip):
        rec = _rec(ocr_text=f"{HEADER}\n{AXIS}", ocr_line_count=2)
        _, change = restrip(rec)
        assert change["before"]["ocr_text"] == f"{HEADER}\n{AXIS}"
        assert change["id"] == "v#0001"

    def test_leaves_an_error_record_with_no_ocr_text_alone(self, restrip):
        rec = {"id": "v#0002", "status": "error"}
        out, change = restrip(dict(rec))
        assert change is None
        assert out == rec


class TestRestripDoesNotUndoTokenRepairs:
    """`ocr_text_raw` is the model's untouched output, so it still says `RHOW`
    after the rhow-to-phow repair rewrote `ocr_text`. Re-deriving from raw
    therefore resurrects the wrong token unless the token table is re-applied
    on top -- which would silently revert a repair backed by 20 read JPEGs, and
    on `cs_vol1#0369` would delete a label the repair recovered.

    `ocr_text` is defined as strip(raw) with the token table applied, so the
    two operations compose in either order.
    """

    def test_does_not_resurrect_a_repaired_token(self, repair_records):
        rec = {
            "id": "cs_vol1_stoic_edge_in_action_case_studies#0365",
            "video": "cs_vol1_stoic_edge_in_action_case_studies",
            "ocr_text": f"PHOW 74,100.00\n{AXIS}",
            "ocr_text_raw": f"RHOW 74,100.00\n{AXIS}",
            "ocr_line_count": 2,
        }
        out, _ = repair_records.restrip_record(rec)
        assert "RHOW" not in out["ocr_text"]
        assert out["ocr_text"] == "PHOW 74,100.00"
        assert out["ocr_text_raw"] == f"RHOW 74,100.00\n{AXIS}", "raw stays pristine"

    def test_reports_no_change_when_only_the_repaired_token_differs(self, repair_records):
        """A record the repair already fixed and that has no axis to strip must
        come back unchanged, not rewritten."""
        rec = {
            "id": "cs_vol1_stoic_edge_in_action_case_studies#0380",
            "video": "cs_vol1_stoic_edge_in_action_case_studies",
            "ocr_text": "PHOW 74,100.00",
            "ocr_text_raw": "RHOW 74,100.00",
            "ocr_line_count": 1,
        }
        out, change = repair_records.restrip_record(rec)
        assert change is None
        assert out["ocr_text"] == "PHOW 74,100.00"

    def test_a_repair_scoped_to_another_video_is_not_applied(self, repair_records):
        rec = {
            "id": "concept_htf_stoic_trader_protocol#0001",
            "video": "concept_htf_stoic_trader_protocol",
            "ocr_text": f"RHOW 74,100.00\n{AXIS}",
            "ocr_line_count": 2,
        }
        out, _ = repair_records.restrip_record(rec)
        assert out["ocr_text"] == "RHOW 74,100.00", "scope is per-video"
