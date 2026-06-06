"""One-time script to enrich known_epr_laws.json with numeric fee fields."""
import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'seed', 'known_epr_laws.json')

with open(DATA_FILE) as f:
    bills = json.load(f)

# Enrichments keyed by (state, bill_number)
enrichments = {
    # --- ECO-MODULATED PACKAGING BILLS ---
    ('ME', 'LD 1541'): {
        'fee_per_ton': 180.0, 'registration_fee_usd': 1500.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Rates TBD by PRO. Estimate based on comparable enacted packaging EPR programs.',
    },
    ('OR', 'SB 582'): {
        'fee_per_ton': 419.0, 'registration_fee_usd': 1500.0,
        'fee_structure_source': 'published_range_midpoint',
        'fee_notes': 'Published rate ~$0.04-$0.34/lb (~$88-$750/tonne). Using midpoint ~$0.19/lb (~$419/tonne).',
    },
    ('CO', 'HB 22-1355'): {
        'fee_per_ton': 180.0, 'registration_fee_usd': 1500.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Rates TBD by PRO. Estimate based on comparable enacted packaging EPR programs.',
    },
    ('CA', 'SB 54'): {
        'fee_per_ton': 180.0, 'registration_fee_usd': 1500.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Aggregate ~$500M/yr target. Per-ton rate set by PRO. Estimate based on comparable programs.',
    },
    ('MN', 'HF 3577'): {
        'fee_per_ton': 180.0, 'registration_fee_usd': 1500.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Rates TBD by PRO. Estimate based on comparable enacted packaging EPR programs.',
    },
    ('MD', 'SB 901'): {
        'fee_per_ton': 180.0, 'registration_fee_usd': 1500.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Rates TBD by PRO. Estimate based on comparable enacted packaging EPR programs.',
    },
    ('WA', 'HB 1131'): {
        'fee_per_ton': 180.0, 'registration_fee_usd': 1500.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Rates TBD through Ecology rulemaking. Estimate based on comparable enacted packaging EPR programs.',
    },

    # --- TEXTILES ---
    ('CA', 'SB 707'): {
        'fee_per_ton': 80.0, 'registration_fee_usd': 500.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Fee structure TBD by PRO and CalRecycle. Estimate based on comparable textile EPR programs.',
    },

    # --- BATTERIES (fall through to CATEGORY_BENCHMARKS in estimator) ---
    ('DC', 'Battery Stewardship Act'): {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('VT', 'Act 148 Battery'):         {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('CA', 'SB 1215'):                 {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('IL', 'SB 3776 Battery'):         {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('MD', 'HB 1415 Battery'):         {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('WA', 'SB 5374 Battery'):         {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('NJ', 'A4 Battery'):              {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},

    # --- LABELING / RECYCLED CONTENT ---
    ('CA', 'SB 343'):                  {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('WA', 'SB 5022 Recycled Content'):{'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},

    # --- SOLAR ---
    ('WA', 'HB 1085'):                 {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},

    # --- PAINT (per-unit, PaintCare published rates) ---
    ('CA', 'PaintCare CA'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average. ~263 units/tonne (1-gal avg ~3.8kg).',
    },
    ('OR', 'PaintCare OR'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('CT', 'PaintCare CT'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('MN', 'PaintCare MN'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('CO', 'PaintCare CO'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('ME', 'PaintCare ME'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('RI', 'PaintCare RI'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('VT', 'PaintCare VT'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('WA', 'PaintCare WA'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },
    ('DC', 'PaintCare DC'): {
        'fee_per_unit_usd': 0.95, 'units_per_tonne': 263, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'paintcare_published',
        'fee_notes': 'Using 1-5 gal tier ($0.95) as representative average.',
    },

    # --- MATTRESSES (per-unit, MRC published rates) ---
    ('CA', 'AB 2901 Mattress'): {
        'fee_per_unit_usd': 19.0, 'units_per_tonne': 40, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'mrc_published',
        'fee_notes': 'Using queen size ($19) as representative average. Avg mattress ~25kg = 40/tonne.',
    },
    ('CT', 'SB 422 Mattress'): {
        'fee_per_unit_usd': 19.0, 'units_per_tonne': 40, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'mrc_published',
        'fee_notes': 'Using queen size ($19) as representative average.',
    },
    ('RI', 'Mattress RI'): {
        'fee_per_unit_usd': 19.0, 'units_per_tonne': 40, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'mrc_published',
        'fee_notes': 'Using queen size ($19) as representative average.',
    },
    ('OR', 'Mattress OR'): {
        'fee_per_unit_usd': 19.0, 'units_per_tonne': 40, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'mrc_published',
        'fee_notes': 'Using queen size ($19) as representative average.',
    },

    # --- CARPET (per-unit, CalRecycle published) ---
    ('CA', 'AB 2398 Carpet'): {
        'fee_per_unit_usd': 0.25, 'units_per_tonne': 714, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'calrecycle_published',
        'fee_notes': '$0.25/sq yd. ~1.4kg/sq yd = ~714 sq yd/tonne.',
    },

    # --- E-WASTE (CA published; other states benchmark) ---
    ('CA', 'AB 1268 E-Waste'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'calrecycle_published',
        'fee_notes': 'Using $14 midpoint of $8-$25 range. ~2kg avg device = 500 units/tonne.',
    },
    ('NY', 'Electronic Equipment Recycling Act'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },
    ('WA', 'E-Cycle WA'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },
    ('CT', 'E-Cycles CT'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },
    ('IL', 'E-Waste IL'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },
    ('MN', 'E-Cycle MN'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },
    ('OR', 'E-Cycles OR'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },
    ('NJ', 'E-Waste NJ'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },
    ('MA', 'E-Waste MA'): {
        'fee_per_unit_usd': 14.0, 'units_per_tonne': 500, 'registration_fee_usd': 0.0,
        'fee_structure_source': 'industry_benchmark',
        'fee_notes': 'Benchmark based on CA AB 1268 comparable program.',
    },

    # --- PHARMA ---
    ('CA', 'SB 212 Pharma'): {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('WA', 'SB 5676 Pharma'): {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('NY', 'Pharma NY'):       {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},
    ('MA', 'Pharma MA'):       {'fee_per_ton': None, 'fee_structure_source': 'no_fee_data'},

    # --- RIGHT-TO-REPAIR (no monetary EPR fee) ---
    ('CO', 'SB 23-290 R2R'): {'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee'},
    ('MN', 'SF 1598 R2R'):   {'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee'},
    ('CA', 'SB 244 R2R'):    {'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee'},
    ('OR', 'HB 2422 R2R'):   {'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee'},

    # --- RECYCLED CONTENT MANDATES (no monetary fee) ---
    ('CA', 'AB 793 Recycled Content'):  {'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee'},
    ('WA', 'SB 5022 Recycled Content'): {'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee'},

    # --- BOTTLE DEPOSIT (consumer deposit, not producer EPR fee) ---
    ('MI', 'Bottle Bill MI'): {
        'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee',
        'fee_notes': 'Consumer-paid deposit system. Producer cost is administrative, not weight-based.',
    },
    ('OR', 'Bottle Bill OR'): {
        'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee',
        'fee_notes': 'Consumer-paid deposit system. Producer cost is administrative, not weight-based.',
    },
    ('CA', 'Bottle Bill CA'): {
        'fee_structure': 'no_monetary_fee', 'fee_structure_source': 'no_monetary_fee',
        'fee_notes': 'Consumer-paid deposit system. Producer cost is administrative, not weight-based.',
    },
}

updated = 0
skipped = []
for bill in bills:
    key = (bill['state'], bill['bill_number'])
    if key in enrichments:
        fees = bill.setdefault('compliance_details', {}).setdefault('fees', {})
        fees.update(enrichments[key])
        updated += 1
    else:
        skipped.append(key)

print(f'Updated: {updated} bills, Skipped: {len(skipped)}')
for s in skipped:
    print(f'  SKIPPED: {s}')

with open(DATA_FILE, 'w') as f:
    json.dump(bills, f, indent=2)
print('Written successfully.')
