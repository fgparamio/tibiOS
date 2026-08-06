"""Union assembly of every capability group's reference data into the
package's single default catalog (design decision MC14 — assembled last
so slices 3-7 touched no shared file; a slice-8 data bug can no longer
break an earlier slice's own test via `ImportError`).

`ALL_ENTRIES` is the union of every group's `*_ENTRIES` tuple
(`CHAT_ENTRIES`, `EMBEDDING_ENTRIES`, `RERANK_ENTRIES`, `VISION_ENTRIES`,
`SPEECH_ENTRIES`, `OCR_ENTRIES`). Because `entries/vision.py` deliberately
does not restate `gemma` — its entries already live in `entries/chat.py`
(MC8/MC12) — unioning every group here produces exactly one `gemma`
entry set, not a duplicate; `tests/unit/catalog/test_catalog_consistency.py`'s
`TestAllEntriesAssembly` verifies this directly rather than assuming it
from the individual groups' isolation.

`DEFAULT_CATALOG` is the package's single `ModelCatalog` instance built
from `ALL_ENTRIES`. Its construction re-validates all three
`ModelCatalog` invariants (no duplicate name, `family_of` match, no
ambiguous footprint — `catalog/catalog.py`) across the full, assembled
dataset at import time — the strongest form of "this data is internally
consistent" the package can assert without a live suite.
"""

from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.entries.chat import CHAT_ENTRIES
from tibios_ray.catalog.entries.embedding import EMBEDDING_ENTRIES
from tibios_ray.catalog.entries.ocr import OCR_ENTRIES
from tibios_ray.catalog.entries.rerank import RERANK_ENTRIES
from tibios_ray.catalog.entries.speech import SPEECH_ENTRIES
from tibios_ray.catalog.entries.vision import VISION_ENTRIES
from tibios_ray.catalog.model import ModelDescriptor

ALL_ENTRIES: tuple[ModelDescriptor, ...] = (
    CHAT_ENTRIES
    + EMBEDDING_ENTRIES
    + RERANK_ENTRIES
    + VISION_ENTRIES
    + SPEECH_ENTRIES
    + OCR_ENTRIES
)

DEFAULT_CATALOG: ModelCatalog = ModelCatalog(ALL_ENTRIES)

__all__ = [
    "ALL_ENTRIES",
    "DEFAULT_CATALOG",
]
