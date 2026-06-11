"""ZwiadBrain exception hierarchy.

Every error raised inside the project inherits from :class:`AppError`, so a
single boundary handler (the CLI entry point) can catch everything ZwiadBrain
raises with one ``except AppError``.
"""


class AppError(Exception):
    """Base exception for ZwiadBrain."""


class ConfigError(AppError):
    """Invalid or missing configuration."""


class SourceError(AppError):
    """Base for data-source errors (Congress, GovInfo, LegiScan, enforcement)."""


class SourceFetchError(SourceError):
    """A source request failed or returned an unusable response."""


class SourceNotFoundError(SourceFetchError):
    """A source returned 404 for a specific resource (often a benign 'no records')."""


class RateLimitError(SourceError):
    """A source rejected a request for exceeding its rate limit."""


class ClassificationError(AppError):
    """The relevance classifier produced an unusable result."""


class RenderError(AppError):
    """A wiki page could not be rendered."""


class ExtractionError(AppError):
    """Document text extraction failed (e.g. Docling is not installed)."""


class WikiSchemaError(AppError):
    """Page frontmatter failed schema validation."""


class StoreError(AppError):
    """A SQLite-boundary operation failed (corrupt index, write error)."""


class LawBrainError(AppError):
    """Base for law-brain integration errors."""


class MatchError(LawBrainError):
    """A law-brain page could not be matched, or its grounding check failed."""


class ItemNotFoundError(AppError):
    """A requested tracked item does not exist."""
