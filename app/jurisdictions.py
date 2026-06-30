"""Region + jurisdiction registry — the single source of truth for jurisdiction codes/names per region.

Replaces hardcoded US-state assumptions with a region-keyed map so the same code paths work for US
states, the EU (EU-wide + member states), and future regions (UK, …). Jurisdiction codes are the
`String(2)` values stored in `Bill.state` and the other `state` columns:
  - US:  two-letter state codes, plus the "US" sentinel for federal.
  - EU:  "EU" sentinel for EU-wide acts, plus ISO-2 member-state codes (ES, DE, FR, …) for Phase B.
Mirrored on the frontend by dashboard-next/src/lib/jurisdictions.ts — keep them in sync.
"""
from __future__ import annotations

# US states + DC. (Federal is the "US" sentinel, added under REGIONS below.)
US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}

# EU-27 member states (ISO-3166-1 alpha-2). "EU" sentinel (EU-wide acts) added under REGIONS below.
EU_MEMBERS: dict[str, str] = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus",
    "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia", "FI": "Finland", "FR": "France",
    "DE": "Germany", "GR": "Greece", "HU": "Hungary", "IE": "Ireland", "IT": "Italy",
    "LV": "Latvia", "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia",
    "ES": "Spain", "SE": "Sweden",
}

# region code -> {label, jurisdictions: {code: name}}. The jurisdiction map includes the region's
# own "whole-region" sentinel ("US" = federal, "EU" = EU-wide) so it's a valid stored value.
REGIONS: dict[str, dict] = {
    "US": {"label": "United States", "jurisdictions": {"US": "Federal", **US_STATES}},
    "EU": {"label": "European Union", "jurisdictions": {"EU": "EU-wide", **EU_MEMBERS}},
}


def region_label(region: str | None) -> str:
    return REGIONS.get((region or "US").upper(), {}).get("label", region or "United States")


def jurisdictions_for(region: str | None) -> dict[str, str]:
    """All valid jurisdiction codes -> names for a region (incl. its whole-region sentinel)."""
    return REGIONS.get((region or "US").upper(), {}).get("jurisdictions", {})


def jurisdiction_name(region: str | None, code: str | None) -> str:
    """Human name for a (region, code) pair; falls back to the raw code."""
    if not code:
        return ""
    return jurisdictions_for(region).get(code.upper(), code)


def is_valid_jurisdiction(region: str | None, code: str | None) -> bool:
    return bool(code) and code.upper() in jurisdictions_for(region)
