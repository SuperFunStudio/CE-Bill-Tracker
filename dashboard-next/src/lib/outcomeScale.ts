/**
 * Relatable-scale equivalences for a documented outcome's headline figure.
 *
 * "100 million containers returned" is a number nobody can picture; every large figure on this site
 * has the same problem. This turns one into a physical quantity a reader already has a mental image
 * of — pools, tanker trucks, elephants, a distance around the Earth.
 *
 * TWO RULES, both load-bearing:
 *
 *  1. UNIT ARITHMETIC ONLY. Every comparison below is a division by a published constant. Nothing
 *     here estimates an effect, a harm avoided, or a cost — those are research claims that belong in
 *     a curated, sourced field on the outcome row, not in a frontend helper that would be inventing
 *     them. A unit we can't convert returns null and the surface simply shows no comparison.
 *  2. THE ARITHMETIC IS PUBLISHED. Every result carries a `basis` string naming the constant it
 *     divided by, so a reader can check the equivalence instead of trusting it. Anything that leans
 *     on a typical-value assumption (the length of a drink container) says so in that string.
 */

export interface ScaleComparison {
  /** The equivalence, e.g. "≈ 1,800 Olympic swimming pools". Always prefixed "≈" — these are orders
   *  of magnitude for the imagination, not measurements. */
  text: string;
  /** The arithmetic spelled out, surfaced as a tooltip / fine print. */
  basis: string;
}

// ── Constants ────────────────────────────────────────────────────────────────
// Volume, in litres.
const L_PER_US_GALLON = 3.785411784;
const L_PER_CUBIC_METRE = 1000;
const L_PER_OIL_BARREL = 158.987;
const OLYMPIC_POOL_L = 2_500_000; // 50 m × 25 m × 2 m
const ROAD_TANKER_L = 30_000;
const BATHTUB_L = 150;

// Mass, in kilograms.
const KG_PER_TONNE = 1000;
const KG_PER_SHORT_TON = 907.18474;
const KG_PER_POUND = 0.45359237;
const EIFFEL_TOWER_KG = 7_300_000; // the iron structure alone, 7,300 tonnes
const ELEPHANT_KG = 6_000; // adult African bush elephant
const CAR_KG = 1_500; // mid-size passenger car

// Area, in square metres.
const M2_PER_HECTARE = 10_000;
const M2_PER_ACRE = 4046.8564224;
const FOOTBALL_PITCH_M2 = 7_140; // 105 m × 68 m
const CENTRAL_PARK_M2 = 3_410_000;

// Length, in metres.
const DRINK_CONTAINER_M = 0.2; // a can or small PET bottle on its side, end to end
const EARTH_CIRCUMFERENCE_KM = 40_075;

/** Round to a precision that matches the magnitude — an approximation shouldn't print six digits. */
function tidy(n: number): string {
  if (n >= 100) return Math.round(n).toLocaleString();
  if (n >= 10) return String(Math.round(n));
  if (n >= 1) return n.toFixed(1).replace(/\.0$/, '');
  return n.toFixed(2);
}

/** "1 pool" / "3 pools" — the plural is on the noun, not the number. */
function count(n: number, singular: string, plural = `${singular}s`): string {
  return `≈ ${tidy(n)} ${n >= 0.995 && n < 1.005 ? singular : plural}`;
}

/** Below half of the smallest anchor the comparison stops helping: "0.24 family cars" is a harder
 *  picture than the kilograms it replaced. The surface shows nothing rather than that. */
const MIN_USEFUL_RATIO = 0.5;

/** Scale words the figure's unit may carry ("million gallons"), stripped off and multiplied back in. */
const MAGNITUDES: [RegExp, number][] = [
  [/^thousand\s+/, 1e3],
  [/^million\s+/, 1e6],
  [/^billion\s+/, 1e9],
  [/^trillion\s+/, 1e12],
];

/** Per-year / annual cadences. Kept out of the conversion and re-attached to the basis line. */
const CADENCE = /\s*(?:\/\s*(?:year|yr|a)|\s+per\s+year|\s+annually)\s*$/i;

interface ParsedUnit {
  magnitude: number;
  /** Unit with magnitude words and cadence removed, lowercased, singular-ish. */
  base: string;
  /** True when the figure is a rate (per year) rather than a stock. */
  perYear: boolean;
}

function parseUnit(unit: string): ParsedUnit {
  let s = unit.trim().toLowerCase();
  const perYear = CADENCE.test(s);
  s = s.replace(CADENCE, '');
  let magnitude = 1;
  for (const [re, mult] of MAGNITUDES) {
    if (re.test(s)) {
      magnitude = mult;
      s = s.replace(re, '');
      break;
    }
  }
  return { magnitude, base: s.trim(), perYear };
}

/** Litres, or null when the unit isn't a volume. */
function toLitres(base: string, qty: number): number | null {
  if (/^(litres?|liters?|l)$/.test(base)) return qty;
  if (/^(megalitres?|megaliters?|ml)$/.test(base)) return qty * 1e6;
  if (/^(gallons?|gal)$/.test(base)) return qty * L_PER_US_GALLON;
  if (/^(cubic\s*met(re|er)s?|m3|m³)$/.test(base)) return qty * L_PER_CUBIC_METRE;
  if (/^barrels?$/.test(base)) return qty * L_PER_OIL_BARREL;
  return null;
}

