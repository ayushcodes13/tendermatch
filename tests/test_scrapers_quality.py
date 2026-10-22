"""Sanitized, hermetic quality and resilience tests for all active portal scrapers."""

from datetime import datetime, timezone
from bs4 import BeautifulSoup
import pytest
import requests

import sys
from types import ModuleType

if "sentence_transformers" not in sys.modules:
    try:
        __import__("sentence_transformers")
    except ImportError:
        stub = ModuleType("sentence_transformers")
        stub.SentenceTransformer = object
        sys.modules["sentence_transformers"] = stub

from data.db import generate_hash
from pipeline.run import collect_all_tenders
from scrapers import cppp, iisc, iit_goa, iit_palakkad, iitm


class MockResponse:
    def __init__(self, text: str = "", json_data: dict | list | None = None, status_code: int = 200):
        self.text = text
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP Error {self.status_code}")

    def json(self):
        if self._json_data is not None:
            return self._json_data
        raise ValueError("No JSON data")


# ==============================================================================
# 1. CPPP Portal Scraper Tests (Central, State, GeM)
# ==============================================================================

CPPP_CENTRAL_HTML = """
<html><body>
<table>
  <tr><th>S.No</th><th>e-Published Date</th><th>Closing Date</th><th>Opening Date</th><th>Title and Ref.No./Tender ID</th><th>Organisation Chain</th></tr>
  <tr>
    <td>1</td>
    <td>22-Oct-2026 09:00 AM</td>
    <td>15-Nov-2026 05:00 PM</td>
    <td>16-Nov-2026 10:00 AM</td>
    <td>Supply of High Vacuum Turbo Molecular Pump System / CPPP/2026_1001_1</td>
    <td>Indian Institute of Science||Department of Electronic Systems Engineering</td>
  </tr>
</table>
</body></html>
"""

CPPP_GEM_HTML = """
<html><body>
<table>
  <tr><th>S.No</th><th>Bid Published Date</th><th>Bid End Date</th><th>Bid Number</th><th>Item Category</th><th>Organisation</th><th>Department</th></tr>
  <tr>
    <td>1</td>
    <td>22-Oct-2026 11:30 AM</td>
    <td>12-Nov-2026 03:00 PM</td>
    <td>GEM/2026/B/9876543</td>
    <td>Atomic Layer Deposition System</td>
    <td>Indian Institute of Technology Madras</td>
    <td>Department of Physics</td>
  </tr>
</table>
</body></html>
"""


def test_cppp_central_row_parsing():
    soup = BeautifulSoup(CPPP_CENTRAL_HTML, "html.parser")
    rows = soup.find("table").find_all("tr")[1:]
    cells = [td.get_text(strip=True) for td in rows[0].find_all("td")]
    tender = cppp.parse_cppp_row(cells, "https://eprocure.gov.in/tender/1001")

    assert tender["title"] == "Supply of High Vacuum Turbo Molecular Pump System"
    assert tender["tender_id"] == "CPPP/2026_1001_1"
    assert "Indian Institute of Science" in tender["organization"]
    assert tender["published_date"] == "22-Oct-2026 09:00 AM"
    assert tender["closing_date"] == "15-Nov-2026 05:00 PM"
    assert tender["source_type"] == "cppp"


def test_cppp_gem_row_parsing():
    soup = BeautifulSoup(CPPP_GEM_HTML, "html.parser")
    rows = soup.find("table").find_all("tr")[1:]
    cells = [td.get_text(strip=True) for td in rows[0].find_all("td")]
    tender = cppp.parse_gem_row(cells, "https://eprocure.gov.in/gem/9876543")

    assert tender["tender_id"] == "GEM/2026/B/9876543"
    assert tender["title"] == "Atomic Layer Deposition System"
    assert tender["product_category"] == "Atomic Layer Deposition System"
    assert tender["organization"] == "Indian Institute of Technology Madras"
    assert tender["source_type"] == "gem"


def test_cppp_malformed_rows_fail_safely():
    # Empty table
    soup_empty = BeautifulSoup("<html><body><table><tr><th>Header</th></tr></table></body></html>", "html.parser")
    tenders = cppp.parse_tenders(soup_empty, "central")
    assert tenders == []

    # Row with truncated cells does not raise IndexError
    short_cells = ["1", "22-Oct-2026 09:00 AM"]
    tender = cppp.parse_cppp_row(short_cells, "https://eprocure.gov.in/test")
    assert tender["title"] == ""
    assert tender["tender_id"] is None


