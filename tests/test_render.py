"""Tests for page rendering: model -> Markdown page, path routing, idempotent writes."""

import datetime as dt
from pathlib import Path

from zwiadbrain.models import (
    Action,
    Amendment,
    Bill,
    CommentarySource,
    Enactment,
    EnforcementAction,
    FloorAction,
    Hearing,
    LegHistory,
    Statement,
    TextVersion,
    Vote,
)
from zwiadbrain.pipeline.render import page_path, render_page, write_page
from zwiadbrain.wiki.schema import from_page
from zwiadbrain.wiki.templates import render_bill_body


def _bill() -> Bill:
    return Bill(
        id="us-ca-sb-362",
        jurisdiction="US-CA",
        title="California Delete Act",
        bill_number="SB 362",
        status="enrolled",
        introduced_date=dt.date(2023, 2, 10),
        summary="Creates a one-stop deletion mechanism for data brokers.",
        actions=[Action(text="Introduced", date=dt.date(2023, 2, 10), chamber="Senate")],
        amendments=[Amendment(number="A1", what_changed="Narrowed broker definition.")],
        sources={"LegiScan": "https://legiscan.com/CA/bill/SB362"},
    )


def test_render_page_includes_frontmatter_and_required_sections() -> None:
    """should emit a frontmatter block plus the standard bill body sections"""
    page = render_page(_bill())
    assert page.startswith("---")
    assert "California Delete Act" in page
    assert "## Summary" in page
    assert "## Status & Timeline" in page
    assert "## Amendments" in page
    assert "## Sources" in page


def test_render_page_frontmatter_round_trips_to_model() -> None:
    """should produce frontmatter that parses back into the same kind of model"""
    item = from_page(render_page(_bill()))
    assert isinstance(item, Bill)
    assert item.bill_number == "SB 362"


def test_render_page_omits_empty_sections() -> None:
    """should not emit headers for sections with no content"""
    page = render_page(Bill(id="x", jurisdiction="US-CA", title="t", bill_number="SB 1"))
    assert "## Status & Timeline" not in page
    assert "## Commentary & Analysis" not in page


def test_render_page_is_deterministic() -> None:
    """should render the same model to identical bytes (idempotency)"""
    bill = _bill()
    assert render_page(bill) == render_page(bill)


def test_commentary_section_demotes_headings_and_fences_with_markers() -> None:
    """should fence each copied page with begin/end markers and demote its headings"""
    bill = _bill()
    bill.commentary_sources = [
        CommentarySource(
            path="wiki/regulation-california-delete-act.md",
            slug="regulation-california-delete-act",
            updated=dt.date(2026, 5, 6),
            content_hash="h",
            matched_by="deterministic",
            confidence=1.0,
            body="## Summary\n\nThe Delete Act created DROP.",
        )
    ]
    page = render_page(bill)
    assert "## Commentary & Analysis" in page
    assert "<!-- lawbrain:begin slug=regulation-california-delete-act -->" in page
    assert "<!-- lawbrain:end slug=regulation-california-delete-act -->" in page
    assert "### Summary" in page  # the copied body's ## heading is demoted to ###


def test_page_path_routes_by_jurisdiction_and_type(tmp_path: Path) -> None:
    """should route to federal/state and bills/enforcement directories by id"""
    assert page_path(_bill(), tmp_path) == tmp_path / "states" / "ca" / "bills" / "us-ca-sb-362.md"
    fed = Bill(id="hr-1", jurisdiction="US", title="t", bill_number="HR 1")
    assert page_path(fed, tmp_path) == tmp_path / "federal" / "bills" / "hr-1.md"
    enf = EnforcementAction(id="ftc-x", jurisdiction="US", title="t", agency="FTC")
    assert page_path(enf, tmp_path) == tmp_path / "federal" / "enforcement" / "ftc-x.md"


def test_write_page_is_idempotent(tmp_path: Path) -> None:
    """should write on first call, skip the rewrite when content is unchanged"""
    bill = _bill()
    assert write_page(bill, tmp_path) is True
    assert write_page(bill, tmp_path) is False
    path = page_path(bill, tmp_path)
    assert path.read_text(encoding="utf-8") == render_page(bill)


# ---------------------------------------------------------------------------
# Legislative History rendering tests (Phase 05)
# ---------------------------------------------------------------------------


