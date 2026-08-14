"""The amending-act heuristic. Every case here is a real title from the prod corpus.

The asymmetry the tests encode: a missed amending act leaves a small over-count in place, while a
wrongly-flagged principal act deletes a real law from the count. So the false-positive cases below are
the load-bearing ones — they are the failure mode the rule exists to avoid.
"""
import pytest

from app.ingestion.act_role import classify_act_role, is_amending, is_revoked


@pytest.mark.parametrize("title,region", [
    # EU: amendment announced as the act's whole purpose.
    ("DIRECTIVE 2008/33/EC OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL of 11 March 2008 "
     "amending Directive 2000/53/EC on end-of-life vehicles", "EU"),
    ("COMMISSION DIRECTIVE (EU) 2015/1127 of 10 July 2015 amending Annex II to Directive 2008/98/EC",
     "EU"),
    ("Commission Decision of 16 January 2001 amending Decision 2000/532/EC as regards the list of "
     "wastes", "EU"),
    # Westminster: the parenthesized qualifier exists to mark the instrument as amending.
    ("The End-of-Life Vehicles (Producer Responsibility) (Amendment) Regulations 2010", "UK"),
    ("The Producer Responsibility Obligations (Packaging Waste) (Miscellaneous Amendments) "
     "Regulations 2016", "UK"),
    ("The Producer Responsibility Obligations (Packaging Waste) (Amendment No. 2) Regulations 2008",
     "UK"),
    ("Product Stewardship (Oil) (Consequential Amendments) Act 2000", "AU"),
    ("Product Stewardship (Oil) Amendment Act 2007", "AU"),
    # Parenthetical subject between "Amendment" and "Act" — amends the Excise Tariff Act.
    ("Excise Tariff Amendment (Product Stewardship for Oil) Act 2014", "AU"),
    ("India Plastic Waste Management (Amendment) Rules, 2024 (packaging EPR)", "IN"),
    # Non-English amending frames.
    ("Décret n° 2016-794 du 14 juin 2016 modifiant le décret n° 2015-1826 du 30 décembre 2015 "
     "relatif à la commission des filières", "FR"),
    ("Resolution 1342 of 2020 (MADS) — amends Resolution 1407/2018 packaging EPR targets", "CO"),
])
def test_flags_amending_acts(title, region):
    assert is_amending(title, region=region) is True


@pytest.mark.parametrize("title,region,state", [
    # THE US IS EXEMPT. Both of these amend a code and both are the establishing law for a real
    # obligation — the exact rows that made region-level exemption necessary.
    ("An Act amending Title 27 (Environmental Resources) of the Pennsylvania Consolidated Statutes, "
     "in environmental protection, providing for decommissioning of solar energy facilities.",
     "US", "PA"),
    ("Health Care - As enacted, makes revisions to the law relative to wheelchair repair. - "
     "Amends TCA Title 4; Title 8; Title 47, Chapter 18; Title 56; Title 68 and Title 71.",
     "US", "TN"),
    ("Battery Stewardship Program Temporary Amendment Act of 2021", "US", "DC"),
    ("Zero Waste Plastic Product Stewardship Amendment Act of 2022", "US", "DC"),
    ("Waste Tire Recycling Act Amendments", "US", "UT"),
    # "…and amending X" — the amendment is consequential to a substantive regime.
    ("Décret n° 2006-1766 du 23 décembre 2006 relatif au barème de la contribution prévue à "
     "l'article L. 541-10-1 du code de l'environnement et des soutiens versés aux collectivités "
     "mentionnées à ce même article et modifiant le décret n° 2006-239 du 1er mars 2006",
     "FR", "FR"),
    ("Regulation (EU) 2019/1020 of 20 June 2019 on market surveillance and compliance of products "
     "and amending Directive 2004/42/EC", "EU", None),
    # Principal acts that merely discuss amendment, or name no instrument at all.
    ("DIRECTIVE (EU) 2019/904 on the reduction of the impact of certain plastic products on the "
     "environment", "EU", None),
    ("The Producer Responsibility Obligations (Packaging and Packaging Waste) Regulations 2024",
     "UK", None),
    ("Consultation on the amendment of packaging recycling targets", "UK", None),
])
def test_leaves_principal_acts_alone(title, region, state):
    assert is_amending(title, region=region, state=state) is False


def test_empty_and_missing_titles_are_not_amending():
    assert classify_act_role(None) == (False, None)
    assert classify_act_role("   ") == (False, None)


def test_region_defaults_to_us_so_an_unlabelled_row_is_never_flagged():
    # region=None means "caller didn't say"; defaulting to the exempt region keeps the rule from
    # firing on rows whose provenance we don't know.
    assert is_amending("Regulation amending Directive 2008/98/EC") is False
    assert is_amending("Regulation amending Directive 2008/98/EC", region="EU") is True


@pytest.mark.parametrize("title", [
    "The Packaging Waste (Data Collection and Reporting) (Wales) Regulations 2023 (revoked)",
    "The Producer Responsibility Obligations (Packaging Waste) (Amendment) (Wales) Regulations 2020 (revoked)",
    "Some Instrument 1999 (repealed)",
    "Some Instrument 1999 (Revoked) ",
])
def test_detects_titles_that_declare_themselves_revoked(title):
    assert is_revoked(title) is True


@pytest.mark.parametrize("title", [
    # The marker must be a trailing status annotation, not the act's subject matter — a law ABOUT
    # revocation, or one that revokes something else, is still in force itself.
    "The Waste (Revocation) Regulations 2011",
    "An Act providing for the revocation of certain packaging permits",
    "Directive 2018/851 amending Directive 2008/98/EC",
    "",
])
def test_does_not_treat_subject_matter_as_a_revocation_marker(title):
    assert is_revoked(title) is False


def test_revoked_and_amending_are_independent():
    # A revoked amending instrument is both; neither test consumes the other.
    t = "The Producer Responsibility Obligations (Packaging Waste) (Amendment) (Wales) Regulations 2020 (revoked)"
    assert is_revoked(t) is True
    assert is_amending(t, region="UK") is True


def test_rule_name_is_reported_for_audit():
    ok, rule = classify_act_role("The End-of-Life Vehicles (Amendment) Regulations 2010", region="UK")
    assert (ok, rule) == (True, "paren_amendment")
    ok, rule = classify_act_role("Directive 2018/851 amending Directive 2008/98/EC", region="EU")
    assert (ok, rule) == (True, "amending_cite")
