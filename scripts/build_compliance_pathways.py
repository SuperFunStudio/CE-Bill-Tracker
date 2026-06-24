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
         registration_url="https://circularactionalliance.org/",  # was /producers (404, audit 2026-06-18)
         jurisdiction_scope="multistate",
         materials=["plastic_packaging", "paper_packaging", "packaging", "paper"],
         description="The packaging & paper-products PRO designated across CA, CO, MD, MN, OR, WA and "
                     "other packaging-EPR states."),
    dict(slug="paintcare", name="PaintCare", entity_type="pro",
         url="https://www.paintcare.org",
         registration_url="https://www.paintcare.org/manufacturers/",
         jurisdiction_scope="multistate", materials=["paint"],
         description="Nonprofit paint stewardship PRO operating every U.S. state paint-EPR program."),
    # Call2Recycle rebranded to "Battery Network" in 2025; the call2recycle.org links now WAF-block
    # bots (audit 2026-06-18). Slug kept stable so existing domain/material routing still resolves.
    dict(slug="call2recycle", name="Battery Network (formerly Call2Recycle)", entity_type="pro",
         url="https://batterynetwork.org",
         registration_url="https://batterynetwork.org/battery-stewardship/",
         jurisdiction_scope="national", materials=["batteries"],
         description="The national battery stewardship PRO (rebranded from Call2Recycle to Battery "
                     "Network); operator for most state battery-EPR programs."),
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
         url="https://med-project.org",
         registration_url="https://med-project.org/",  # was /covered-manufacturers/ (404, audit 2026-06-18)
         jurisdiction_scope="multistate", materials=["pharmaceuticals", "medical_sharps"],
         description="Pharmaceutical & sharps take-back PRO operating many drug-stewardship programs."),
    # Mercury-added products: the reporting obligation is the multi-state IMERC clearinghouse (run by
    # NEWMOA), NOT a PRO. Several "no producer obligation" laws actually require an IMERC filing.
    dict(slug="newmoa-imerc", name="IMERC — Interstate Mercury Education & Reduction Clearinghouse (NEWMOA)",
         entity_type="agency", url="https://www.newmoa.org/programs/mercury-clearinghouse/",
         registration_url="https://www.newmoa.org/programs/mercury-clearinghouse/imerc-guidance/report/",
         jurisdiction_scope="multistate",
         materials=["mercury", "mercury_added_products", "lighting", "thermostats"],
         description="Multi-state clearinghouse where producers of mercury-added products (lamps, "
                     "thermostats, switches) file required notifications and sales reports."),
    # California's mercury-product rules (e.g. thermostats) are administered by DTSC, distinct from
    # CalRecycle. Curated separately so CA mercury laws don't get pointed at CalRecycle.
    dict(slug="ca-dtsc", name="California Dept. of Toxic Substances Control (DTSC)", entity_type="agency",
         url="https://dtsc.ca.gov",
         registration_url="https://dtsc.ca.gov/toxics-in-products/mercury-thermostat-requirements/",
         jurisdiction_scope="single_state", home_state="CA", materials=["mercury", "thermostats"],
         description="California agency administering mercury-added product requirements (thermostats, etc.)."),
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
    # HI's enacted e-waste law (Act 13, 2008 Sp. Sess.) points producers at the DOH e-waste program;
    # the homepage IS the program page, so it doubles as the registration link.
    ("HI", "hi-doh", "Hawaii Department of Health — Electronic Waste Program", "https://health.hawaii.gov/ewaste/"),
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

