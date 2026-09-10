"""Ingestion: Source in, stored Chunks out.

``Ingestor`` is the one public way in. Conversion and chunking are internal to
it -- exporting them here is what let /api/ingest call the wrong one.
"""

from app.ingestion.ingestor import Ingestor

__all__ = ["Ingestor"]
