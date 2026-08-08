"""Date derivation for foreign/EU laws — the title is often the most precise source we have.

Every title below is a real corpus row (or its native-language form). The anchor case is the PPWR:
CELEX 32025R0040 carries the OJ numbering year 2025, but the regulation was adopted 19 December 2024, so
the CELEX-year fallback put it in the wrong bucket on every year chart. Titles state the adoption date
formally — "… of 19 December 2024 on packaging and packaging waste" — so the title date has to win.
"""
import datetime

import pytest

from app.ingestion.law_dates import derive_law_year, derive_status_date, derive_title_date


def d(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


class TestEuTitles:
    """EU acts are always styled "<type> <number> of <D Month YYYY> on <subject>"."""

    @pytest.mark.parametrize("title,expected", [
        ("REGULATION (EU) 2025/40 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL of 19 December 2024 "
         "on packaging and packaging waste", "2024-12-19"),
        ("DIRECTIVE (EU) 2019/904 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL of 5 June 2019 on the "
         "reduction of the impact of certain plastic products on the environment", "2019-06-05"),
        ("European Parliament and Council Directive 94/62/EC of 20 December 1994 on packaging and "
         "packaging waste", "1994-12-20"),
        ("REGULATION (EU) 2023/1542 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL of 12 July 2023 "
         "concerning batteries and waste batteries", "2023-07-12"),
    ])
    def test_adoption_date_is_read_from_the_title(self, title, expected):
        assert derive_title_date(title) == d(expected)

    def test_title_date_overrides_a_disagreeing_celex_year(self):
        """The whole point: 32025R0040 -> 2025 by CELEX, but the act is a December 2024 adoption."""
        title = ("REGULATION (EU) 2025/40 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL of "
                 "19 December 2024 on packaging and packaging waste")
        assert derive_law_year("32025R0040", title)[0] == 2025  # the old, off-by-a-year behaviour
        assert derive_status_date("32025R0040", title) == d("2024-12-19")

    def test_oj_citation_dates_are_not_mistaken_for_the_adoption_date(self):
        """Numeric dates in a title are Official Journal citations — often for a DIFFERENT act. Only
        word-months are parsed, and the act's own date precedes anything it cites."""
        title = ("Directive 2000/53/EC of the European Parliament and of the Council of 18 September "
                 "2000 on end-of life vehicles - Commission Statements Official Journal L 269 , "
                 "21/10/2000 P. 0034 - 0043")
        assert derive_title_date(title) == d("2000-09-18")


class TestUkTitles:
    """UK titles carry the year as part of the formal name but never a day, so they stay year-only —
    and the year must agree with the SI number (uksi/<year>/<no>)."""

    @pytest.mark.parametrize("number,title,year", [
        ("ukpga/2021/30", "Environment Act 2021 (EPR/DRS/packaging framework)", 2021),
        ("uksi/2024/1332", "Producer Responsibility Obligations (Packaging & Packaging Waste) "
                           "Regs 2024", 2024),
        ("uksi/2013/3113", "Waste Electrical and Electronic Equipment (WEEE) Regs 2013", 2013),
        ("uksi/2018/1214", "The Waste Electrical and Electronic Equipment (Amendment) (No. 2) "
                           "Regulations 2018", 2018),
        ("wsi/2020/1390", "The Producer Responsibility Obligations (Packaging Waste) (Amendment) "
                          "(Wales) Regulations 2020 (revoked)", 2020),
    ])
    def test_year_only_and_consistent_with_the_si_number(self, number, title, year):
        assert derive_title_date(title) is None, "UK titles name no day"
        assert derive_status_date(number, title) == datetime.date(year, 1, 1)
        assert int(number.split("/")[1]) == year

    def test_amendment_number_is_not_read_as_a_day(self):
        """"(Amendment No. 2) Regulations 2008" — the "2" must not combine into a date."""
        title = ("The Producer Responsibility Obligations (Packaging Waste) (Amendment No. 2) "
                 "Regulations 2008")
        assert derive_status_date("uksi/2008/1941", title) == datetime.date(2008, 1, 1)


class TestOtherLanguages:
    """The same convention, other languages — including the two word orders and the inflected month
    forms that date phrases actually use (PL "grudnia", CS "prosince", LT "gruodžio")."""

    @pytest.mark.parametrize("title,expected", [
        ("Décret n° 2025-73 du 28 janvier 2025 portant modification de la composition du Conseil "
         "national de l'économie circulaire", "2025-01-28"),
        ("Loi n° 2020-105 du 10 février 2020 relative à la lutte contre le gaspillage", "2020-02-10"),
        ("Ordonnance du 1er juillet 2021 sur les emballages", "2021-07-01"),
        ("Ustawa z dnia 6 grudnia 2024 r. o zmianie ustawy o odpadach", "2024-12-06"),
        ("Verordnung vom 19. Dezember 2024 über Verpackungen", "2024-12-19"),
        ("Besluit van 5 juni 2019 houdende regels over verpakkingen", "2019-06-05"),
        ("Decreto del 5 giugno 2019 sui rifiuti di imballaggio", "2019-06-05"),
        ("Lov af 5. juni 2019 om emballage", "2019-06-05"),
        ("Laki 5. kesäkuuta 2019 jätteistä", "2019-06-05"),
        ("Zákon ze dne 6. prosince 2024 o odpadech", "2024-12-06"),
        # Year-first order (Lithuanian).
        ("Nutarimas 2024 m. gruodžio 6 d. dėl pakuočių", "2024-12-06"),
    ])
    def test_day_precision_across_languages(self, title, expected):
        assert derive_title_date(title) == d(expected)


class TestGuards:
    def test_forward_looking_deadlines_are_not_adoption_dates(self):
        """A title may name a compliance date; that is not when the law was made."""
        assert derive_title_date("Regulations banning single-use plastics from 3 July 2021") is None
        assert derive_title_date("Act requiring 65% recycling by 31 December 2035") is None

    def test_future_years_never_win(self):
        assert derive_title_date("A resolution to achieve circularity by 2030") is None
        assert derive_law_year(None, "Roadmap to 2050 targets") is None

    def test_impossible_calendar_dates_are_skipped_not_raised(self):
        assert derive_title_date("Act of 31 February 2019 on waste") is None

    def test_no_title_no_date(self):
        assert derive_title_date(None) is None
        assert derive_title_date("") is None

    @pytest.mark.xfail(reason="Known gap: Spanish/Portuguese titles put the year in the instrument "
                              "number and omit it from the date phrase ('Real Decreto 1055/2022, de 16 "
                              "de diciembre'), so the day+month must be composed with a year derived "
                              "elsewhere. No corpus row needs it yet — the ES rows carry English "
                              "curated titles with no date phrase at all.",
                       strict=True)
    def test_day_month_without_year_in_phrase(self):
        title = "Real Decreto 1055/2022, de 16 de diciembre, de envases y residuos de envases"
        assert derive_status_date("BOE-A-2022-22690", title) == d("2022-12-16")