# --- Curated overrides: where automated (model + material) resolution is wrong or too coarse. ---
# These are the cases where a human found the authoritative "how to comply" page the classifier
# can't infer — a material-specific program page, or a "no obligation"-classified law that actually
# carries a reporting duty. Two granularities:
#   PROGRAM_PAGES[(state, material)] — generalizes across every law of that material in the state
#                                      (e.g. all RI electronics laws -> RI DEM e-waste page).
#   BILL_OVERRIDES[(state, norm_bill_number)] — pins ONE law, for when (state, material) collides
#                                      (e.g. CA+batteries is BOTH SB-1215/CalRecycle and AB-2440/PRO).
# A match sets basis="manual". BILL_OVERRIDES wins over PROGRAM_PAGES. Each value may set any of:
#   entity_slug, url, action_type, action_summary  (only the keys present are applied).
PROGRAM_PAGES = {
    # HI Act 13 has no management_model -> classifier lands it on "none", but the DOH e-waste program
    # is a real registration path. (state, material) flips every HI electronics law onto it.
    ("HI", "electronics"): dict(
        entity_slug="hi-doh",
        url="https://health.hawaii.gov/ewaste/",
        action_type="register_with_state",
        action_summary="Register your covered electronic devices with Hawaii DOH's e-waste program."),
    ("RI", "electronics"): dict(
        entity_slug="ri-dem",
        url="https://dem.ri.gov/environmental-protection-bureau/land-revitalization-and-sustainable-materials-management/ewaste",
        action_type="register_with_state",
        action_summary="Register your covered electronic products with RI DEM's e-waste program."),
}


def _norm_bn(bn):
    return (bn or "").replace(" ", "").upper()


