"""
Vector embedding management for semantic comparisons.

Pipeline role:
Provides the mathematical representation of manufacturers and tenders. 
Encapsulates the SentenceTransformers model and manages the transformation 
of raw descriptions into a normalized vector space.

Key responsibilities:
- Initializing the local Transformer model.
- Converting manufacturer metadata into stored embeddings (for reuse).
- On-the-fly embedding of incoming tender text.
- Fabricating the ready-to-use TenderMatcher instance.

Inputs:
- 'embedding_text' strings from manufacturer profiles.
- Raw tender descriptions.

Outputs:
- Unit-normalized NumPy arrays (vectors).

Notes:
- Uses the 'bge-small-en-v1.5' model for a balance of speed and precision.
- Normalization is enabled by default to support dot-product based cosine similarity.
"""

import json
from sentence_transformers import SentenceTransformer
from matching.matcher import TenderMatcher


class ManufacturerEmbedder:
    """
    Wrapper for SentenceTransformers to handle manufacturer and tender vectorization.

    Attributes:
        model (SentenceTransformer): The underlying neural network model.
        manufacturers (list): Metadata for manufacturers being processed.
        embeddings (ndarray): Computed and cached vectors for manufacturers.
    """
    def __init__(self, model_name="BAAI/bge-small-en-v1.5"):
        self.model = SentenceTransformer(model_name)
        self.manufacturers = []
        self.embeddings = None

    def load_manufacturers(self, manufacturers_list):
        """
        Populates the internal manufacturer list.

        Args:
            manufacturers_list (list): List of dictionaries from manufacturers.json.
        """
        self.manufacturers = manufacturers_list

    def build_embeddings(self):
        """
        Generates unit-normalized vectors for all loaded manufacturers.

        Notes:
            - Operates on the 'embedding_text' field of each manufacturer.
            - Normalization ensures dot-product equals cosine similarity.
        """
        texts = [m["embedding_text"] for m in self.manufacturers]

        self.embeddings = self.model.encode(
            texts,
            normalize_embeddings=True  # IMPORTANT for cosine similarity
        )

    def get_embeddings(self):
        return self.embeddings

    def get_manufacturers(self):
        return self.manufacturers

    def embed_text(self, text):
        """
        Generates a vector representation for an arbitrary string.

        Args:
            text (str): Input text (typically tender title + description).

        Returns:
            ndarray: Unit-normalized embedding vector.
        """
        return self.model.encode(
            text,
            normalize_embeddings=True
        )


def build_matcher():
    """
    Factory function to initialize the full matching system.

    Returns:
        TenderMatcher: A configured matcher with pre-computed manufacturer embeddings.

    Notes:
        - Bootstraps the system by reading data/manufacturers.json.
    """
    with open("data/manufacturers.json") as f:
        manufacturers = json.load(f)

    embedder = ManufacturerEmbedder()
    embedder.load_manufacturers(manufacturers)
    embedder.build_embeddings()

    return TenderMatcher(embedder)