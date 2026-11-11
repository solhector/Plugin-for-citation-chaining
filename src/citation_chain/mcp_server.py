"""MCP bridge. Install with: pip install -e '.[mcp]'

The default transport is local stdio. For remote HTTP set MCP_TRANSPORT=streamable-http.
WARNING: this module does not implement authentication or authorization. Never expose
its write-capable tools on a public, unauthenticated endpoint.
"""
import os

from .store import Store
from .engine import Engine

try:
    from mcp.server import MCPServer
except ImportError as exc:
    raise SystemExit("Install the MCP extra: pip install -e '.[mcp]'") from exc


mcp = MCPServer("Citation Chaining")


def db() -> Store:
    return Store(os.environ.get("CITATION_CHAIN_DB", "./literature.sqlite3"))


@mcp.tool()
def lookup_paper(title: str) -> list[dict]:
    """Find candidate OpenAlex works. Do not automatically choose a fuzzy match."""
    store = db()
    try:
        return Engine(store).find(title)
    finally:
        store.close()


@mcp.tool()
def add_seed(identifier: str, collection: str = "medieval-epistemology") -> dict:
    """Add a confirmed DOI or W-ID to the database as a depth-zero seed."""
    store = db()
    try:
        return Engine(store).add(identifier, collection)
    finally:
        store.close()


@mcp.tool()
def expand_citation_chain(collection: str = "medieval-epistemology", rounds: int = 1,
                          max_works: int = 10, per_work: int = 50, max_new: int = 300) -> dict:
    """Expand both citation directions and store resumable pagination progress."""
    store = db()
    try:
        return Engine(store).expand(collection, rounds, max_works, per_work, max_new)
    finally:
        store.close()


@mcp.tool()
def library_stats(collection: str = "medieval-epistemology") -> dict:
    """Count works, citation edges, unresolved references and pending works."""
    store = db()
    try:
        return store.stats(collection)
    finally:
        store.close()


@mcp.tool()
def search_library(term: str, collection: str = "medieval-epistemology") -> list[dict]:
    """Search saved work titles and author names in one collection."""
    store = db()
    try:
        return store.search(collection, term)
    finally:
        store.close()


@mcp.tool()
def record_unmatched_reference(raw_reference: str, collection: str = "medieval-epistemology",
                               citing_id: str = "") -> dict:
    """Preserve a manually transcribed PDF citation pending resolution."""
    store = db()
    try:
        return {"record_id": store.add_unresolved(collection, raw_reference, citing_id or None)}
    finally:
        store.close()


@mcp.tool()
def export_citation_library(directory: str, collection: str = "medieval-epistemology") -> dict:
    """Write CSV files to a server-side directory. Not a file download operation."""
    store = db()
    try:
        return {"files": store.export(collection, directory)}
    finally:
        store.close()


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "streamable-http":
        # Use only behind an authenticated HTTPS ingress with a persistent DB volume.
        mcp.run(
            transport="streamable-http",
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "8000")),
        )
    else:
        raise ValueError("MCP_TRANSPORT must be 'stdio' or 'streamable-http'")


if __name__ == "__main__":
    main()