# ==============================================================================
# 2. IISc Bangalore Scraper Tests
# ==============================================================================

IISC_HTML = """
<html><body>
<div class="tender-content">
  <ul>
    <li>
      <a href="/tenders/2026/iisc-cryo-pump.pdf">Tender for Procurement of Cryopump (22/10/2026)</a>
    </li>
    <li>
      <a href="/tenders/2026/spectrometer-amendment.pdf">RFQ for FTIR Spectrometer published (20/10/2026) with corrigendum (22/10/2026)</a>
    </li>
    <li>General campus holiday advisory circular (15/10/2026)</li>
  </ul>
</div>
</body></html>
"""


def test_iisc_scraping_and_corrigendum_detection(monkeypatch):
    monkeypatch.setattr(iisc.requests, "get", lambda *a, **kw: MockResponse(text=IISC_HTML))
    tenders = iisc.scrape_iisc()

    assert len(tenders) == 2, "Non-tender circular should be filtered out"
    cryo = tenders[0]
    assert "Procurement of Cryopump" in cryo["title"]
    assert cryo["source_url"] == "https://iisc.ac.in/tenders/2026/iisc-cryo-pump.pdf"
    assert cryo["published_date"] == "2026-10-21T18:30:00+00:00"

    corrigendum = tenders[1]
    assert "FTIR Spectrometer" in corrigendum["title"]
    assert corrigendum["published_date"] == "2026-10-19T18:30:00+00:00"
    assert corrigendum["corrigendum_date"] == "2026-10-21T18:30:00+00:00"


def test_iisc_empty_or_broken_page_handled_safely(monkeypatch):
    monkeypatch.setattr(iisc.requests, "get", lambda *a, **kw: MockResponse(text="<html><body><p>No tenders currently available</p></body></html>"))
    tenders = iisc.scrape_iisc()
    assert tenders == []


# ==============================================================================
# 3. IIT Madras API Scraper Tests
# ==============================================================================

IITM_API_JSON = [
    {
        "formid": "9021",
        "referencenumber": "IITM/PHY/2026/042",
        "tendertitle": "Supply of Sputter Deposition System with RF Power Supply",
        "tenderdescription": "Ultra-high vacuum magnetron sputtering system for departmental research.",
        "keywords": "PVD, Sputtering, Vacuum",
        "openingdatevalue": "2026-10-22T10:00",
        "closingdatevalue": "2026-11-20T15:00",
    },
    {
        "formid": "9022",
        "referencenumber": "IITM/CIVIL/2026/015",
        "tendertitle": "Campus cafeteria civil maintenance",
        "tenderdescription": "Plumbing and furniture repair work.",
        "keywords": "civil, maintenance",
        "openingdatevalue": "2020-01-01T10:00",
        "closingdatevalue": "2020-01-15T15:00",
    },
]


def test_iitm_api_parsing_and_freshness_filtering(monkeypatch):
    monkeypatch.setattr(iitm.requests, "get", lambda *a, **kw: MockResponse(json_data=IITM_API_JSON))
    tenders = iitm.scrape_iitm(cutoff_hours=48)

    # Tender 1 is currently active/open; Tender 2 closed in 2020
    assert len(tenders) == 1
    t = tenders[0]
    assert t["tender_id"] == "IITM/PHY/2026/042"
    assert "Sputter Deposition System" in t["title"]
    assert t["organization"] == "Indian Institute of Technology Madras"
    assert t["source_url"] == "https://tenders.iitm.ac.in/viewnewtender.html?formid=9021"
    assert "PVD, Sputtering, Vacuum" in t["raw_text"]


# ==============================================================================
# 4. IIT Palakkad Table Scraper Tests
# ==============================================================================

