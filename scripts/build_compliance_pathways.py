"""Seed the compliance-entity directory and build a compliance_pathway per enacted law.

This is the "now what do I do" rung: it turns the management_model classification
(bills.compliance_details.management, see scripts/extract_management_model.py +
correct_management_model.py) into a concrete next-action a producer can act on —
join THIS PRO / file an individual plan with THIS state / register with the program —
plus the soonest deadline and whether a fee applies.

Two parts, both idempotent:
  1. Upsert the curated ENTITY directory (real PROs + key agencies, slug-keyed).
  2. Rebuild a PATHWAY row per enacted law from its management_model, linking the
     entity by source_url domain (high precision) or material, and snapshotting the
     next future deadline + fee presence.

Usage:
  venv/Scripts/python scripts/build_compliance_pathways.py --test   # print, no writes
  venv/Scripts/python scripts/build_compliance_pathways.py
  venv/Scripts/python scripts/build_compliance_pathways.py --prod-dsn "..."
"""
import argparse
import json

from sqlalchemy import create_engine, text

from app.config import settings

# --- Curated directory. These are stable real-world bodies; hand-curated for accuracy. ---
ENTITIES = [
    # PROs
    dict(slug="circular-action-alliance", name="Circular Action Alliance", entity_type="pro",
         url="https://circularactionalliance.org",
         registration_url="https://circularactionalliance.org/producers",
         jurisdiction_scope="multistate",
         materials=["plastic_packaging", "paper_packaging", "packaging", "paper"],
         description="The packaging & paper-products PRO designated across CA, CO, MD, MN, OR, WA and "
                     "other packaging-EPR states."),
    dict(slug="paintcare", name="PaintCare", entity_type="pro",
         url="https://www.paintcare.org",
         registration_url="https://www.paintcare.org/manufacturers/",
         jurisdiction_scope="multistate", materials=["paint"],
         description="Nonprofit paint stewardship PRO operating every U.S. state paint-EPR program."),
    dict(slug="call2recycle", name="Call2Recycle", entity_type="pro",
         url="https://www.call2recycle.org",
         registration_url="https://www.call2recycle.org/battery-stewardship/",
         jurisdiction_scope="national", materials=["batteries"],
         description="The national battery stewardship PRO; operator for most state battery-EPR programs."),
    dict(slug="mattress-recycling-council", name="Mattress Recycling Council", entity_type="pro",
         url="https://mattressrecyclingcouncil.org",
         registration_url="https://mattressrecyclingcouncil.org/",
         jurisdiction_scope="multistate", materials=["mattresses"],
         description="The mattress-recycling PRO running the Bye Bye Mattress programs (CA, CT, OR, RI)."),
    dict(slug="thermostat-recycling-corp", name="Thermostat Recycling Corporation (TRC)",
         entity_type="pro", url="https://www.thermostat-recycle.org",
         registration_url="https://www.thermostat-recycle.org/",
         jurisdiction_scope="multistate", materials=["thermostats", "mercury"],
         description="Industry PRO collecting mercury-containing thermostats across ~ a dozen states."),
    dict(slug="elv-solutions", name="End of Life Vehicle Solutions (ELVS)", entity_type="pro",
         url="https://www.elvsolutions.org", registration_url="https://www.elvsolutions.org/",
         jurisdiction_scope="national", materials=["auto_switches", "mercury"],
         description="Automaker-funded PRO recovering mercury switches from end-of-life vehicles."),
    dict(slug="med-project", name="MED-Project", entity_type="pro",
         url="https://med-project.org", registration_url="https://med-project.org/covered-manufacturers/",
         jurisdiction_scope="multistate", materials=["pharmaceuticals", "medical_sharps"],
         description="Pharmaceutical & sharps take-back PRO operating many drug-stewardship programs."),
    dict(slug="carpet-america-recovery-effort", name="Carpet America Recovery Effort (CARE)",
         entity_type="pro", url="https://carpetrecovery.org",
         registration_url="https://carpetrecovery.org/", jurisdiction_scope="multistate",
         materials=["carpet"], description="Carpet stewardship PRO administering California's program."),
    # Agencies (individual-plan / state-run administrators)
    dict(slug="calrecycle", name="CalRecycle (CA Dept. of Resources Recycling & Recovery)",
         entity_type="agency", url="https://calrecycle.ca.gov", registration_url=None,
         jurisdiction_scope="single_state", home_state="CA",
         materials=None, description="California's recycling agency; administers CA's state-run programs."),
    dict(slug="wa-ecology", name="Washington State Department of Ecology", entity_type="agency",
         url="https://ecology.wa.gov", registration_url=None, jurisdiction_scope="single_state",
         home_state="WA", materials=None, description="Washington's environmental agency."),
]

