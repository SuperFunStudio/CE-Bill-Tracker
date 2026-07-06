"""One-time Sonnet estimate of the `dispersion` axis for the seed materials (MATERIAL_PROFILES).

value_density is grounded in $/tonne and channel_maturity is derived from the corpus; dispersion — how
thinly a material is spread across independent holders at end of life — has no clean data proxy, so we
have Sonnet estimate all 16 at once (one call → consistent relative calibration) and bake the results
into the table. Run:  python -m scripts.estimate_dispersion   (uses ANTHROPIC key from .env)

Prints current vs estimated dispersion + one-line reasoning; paste the estimates into MATERIAL_PROFILES.
Reproducible: re-run to refresh. Not wired into the app — this is a table-maintenance tool.
"""
import json

import anthropic

from app.config import settings
from app.evaluation.strength import MATERIAL_PROFILES

MODEL = "claude-sonnet-4-6"

SYSTEM = """\
You calibrate a single axis for circular-economy materials: DISPERSION — how thinly the material is \
spread across independent holders at end of life, which sets how hard collection is.
- 0.0-0.2: concentrated at a few large points (e.g. lead-acid batteries returned to auto shops; \
industrial/commercial streams).
- 0.4-0.6: moderately spread but with existing aggregation points.
- 0.8-1.0: in nearly every household in small amounts, no natural aggregation (e.g. apparel, footwear, \
flexible film).
Judge on the END-OF-LIFE holder distribution, NOT on material value or whether a channel exists. Be \
consistent across the set — calibrate them relative to each other. Output STRICT JSON only."""

USER = """\
Estimate dispersion (0..1) for each material. Return JSON only, an object keyed by the exact material \
label, each value {{"dispersion": <0..1>, "reasoning": "<one short sentence>"}}:

Materials:
{materials}"""


def main() -> None:
    labels = [p.label for p in MATERIAL_PROFILES]
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    resp = client.messages.create(
        model=MODEL, max_tokens=2000, temperature=0, system=SYSTEM,
        messages=[{"role": "user", "content": USER.format(materials="\n".join(f"- {label}" for label in labels))}],
    )
    raw = resp.content[0].text.strip()
    data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])

    print(f"{'material':32} {'now':>5} {'sonnet':>7}   reasoning")
    print("-" * 100)
    for p in MATERIAL_PROFILES:
        est = data.get(p.label, {})
        d = est.get("dispersion")
        d_str = f"{d:.2f}" if isinstance(d, (int, float)) else "  ? "
        print(f"{p.label:32} {p.dispersion:>5.2f} {d_str:>7}   {est.get('reasoning', '')[:60]}")

    print("\n# dispersion values (label -> sonnet estimate), for MATERIAL_PROFILES:")
    for p in MATERIAL_PROFILES:
        d = data.get(p.label, {}).get("dispersion")
        if isinstance(d, (int, float)):
            print(f'#   {p.label:32} {round(float(d), 2)}')


if __name__ == "__main__":
    main()
