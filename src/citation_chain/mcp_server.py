"""Optional MCP 2.x bridge. Install `pip install -e '.[mcp]'` to enable."""
import os
from .store import Store
from .engine import Engine
try:
    from mcp.server.mcpserver import MCPServer
except ImportError as exc:
    raise SystemExit("Install the MCP extra: pip install -e '.[mcp]'") from exc

mcp = MCPServer("Citation Chaining")


def db() -> Store:
    return Store(os.environ.get("CITATION_CHAIN_DB", "./literature.sqlite3"))


@mcp.tool()
def lookup_paper(title: str) -> list[dict]:
    """Find candidate OpenAlex work IDs by title. Do not guess which result is correct."""
    store = db()
    try:
        return Engine(store).find(title)
    finally:
        store.close()


@mcp.tool()
def add_seed(identifier: str, collection: str = "medieval-epistemology") -> dict:
    """Add a confirmed OpenAlex W-ID or DOI as a depth-zero seed to a persistent collection."""
    store = db()
    try:
        return Engine(store).add(identifier, collection)
    finally:
        store.close()


@mcp.tool()
def expand_citation_chain(collection: str = "medieval-epistemology", rounds: int = 1,
                          max_works: int = 10, per_work: int = 50, max_new: int = 300) -> dict:
    """Expand references and citing papers, persist edges and progress; default limits keep costs bounded."""
    store = db()
    try:
        return Engine(store).expand(collection,rounds,max_works,per_work,max_new)
    finally:
        store.close()


@mcp.tool()
def library_stats(collection: str = "medieval-epistemology") -> dict:
    """Count works, citations, unresolved references and pending expansions."""
    store = db()
    try:
        return store.stats(collection)
    finally:
        store.close()


@mcp.tool()
def search_library(term: str, collection: str = "medieval-epistemology") -> list[dict]:
    """Search saved titles or author names, not the internet."""
    store = db()
    try:
        return store.search(collection,term)
    finally:
        store.close()


@mcp.tool()
def record_unmatched_reference(raw_reference: str, collection: str = "medieval-epistemology",
                               citing_id: str = "") -> dict:
    """Preserve a PDF-footnote reference not resolved by OpenAlex; never silently discard it."""
    store = db()
    try:
        return {"record_id":store.add_unresolved(collection,raw_reference,citing_id or None)}
    finally:
        store.close()


@mcp.tool()
def export_citation_library(directory: str, collection: str = "medieval-epistemology") -> dict:
    """Write CSV files for works, citation edges, progress and unmatched references."""
    store = db()
    try:
        return {"files":store.export(collection,directory)}
    finally:
        store.close()


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
