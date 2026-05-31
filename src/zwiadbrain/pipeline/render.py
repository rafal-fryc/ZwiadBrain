"""Render models to committed wiki pages, route them to disk, write idempotently."""

from pathlib import Path

import frontmatter

from zwiadbrain.exceptions import WikiSchemaError
from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.wiki.schema import to_frontmatter
from zwiadbrain.wiki.templates import (
    preserve_lawbrain_region,
    render_bill_body,
    render_enforcement_body,
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
        if prev_text == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True
