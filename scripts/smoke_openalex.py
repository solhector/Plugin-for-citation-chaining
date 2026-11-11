"""Bounded, live OpenAlex smoke test. Does not require a paid plan.

Run from repository root:
    python scripts/smoke_openalex.py

When complete, inspect smoke-output/report.json and CSV files.
This test is *not* a substitute for broader citation coverage checks.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from citation_chain.engine import Engine
from citation_chain.openalex import OpenAlex
from citation_chain.store import Store

DOI = "10.1080/03044181.2022.2060483"  # John H. Arnold (2022)
COLLECTION = "openalex-smoke-arnold-2022"


def main() -> None:
    output = Path(os.environ.get("SMOKE_OUTPUT", "smoke-output"))
    output.mkdir(parents=True, exist_ok=True)
    database = output / "literature.sqlite3"
    if database.exists():
        database.unlink()  # Test data only; never overwrite a research library!

    client = OpenAlex(timeout=20)
    store = Store(str(database))
    try:
        engine = Engine(store, client)
        seed = engine.add(DOI, COLLECTION)
        assert "ghost" in (seed.get("title") or "").lower(), seed
        raw = store.raw(seed["id"])
        assert raw is not None, "Seed missing from SQLite"
        assert raw.get("referenced_works") is not None, "No referenced_works field"

        # Expand only the seed, one modest page in each direction.
        result = engine.expand(COLLECTION, rounds=1, max_works=1,
                               per_work=8, max_new=16)
        details = result["details"]
        assert len(details) == 1, "Seed was not attempted"
        failures = {k: v["error"] for k, v in details[0].items()
                    if isinstance(v, dict) and "error" in v}
        if failures:
            raise RuntimeError(f"Live expansion failed: {failures}")
        stats = result["stats"]
        assert stats["works"] > 1, "No references or citing works were saved"
        assert stats["citation_edges"] > 0, "No citation relationships saved"
        csv_paths = store.export(COLLECTION, str(output))
        report = {
            "doi": DOI,
            "seed_id": seed["id"],
            "seed_title": seed["title"],
            "references_listed_by_openalex": len(raw.get("referenced_works") or []),
            "first_page_expansion": result,
            "csv_files": [Path(p).name for p in csv_paths],
            "note": "Only one capped page per direction was checked. This is not exhaustive.",
        }
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
