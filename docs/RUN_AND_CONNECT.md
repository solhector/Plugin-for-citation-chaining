# Run, test, and connect Citation Chaining

This guide separates **a live bibliographic test**, **local/remote MCP serving**, and **connecting from ChatGPT**. They are three different milestones.

## A. First real OpenAlex test: GitHub Actions (no server rental)

1. Open this repository's **Actions** tab.
2. Select **Live OpenAlex smoke test** in the workflows list.
3. Click **Run workflow**, choose `main`, and run it.
4. Read the job log. A successful run must show Arnold's 2022 paper, a DOI match, and at least one citation relation saved in SQLite.
5. Download the `openalex-smoke-results` artifact for `report.json`, `works.csv`, `citations.csv`, `progress.csv` and `unresolved.csv`.

The workflow also runs automatically on a push touching its test script, the workflow, or the citation-chain Python source.

The smoke test limits its expansion to **eight items per direction**. It does not establish completeness of a humanities bibliography, nor run a full two-round chain.

You can run a small first-page smoke test without a key, subject to OpenAlex's current free API access policy. If the service returns 401/429 or reports that cursor paging needs authentication, create a free key at https://openalex.org, then in the GitHub repository navigate to **Settings → Secrets and variables → Actions → New repository secret**, set the name to `OPENALEX_API_KEY`, and rerun. Never commit API keys.

## B. Use a persistent research database in GitHub Codespaces

1. From the repository, click **Code → Codespaces → Create codespace on main**.
2. Run these commands in the Codespaces terminal:

```bash
python -m pip install -e .
citation-chain lookup "Talking with ghosts Rancière Derrida archive"
citation-chain add 10.1080/03044181.2022.2060483
citation-chain expand --rounds 1 --max-works 1 --per-work 20 --max-new 40
citation-chain stats
citation-chain export ./exports
```

For longer, repeated searches, add `OPENALEX_API_KEY` to your **Codespaces secrets** (not the same as an Actions secret). The CLI reads the key automatically.

The database defaults to `./literature.sqlite3`, which is excluded from Git by `.gitignore`. It is durable while the Codespace exists, but **not a long-term backup**: export your CSVs and back up the SQLite database before deleting a Codespace. Do not put a private research database or API secrets in a public Git repository.

## C. Check the MCP server locally

With Python 3.11+:

```bash
python -m pip install -e '.[mcp]'
export CITATION_CHAIN_DB="$PWD/literature.sqlite3"
python -m citation_chain.mcp_server
```

That launches the default **stdio** transport for a compatible local MCP client. This does not publish an internet address and does not make the service accessible in ChatGPT.

For an **HTTP smoke check on a trusted development machine**, set:

```bash
export MCP_TRANSPORT=streamable-http
export MCP_HOST=127.0.0.1
export PORT=8000
python -m citation_chain.mcp_server
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. To test tools locally, use the official MCP Inspector or an MCP Python client. Do not expose that endpoint publicly while unauthenticated.

## D. Deploy a remote MCP server

A production setup additionally requires:

- Hosting with a stable **HTTPS** address, such as `https://your-domain.example/mcp`.
- A persistent writable volume and `CITATION_CHAIN_DB=/data/literature.sqlite3`. A disposable container filesystem can lose the database on restart.
- A server-side `OPENALEX_API_KEY` secret, never stored in GitHub source.
- An **authentication and authorization layer** in front of MCP, preferably using the authentication model supported by your selected MCP client. This repository does **not** yet implement OAuth, accounts, or user separation. Do not publicly deploy its current write-capable tools without an access-control solution.
- A secure reverse proxy and HTTP service configuration, e.g. `MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 PORT=8000` behind authenticated HTTPS ingress.

The GitHub repository **does not itself host an MCP service**. A GitHub Actions smoke test is not a persistent server, and a stopped Codespace does not serve requests.

## E. Connect from ChatGPT, if your account/workspace permits it

As of November 2026, OpenAI's documentation describes custom MCP server connections and full read/write MCP support for ChatGPT Business and Enterprise/Edu workspaces, primarily on **ChatGPT web**. Availability and authorization vary by account/workspace; do not assume a personal Plus plan supports adding this write-capable server.

On an eligible account, go to **Plugins**, use **Add custom MCP server**, enter your HTTPS `/mcp` URL and authentication, review the exposed tools, and test in a chat. The interface may show Apps instead of Plugins depending on the current rollout.

Official documentation:
- https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt
- https://py.sdk.modelcontextprotocol.io/v2/
- https://help.openalex.org/api/authentication/

**Status at commit time:** Unit tests passed locally. The real HTTP test was not runnable in this assistant's sandbox (external DNS unavailable); verify the GitHub Actions job status before claiming live success. Remote production deployment and ChatGPT connection are not complete.
