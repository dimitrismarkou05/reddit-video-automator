"""Update detection and parent-story linking algorithm."""

from reddit.linker.core import UpdateLinker
from reddit.linker.models import InlineUpdateSection
from reddit.linker.patterns import UPDATE_KEYWORDS, INLINE_UPDATE_PATTERNS

__all__ = [
    "UpdateLinker",
    "InlineUpdateSection",
    "UPDATE_KEYWORDS",
    "INLINE_UPDATE_PATTERNS",
]
