"""`_strip_axis_ladders` — the multi-line ladder rule, and the one-line rule.

Every string here is a verbatim `ocr_text` line from
`.artifacts/research/visual/*/visual_records.jsonl`, with the frame id given so
the claim can be checked against the JPEG. The guard cases matter more than the
defect case: a date axis left in costs one furniture line, but a `DAY` row or a
crosshair date wrongly stripped destroys content that nothing downstream can
recover.
"""

from __future__ import annotations

# concept_candle_swing_theory_pdh_pdl_pdc#0574 -- the whole bottom date axis of a
# 1W NQ chart on a single line. 39 lines of price ladder were stripped from this
# same frame by the run rule; this line survived it.
CANDLE_0574_AXIS = (
    "Nov 11 18 25 Dec 9 16 23 30 2025 13 21 27 Feb 10 18 24 Mar 10 17 24 31 Apr 14 21 28 May"
)


class TestOneLineAxis:
    """The blind spot: an axis emitted as one line, which a run rule cannot see."""

    def test_strips_a_full_date_axis_emitted_as_one_line(self, visual_extract):
        text = "\n".join([
            "100 NASDAQ 100 E-mini Futures · 1W · CME",
            "O 25,863.25 H 25,893.75 L 25,265.25 C 25,394.50",
            "USD",
            CANDLE_0574_AXIS,
        ])
        cleaned, removed = visual_extract._strip_axis_ladders(text)
        assert CANDLE_0574_AXIS not in cleaned
        assert removed == 1
        assert "100 NASDAQ 100 E-mini Futures · 1W · CME" in cleaned

    def test_strips_a_bare_day_number_axis_with_no_month_token(self, visual_extract):
        # cs_vol2_nasdaq_range_study#0371 -- every-other-day ticks, no month name.
        line = "4 6 10 12 16 18 20 24 26"
        cleaned, removed = visual_extract._strip_axis_ladders(f"PDH\n{line}\nPDL")
        assert cleaned == "PDH\nPDL"
        assert removed == 1

    def test_strips_a_weekday_dated_axis(self, visual_extract):
        # concept_candle_swing_theory_pdh_pdl_pdc#0535
        line = "Mon 29 Dec '25 Tue 20 Jan '26"
        cleaned, _ = visual_extract._strip_axis_ladders(f"HCOM\n{line}")
        assert cleaned == "HCOM"


class TestContentIsNotStripped:
    """What the token threshold exists to protect. All verbatim from the corpus."""

    def test_keeps_a_diagram_day_row(self, visual_extract):
        # cs_vol1_stoic_edge_in_action_case_studies#0366 -- the DAY 1..5 row of a
        # diagram, which §4 already records as dropping off frames too often.
        text = "FIRST RED DAY\n1 2 3 4 5"
        cleaned, removed = visual_extract._strip_axis_ladders(text)
        assert cleaned == text
        assert removed == 0

    def test_keeps_a_crosshair_date_readout(self, visual_extract):
        # concept_candle_swing_theory_pdh_pdl_pdc#0539 -- names the date the
        # instructor is pointing at; the OHLC join reads these.
        text = "Mon 29 Dec '25"
        cleaned, removed = visual_extract._strip_axis_ladders(text)
        assert cleaned == text
        assert removed == 0

    def test_keeps_the_ohlc_header(self, visual_extract):
        # The frame-to-bar join is built on this line. Mostly digits, and long.
        text = "O 25,863.25 H 25,893.75 L 25,265.25 C 25,394.50"
        cleaned, removed = visual_extract._strip_axis_ladders(text)
        assert cleaned == text
        assert removed == 0

    def test_keeps_a_called_out_price_standing_alone(self, visual_extract):
        text = "PDC\n26,037.25\nThursday"
        cleaned, removed = visual_extract._strip_axis_ladders(text)
        assert cleaned == text
        assert removed == 0


class TestRunRuleStillHolds:
    """The existing multi-line behaviour must not change."""

    def test_strips_a_multi_line_price_ladder(self, visual_extract):
        text = "PDH\n25,900.00\n25,800.00\n25,700.00\n25,600.00\nPDL"
        cleaned, removed = visual_extract._strip_axis_ladders(text)
        assert cleaned == "PDH\nPDL"
        assert removed == 4

    def test_keeps_a_price_run_shorter_than_the_minimum(self, visual_extract):
        text = "PDH\n25,900.00\n25,800.00\n25,700.00\nPDL"
        cleaned, removed = visual_extract._strip_axis_ladders(text)
        assert cleaned == text
        assert removed == 0