/** Kilograms, or null when the unit isn't a mass. */
function toKilograms(base: string, qty: number): number | null {
  if (/^(kilograms?|kg)$/.test(base)) return qty;
  if (/^(tonnes?|metric\s*tons?|t)$/.test(base)) return qty * KG_PER_TONNE;
  if (/^(short\s*)?tons?$/.test(base)) return qty * KG_PER_SHORT_TON;
  if (/^(pounds?|lbs?)$/.test(base)) return qty * KG_PER_POUND;
  return null;
}

/** Square metres, or null when the unit isn't an area. */
function toSquareMetres(base: string, qty: number): number | null {
  if (/^hectares?$/.test(base)) return qty * M2_PER_HECTARE;
  if (/^acres?$/.test(base)) return qty * M2_PER_ACRE;
  if (/^(square\s*met(re|er)s?|m2|m²)$/.test(base)) return qty;
  return null;
}

/** Discrete drink containers — the one count we have a defensible physical dimension for. */
const CONTAINER_UNIT = /^(containers?|bottles?|cans?)$/;

/**
 * The single best comparison for a figure, or null when there isn't an honest one (money, bare
 * percentages, counts of things with no typical size).
 */
export function scaleComparison(
  value: number | null | undefined,
  unit: string | null | undefined,
): ScaleComparison | null {
  if (value == null || !Number.isFinite(value) || value <= 0 || !unit) return null;
  // A money figure has no physical volume, and converting it into one ("enough to buy N…") would be
  // an economic claim dressed as arithmetic. No comparison is better than an invented one.
  if (unit.includes('$') || /\b(usd|eur|gbp|aud|dollars?|euros?)\b/i.test(unit)) return null;

  const { magnitude, base, perYear } = parseUnit(unit);
  const qty = value * magnitude;
  const cadence = perYear ? ', each year' : '';

  const litres = toLitres(base, qty);
  if (litres !== null) {
    const asLitres = `${tidy(litres).replace(/,/g, ',')} litres${cadence}`;
    if (litres >= OLYMPIC_POOL_L) {
      return {
        text: count(litres / OLYMPIC_POOL_L, 'Olympic swimming pool'),
        basis: `${asLitres} ÷ 2,500,000 L, the volume of a 50 m Olympic pool.`,
      };
    }
    if (litres >= ROAD_TANKER_L) {
      return {
        text: count(litres / ROAD_TANKER_L, 'road tanker'),
        basis: `${asLitres} ÷ 30,000 L, the capacity of a road tanker truck.`,
      };
    }
    if (litres < BATHTUB_L * MIN_USEFUL_RATIO) return null;
    return {
      text: count(litres / BATHTUB_L, 'bathtub'),
      basis: `${asLitres} ÷ 150 L, the capacity of a domestic bathtub.`,
    };
  }

  const kg = toKilograms(base, qty);
  if (kg !== null) {
    const asKg = `${tidy(kg)} kg${cadence}`;
    if (kg >= EIFFEL_TOWER_KG) {
      return {
        text: count(kg / EIFFEL_TOWER_KG, 'Eiffel Tower'),
        basis: `${asKg} ÷ 7,300 tonnes, the mass of the Eiffel Tower's iron structure.`,
      };
    }
    if (kg >= ELEPHANT_KG) {
      return {
        text: count(kg / ELEPHANT_KG, 'African elephant'),
        basis: `${asKg} ÷ 6,000 kg, the mass of an adult African bush elephant.`,
      };
    }
    if (kg < CAR_KG * MIN_USEFUL_RATIO) return null;
    return {
      text: count(kg / CAR_KG, 'family car'),
      basis: `${asKg} ÷ 1,500 kg, the mass of a mid-size passenger car.`,
    };
  }

  const m2 = toSquareMetres(base, qty);
  if (m2 !== null) {
    if (m2 >= CENTRAL_PARK_M2) {
      return {
        text: count(m2 / CENTRAL_PARK_M2, 'Central Park'),
        basis: `${tidy(m2)} m²${cadence} ÷ 3.41 km², the area of Central Park.`,
      };
    }
    if (m2 < FOOTBALL_PITCH_M2 * MIN_USEFUL_RATIO) return null;
    return {
      text: count(m2 / FOOTBALL_PITCH_M2, 'football pitch', 'football pitches'),
      basis: `${tidy(m2)} m²${cadence} ÷ 7,140 m², a 105 m × 68 m football pitch.`,
    };
  }

  if (CONTAINER_UNIT.test(base)) {
    // Containers are hollow, so stacking them is meaningless — but laying them end to end isn't, and
    // a distance is the easiest large quantity to picture. The 0.2 m figure is a typical drink
    // container on its side, and the basis line says so rather than presenting it as exact.
    const km = (qty * DRINK_CONTAINER_M) / 1000;
    const ratio = km / EARTH_CIRCUMFERENCE_KM;
    const earth =
      ratio >= 0.95
        ? ` — ${tidy(ratio)}× around the Earth`
        : ratio >= 0.1
          ? ` — ${Math.round(ratio * 100)}% of the way around the Earth`
          : '';
    return {
      text: `≈ ${tidy(km)} km laid end to end${earth}`,
      basis: `${tidy(qty)} ${base}${cadence} × 0.2 m, a typical drink container on its side. Earth's circumference is 40,075 km.`,
    };
  }

  return null;
}
