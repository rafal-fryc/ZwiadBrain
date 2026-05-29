import datetime as dt

from zwiadbrain.models import EnforcementAction, EnforcementDevelopment, parse_wiki_item


def test_enforcement_action_accepts_developments() -> None:
    action = EnforcementAction(
        id="ftc-c-4790",
        jurisdiction="US",
        title="FTC v. Acme",
        agency="FTC",
        respondent="Acme, Inc.",
        developments=[
            EnforcementDevelopment(
                date=dt.date(2025, 1, 2),
                summary="Complaint filed.",
                source_url="https://www.ftc.gov/x",
            )
        ],
    )
    assert action.developments[0].summary == "Complaint filed."


def test_parse_wiki_item_routes_enforcement_with_developments() -> None:
    data = {
        "id": "ftc-c-4790", "type": "enforcement", "jurisdiction": "US",
        "title": "FTC v. Acme", "agency": "FTC",
        "developments": [
            {"date": "2025-01-02", "summary": "Complaint filed.",
             "source_url": "https://www.ftc.gov/x"}
        ],
    }
    item = parse_wiki_item(data)
    assert isinstance(item, EnforcementAction)
    assert item.developments[0].date == dt.date(2025, 1, 2)


def test_enforcement_development_rejects_non_http_url() -> None:
    import pytest
    with pytest.raises(ValueError):
        EnforcementDevelopment(summary="x", source_url="ftp://nope")
