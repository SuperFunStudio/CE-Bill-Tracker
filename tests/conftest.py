import pytest


@pytest.fixture
def sample_epr_bill():
    return {
        "state": "OR",
        "bill_number": "SB 582",
        "title": "Plastic Pollution and Recycling Modernization Act",
        "description": "An act relating to extended producer responsibility for packaging waste reduction and recycling modernization.",
    }


@pytest.fixture
def sample_non_epr_bill():
    return {
        "state": "TX",
        "bill_number": "HB 100",
        "title": "An Act Relating to Tax Credits for Small Businesses",
        "description": "Provides income tax credits for small business owners in Texas.",
    }