# State environmental/recycling agency that administers EPR / producer-plan filings, for the
# states with enacted individual- or government-run laws. (CA, WA already in ENTITIES above.)
# name, homepage — the "where to start" link; the specific program page varies post-rulemaking.
_AGENCIES = [
    ("ME", "me-dep", "Maine Department of Environmental Protection", "https://www.maine.gov/dep"),
    ("OR", "or-deq", "Oregon Department of Environmental Quality (DEQ)", "https://www.oregon.gov/deq"),
    ("VT", "vt-dec", "Vermont Department of Environmental Conservation", "https://dec.vermont.gov"),
    ("CO", "co-cdphe", "Colorado Dept. of Public Health & Environment (CDPHE)", "https://cdphe.colorado.gov"),
    ("IL", "il-epa", "Illinois Environmental Protection Agency", "https://epa.illinois.gov"),
    ("IN", "in-idem", "Indiana Dept. of Environmental Management (IDEM)", "https://www.in.gov/idem"),
    ("MD", "md-mde", "Maryland Department of the Environment (MDE)", "https://mde.maryland.gov"),
    ("MI", "mi-egle", "Michigan Dept. of Environment, Great Lakes & Energy (EGLE)", "https://www.michigan.gov/egle"),
    ("MN", "mn-mpca", "Minnesota Pollution Control Agency (MPCA)", "https://www.pca.state.mn.us"),
    ("NC", "nc-deq", "North Carolina Department of Environmental Quality", "https://www.deq.nc.gov"),
    ("NJ", "nj-dep", "New Jersey Department of Environmental Protection", "https://dep.nj.gov"),
    ("OK", "ok-deq", "Oklahoma Department of Environmental Quality", "https://www.deq.ok.gov"),
    ("PA", "pa-dep", "Pennsylvania Department of Environmental Protection", "https://www.dep.pa.gov"),
    ("RI", "ri-dem", "Rhode Island Department of Environmental Management", "https://dem.ri.gov"),
    ("SC", "sc-des", "South Carolina Department of Environmental Services", "https://des.sc.gov"),
    ("TX", "tx-tceq", "Texas Commission on Environmental Quality (TCEQ)", "https://www.tceq.texas.gov"),
    ("UT", "ut-deq", "Utah Department of Environmental Quality", "https://deq.utah.gov"),
    ("VA", "va-deq", "Virginia Department of Environmental Quality", "https://www.deq.virginia.gov"),
    ("WI", "wi-dnr", "Wisconsin Department of Natural Resources", "https://dnr.wisconsin.gov"),
    ("WV", "wv-dep", "West Virginia Department of Environmental Protection", "https://dep.wv.gov"),
    ("FL", "fl-dep", "Florida Department of Environmental Protection", "https://floridadep.gov"),
    ("CT", "ct-deep", "Connecticut Dept. of Energy & Environmental Protection (DEEP)", "https://portal.ct.gov/deep"),
    ("DC", "dc-doee", "DC Department of Energy & Environment (DOEE)", "https://doee.dc.gov"),
    ("IA", "ia-dnr", "Iowa Department of Natural Resources", "https://www.iowadnr.gov"),
]
for _st, _slug, _name, _url in _AGENCIES:
    ENTITIES.append(dict(slug=_slug, name=_name, entity_type="agency", url=_url,
                         registration_url=None, jurisdiction_scope="single_state",
                         home_state=_st, materials=None,
                         description=f"{_st} environmental agency; administers the state's EPR/producer-plan filings."))

