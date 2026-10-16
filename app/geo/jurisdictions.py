"""The Atlas Circular jurisdiction tree — the seed data + the (region, state) -> code mapping.

Atlas reframes the corpus around *place*: a hierarchy world -> bloc/country -> state -> municipality.
Today's bills carry only flat `region` (2-char country/family) + `state` (2-char sub) columns; this
module is the single source of truth for turning those into a real tree and, crucially, for the
`aliases` that let a natural-language query ("examples from France") resolve to a jurisdiction node
even when the word never appears in a bill's title or (foreign-language) body text.

Levels: world -> bloc (EU) | country (US, FR, …) -> state (US-CA, provinces) -> municipality (future).
Codes are hierarchical + globally unique so the flat-column `CA` collision is resolved:
  US California = "US-CA"  vs  Canada = "CA".
US municipalities are seeded only where curated ordinances exist (US_MUNICIPALITIES), e.g. "US-CA-SF".

Backfill + resolver both import from here so the tree and the mapping never drift.
"""
from __future__ import annotations

ROOT_CODE = "WORLD"

# code -> (name, level, aliases). Blocs + countries hang directly under WORLD. `region` column value
# equals the code for every non-US row (incl. the EU bloc); US rows are handled by US_STATES below.
COUNTRIES: dict[str, tuple[str, str, list[str]]] = {
    "US": ("United States", "country", ["US", "USA", "U.S.", "U.S.A.", "United States", "America", "American", "United States of America"]),
    "EU": ("European Union", "bloc", ["EU", "E.U.", "European Union", "Europe", "European", "EU-wide", "European Commission"]),
    "FR": ("France", "country", ["FR", "France", "French", "République française", "Republique francaise"]),
    "DE": ("Germany", "country", ["DE", "Germany", "German", "Deutschland"]),
    "UK": ("United Kingdom", "country", ["UK", "U.K.", "GB", "United Kingdom", "Britain", "Great Britain", "British", "England", "Scotland", "Wales", "Northern Ireland"]),
    "JP": ("Japan", "country", ["JP", "Japan", "Japanese", "Nippon", "Nihon"]),
    "CN": ("China", "country", ["CN", "China", "Chinese", "PRC", "People's Republic of China"]),
    "CA": ("Canada", "country", ["CA", "Canada", "Canadian"]),
    "AU": ("Australia", "country", ["AU", "Australia", "Australian"]),
    "ES": ("Spain", "country", ["ES", "Spain", "Spanish", "España", "Espana"]),
    "NL": ("Netherlands", "country", ["NL", "Netherlands", "Dutch", "Holland", "The Netherlands"]),
    "PL": ("Poland", "country", ["PL", "Poland", "Polish", "Polska"]),
    "SE": ("Sweden", "country", ["SE", "Sweden", "Swedish", "Sverige"]),
    "AT": ("Austria", "country", ["AT", "Austria", "Austrian", "Österreich", "Osterreich"]),
    "BR": ("Brazil", "country", ["BR", "Brazil", "Brazilian", "Brasil"]),
    "CH": ("Switzerland", "country", ["CH", "Switzerland", "Swiss", "Schweiz", "Suisse"]),
    "CL": ("Chile", "country", ["CL", "Chile", "Chilean"]),
    "CZ": ("Czechia", "country", ["CZ", "Czechia", "Czech", "Czech Republic"]),
    "DK": ("Denmark", "country", ["DK", "Denmark", "Danish", "Danmark"]),
    "EE": ("Estonia", "country", ["EE", "Estonia", "Estonian", "Eesti"]),
    "FI": ("Finland", "country", ["FI", "Finland", "Finnish", "Suomi"]),
    "IE": ("Ireland", "country", ["IE", "Ireland", "Irish", "Éire", "Eire"]),
    "LT": ("Lithuania", "country", ["LT", "Lithuania", "Lithuanian", "Lietuva"]),
    "LU": ("Luxembourg", "country", ["LU", "Luxembourg", "Luxembourgish"]),
    "LV": ("Latvia", "country", ["LV", "Latvia", "Latvian", "Latvija"]),
    "SI": ("Slovenia", "country", ["SI", "Slovenia", "Slovenian", "Slovenija"]),
    "SK": ("Slovakia", "country", ["SK", "Slovakia", "Slovak", "Slovensko"]),
    # Non-US/EU regions from the foreign-expansion backlog (were ingested + on the globe but had no
    # jurisdiction node, so place-scoped Ask-the-Bills questions silently dropped them — e.g. "compare
    # Kenya with Chile and Japan" scoped to Chile+Japan only). Resolve by NAME, not the bare 2-letter
    # code: CO/IN collide with US states (Colorado/Indiana) and IT/NO/PE/MW collide with common domain
    # tokens (IT dept, "no", PE=polyethylene, MW=megawatt). Türkiye carries the English exonym "Turkey".
    "CO": ("Colombia", "country", ["Colombia", "Colombian"]),
    "IN": ("India", "country", ["India", "Indian", "Bharat"]),
    "IT": ("Italy", "country", ["Italy", "Italian", "Italia"]),
    "KE": ("Kenya", "country", ["Kenya", "Kenyan"]),
    "MW": ("Malawi", "country", ["Malawi", "Malawian"]),
    "MX": ("Mexico", "country", ["Mexico", "Mexican", "México"]),
    "NO": ("Norway", "country", ["Norway", "Norwegian", "Norge"]),
    "PE": ("Peru", "country", ["Peru", "Peruvian", "Perú"]),
    "RW": ("Rwanda", "country", ["Rwanda", "Rwandan"]),
    "SL": ("Sierra Leone", "country", ["Sierra Leone", "Sierra Leonean"]),
    "TR": ("Türkiye", "country", ["Türkiye", "Turkiye", "Turkey", "Turkish"]),
    "UY": ("Uruguay", "country", ["Uruguay", "Uruguayan"]),
    "ZM": ("Zambia", "country", ["Zambia", "Zambian"]),
}