def _bill_with_full_leg_history() -> Bill:
    """A Bill with every LegHistory subsection populated for rendering tests."""
    from zwiadbrain.models import StatutesAtLarge
    return Bill(
        id="hr-1-full",
        jurisdiction="US",
        title="Full History Bill",
        bill_number="HR 1",
        leg_history=LegHistory(
            narrative="This bill started as a narrow measure and was expanded significantly.",
            versions=[
                TextVersion(
                    code="ENR",
                    date=dt.date(2024, 3, 1),
                    url="https://congress.gov/bill/hr-1/text/enr",
                ),
            ],
            committee_reports=[],
            hearings=[
                Hearing(
                    title="Hearing on HR 1",
                    committee="House Judiciary",
                    date=dt.date(2024, 1, 10),
                    url="https://congress.gov/hearing/hr-1",
                ),
            ],
            floor_consideration=[
                FloorAction(
                    date=dt.date(2024, 2, 5),
                    chamber="House",
                    congressional_record="H. Res. 42",
                    url="https://congress.gov/crec/2024/02/05",
                ),
            ],
            votes=[
                Vote(
                    date=dt.date(2024, 2, 5),
                    chamber="House",
                    result="Passed 250-180",
                    roll_call_url="https://clerk.house.gov/votes/2024/rc001",
                ),
            ],
            conference=None,
            enactment=Enactment(
                date_signed=dt.date(2024, 3, 15),
                public_law="P.L. 118-1",
                statutes_at_large=StatutesAtLarge(citation="138 Stat. 1", url="https://www.govinfo.gov/app/details/STATUTE-138-Pg1"),
                url="https://congress.gov/public-law/118/1",
            ),
            statements=[
                Statement(
                    speaker="Rep. Smith",
                    role="sponsor",
                    date=dt.date(2024, 2, 5),
                    quote="This bill will protect consumers.",
                    source_url="https://congress.gov/crec/smith-statement",
                    source_type="CREC",
                    verified=True,
                ),
                Statement(
                    speaker="Rep. Jones",
                    role="member",
                    date=dt.date(2024, 2, 5),
                    quote="I support this legislation.",
                    source_url="https://congress.gov/crec/jones-statement",
                    source_type="CREC",
                    verified=False,
                ),
            ],
        ),
    )


def test_leg_history_all_subsections_render_links() -> None:
    """should render a Markdown link for each verifiable subsection item"""
    bill = _bill_with_full_leg_history()
    body = render_bill_body(bill)

    # Version link
    assert "](https://congress.gov/bill/hr-1/text/enr)" in body
    # Hearing link
    assert "](https://congress.gov/hearing/hr-1)" in body
    # Floor consideration Congressional Record as link
    assert "](https://congress.gov/crec/2024/02/05)" in body
    # Vote roll call link
    assert "](https://clerk.house.gov/votes/2024/rc001)" in body
    # Enactment public law link
    assert "](https://congress.gov/public-law/118/1)" in body
    # Both statement links
    assert "](https://congress.gov/crec/smith-statement)" in body
    assert "](https://congress.gov/crec/jones-statement)" in body


def test_leg_history_verified_statement_ends_with_checkmark() -> None:
    """should append ✓ to verified statement lines and omit it from unverified ones"""
    body = render_bill_body(_bill_with_full_leg_history())
    lines = body.splitlines()
    smith_lines = [line for line in lines if "Rep. Smith" in line]
    jones_lines = [line for line in lines if "Rep. Jones" in line]
    assert smith_lines, "Rep. Smith statement not found"
    assert jones_lines, "Rep. Jones statement not found"
    smith_line = smith_lines[0]
    jones_line = jones_lines[0]
    assert smith_line.endswith(" ✓"), f"verified statement should end with ✓: {smith_line!r}"
    assert "✓" not in jones_line, f"unverified statement should not contain ✓: {jones_line!r}"


def test_leg_history_narrative_appears_under_legislative_journey() -> None:
    """should render narrative prose under the ### Legislative Journey sub-heading"""
    body = render_bill_body(_bill_with_full_leg_history())
    assert "### Legislative Journey" in body
    assert "started as a narrow measure" in body


def test_leg_history_hearing_without_url_is_omitted() -> None:
    """should skip a hearing that has no url (not verifiable)"""
    bill = Bill(
        id="hr-2",
        jurisdiction="US",
        title="No-URL Hearing Bill",
        bill_number="HR 2",
        leg_history=LegHistory(
            hearings=[
                Hearing(title="Secret Hearing", committee="Ways and Means", url=None),
                Hearing(
                    title="Public Hearing",
                    committee="Judiciary",
                    url="https://congress.gov/hearing/public",
                ),
            ],
        ),
    )
    body = render_bill_body(bill)
    assert "Secret Hearing" not in body
    assert "Public Hearing" in body