IIT_PALAKKAD_HTML = """
<html><body>
<table>
  <tr><th>Tender No</th><th>Title</th><th>Publish Date</th><th>Close Date</th><th>Documents</th><th>Remarks</th></tr>
  <tr>
    <td>IITPKD/CHM/2026/03</td>
    <td>High Performance Liquid Chromatography (HPLC) System</td>
    <td>21/10/2026</td>
    <td>18/11/2026</td>
    <td>
      <a href="/sites/default/files/tender-doc-1.pdf">Tender Notice</a>
      <a href="/sites/default/files/specs.pdf">Technical Specs</a>
    </td>
    <td>Two bid system</td>
  </tr>
</table>
</body></html>
"""


def test_iit_palakkad_table_and_documents_parsing(monkeypatch):
    monkeypatch.setattr(iit_palakkad.requests, "get", lambda *a, **kw: MockResponse(text=IIT_PALAKKAD_HTML))
    tenders = iit_palakkad.scrape_iit_palakkad()

    assert len(tenders) == 1
    t = tenders[0]
    assert t["tender_id"] == "IITPKD/CHM/2026/03"
    assert "Liquid Chromatography" in t["title"]
    assert t["source_url"] == "https://iitpkd.ac.in/sites/default/files/tender-doc-1.pdf"
    assert len(t["document_links"]) == 2
    assert "https://iitpkd.ac.in/sites/default/files/specs.pdf" in t["document_links"]
    assert "Two bid system" in t["raw_text"]


# ==============================================================================
# 5. IIT Goa Table Scraper Tests
# ==============================================================================

IIT_GOA_HTML = """
<html><body>
<table>
  <tr><th>Date</th><th>Tender Description</th><th>Category</th><th>Due Date</th></tr>
  <tr>
    <td>22/10/2026</td>
    <td><a href="notices/tender_laser.pdf">Supply of Nd:YAG Pulsed Laser System</a></td>
    <td>Research Equipment</td>
    <td>14/11/2026</td>
  </tr>
</table>
</body></html>
"""


def test_iit_goa_table_parsing_and_link_resolution(monkeypatch):
    monkeypatch.setattr(iit_goa.requests, "get", lambda *a, **kw: MockResponse(text=IIT_GOA_HTML))
    tenders = iit_goa.scrape_iit_goa()

    assert len(tenders) == 1
    t = tenders[0]
    assert t["title"] == "Supply of Nd:YAG Pulsed Laser System"
    assert t["source_url"] == "https://iitgoa.ac.in/tenders/notices/tender_laser.pdf"
    assert t["organization"] == "IIT Goa"
    assert t["published_date"] == "22/10/2026"
    assert t["closing_date"] == "14/11/2026"


# ==============================================================================
# 6. Pipeline Source Isolation & Resilience Tests
# ==============================================================================

def test_collect_all_tenders_isolates_individual_scraper_failures(monkeypatch):
    """Verify that if one portal fails (e.g. timeout), other scrapers continue and results record the partial failure."""
    def fake_cppp_timeout():
        raise requests.exceptions.ConnectTimeout("eprocure.gov.in timed out")

    def fake_iitm_success():
        return [{
            "tender_id": "IITM-001",
            "title": "Cryogenic System",
            "organization": "IIT Madras",
            "published_date": "2026-10-22T08:00",
            "closing_date": "2026-11-22T17:00",
            "source_url": "https://tenders.iitm.ac.in/001",
        }]

    def fake_empty():
        return []

    monkeypatch.setattr("pipeline.run.scrape_cppp", fake_cppp_timeout)
    monkeypatch.setattr("pipeline.run.scrape_iitm", fake_iitm_success)
    monkeypatch.setattr("pipeline.run.scrape_iit_palakkad", fake_empty)
    monkeypatch.setattr("pipeline.run.scrape_iit_goa", fake_empty)
    monkeypatch.setattr("pipeline.run.scrape_iisc", fake_empty)

    tenders = collect_all_tenders()

    # The collection should contain the successful tender from IITM
    assert len(tenders) == 1
    assert tenders[0]["tender_id"] == "IITM-001"

    # Per-source outcome tracking
    results = tenders.source_results
    assert results["cppp"]["status"] == "failed"
    assert results["cppp"]["error_type"] == "ConnectTimeout"
    assert results["iitm"]["status"] == "ok"
    assert results["iitm"]["tenders"] == 1
    assert results["iit_goa"]["status"] == "ok"
    assert results["iit_goa"]["tenders"] == 0
