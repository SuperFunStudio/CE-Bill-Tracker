"""Parsing in the Indonesia (BPK) and Mexico (LeyesBiblio index) adapters, against captured markup."""
import datetime

import httpx
import pytest

from app.ingestion import foreign
from app.ingestion.foreign import (
    _ID_NATIONAL_RE,
    _ID_SUBJECT_RE,
    IndonesiaBpkClient,
    MexicoLeyesBiblioClient,
    _id_date,
)


def test_indonesian_long_dates():
    assert _id_date("18 Oktober 2019") == datetime.date(2019, 10, 18)
    assert _id_date(" 05 Desember 2019 ") == datetime.date(2019, 12, 5)
    assert _id_date("7 Mei 2008") == datetime.date(2008, 5, 7)
    assert _id_date("31 Februari 2020") is None
    assert _id_date("") is None


@pytest.mark.parametrize("kind,subject,keep", [
    ("Peraturan Menteri Lingkungan Hidup Dan Kehutanan Nomor 75 Tahun 2019",
     "Peta Jalan Pengurangan Sampah oleh Produsen", True),
    ("Undang-undang (UU) No. 18 Tahun 2008", "Pengelolaan Sampah", True),
    # full-text search hits that aren't about waste
    ("Undang-undang (UU) Nomor 28 Tahun 2009", "Pajak Daerah dan Retribusi Daerah", False),
    ("Peraturan Menteri Pertanian Nomor 40 Tahun 2021",
     "Penyelenggaraan Satu Data Indonesia oleh Walidata dan Produsen Data", False),
    # regional instruments are the municipal layer, not this adapter
    ("Peraturan Walikota (PERWALI) Kota Tangerang Selatan Nomor 83 Tahun 2022",
     "Pengurangan Sampah Plastik", False),
])
def test_indonesia_discovery_keeps_only_national_waste_instruments(kind, subject, keep):
    assert bool(_ID_NATIONAL_RE.search(kind) and _ID_SUBJECT_RE.search(subject)) is keep


_BPK_DETAILS = """
<div class="col-lg-3 fw-bold">Judul</div><div class="col-lg-9">Peraturan Menteri Lingkungan Hidup Dan
 Kehutanan Nomor 75 Tahun 2019 tentang Peta Jalan Pengurangan Sampah oleh Produsen</div>
<div class="col-lg-3 fw-bold">Tanggal Penetapan</div><div class="col-lg-9"> <span>18 Oktober 2019</span></div>
<meta name="description" content="… Status: Berlaku. Unduh dokumen …" />
<a href="/Download/372928/P.75-2019%20PETA%20JALAN%20SAMPAH.pdf">Download</a>
"""


async def test_indonesia_fetch_reads_title_date_and_pdf(monkeypatch):
    calls = []

    async def fake_get(self, url, binary=False):
        calls.append(url)
        return b"%PDF" if binary else _BPK_DETAILS

    monkeypatch.setattr(IndonesiaBpkClient, "_get", fake_get)
    monkeypatch.setattr(foreign, "_pdf_to_text", lambda data: "Menimbang " * 50)
    async with IndonesiaBpkClient() as c:
        law = await c.fetch("312182", "Producer roadmap")
    assert calls == ["https://peraturan.bpk.go.id/Details/312182",
                     "https://peraturan.bpk.go.id/Download/372928"]
    assert law.status_date == datetime.date(2019, 10, 18)
    assert law.title.startswith("Peraturan Menteri Lingkungan Hidup")
    assert law.foreign_id == "ID:bpk:312182"


async def test_indonesia_skips_repealed(monkeypatch):
    async def fake_get(self, url, binary=False):
        return _BPK_DETAILS.replace("Status: Berlaku", "Status: Dicabut")

    monkeypatch.setattr(IndonesiaBpkClient, "_get", fake_get)
    async with IndonesiaBpkClient() as c:
        assert await c.fetch("312182") is None


_MX_INDEX = """
<tr><td>197</td><td><a href="ref/lgec.htm"><font>LEY General de Econom\xeda Circular</font></a>
<p>DOF 19/01/2026</p></td><td>Sin reforma</td><td><a href="pdf/LGEC.pdf">pdf</a></td></tr>
<tr><td>12</td><td><a href="ref/lgra.htm"><font>LEY General de Residuos Arqueol\xf3gicos Nueva</font></a>
<p>DOF 02/03/2027</p></td><td></td><td><a href="pdf/LGRAN.pdf">pdf</a></td></tr>
<tr><td>13</td><td><a href="ref/lisr.htm"><font>LEY del Impuesto sobre la Renta</font></a>
<p>DOF 11/12/2013</p></td><td></td><td><a href="pdf/LISR.pdf">pdf</a></td></tr>
"""


async def test_mexico_discovery_adds_new_matching_laws_from_the_index():
    def handler(request):
        return httpx.Response(200, content=_MX_INDEX.encode("latin-1"))

    async with MexicoLeyesBiblioClient() as c:
        c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        found = await c.discover()
    ids = [sid for sid, _ in found]
    assert "LGRAN" in ids and "LISR" not in ids  # title filter: waste law in, tax law out
    assert ids.count("LGEC") == 1  # seeded law isn't duplicated by its index row
    assert c._index_dates["LGRAN"] == datetime.date(2027, 3, 2)
