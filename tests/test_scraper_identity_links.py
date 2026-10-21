from data.db import generate_hash
from scrapers import iisc, iit_goa, institutions


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_iisc_scraper_uses_resolved_item_link_for_identity(monkeypatch):
    class Item:
        def get_text(self, *args, **kwargs):
            return "Tender for laboratory equipment"

        def find(self, name, href=None):
            return {"href": "/notices/tender-1.pdf"} if name == "a" else None

    class Soup:
        def find_all(self, name):
            return [Item()] if name == "li" else []

    monkeypatch.setattr(iisc.requests, "get", lambda *args, **kwargs: FakeResponse("fixture"))
    monkeypatch.setattr(iisc, "BeautifulSoup", lambda *args, **kwargs: Soup())

    tender = iisc.scrape_iisc()[0]

    assert tender["source_url"] == "https://iisc.ac.in/notices/tender-1.pdf"
    assert tender["tender_id"].startswith("iisc_")
    assert generate_hash(tender) == generate_hash({**tender, "title": "Revised tender title"})


def test_iit_goa_scraper_resolves_relative_notice_links(monkeypatch):
    class Cell:
        def __init__(self, value, link=None):
            self.value = value
            self.link = link

        def get_text(self, *args, **kwargs):
            return self.value

        def find(self, name, href=None):
            return {"href": self.link} if name == "a" and self.link else None

    class Row:
        def find_all(self, name):
            return [
                Cell("21/10/2026"), Cell("Tender for pump", "files/tender-2.pdf"),
                Cell("Equipment"), Cell("30/10/2026"),
            ] if name == "td" else []

    class Table:
        def find_all(self, name):
            return [object(), Row()] if name == "tr" else []

    class Soup:
        def find(self, name):
            return Table() if name == "table" else None

    monkeypatch.setattr(iit_goa.requests, "get", lambda *args, **kwargs: FakeResponse("fixture"))
    monkeypatch.setattr(iit_goa, "BeautifulSoup", lambda *args, **kwargs: Soup())

    tender = iit_goa.scrape_iit_goa()[0]

    assert tender["source_url"] == "https://iitgoa.ac.in/tenders/files/tender-2.pdf"
    assert tender["tender_id"] == tender["source_url"]


def test_generic_institution_scraper_uses_detail_url_not_process_random_hash():
    class Link:
        def __init__(self, text, href):
            self.text = text
            self.href = href

        def get_text(self, strip=False):
            return self.text.strip() if strip else self.text

        def __getitem__(self, key):
            assert key == "href"
            return self.href

    class Soup:
        def __init__(self, link):
            self.link = link

        def find_all(self, name, href=False):
            return [self.link] if name == "a" else []

    first = institutions.parse_generic_links(
        Soup(Link("Tender for laboratory equipment", "/files/tender.pdf")),
        "research_unit",
        "https://example.edu/tenders",
    )[0]
    refreshed = institutions.parse_generic_links(
        Soup(Link("Revised tender for laboratory equipment", "/files/tender.pdf")),
        "research_unit",
        "https://example.edu/tenders",
    )[0]

    assert first["tender_id"] is None
    assert refreshed["tender_id"] is None
    assert generate_hash(first) == generate_hash(refreshed)
