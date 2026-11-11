# Citation Chaining

A small, **persistent** citation-chaining system for scholarly literature, with an optional Model Context Protocol (MCP) interface. Designed as a usable first version rather than an automatic literature-review writer.

## Features

- Bidirectional snowballing through **OpenAlex**: `referenced_works` and works that `cite` a work.
- Persist literature, citation edges, discovery depth, provenance, and per-direction pagination state in **SQLite**.
- Resume an interrupted run without starting from scratch.
- Retain unmatched OpenAlex references and manually entered footnotes in `unresolved`, particularly important for humanities books, older articles and edited volumes.
- Separate named research collections in one database; no forced topic classification.
- Export works, citation edges, progress, and unmatched references as separate UTF-8 CSV files.
- Optional MCP tools for connecting the same database to an AI client.

## First five minutes

Requires Python 3.11 or later. From the project directory:

```bash
python -m pip install -e .

# Start with a paper that has a DOI or known OpenAlex ID.
# For example: John H. Arnold, "Talking with Ghosts" (2022):
citation-chain --db ./literature.sqlite3 add 10.1080/03044181.2022.2060483 --collection medieval-epistemology

# Alternatively search by title and select the correct W-ID:
citation-chain --db ./literature.sqlite3 lookup "Talking with Ghosts Rancière Derrida archive"

# First round only expands the seeds, in both directions:
citation-chain --db ./literature.sqlite3 expand --collection medieval-epistemology \
  --rounds 1 --max-works 10 --per-work 50 --max-new 300

# Two rounds also expand literature discovered at depth 1:
citation-chain --db ./literature.sqlite3 expand --collection medieval-epistemology \
  --rounds 2 --max-works 20 --per-work 50 --max-new 300

citation-chain --db ./literature.sqlite3 stats --collection medieval-epistemology
citation-chain --db ./literature.sqlite3 search "inquisition" --collection medieval-epistemology
citation-chain --db ./literature.sqlite3 export ./exports --collection medieval-epistemology
```

The DOI above belongs to the actual 2022 Arnold article. Title lookup never silently selects a fuzzy match; inspect candidate results and then add the confirmed W-ID.

## OpenAlex access

The API permits some anonymous queries, but for real chaining register for a **free OpenAlex API key** at https://openalex.org and set it in your shell:

```bash
export OPENALEX_API_KEY='YOUR_KEY_HERE'
```

The OpenAlex API permits free keyed access within a daily budget; large citation chains can exhaust that budget. This code uses small default limits and does **not** automatically purchase additional quota. It backs off on 429 responses and preserves progress. See https://help.openalex.org/api/authentication/.

Note: OpenAlex references represent *matched* items, not necessarily the complete bibliography of a book or paper. A lack of references does **not** demonstrate that a work cited nothing.

## Adding unmatched footnotes

```bash
citation-chain unresolved "Example: Author, Title (Paris, 1880), pp. 1–5" \
  --collection medieval-epistemology
```

The `--citing-id` can be omitted for an unidentified citing source. The unmatched item stays in the CSV export and is never invented as a confirmed OpenAlex work/citation edge.

## MCP server (optional)

Install:

```bash
python -m pip install -e '.[mcp]'
```

Launch a local stdio MCP server:

```bash
export CITATION_CHAIN_DB="$PWD/literature.sqlite3"
python -m citation_chain.mcp_server
```

Available MCP tools: `lookup_paper`, `add_seed`, `expand_citation_chain`, `library_stats`, `search_library`, `record_unmatched_reference`, and `export_citation_library`.

To deploy as a remote MCP server, set `MCP_TRANSPORT=streamable-http`. **Do not expose an unauthenticated write-capable service on the public Internet.** Use an authenticated HTTPS proxy, a private network or equivalent access control before connecting it to a remote AI client. This project contains no built-in OAuth, user management or remote database hosting. An actual ChatGPT plugin connection may require a publicly reachable, secured server and suitable account/workspace permissions. See https://py.sdk.modelcontextprotocol.io/ for the Python MCP SDK v2.

## Reliability, scope, and limitations

- A citation edge **A → B** means A cites B, not that A agrees with B.
- Discovery `depth` counts expansion rounds from a seed; it is not scholarly importance.
- The collection grows without deduplicating distinct editions that OpenAlex identifies separately; matching quality depends on OpenAlex.
- Work and edge records carry a provenance field and timestamp; outgoing references are matched OpenAlex IDs. `unresolved.csv` tracks unresolvable references without pretending to know their metadata.
- A `rounds=2` invocation may not finish all depth-1 nodes if `--max-works` or `--max-new` is low. Re-run until the frontier is empty for the desired round count.
- The `pending_works` total in `stats` includes unexpanded *future* depths, and does not mean all those works are pending within your currently selected round limit.
- OpenAlex pagination past the first cursor page requires a free key. API errors are reported per source and preserve already-saved results.
- This MVP does not parse raw PDF footnotes, download PDFs, judge a paper's scholarly significance, or deploy the remote server for you.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use an in-memory fake OpenAlex service; live API usage has **not** been end-to-end tested in this environment.

## Database tables

- `works`: canonical OpenAlex record and metadata.
- `membership`: collection membership, shortest discovery depth, discovering work.
- `citations`: directed edges (citing, cited), evidence source.
- `progress`: cursors and offsets for resumable expansion by paper and direction.
- `unresolved`: manually captured bibliography entries or unavailable records.

License: MIT (see LICENSE).
