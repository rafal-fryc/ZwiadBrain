import pytest

from zwiadbrain.pipeline.ids import build_enforcement_id, parse_strong_key


@pytest.mark.parametrize("text,expected", [
    ("In FTC v. Acme, No. 2:25-cv-12295 (N.D. Cal.)", "2-25-cv-12295"),
    ("FTC Matter, Docket No. C-4790", "c-4790"),
    ("Administrative Docket D-9447 issued", "d-9447"),
    ('FTC, File No. 2023155, announced', "2023155"),
    ("No identifiers in this press release at all.", None),
])
def test_parse_strong_key(text: str, expected: str | None) -> None:
    assert parse_strong_key(text) == expected


def test_parse_strong_key_prefers_court_docket_over_file_number() -> None:
    text = "FTC v. Acme, No. 2:25-cv-12295; File No. 2023155"
    assert parse_strong_key(text) == "2-25-cv-12295"


def test_build_enforcement_id_with_strong_key() -> None:
    assert (
        build_enforcement_id("ftc", strong_key="c-4790", respondent="Acme", year=2025)
        == "ftc-c-4790"
    )
    assert (
        build_enforcement_id("ca-oag", strong_key="2:25-cv-12295", respondent="Acme", year=2025)
        == "ca-oag-2-25-cv-12295"
    )


def test_build_enforcement_id_fallback_respondent_year() -> None:
    assert build_enforcement_id("ftc", strong_key=None, respondent="Acme Data Brokers, Inc.",
                                year=2025) == "ftc-2025-acme-data-brokers"


def test_build_enforcement_id_disambiguates_collision() -> None:
    existing = {"ftc-2025-acme"}
    assert build_enforcement_id("ftc", strong_key=None, respondent="Acme", year=2025,
                                existing_ids=existing) == "ftc-2025-acme-2"


def test_enforcement_id_never_collides_with_bill_ids() -> None:
    eid = build_enforcement_id("ca-oag", strong_key=None, respondent="DoorDash", year=2025)
    assert eid == "ca-oag-2025-doordash"
    assert eid != "ca-2025-sb-53"  # state bill id shape; second segment differs (oag vs year)
