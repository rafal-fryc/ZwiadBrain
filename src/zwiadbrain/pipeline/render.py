"""Render models to committed wiki pages, route them to disk, write idempotently."""

import re
from pathlib import Path

import frontmatter

from zwiadbrain.exceptions import WikiSchemaError
from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.wiki.schema import to_frontmatter
from zwiadbrain.wiki.templates import (
    preserve_extracted_text_region,
    preserve_lawbrain_region,
    render_bill_body,
    render_enforcement_body,
    render_extracted_text_region,
    render_lawbrain_region,
    splice_extracted_text_region,
    splice_lawbrain_region,
)


def render_body(item: Bill | EnforcementAction) -> str:
    """Render the Markdown body (no frontmatter) for a page."""
    if isinstance(item, Bill):
        return render_bill_body(item)
    return render_enforcement_body(item)


def render_page(item: Bill | EnforcementAction) -> str:
    """Render a full committed page: frontmatter block + Markdown body."""
    post = frontmatter.Post(render_body(item))
    post.metadata = to_frontmatter(item)
    text: str = frontmatter.dumps(post)
    return text if text.endswith("\n") else text + "\n"


def _jurisdiction_parts(jurisdiction: str) -> tuple[str, ...]:
    if jurisdiction in ("US", "US-Federal"):
        return ("federal",)
    if jurisdiction.startswith("US-") and len(jurisdiction) == 5:
        return ("states", jurisdiction[3:].lower())
    raise WikiSchemaError(f"unsupported jurisdiction for a tracked page: {jurisdiction!r}")


def page_path(item: Bill | EnforcementAction, wiki_root: Path) -> Path:
    """Compute the committed-page path for an item under ``wiki_root``."""
    kind = "bills" if isinstance(item, Bill) else "enforcement"
    return wiki_root.joinpath(*_jurisdiction_parts(item.jurisdiction), kind, f"{item.id}.md")


def sidecar_path(item: Bill | EnforcementAction, wiki_root: Path) -> Path:
    """The ``<id>.text.md`` sibling that holds an item's extracted document text."""
    page = page_path(item, wiki_root)
    return page.with_name(f"{page.stem}.text.md")


def write_page(item: Bill | EnforcementAction, wiki_root: Path) -> bool:
    """Write the rendered page, skipping the write when content is unchanged.

    Returns True if the file was created or changed, False if already up to date,
    so an unchanged scan leaves a clean ``git status``.

    Central D63 preservation: when the page already exists, a committed
    ``lawbrain:region`` is spliced forward onto the freshly rendered body unless
    the item supplies its own region (i.e. carries commentary bodies). Every
    render path therefore keeps committed commentary/Further Reading intact;
    only ``/zwiad-sync-lawbrain`` creates, updates, or removes the region.
    """
    path = page_path(item, wiki_root)
    content = render_page(item)
    if path.exists():
        prev_text = path.read_text(encoding="utf-8")
        content = preserve_lawbrain_region(prev_text, content)
        content = preserve_extracted_text_region(prev_text, content)
        if prev_text == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def committed_summary(page_text: str) -> str | None:
    """The text under a committed page's ``## Summary`` heading, or ``None`` (D123).

    The plain-language summary is body-only (D20) — frontmatter cannot rebuild it — so
    a re-render from freshly fetched data must carry it over from the committed page.
    """
    body: str = frontmatter.loads(page_text).content
    match = re.search(r"(?:^|\n)## Summary\n\n(.*?)(?:\n\n## |\Z)", body, re.S)
    if match is None:
        return None
    summary = match.group(1).strip()
    return summary or None


def write_lawbrain_region(item: Bill | EnforcementAction, wiki_root: Path) -> bool:
    """Attach/update a page's ``lawbrain:region`` without rebuilding its body.

    The sync path (``/zwiad-sync-lawbrain``) owns create/update/remove of the region
    (D63) but must NOT re-render the body: a Bill's ``summary`` / ``actions`` /
    ``text_versions`` are body-only (``schema._BODY_ONLY_FIELDS``) and cannot be
    reconstructed from frontmatter, so :func:`write_page`'s full re-render drops
    ``## Summary`` / ``## Status & Timeline`` / ``## Full Text``. This reads the
    committed page, keeps its body verbatim, splices the freshly-built region in, and
    rewrites only the frontmatter bookkeeping (``commentary_sources``). The page must
    already exist (sync only attaches to tracked targets). Idempotent: returns ``True``
    only when the bytes change.

    Output is byte-identical to a :func:`write_page` render of the same fully-populated
    item, since the preserved body equals what :func:`render_body` would emit and the
    frontmatter is serialized via the same :func:`to_frontmatter` path.
    """
    path = page_path(item, wiki_root)
    prev_text = path.read_text(encoding="utf-8")
    prev_body: str = frontmatter.loads(prev_text).content
    fresh_region = render_lawbrain_region(item)
    # A fresh region is authoritative — splice it in (replacing any existing one).
    # When it is None (e.g. an idempotent re-run where merge_commentary no-op'd the
    # bodies to None, or refresh-only bookkeeping), keep the committed region
    # verbatim rather than deleting it — same contract as preserve_lawbrain_region,
    # so re-runs are byte-identical and analysis is never silently dropped (D63).
    new_body = (
        prev_body
        if fresh_region is None
        else splice_lawbrain_region(prev_body, fresh_region)
    )
    post = frontmatter.Post(new_body)
    post.metadata = to_frontmatter(item)
    content: str = frontmatter.dumps(post)
    if not content.endswith("\n"):
        content += "\n"
    if content == prev_text:
        return False
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def write_extracted_text_region(item: Bill | EnforcementAction, wiki_root: Path) -> bool:
    """Add/refresh a page's extracted-text link region pointing at its sidecar file.

    Splices the region onto the raw committed page text (no body/frontmatter
    re-render), so it is byte-stable, sits strictly last, and leaves any committed
    law-brain region intact. The page must already exist. Idempotent: returns
    ``True`` only when the bytes change.
    """
    path = page_path(item, wiki_root)
    prev_text = path.read_text(encoding="utf-8")
    region = render_extracted_text_region(sidecar_path(item, wiki_root).name)
    content = splice_extracted_text_region(prev_text, region)
    if content == prev_text:
        return False
    path.write_text(content, encoding="utf-8", newline="\n")
    return True