# US sub-jurisdictions. Federal (state == "US") maps to the US country node itself, not a child.
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
    "DC": "District of Columbia", "PR": "Puerto Rico",
}


# US municipalities with curated ordinances (data/seed/municipal_ordinances.json). A city ordinance's
# bill row carries state = "<ST>-<CITY>" (e.g. "OR-PORTLAND"), so jurisdiction_code() yields
# "US-OR-PORTLAND" with no special case, and the exact-match state filters behind the leaderboard and
# state profiles keep city ordinances out of state-legislature counts. Aliases are city names only —
# never a bare abbreviation like "LA" (Louisiana) or a name shared with another state's city.
US_MUNICIPALITIES: dict[str, tuple[str, list[str]]] = {
    "OR-PORTLAND": ("Portland", ["Portland, Oregon", "Portland OR", "City of Portland"]),
    "TX-SANANTONIO": ("San Antonio", ["San Antonio"]),
    "TX-AUSTIN": ("Austin", ["Austin, Texas", "Austin TX", "City of Austin"]),
    "CA-PALOALTO": ("Palo Alto", ["Palo Alto"]),
    "CA-SF": ("San Francisco", ["San Francisco", "City of San Francisco"]),
    "CA-BERKELEY": ("Berkeley", ["Berkeley"]),
    "CA-LA": ("Los Angeles", ["Los Angeles", "City of Los Angeles"]),
    "CO-BOULDER": ("Boulder", ["Boulder, Colorado", "Boulder CO", "City of Boulder"]),
    "CO-DENVER": ("Denver", ["Denver"]),
    "PA-PITTSBURGH": ("Pittsburgh", ["Pittsburgh"]),
    "PA-PHILADELPHIA": ("Philadelphia", ["Philadelphia", "Philly"]),
    "WA-SEATTLE": ("Seattle", ["Seattle"]),
    "IL-CHICAGO": ("Chicago", ["Chicago"]),
    "NY-NYC": ("New York City", ["New York City", "NYC"]),
    "MA-BOSTON": ("Boston", ["Boston"]),
}


def jurisdiction_code(region: str, state: str) -> str:
    """Map a bill's (region, state) to its jurisdiction code. The one place this logic lives."""
    region = (region or "").strip().upper()
    state = (state or "").strip().upper()
    if region == "US":
        return "US" if state in ("US", "") else f"US-{state}"
    return region  # non-US: country code == region (incl. the EU bloc)


def seed_nodes() -> list[dict]:
    """The full tree to insert, parents before children. Each: {code, name, level, parent_code,
    aliases, path}. path is a dotted ltree label built from lowercased, ltree-safe codes."""
    def label(code: str) -> str:
        return code.lower().replace("-", "_")

    nodes: list[dict] = [
        {"code": ROOT_CODE, "name": "World", "level": "world", "parent_code": None,
         "aliases": ["world", "global", "everywhere"], "path": label(ROOT_CODE)},
    ]
    for code, (name, level, aliases) in COUNTRIES.items():
        nodes.append({
            "code": code, "name": name, "level": level, "parent_code": ROOT_CODE,
            "aliases": aliases, "path": f"{label(ROOT_CODE)}.{label(code)}",
        })
    for st, name in US_STATES.items():
        code = f"US-{st}"
        nodes.append({
            "code": code, "name": name, "level": "state", "parent_code": "US",
            "aliases": [st, name], "path": f"{label(ROOT_CODE)}.us.{label(code)}",
        })
    for sub, (name, aliases) in US_MUNICIPALITIES.items():
        st = sub.split("-", 1)[0]
        parent, code = f"US-{st}", f"US-{sub}"
        nodes.append({
            "code": code, "name": name, "level": "municipality", "parent_code": parent,
            "aliases": aliases, "path": f"{label(ROOT_CODE)}.us.{label(parent)}.{label(code)}",
        })
    return nodes