BILL_OVERRIDES = {
    ("CA", _norm_bn("AB-732")): dict(
        entity_slug="ca-dtsc",
        url="https://dtsc.ca.gov/toxics-in-products/mercury-thermostat-requirements/",
        action_type="register_with_state",
        action_summary="Comply with California DTSC's mercury-added product requirements "
                       "(e.g. thermostat collection)."),
    ("CA", _norm_bn("SB-1215")): dict(
        entity_slug="calrecycle",
        url="https://calrecycle.ca.gov/electronics/embeddedbatteries/noticeguide/",
        action_type="register_with_state",
        action_summary="Follow CalRecycle's embedded-battery requirements for covered "
                       "electronic devices (notice & recycling guide)."),
    ("MA", _norm_bn("H-5112")): dict(
        entity_slug="newmoa-imerc",
        url="https://www.newmoa.org/programs/mercury-clearinghouse/imerc-guidance/report/",
        action_type="register_with_state",
        action_summary="Report your mercury-added lamps/products to IMERC, the multi-state "
                       "mercury clearinghouse (NEWMOA)."),
    ("IL", _norm_bn("SB-2313")): dict(
        entity_slug="call2recycle",
        url="https://batterynetwork.org/recycling-laws-by-state/",
        action_type="join_pro",
        action_summary="Battery producers register with Battery Network (formerly Call2Recycle) "
                       "for the Illinois program."),
    # Found by scripts/propose_compliance_links.py (2026-06-18, verified alive, conf 0.93); was
    # classified "none" with a bare CalRecycle homepage. entity_slug is required to render the link.
    ("CA", _norm_bn("AB-2398")): dict(
        entity_slug="carpet-america-recovery-effort",
        url="https://carpetrecovery.org/carpet-manufacturer-registration-for-the-care-stewardship-plan-for-california-ab-2398/",
        action_type="join_pro",
        action_summary="Carpet manufacturers selling into California must register with and join "
                       "the Carpet America Recovery Effort (CARE) to be covered under its "
                       "CalRecycle-approved carpet stewardship plan and comply with AB 2398."),
    # Found by propose_compliance_links.py (2026-06-18, verified alive, conf 0.95); was a bare
    # CalRecycle homepage. Deep beverage-container distributor/manufacturer registration page.
    ("CA", _norm_bn("SB-1013")): dict(
        entity_slug="calrecycle",
        url="https://calrecycle.ca.gov/bevcontainer/bevdistman/",
        action_type="register_with_state",
        action_summary="Beverage manufacturers and distributors of newly covered containers "
                       "(including wine and distilled spirits) must register with CalRecycle's "
                       "Beverage Container Recycling Program and file distributor reports plus "
                       "CRV/processing-fee payments."),
    # Found by propose_compliance_links.py (2026-06-18, verified alive, conf 0.95). CORRECTS a
    # known mislabel: SB-1143 is a PAINT law previously pointed at CalRecycle; the PRO is PaintCare.
    ("CA", _norm_bn("SB-1143")): dict(
        entity_slug="paintcare",
        url="https://www.paintcare.org/manufacturers/",
        action_type="join_pro",
        action_summary="A paint manufacturer must register its company and brands with PaintCare, "
                       "the designated paint stewardship organization, to comply with California's "
                       "architectural paint stewardship program."),
    # === Layer-3 homepage batch, applied 2026-06-19 (verified links; see compliance_link_proposals_homepage_full.txt) ===
    # CA AB899 — AB 899 (Ch. 627, 2025) amends PRC §14549.7 to raise the Glass Market Development Payment rate, and this is the official CalRecycle .gov program page describing how glass beverage container manufacturers qualify, report, and claim that government-run payment.
    #   verify: [alive] ok  |  confidence=0.74  |  suggested entity: California Department of Resources Recycling and Recovery (CalRecycle) — Glass Market Development Payment (GMDP) Program (agency)
    ("CA", _norm_bn("AB899")): dict(
        url="https://calrecycle.ca.gov/bevcontainer/wine-spirits/",
        action_type="report_to_program",
        action_summary="A California glass beverage container manufacturer that buys in-state recycled glass should file a GMD Determination of Eligibility and submit quarterly Glass Market Development Payment claim/reports to CalRecycle (Statistical Information Section, MarketInformation@calrecycle.ca.gov) under PRC \u00a714549.7 to receive the per-ton payment."),
    # CA SB-1181 — SB-1181 amends the state-run California Tire Recycling Act (manifest/hauler tracking moving to CalRecycle's electronic system); CalRecycle's official tires program page is the authoritative state registration/reporting hub, as there is no designated producer PRO for tires in California.
    #   verify: [alive] ok  |  confidence=0.55  |  suggested entity: California Department of Resources Recycling and Recovery (CalRecycle) (agency)
    ("CA", _norm_bn("SB-1181")): dict(
        url="https://calrecycle.ca.gov/tires/",
        action_type="register_with_state",
        action_summary="Register with CalRecycle's Waste Tire Management Program (e.g., as a waste/used tire hauler obtain a Tire Program ID and use CalRecycle's electronic manifest system under SB-1181), and register a California Tire Fee account with CDTFA to report and remit the tire fee."),
    # CA SB-1723 — This is DPR's official program page implementing FAC 12841.4, which states the section requires every covered pesticide registrant to participate in a recycling program and annually certify compliance to the director.
    #   verify: [redirected] redirected to a different location  |  confidence=0.9  |  suggested entity: California Department of Pesticide Regulation (DPR) (agency)
    ("CA", _norm_bn("SB-1723")): dict(
        url="https://www.cdpr.ca.gov/docs/mill/container_recycling/pest_container.htm",
        action_type="report_to_program",
        action_summary="If you are a registrant of a production agricultural- or structural-use pesticide sold in California in rigid nonrefillable HDPE containers of 55 gallons or less, establish or participate in an ANSI/ASABE S596-compliant recycling program and submit an annual certifying document to the Department of Pesticide Regulation director."),
    # CA SB-212 — This is CalRecycle's official SB 212 'Covered Entities' requirements page, which spells out exactly what sharps producers must do to comply, citing the governing Public Resources Code sections.
    #   verify: [alive] ok  |  confidence=0.92  |  suggested entity: California Department of Resources Recycling and Recovery (CalRecycle) (agency)
    ("CA", _norm_bn("SB-212")): dict(
        entity_slug="med-project",
        url="https://calrecycle.ca.gov/epr/pharmasharps/coveredentities/",
        action_type="join_pro",
        action_summary="A sharps manufacturer (covered entity) must establish and implement a CalRecycle-approved home-generated sharps stewardship program\u2014typically by joining the designated stewardship organization MED-Project\u2014and submit product lists to the Board of Pharmacy plus a stewardship plan, budget, and annual reports to CalRecycle."),
    # CA SB-38 — This is CalRecycle's official registration page stating that distributors and manufacturers must register with the state to meet the program's reporting and payment requirements for beverage containers (glass, metal, plastic).
    #   verify: [alive] ok  |  confidence=0.92  |  suggested entity: California Department of Resources Recycling and Recovery (CalRecycle) (agency)
    ("CA", _norm_bn("SB-38")): dict(
        url="https://www2.calrecycle.ca.gov/BevContainerDetermination/",
        action_type="register_with_state",
        action_summary="Beverage manufacturers and distributors must register with CalRecycle by submitting the Beverage Manufacturer & Distributor Registration Form to meet the reporting and payment requirements of California's Beverage Container Recycling and Litter Reduction Act."),
    # CO HB26-1111 — The CDA Pesticides Program page is the official state agency page administering the HB26-1111 Pesticide Disposal and Recycling Program, explicitly developing rules for product registration and disposal fees for pesticide registrants.
    #   verify: [alive] ok  |  confidence=0.85  |  suggested entity: Colorado Department of Agriculture (CDA), Pesticides Program — Pesticide Disposal and Recycling Program (agency)
    ("CO", _norm_bn("HB26-1111")): dict(
        url="https://ag.colorado.gov/plants/pesticides",
        action_type="register_with_state",
        action_summary="Pesticide producers/registrants must register their products with and pay disposal fees to the Colorado Department of Agriculture's Pesticide Disposal and Recycling Program (Enterprise) created by HB26-1111."),
    # CT HB-7249 — This is the official CT DEEP program page that explicitly states manufacturers must register their brand(s) with DEEP using the ERCC online registration to comply with the CT Electronics Recycling Law (CGS §§22a-629–640).
    #   verify: [alive] ok  |  confidence=0.95  |  suggested entity: Connecticut Department of Energy and Environmental Protection (DEEP) (agency)
    ("CT", _norm_bn("HB-7249")): dict(
        url="https://portal.ct.gov/DEEP/Reduce-Reuse-Recycle/Electronics/Requirements-for-Manufacturers",
        action_type="register_with_state",
        action_summary="Manufacturers of covered electronic devices (computers, monitors, printers, televisions) must register their brands annually with Connecticut DEEP via the Electronics Recycling Coordination Clearinghouse (ERCC) online 'eCycle' registration system and pay the annual registration fee."),
    # FL Fla. Stat. 403.7192 — It is the Florida DEP (state agency) program page that specifically administers and explains the Fla. Stat. 403.7192 manufacturer/marketer 'unit management system' obligation for rechargeable batteries; the statute creates no separate online producer-registration portal or designated PRO.
    #   verify: [blocked] server refused / unavailable  |  confidence=0.8  |  suggested entity: Florida Department of Environmental Protection (DEP) (agency)
    ("FL", _norm_bn("Fla. Stat. 403.7192")): dict(
        url="https://floridadep.gov/waste/permitting-compliance-assistance/content/battery-main-page",
        action_type="file_individual_plan",
        action_summary="A manufacturer or marketer of nickel-cadmium or small sealed lead-acid rechargeable batteries (and products containing them) sold in Florida must implement and operate a 'unit management program' for collection, labeling, and recycling/disposal of the units\u2014done individually, through a representative manufacturers' organization, or by contract\u2014per Fla. Stat. 403.7192 as administered by the Florida DEP."),
    # IN HB-1589 — This is the official IDEM (in.gov) Indiana E-Cycle program page implementing the Indiana E-Waste Law (IC 13-20.5), which explicitly states manufacturers must submit online registration and an annual report.
    #   verify: [alive] ok  |  confidence=0.97  |  suggested entity: Indiana Department of Environmental Management (IDEM) — Indiana E-Cycle Program (agency)
    ("IN", _norm_bn("HB-1589")): dict(
        url="https://www.in.gov/idem/recycle/indiana-e-cycle/",
        action_type="register_with_state",
        action_summary="Manufacturers of video display devices sold to Indiana households must submit an online manufacturer registration and annual report to IDEM's Indiana E-Cycle Program (via its Re-TRAC portal) by March 1 and pay the registration fee."),
    # MD HB-575 — This official MDE .gov program page describes the Statewide Electronics Recycling Program's manufacturer registration requirement and links directly to the registration form and guidelines.
    #   verify: [alive] ok  |  confidence=0.95  |  suggested entity: Maryland Department of the Environment (MDE) — Statewide Electronics Recycling Program (agency)
    ("MD", _norm_bn("HB-575")): dict(
        url="https://mde.maryland.gov/programs/land/WasteManagement/Pages/eCycling.aspx",
        action_type="register_with_state",
        action_summary="A covered electronic device manufacturer must register annually with the Maryland Department of the Environment (by March) and pay the annual fee, using MDE's Electronic Manufacturer Registration Form."),
    # ME LD-1921 — This is the official Maine DEP (Bureau of Remediation and Waste Management) program page specifically for mercury auto-switch recycling under 38 MRSA §1665-A, and it names ELVS as the collective compliance program manufacturers pay into.
    #   verify: [alive] ok  |  confidence=0.82  |  suggested entity: End of Life Vehicle Solutions (ELVS) — national mercury switch recovery program designated by Maine DEP (pro)
    ("ME", _norm_bn("LD-1921")): dict(
        entity_slug="elv-solutions",
        url="https://www.maine.gov/dep/waste/motorvehiclerecycling/hg-recycling.html",
        action_type="join_pro",
        action_summary="A motor vehicle manufacturer satisfies its 38 MRSA \u00a71665-A 'individually or collectively' obligation by funding/participating in the ELVS collective mercury auto-switch collection and recycling program that Maine DEP directs producers to (sign up at elvsolutions.org, $4/switch), rather than running a separate plan."),
    # MI SB-897 — This is the official EGLE state agency program page for Michigan's Electronics Recycling Act (Act 451, Part 173), which explicitly states manufacturers must annually register brands and links to the Ecycle registration portal.
    #   verify: [alive] ok  |  confidence=0.95  |  suggested entity: Michigan Department of Environment, Great Lakes, and Energy (EGLE) (agency)
    ("MI", _norm_bn("SB-897")): dict(
        url="https://www.michigan.gov/egle/about/organization/materials-management/ewaste/takeback-program",
        action_type="register_with_state",
        action_summary="Manufacturers of covered electronic devices must annually register each of their brands with Michigan EGLE's Electronic Waste Takeback Program (via the Ecycle registration system at ecycleregistration.org) and operate a free consumer takeback program."),
    # MN HF-854 — This is the MPCA's official program page for electronics manufacturers under the Minnesota Electronics Recycling Act, detailing the required registration form, fee, and recycling obligation.
    #   verify: [alive] ok  |  confidence=0.96  |  suggested entity: Minnesota Pollution Control Agency (MPCA) (agency)
    ("MN", _norm_bn("HF-854")): dict(
        url="https://www.pca.state.mn.us/business-with-us/electronics-manufacturers",
        action_type="register_with_state",
        action_summary="Manufacturers of video display devices must register with the Minnesota Pollution Control Agency (MPCA), pay an annual registration fee, and meet a recycling obligation based on their Minnesota market share by filing the manufacturer registration form (w-gen2-52) by August 15 each year."),
    # NC SB-1492 — This is the official NC DEQ state program page for electronics management that lists the manufacturer registration deadlines, fees, annual reporting, and links to the e-Cycle Registration portal and required forms.
    #   verify: [alive] ok  |  confidence=0.95  |  suggested entity: North Carolina Department of Environmental Quality (NC DEQ), Division of Waste Management, Solid Waste Section (agency)
    ("NC", _norm_bn("SB-1492")): dict(
        url="https://www.deq.nc.gov/about/divisions/waste-management/solid-waste-section/special-wastes-and-alternative-handling/electronics-management",
        action_type="register_with_state",
        action_summary="Computer and television manufacturers must register annually with NC DEQ's Division of Waste Management (via the e-Cycle Registration portal linked on the Electronics Management page), pay annual registration fees, and submit annual reports; computer manufacturers must also file a recycling plan."),
    # NJ A-3572 — This is the official NJDEP E-Cycle Manufacturers program page on the state's dep.nj.gov domain, dedicated specifically to manufacturer obligations under the NJ Electronic Waste Management Act.
    #   verify: [alive] ok  |  confidence=0.92  |  suggested entity: New Jersey Department of Environmental Protection (NJDEP), Division of Sustainable Waste Management — E-Cycle Program (agency)
    ("NJ", _norm_bn("A-3572")): dict(
        url="https://dep.nj.gov/dshw/rhwm/e-waste/e-cycle-manu/",
        action_type="register_with_state",
        action_summary="Manufacturers of covered electronic devices must register annually with the NJDEP E-Cycle program and submit a collection/recycling plan to comply."),
    # OK SB-1631 — This is the official Oklahoma DEQ program page for OCERA (27A O.S. § 2-11-601, SB-1631) that links the statute, rules, recovery plan guide, and annual report form, and details manufacturer registration/reporting obligations.
    #   verify: [alive] ok  |  confidence=0.97  |  suggested entity: Oklahoma Department of Environmental Quality (DEQ) (agency)
    ("OK", _norm_bn("SB-1631")): dict(
        url="https://oklahoma.gov/deq/divisions/land-protection/sust-materials-management/recycling/electronics-recycling/ocera.html",
        action_type="file_individual_plan",
        action_summary="A manufacturer that sells, imports, or produces 50+ covered computers/monitors per year in Oklahoma must implement an individual take-back recovery plan, submit an annual manufacturer report, and pay an annual fee to the Oklahoma DEQ by March 1 each year (email OCERA.Reporting@deq.ok.gov / cat.ecker@deq.ok.gov)."),
    # OR HB-2626 — This is the official Oregon.gov DEQ Oregon E-Cycles 'For Manufacturers' page that states covered electronics manufacturers must register with DEQ by Dec. 31 and provides the registration process and fees.
    #   verify: [alive] ok  |  confidence=0.97  |  suggested entity: Oregon Department of Environmental Quality (DEQ) — Oregon E-Cycles (agency)
    ("OR", _norm_bn("HB-2626")): dict(
        url="https://www.oregon.gov/deq/ecycles/pages/manufacturers.aspx",
        action_type="register_with_state",
        action_summary="Manufacturers of computers, monitors, TVs, and desktop printers sold in or into Oregon must register their brands with Oregon DEQ (and submit annual sales data) to comply with the Oregon E-Cycles program."),
    # OR HB-3273 — This is the official Oregon DEQ program page that administers HB-3273 (ORS 459A.200+), names the DEQ-approved program operators manufacturers must join, and links the manufacturer participation guidance.
    #   verify: [alive] ok  |  confidence=0.9  |  suggested entity: Oregon Department of Environmental Quality (DEQ) (agency)
    ("OR", _norm_bn("HB-3273")): dict(
        entity_slug="med-project",
        url="https://www.oregon.gov/deq/mm/pages/drugtakeback.aspx",
        action_type="join_pro",
        action_summary="A covered drug manufacturer must participate in and fund a DEQ-approved drug take-back program operator (e.g., Drug Takeback Solutions Foundation or MED-Project USA, LLC) and ensure its covered drugs are listed via the Oregon Board of Pharmacy registration, as overseen by Oregon DEQ."),
    # SC H-4093 — This is the official SCDES program page implementing the Act, which expressly states manufacturers must register and pay fees and provides the registration contact/portal.
    #   verify: [alive] ok  |  confidence=0.92  |  suggested entity: South Carolina Department of Environmental Services (SCDES) (agency)
    ("SC", _norm_bn("H-4093")): dict(
        url="https://des.sc.gov/community/recycling-waste-reduction/electronics-recycling/electronics-recycling-businesses-retailers-and-manufacturers",
        action_type="register_with_state",
        action_summary="Manufacturers of covered computer/monitor/television devices must register with the SC Department of Environmental Services (SCDES) through its e-permitting system (contact e-register@des.sc.gov), pay the applicable fee, and provide or fund a no-cost recovery program."),
    # TX HB-2714 — This is the official TCEQ program page for HB 2714's Texas Recycles Computers Program, citing 30 TAC 328.137 and providing the manufacturer notification/recovery-plan and annual report forms.
    #   verify: [alive] ok  |  confidence=0.95  |  suggested entity: Texas Commission on Environmental Quality (TCEQ) — Texas Recycles Computers Program (agency)
    ("TX", _norm_bn("HB-2714")): dict(
        url="https://www.tceq.texas.gov/p2/recycle/electronics/computer-recycling.html",
        action_type="file_individual_plan",
        action_summary="A computer-equipment manufacturer selling new equipment in or into Texas must submit a notification and recovery plan (TCEQ-20597) to the TCEQ Texas Recycles Computers Program to get on TCEQ's manufacturer list, and file an annual recycling report by January 31 each year."),
    # UT SB-184 — The enacted statute (Utah Code 19-6-1203, the codification of SB-184) is the authoritative source that defines the manufacturer's annual reporting obligation 'to the department' (Utah DEQ), and DEQ provides no separate dedicated e-waste producer reporting portal.
    #   verify: [alive] ok  |  confidence=0.78  |  suggested entity: Utah Department of Environmental Quality, Division of Waste Management and Radiation Control (agency)
    ("UT", _norm_bn("SB-184")): dict(
        url="https://le.utah.gov/xcode/Title19/Chapter6/C19-6-P12_1800010118000101.pdf",
        action_type="report_to_program",
        action_summary="A manufacturer of consumer electronic devices must prepare and submit an annual report (listing eligible recycling programs) to the Utah Department of Environmental Quality on or before August 1 each year before offering devices for sale in Utah."),
    # VA HB-344 — This is the official Virginia DEQ statewide-recycling program page for the Computer Recovery and Recycling Act and hosts the Computer Manufacturer Registration Form, Annual Report Form, and recovery-plan requirements.
    #   verify: [blocked] server refused / unavailable  |  confidence=0.97  |  suggested entity: Virginia Department of Environmental Quality (DEQ) (agency)
    ("VA", _norm_bn("HB-344")): dict(
        url="https://www.deq.virginia.gov/land-waste/waste-management/recycling/statewide-recycling-programs/computer-electronics-recycling",
        action_type="file_individual_plan",
        action_summary="A computer manufacturer that sold more than 500 computer units under its brand in Virginia must file its own recovery/recycling plan with the Virginia DEQ (using the Computer Manufacturer Registration Form) before its products can be sold in the state."),
    # VT S-77 — This is the official Vermont DEC (.gov) E-Cycles program page for manufacturers, which states non-exempt manufacturers must register with the state and links directly to the state registration form.
    #   verify: [alive] ok  |  confidence=0.97  |  suggested entity: Vermont Department of Environmental Conservation – E-Cycles Program (agency)
    ("VT", _norm_bn("S-77")): dict(
        url="https://dec.vermont.gov/e-cycles-manufacturers-and-retailers",
        action_type="register_with_state",
        action_summary="An electronics manufacturer selling covered devices (computers, monitors, printers, TVs) in Vermont must register and pay registration and implementation fees through the Vermont DEC E-Cycles Program before its brand can be legally sold in the state."),
    # WA SB-5939 — This is the official Washington Department of Ecology (.gov) program page dedicated to the PV Module Stewardship and Takeback Program created by SB 5939, citing the statute and linking to the manufacturer stewardship-plan guidance.
    #   verify: [alive] ok  |  confidence=0.92  |  suggested entity: Washington State Department of Ecology (agency)
    ("WA", _norm_bn("SB-5939")): dict(
        url="https://ecology.wa.gov/waste-toxics/reducing-recycling-waste/our-recycling-programs/solar-panels",
        action_type="file_individual_plan",
        action_summary="A solar panel (PV module) manufacturer must develop and submit a stewardship/takeback plan to the Washington Department of Ecology for approval (per Chapter 70A.510.010 RCW), following Ecology's manufacturer plan guidance, before selling modules in or into Washington."),
    # WI SB-107 — This is the official Wisconsin DNR program page specifically for electronics manufacturers, detailing who must register and the registration requirements under the E-Cycle Wisconsin law.
    #   verify: [alive] ok  |  confidence=0.97  |  suggested entity: E-Cycle Wisconsin, Wisconsin Department of Natural Resources (DNR) (agency)
    ("WI", _norm_bn("SB-107")): dict(
        url="https://dnr.wisconsin.gov/topic/Ecycle/Manufacturers.html",
        action_type="register_with_state",
        action_summary="Manufacturers of covered electronic devices sold to Wisconsin households or K-12 schools must register annually with E-Cycle Wisconsin (administered by the Wisconsin DNR) and meet their assigned recycling targets."),
    # WV SB-746 — This is WVDEP's official .gov 'Covered Electronic Device Manufacturer and Retailer Compliance Information' page, which directly cites SB-746 and the WV Code §22-15A-25 manufacturer registration requirement.
    #   verify: [alive] ok  |  confidence=0.97  |  suggested entity: West Virginia Department of Environmental Protection (WVDEP), Rehabilitation Environmental Action Plan (REAP) – Covered Electronic Devices Program (agency)
    ("WV", _norm_bn("SB-746")): dict(
        url="https://dep.wv.gov/environmental-advocate/reap/cedprogram/Pages/default.aspx",
        action_type="register_with_state",
        action_summary="A manufacturer that sells or leases covered electronic devices in West Virginia must register annually (by January 1 each year) with the WV Department of Environmental Protection's REAP Covered Electronic Devices program and pay the registration fee."),
    # CA AB-1311 — beverage-container law; Layer-3 candidate 404'd on a stale /Registration/
    #   subpath, substituted CalRecycle's working bev-distributor/manufacturer page (verified 200).
    ("CA", _norm_bn("AB-1311")): dict(
        entity_slug="calrecycle",
        url="https://calrecycle.ca.gov/bevcontainer/bevdistman/",
        action_type="register_with_state",
        action_summary="Beverage manufacturers and distributors of covered containers must register with CalRecycle's Beverage Container Recycling Program (Beverage Distributor/Manufacturer registration) and file the required reports and CRV/processing-fee payments."),
    # CA AB-962 — beverage-container law; Layer-3 candidate 404'd on a stale /Registration/
    #   subpath, substituted CalRecycle's working bev-distributor/manufacturer page (verified 200).
    ("CA", _norm_bn("AB-962")): dict(
        entity_slug="calrecycle",
        url="https://calrecycle.ca.gov/bevcontainer/bevdistman/",
        action_type="register_with_state",
        action_summary="Beverage manufacturers and distributors of covered containers must register with CalRecycle's Beverage Container Recycling Program (Beverage Distributor/Manufacturer registration) and file the required reports and CRV/processing-fee payments."),
    # CA SB1113 — beverage-container law; Layer-3 candidate 404'd on a stale /Registration/
    #   subpath, substituted CalRecycle's working bev-distributor/manufacturer page (verified 200).
    ("CA", _norm_bn("SB1113")): dict(
        entity_slug="calrecycle",
        url="https://calrecycle.ca.gov/bevcontainer/bevdistman/",
        action_type="register_with_state",
        action_summary="Beverage manufacturers and distributors of covered containers must register with CalRecycle's Beverage Container Recycling Program (Beverage Distributor/Manufacturer registration) and file the required reports and CRV/processing-fee payments."),
    # CA SB353 — beverage-container law; Layer-3 candidate 404'd on a stale /Registration/
    #   subpath, substituted CalRecycle's working bev-distributor/manufacturer page (verified 200).
    ("CA", _norm_bn("SB353")): dict(
        entity_slug="calrecycle",
        url="https://calrecycle.ca.gov/bevcontainer/bevdistman/",
        action_type="register_with_state",
        action_summary="Beverage manufacturers and distributors of covered containers must register with CalRecycle's Beverage Container Recycling Program (Beverage Distributor/Manufacturer registration) and file the required reports and CRV/processing-fee payments."),
    # CA SB-20 — Electronic Waste Recycling Act of 2003; recovered CalRecycle CEW manufacturer
    #   page (verified 200) after the Layer-3 candidate 404'd.
    ("CA", _norm_bn("SB-20")): dict(
        entity_slug="calrecycle",
        url="https://calrecycle.ca.gov/electronics/manufacturer/",
        action_type="register_with_state",
        action_summary="Manufacturers of covered electronic devices must comply with CalRecycle's Covered Electronic Waste (CEW) program requirements for manufacturers under the Electronic Waste Recycling Act of 2003 (SB 20)."),
}


