"""Split converted documents into retrieval-sized chunks.

``HybridChunker`` splits on the document's own heading structure and keeps
table rows attached to their headers, so a chunk stays meaningful on its own
once it is embedded.
"""

from docling.chunking import HybridChunker
from docling_core.types.doc.document import DoclingDocument

from app.models.schemas import Chunk


class DocumentChunker:
    def __init__(self, chunker: HybridChunker | None = None) -> None:
        self._chunker = chunker or HybridChunker()

    def chunk(self, document: DoclingDocument) -> list[Chunk]:
        """Split one converted document into chunks.

        The text is contextualized, meaning the surrounding headings are
        prefixed onto the chunk body. That way an embedded chunk still carries
        the section it came from instead of being a bare paragraph.
        """
        return [
            Chunk(
                text=self._chunker.contextualize(chunk),
                headings=list(getattr(chunk.meta, "headings", None) or []),
            )
            for chunk in self._chunker.chunk(document)
        ]
