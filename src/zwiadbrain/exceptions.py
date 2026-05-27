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


class RateLimitError(SourceError):
    """A source rejected a request for exceeding its rate limit."""


class ClassificationError(AppError):
    """The relevance classifier produced an unusable result."""


class RenderError(AppError):
    """A wiki page could not be rendered."""


class WikiSchemaError(AppError):
    """Page frontmatter failed schema validation."""


class LawBrainError(AppError):
    """Base for law-brain integration errors."""


class MatchError(LawBrainError):
    """A law-brain page could not be matched, or its grounding check failed."""


class ItemNotFoundError(AppError):
    """A requested tracked item does not exist."""