def apply_override(state, bn, mats, p, entities_by_slug):
    """Apply a curated override (per-bill, else per-material) onto a computed pathway dict."""
    ov = BILL_OVERRIDES.get((state, _norm_bn(bn)))
    if ov is None:
        for m in (mats or []):
            if (state, m) in PROGRAM_PAGES:
                ov = PROGRAM_PAGES[(state, m)]
                break
    if not ov:
        return p
    if ov.get("entity_slug"):
        ent = entities_by_slug.get(ov["entity_slug"])
        if ent:
            p["entity_slug"] = ent["slug"]
            p["registration_url"] = ov.get("url") or ent.get("registration_url") or ent.get("url")
    if ov.get("url"):
        p["registration_url"] = ov["url"]
    if ov.get("action_type"):
        p["action_type"] = ov["action_type"]
    if ov.get("action_summary"):
        p["action_summary"] = ov["action_summary"]
    p["basis"] = "manual"
    return p

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

    p = dict(entity_slug=(entity["slug"] if entity else None), action_type=action,
             action_summary=summary, registration_url=reg, management_model=model,
             next_deadline_date=next_dl, has_fee=has_fee, confidence=conf, basis=basis)
    return apply_override(state, bn, mats, p, entities_by_slug)


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
        where b.ce_relevant and b.state!='US' and b.status='enacted'
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
