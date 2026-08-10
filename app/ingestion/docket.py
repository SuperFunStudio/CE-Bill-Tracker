"""Pre-filing DOCKET numbers vs. real bill numbers.

Massachusetts and Kentucky assign an identifier at *filing* that is not yet a bill number:
MA gives every filing a House/Senate Docket number (``HD-3107`` / ``SD-2101``) and KY a Bill
Request (``BR-342``). On referral the same text is renumbered — ``HD-3107`` becomes ``H-988``,
``BR-342`` becomes an ``HB``. OpenStates publishes BOTH records, so the corpus ends up holding the
docket shell and the filed bill as two rows with identical titles.

That double-count is only half the problem. A shell that was never referred has no actions at all,
so ``latest_action_date`` is NULL, so ``status_date`` is NULL (see coordinator._upsert_openstates_bill)
— and it lands in the "N bills carry no date" bucket of every year-bucketed view, reading as a
coverage gap when it is really a duplicate. 49 of the 51 dateless US rows in the corpus were exactly
this, each with a dated same-title sibling under its filed number.

The rule is deliberately NOT "drop anything with a docket prefix": a docket number that HAS recorded
action is a bill the legislature is genuinely moving under that identifier (19 in-scope rows sat at
``passed_chamber``/``in_committee`` with real dates). Only the action-less shell is suppressed, which
also makes the rule self-healing — the moment such a bill picks up its first action it stops matching
and is ingested normally.
"""
from __future__ import annotations

import re

# Docket/request prefixes, by the state that issues them. Scoped per-state on purpose: "BR" or "SD"
# could plausibly be a real bill series in another chamber, and a blanket prefix match would then
# silently shed real bills.
DOCKET_PREFIXES: dict[str, tuple[str, ...]] = {
    "MA": ("HD", "SD"),
    "KY": ("BR",),
}

_DOCKET_RE = {
    state: re.compile(rf"^({'|'.join(pfx)})-\d+$", re.IGNORECASE)
    for state, pfx in DOCKET_PREFIXES.items()
}


def is_docket_shell(state: str | None, bill_number: str | None, last_action_date) -> bool:
    """True for a pre-filing docket identifier that has no recorded legislative action.

    `last_action_date` is the source's latest-action date (None when the source reports no actions).
    """
    if last_action_date is not None:
        return False
    pattern = _DOCKET_RE.get((state or "").upper())
    return bool(pattern and pattern.match((bill_number or "").strip()))