def test_leg_history_statement_without_source_url_is_omitted() -> None:
    """should skip a statement that has no source_url (not verifiable)"""
    bill = Bill(
        id="hr-3",
        jurisdiction="US",
        title="No-URL Statement Bill",
        bill_number="HR 3",
        leg_history=LegHistory(
            statements=[
                Statement(
                    speaker="Rep. Anonymous",
                    role="member",
                    quote="Words.",
                    source_url="",
                    source_type="other",
                ),
                Statement(
                    speaker="Rep. Cited",
                    role="member",
                    quote="Cited words.",
                    source_url="https://congress.gov/cited",
                    source_type="CREC",
                ),
            ],
        ),
    )
    body = render_bill_body(bill)
    assert "Rep. Anonymous" not in body
    assert "Rep. Cited" in body


def test_leg_history_byte_identical_re_render() -> None:
    """should produce identical output on two consecutive renders of the same bill"""
    bill = _bill_with_full_leg_history()
    assert render_bill_body(bill) == render_bill_body(bill)


def test_leg_history_subsection_order() -> None:
    """should emit subsections in the pinned order: Journey→Versions→Hearings→…→Statements"""
    body = render_bill_body(_bill_with_full_leg_history())
    idx_journey = body.index("### Legislative Journey")
    idx_versions = body.index("### Versions")
    idx_hearings = body.index("### Hearings")
    idx_floor = body.index("### Floor Consideration")
    idx_votes = body.index("### Votes")
    idx_enactment = body.index("### Enactment")
    idx_statements = body.index("### Statements")
    assert idx_journey < idx_versions < idx_hearings < idx_floor
    assert idx_floor < idx_votes < idx_enactment < idx_statements


def test_leg_history_floor_action_plain_text_when_no_url() -> None:
    """should render floor action as plain text when url is absent"""
    bill = Bill(
        id="hr-4",
        jurisdiction="US",
        title="Plain Floor Bill",
        bill_number="HR 4",
        leg_history=LegHistory(
            floor_consideration=[
                FloorAction(
                    date=dt.date(2024, 2, 5),
                    chamber="House",
                    congressional_record="H. Res. 99",
                    url=None,
                ),
            ],
        ),
    )
    body = render_bill_body(bill)
    assert "H. Res. 99" in body
    # No markdown link syntax around it
    assert "](None)" not in body
    assert "[H. Res. 99]" not in body


def test_leg_history_vote_plain_text_when_no_roll_call_url() -> None:
    """should render vote result as plain text when roll_call_url is absent"""
    bill = Bill(
        id="hr-5",
        jurisdiction="US",
        title="Plain Vote Bill",
        bill_number="HR 5",
        leg_history=LegHistory(
            votes=[
                Vote(
                    date=dt.date(2024, 2, 5),
                    chamber="House",
                    result="Passed 300-120",
                    roll_call_url=None,
                ),
            ],
        ),
    )
    body = render_bill_body(bill)
    assert "Passed 300-120" in body
    assert "[roll call]" not in body


def test_leg_history_enactment_with_url_and_no_public_law() -> None:
    """should render 'Public law document' as link text when public_law is empty but url present"""
    bill = Bill(
        id="hr-6",
        jurisdiction="US",
        title="URL-only Enactment Bill",
        bill_number="HR 6",
        leg_history=LegHistory(
            enactment=Enactment(
                date_signed=dt.date(2024, 3, 15),
                public_law=None,
                url="https://congress.gov/public-law/118/99",
            ),
        ),
    )
    body = render_bill_body(bill)
    assert "[Public law document](https://congress.gov/public-law/118/99)" in body


def _vote_section_lines(bill: Bill) -> list[str]:
    """Return the bullet lines under the ### Votes sub-heading of a rendered bill."""
    body = render_bill_body(bill)
    return [line for line in body.splitlines() if line.startswith("- ") and "Passed" in line]


def test_leg_history_vote_without_chamber_has_no_bare_separator() -> None:
    """should not emit a bare ' :' or double spaces when chamber is missing"""
    bill = Bill(
        id="hr-7",
        jurisdiction="US",
        title="No-chamber Vote Bill",
        bill_number="HR 7",
        leg_history=LegHistory(
            votes=[Vote(date=dt.date(2024, 2, 5), chamber=None, result="Passed 1-0")],
        ),
    )
    lines = _vote_section_lines(bill)
    assert lines == ["- 2024-02-05: Passed 1-0"]
    assert " :" not in lines[0]
    assert "  " not in lines[0]


def test_leg_history_vote_without_date_or_chamber_has_no_bare_separator() -> None:
    """should render only the result when both date and chamber are missing"""
    bill = Bill(
        id="hr-8",
        jurisdiction="US",
        title="Result-only Vote Bill",
        bill_number="HR 8",
        leg_history=LegHistory(
            votes=[
                Vote(
                    date=None,
                    chamber=None,
                    result="Passed 2-0",
                    roll_call_url="https://clerk.house.gov/votes/rc009",
                ),
            ],
        ),
    )
    body = render_bill_body(bill)
    assert "- Passed 2-0 — [roll call](https://clerk.house.gov/votes/rc009)" in body
    assert " :" not in body
    assert "-  " not in body