# source_url domain -> entity slug (highest-precision link signal)
DOMAIN_TO_SLUG = {
    "paintcare.org": "paintcare",
    "mattressrecyclingcouncil.org": "mattress-recycling-council",
    "thermostat-recycle.org": "thermostat-recycling-corp",
    "batterynetwork.org": "call2recycle",
    "call2recycle": "call2recycle",
    "elvsolutions.org": "elv-solutions",
    "carpetrecovery.org": "carpet-america-recovery-effort",
    "med-project.org": "med-project",
}
# material -> PRO slug, used only for pro_* laws with no domain match
MATERIAL_TO_SLUG = {
    "plastic_packaging": "circular-action-alliance", "paper_packaging": "circular-action-alliance",
    "packaging": "circular-action-alliance", "paper": "circular-action-alliance",
    "batteries": "call2recycle", "paint": "paintcare",
    "mattresses": "mattress-recycling-council", "thermostats": "thermostat-recycling-corp",
    "auto_switches": "elv-solutions", "pharmaceuticals": "med-project",
    "medical_sharps": "med-project", "carpet": "carpet-america-recovery-effort",
}
STATE_AGENCY = {"CA": "calrecycle", "WA": "wa-ecology",
                **{st: slug for st, slug, _n, _u in _AGENCIES}}

# Most-specific material first, for the "report your covered X" phrasing.
MATERIAL_LABEL_PRIORITY = [
    ("plastic_packaging", "packaging"), ("paper_packaging", "packaging"), ("packaging", "packaging"),
    ("batteries", "batteries"), ("paint", "paint"), ("mattresses", "mattresses"),
    ("thermostats", "thermostats"), ("auto_switches", "mercury auto switches"),
    ("pharmaceuticals", "covered drugs"), ("medical_sharps", "sharps"), ("carpet", "carpet"),
    ("electronics", "covered electronic devices"), ("solar_panels", "solar panels"),
    ("tires", "waste tires"), ("lighting", "mercury lighting"), ("pesticides", "pesticide containers"),
]


def material_label(mats):
    mats = mats or []
    for key, label in MATERIAL_LABEL_PRIORITY:
        if key in mats:
            return label
    return "covered products"


def pick_entity_slug(model, mats, source_url):
    surl = (source_url or "").lower()
    for dom, slug in DOMAIN_TO_SLUG.items():
        if dom in surl:
            return slug, "pro_domain"
    if model in ("pro_collective", "pro_multiple"):
        for m in (mats or []):
            if m in MATERIAL_TO_SLUG:
                return MATERIAL_TO_SLUG[m], "material"
    return None, None


