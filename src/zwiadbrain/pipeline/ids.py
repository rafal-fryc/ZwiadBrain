"""Shared bill-id parser.

``bill.id`` is ``"{congress}-{type}-{number}"`` where ``<type>`` may itself
contain no hyphens (hr, s, hjres, sjres, hconres, sconres, hres, sres).
Congress is always an integer and number is always the trailing segment, so we
split on the FIRST and LAST hyphen to stay robust against multi-character types.

This is the single hardened parser for the whole project: ``leg_history`` and
the CLI both call it.  A malformed id is a configuration/data error, so it
raises :class:`ConfigError` (an :class:`AppError`) rather than a bare
``ValueError`` that would escape the CLI's ``except AppError`` boundary.
"""

from __future__ import annotations

from zwiadbrain.exceptions import ConfigError


def parse_bill_id(bill_id: str) -> tuple[int, str, str]:
    """Parse ``bill.id`` into ``(congress: int, bill_type: str, number: str)``.

    Example::

        parse_bill_id("118-hr-9020")   # -> (118, "hr", "9020")
        parse_bill_id("118-hjres-45")  # -> (118, "hjres", "45")

    Raises :class:`ConfigError` when *bill_id* does not have three
    hyphen-separated segments, or when the congress segment is not an integer.
    """
    first_dash = bill_id.find("-")
    last_dash = bill_id.rfind("-")
    if first_dash == -1 or first_dash == last_dash:
        raise ConfigError(
            f"bill.id must be '<congress>-<type>-<number>', got: {bill_id!r}"
        )
    bill_type = bill_id[first_dash + 1 : last_dash]
    number = bill_id[last_dash + 1 :]
    if not bill_type or not number:
        raise ConfigError(
            f"bill.id must be '<congress>-<type>-<number>', got: {bill_id!r}"
        )
    try:
        congress = int(bill_id[:first_dash])
    except ValueError as exc:
        raise ConfigError(
            f"bill.id congress segment must be an integer, got: {bill_id!r}"
        ) from exc
    return congress, bill_type, number
