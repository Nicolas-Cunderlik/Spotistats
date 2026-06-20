"""Similarity service wrapper around the offline-trained song-similarity model.

The model is loaded once, lazily, on first use. If artifacts are missing
(train.py hasn't been run) or loading fails for any reason, lookups just
return an empty list instead of raising.
"""
import logging

logger = logging.getLogger(__name__)

class SimilarityService:
    def __init__(self):
        self._model = None
        self._load_failed = False

    def _ensure_model(self):
        if self._model is None and not self._load_failed:
            try:
                from ..ml.similarity_model import SimilarityModel
                self._model = SimilarityModel()
            except Exception:
                logger.exception("Failed to load similarity model")
                self._load_failed = True
        return self._model

    def find_similar(self, track_id, k=3):
        model = self._ensure_model()
        if model is None:
            return []
        try:
            return model.find_similar(track_id, k=k)
        except Exception:
            logger.exception("Similarity lookup failed for %s", track_id)
            return []