def build_pathway(law, entities_by_slug):
    state, bn, model, scope, conf, mats, surl, next_dl, has_fee = law
    mat = material_label(mats)
    slug, basis = pick_entity_slug(model, mats, surl)
    entity = entities_by_slug.get(slug) if slug else None
    reg = (entity.get("registration_url") or entity.get("url")) if entity else surl

    if model in ("pro_collective", "pro_multiple"):
        action = "join_pro"
        if entity:
            extra = " (more than one PRO may be available)" if model == "pro_multiple" else ""
            summary = f"Join {entity['name']} and report your {mat}{extra}."
        else:
            summary = f"Join the program's producer responsibility organization (PRO) and report your {mat}."
            basis = basis or "management_model"
    elif model == "individual":
        action = "file_individual_plan"
        slug = STATE_AGENCY.get(state)
        entity = entities_by_slug.get(slug) if slug else None
        agency = entity["name"] if entity else f"the {state} environmental agency"
        summary = f"File your own individual producer/manufacturer plan for {mat} with {agency}."
        reg = (entity.get("url") if entity else None) or surl
        basis = "management_model"
    elif model == "government_run":
        action = "register_with_state"
        slug = STATE_AGENCY.get(state)
        entity = entities_by_slug.get(slug) if slug else None
        agency = entity["name"] if entity else f"the {state} state program"
        summary = f"Register with and report to {agency}'s state-run {mat} program."
        reg = (entity.get("url") if entity else None) or surl
        basis = "management_model"
    elif model == "market_contract":
        action = "arrange_collection"; entity = None
        summary = f"No PRO — arrange collection of {mat} through a permitted handler as the statute requires."
        basis = "management_model"
    elif model == "not_specified":
        action = "monitor"; entity = None
        summary = "No producer registration established by this law; monitor for implementing rules / fees."
        basis = "management_model"
    else:  # unknown / missing
        action = "none"; entity = None
        summary = "Compliance pathway not yet determined (statutory text unavailable)."
        basis = "management_model"

    return dict(entity_slug=(entity["slug"] if entity else None), action_type=action,
                action_summary=summary, registration_url=reg, management_model=model,
                next_deadline_date=next_dl, has_fee=has_fee, confidence=conf, basis=basis)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--prod-dsn", default=None)
    args = ap.parse_args()
    engine = create_engine(args.prod_dsn or settings.database_url)

    # 1) Upsert entities
    if not args.test:
        with engine.begin() as c:
            for e in ENTITIES:
                c.execute(text("""
                    insert into compliance_entity
                      (slug,name,entity_type,url,registration_url,jurisdiction_scope,home_state,materials,description)
                    values (:slug,:name,:entity_type,:url,:registration_url,:jurisdiction_scope,:home_state,
                            cast(:materials as jsonb),:description)
                    on conflict (slug) do update set
                      name=excluded.name, entity_type=excluded.entity_type, url=excluded.url,
                      registration_url=excluded.registration_url, jurisdiction_scope=excluded.jurisdiction_scope,
                      home_state=excluded.home_state, materials=excluded.materials, description=excluded.description
                """), {**e, "materials": json.dumps(e.get("materials")),
                       "home_state": e.get("home_state")})
    print(f"Entities upserted: {len(ENTITIES)}")

    # entity slug -> id + fields
    with engine.connect() as c:
        ents = {r[0]: {"id": r[1], "slug": r[0], "name": r[2], "url": r[3], "registration_url": r[4]}
                for r in c.execute(text(
                    "select slug,id,name,url,registration_url from compliance_entity"))}

    # 2) Build pathways for every enacted law
    sql = text("""
        select b.id, b.state, b.bill_number,
               b.compliance_details->'management'->>'management_model',
               b.compliance_details->'management'->>'coordination_scope',
               (b.compliance_details->'management'->>'confidence')::float,
               b.material_categories, b.source_url,
               (select min(d.deadline_date) from compliance_deadlines d
                  where d.bill_id=b.id and d.deadline_date>=current_date),
               exists(select 1 from bill_fee_citation f where f.bill_id=b.id)
        from bills b
        where b.epr_relevant and b.state!='US' and b.status='enacted'
    """)
    with engine.connect() as c:
        rows = list(c.execute(sql))

    tally = {}
    samples = []
    for r in rows:
        bid = r[0]
        p = build_pathway(r[1:], ents)
        tally[p["action_type"]] = tally.get(p["action_type"], 0) + 1
        if len(samples) < 12:
            samples.append((r[1], r[2], p))
        if not args.test:
            ent_id = ents[p["entity_slug"]]["id"] if p["entity_slug"] else None
            with engine.begin() as c:
                c.execute(text("""
                    insert into compliance_pathway
                      (bill_id,entity_id,management_model,action_type,action_summary,
                       registration_url,next_deadline_date,has_fee,confidence,basis)
                    values (:bid,:eid,:mm,:at,:sm,:reg,:dl,:fee,:conf,:basis)
                    on conflict (bill_id) do update set
                      entity_id=excluded.entity_id, management_model=excluded.management_model,
                      action_type=excluded.action_type, action_summary=excluded.action_summary,
                      registration_url=excluded.registration_url, next_deadline_date=excluded.next_deadline_date,
                      has_fee=excluded.has_fee, confidence=excluded.confidence, basis=excluded.basis
                """), {"bid": bid, "eid": ent_id, "mm": p["management_model"], "at": p["action_type"],
                       "sm": p["action_summary"], "reg": p["registration_url"],
                       "dl": p["next_deadline_date"], "fee": p["has_fee"], "conf": p["confidence"],
                       "basis": p["basis"]})

    print(f"Pathways built: {len(rows)}  (test={args.test})\n")
    print("ACTION TYPE tally:")
    for k, v in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {v:3d}  {k}")
    print("\nSamples:")
    for st, bn, p in samples:
        ent = p["entity_slug"] or "-"
        print(f"  {st} {bn:16s} [{p['action_type']:>20s} via {ent}]  {p['action_summary'][:80]}")


if __name__ == "__main__":
    main()
