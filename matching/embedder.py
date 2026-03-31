"""
20 manufacturers → 20 vectors
1 tender → 1 vector
compare → rank
"""

from sentence_transformers import SentenceTransformer

class ManufacturerEmbedder:
    def __init__(self, model_name="BAAI/bge-small-en-v1.5"):
        self.model = SentenceTransformer(model_name)
        self.manufacturers = []
        self.embeddings = None

    def load_manufacturers(self, manufacturers_list):
        """
        manufacturers_list = list of dicts from manufacturers.json
        """
        self.manufacturers = manufacturers_list

    def build_embeddings(self):
        """
        Converts embedding_text → vector embeddings
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
        Used later for embedding tender text
        """
        return self.model.encode(text, normalize_embeddings=True)