def test_leg_history_floor_action_without_date_or_chamber_has_no_leading_dash() -> None:
    """should render only the linked CR citation when date and chamber are missing"""
    bill = Bill(
        id="hr-9",
        jurisdiction="US",
        title="CR-only Floor Bill",
        bill_number="HR 9",
        leg_history=LegHistory(
            floor_consideration=[
                FloorAction(
                    date=None,
                    chamber=None,
                    congressional_record=None,
                    url="https://congress.gov/crec/2024/03/01",
                ),
            ],
        ),
    )
    body = render_bill_body(bill)
    assert "- [Congressional Record](https://congress.gov/crec/2024/03/01)" in body
    # No leading em-dash / stray separator before the citation
    assert "-  — " not in body
    assert "- — " not in body


def test_leg_history_floor_action_without_date_or_chamber_with_cr_text() -> None:
    """should link the CR citation text with no leading separator when date/chamber missing"""
    bill = Bill(
        id="hr-10",
        jurisdiction="US",
        title="CR-text-only Floor Bill",
        bill_number="HR 10",
        leg_history=LegHistory(
            floor_consideration=[
                FloorAction(
                    date=None,
                    chamber=None,
                    congressional_record="H. Rec. 5",
                    url="https://congress.gov/crec/h5",
                ),
            ],
        ),
    )
    body = render_bill_body(bill)
    assert "- [H. Rec. 5](https://congress.gov/crec/h5)" in body
    assert "- — " not in body


def test_render_emits_flipped_out_marker_when_set() -> None:
    """should prepend an HTML comment marker to the body when bill.flipped_out is set"""
    from zwiadbrain.models import FlipOutAudit

    bill = Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="x",
        bill_number="H.R. 1",
        summary="A short summary.",
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason="classifier: drift"),
    )
    body = render_bill_body(bill)
    first_line = body.split("\n", 1)[0]
    assert first_line.startswith("<!-- zwiadbrain:flipped-out ")
    assert 'date="2026-06-04"' in first_line
    assert 'reason="classifier: drift"' in first_line


def test_render_omits_marker_when_not_flipped() -> None:
    """should not emit the marker for a normally-tracked bill"""
    bill = Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="x",
        bill_number="H.R. 1",
        summary="A short summary.",
    )
    body = render_bill_body(bill)
    assert "<!-- zwiadbrain:flipped-out" not in body


def test_render_escapes_quote_in_flip_reason() -> None:
    """should escape a double-quote inside the reason so the HTML comment stays valid"""
    from zwiadbrain.models import FlipOutAudit

    bill = Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="x",
        bill_number="H.R. 1",
        flipped_out=FlipOutAudit(
            date=dt.date(2026, 6, 4), reason='he said "AI" out of scope'
        ),
    )
    body = render_bill_body(bill)
    first_line = body.split("\n", 1)[0]
    # backslash-escape inside double-quoted attribute
    assert 'reason="he said \\"AI\\" out of scope"' in first_line


def test_render_emits_statutes_at_large_link() -> None:
    """should render the StatutesAtLarge as a markdown link in the Enactment block"""
    from zwiadbrain.models import Enactment, StatutesAtLarge

    bill = Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="x",
        bill_number="H.R. 1",
        leg_history=LegHistory(
            enactment=Enactment(
                public_law="118-31",
                url="https://www.govinfo.gov/app/details/PLAW-118publ31",
                statutes_at_large=StatutesAtLarge(
                    citation="138 Stat. 1234",
                    url="https://www.govinfo.gov/app/details/STATUTE-138-Pg1234",
                ),
            ),
        ),
    )
    body = render_bill_body(bill)
    assert (
        "Statutes at Large: [138 Stat. 1234]"
        "(https://www.govinfo.gov/app/details/STATUTE-138-Pg1234)"
    ) in body


def test_render_escapes_html_comment_terminator_in_flip_reason() -> None:
    """should escape --> to --&gt; so the HTML comment isn't terminated mid-reason"""
    from zwiadbrain.models import FlipOutAudit

    bill = Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="x",
        bill_number="H.R. 1",
        flipped_out=FlipOutAudit(
            date=dt.date(2026, 6, 4),
            reason="AI clause --> removed in markup",
        ),
    )
    body = render_bill_body(bill)
    first_line = body.split("\n", 1)[0]
    # The marker must end with the comment terminator exactly once, at the end.
    assert first_line.endswith(" -->")
    assert first_line.count("-->") == 1
    # The sequence inside the reason must be escaped.
    assert "AI clause --&gt; removed in markup" in first_line
