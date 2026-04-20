"""
Debug script for the manufacturer embedding space.

Purpose:
Verifies that the ManufacturerEmbedder correctly loads and vectorizes manufacturer 
profiles. Inspects the dimensions and content of generated embeddings.
"""
import sys
import os
import json

# Add the parent directory to the path so we can import matching
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matching.embedder import ManufacturerEmbedder

# Load manufacturers data
try:
    with open("data/manufacters.json") as f:
        manufacturers = json.load(f)
except FileNotFoundError:
    with open("data/manufacturers.json") as f:
        manufacturers = json.load(f)

embedder = ManufacturerEmbedder()
embedder.load_manufacturers(manufacturers)
embedder.build_embeddings()

embeddings = embedder.get_embeddings()

print("Total manufacturers:", len(embeddings))
print("Embedding shape:", embeddings[0].shape if embeddings is not None and len(embeddings) > 0 else "No embeddings")

print(manufacturers[0]["embedding_text"])