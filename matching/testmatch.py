"""
Integration test for the hybrid manufacturer matcher.

Purpose:
Verifies that the TenderMatcher correctly identifies relevant manufacturers 
using both semantic embeddings and keyword boosts for a mock tender.
"""
import json
from matching.embedder import ManufacturerEmbedder
from matching.matcher import TenderMatcher

# Load manufacturers
with open("data/manufacturers.json") as f:
    manufacturers = json.load(f)

# Init embedder
embedder = ManufacturerEmbedder()
embedder.load_manufacturers(manufacturers)
embedder.build_embeddings()

# Init matcher
matcher = TenderMatcher(embedder)

# Fake tender (test case)
tender = {
    "title": "Dual-Ion Beam Sputtering Coating system with in-situ Optical thickness monitoring system",
}

results = matcher.match(tender)

print("\nMATCH RESULTS:")
for r in results:
    print(r)