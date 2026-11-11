"""SQLite persistence: preserve provenance, pagination state, and unresolved items."""
import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .openalex import work_id


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, year INTEGER, doi TEXT,
 authors TEXT, venue TEXT, language TEXT, type TEXT, cited_by_count INTEGER,
 raw_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS membership (
 collection TEXT NOT NULL, work_id TEXT NOT NULL REFERENCES works(id),
 depth INTEGER NOT NULL, discovered_by TEXT, added_at TEXT NOT NULL,
 PRIMARY KEY(collection, work_id)
);
CREATE TABLE IF NOT EXISTS citations (
 citing_id TEXT NOT NULL REFERENCES works(id), cited_id TEXT NOT NULL REFERENCES works(id),
 evidence TEXT NOT NULL, discovered_at TEXT NOT NULL,
 PRIMARY KEY(citing_id, cited_id)
);
CREATE TABLE IF NOT EXISTS progress (
 collection TEXT NOT NULL, work_id TEXT NOT NULL,
 direction TEXT NOT NULL CHECK(direction IN ('references','citers')),
 offset INTEGER NOT NULL DEFAULT 0, cursor TEXT NOT NULL DEFAULT '*',
 complete INTEGER NOT NULL DEFAULT 0, note TEXT,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(collection,work_id,direction)
);
CREATE TABLE IF NOT EXISTS unresolved (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 collection TEXT NOT NULL, citing_id TEXT,
 raw_reference TEXT NOT NULL, note TEXT,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_membership_depth ON membership(collection, depth);
CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_id);
"""


class Store:
    def __init__(self, path: str):
        self.path = str(Path(path).expanduser())
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    def put_work(self, raw: dict) -> str:
        identifier = work_id(raw["id"])
        authors = "; ".join(a.get("author", {}).get("display_name", "") for a in raw.get("authorships", []))
        location = raw.get("primary_location") or {}
        venue = (location.get("source") or {}).get("display_name", "")
        params = (identifier, raw.get("title") or raw.get("display_name") or "[Untitled]",
                  raw.get("publication_year"), raw.get("doi"), authors, venue,
                  raw.get("language"), raw.get("type"), raw.get("cited_by_count"),
                  json.dumps(raw, ensure_ascii=False), timestamp())
        self.db.execute("""INSERT INTO works(id,title,year,doi,authors,venue,language,type,cited_by_count,raw_json,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,year=excluded.year,doi=excluded.doi,authors=excluded.authors,
          venue=excluded.venue,language=excluded.language,type=excluded.type,
          cited_by_count=excluded.cited_by_count,raw_json=excluded.raw_json,updated_at=excluded.updated_at""", params)
        self.db.commit()
        return identifier

    def raw(self, identifier: str) -> dict | None:
        row = self.db.execute("SELECT raw_json FROM works WHERE id=?", (work_id(identifier),)).fetchone()
        return json.loads(row[0]) if row else None

    def member(self, collection: str, identifier: str, depth: int, discovered_by: str | None = None) -> bool:
        identifier = work_id(identifier)
        existing = self.db.execute("SELECT depth FROM membership WHERE collection=? AND work_id=?", (collection, identifier)).fetchone()
        self.db.execute("""INSERT INTO membership(collection,work_id,depth,discovered_by,added_at)
          VALUES (?,?,?,?,?) ON CONFLICT(collection,work_id) DO UPDATE SET
          depth=MIN(membership.depth,excluded.depth)""",
          (collection, identifier, depth, discovered_by, timestamp()))
        self.db.commit()
        return existing is None

    def link(self, citing: str, cited: str, evidence: str = "OpenAlex"):
        citing, cited = work_id(citing), work_id(cited)
        if citing == cited:
            return
        self.db.execute("INSERT OR IGNORE INTO citations VALUES(?,?,?,?)", (citing, cited, evidence, timestamp()))
        self.db.commit()

    def state(self, collection: str, identifier: str, direction: str) -> dict:
        row = self.db.execute("SELECT * FROM progress WHERE collection=? AND work_id=? AND direction=?",
                              (collection, work_id(identifier), direction)).fetchone()
        return dict(row) if row else {"offset": 0, "cursor": "*", "complete": 0, "note": None}

    def save_state(self, collection: str, identifier: str, direction: str, *, offset: int,
                   cursor: str = "*", complete: bool = False, note: str | None = None):
        self.db.execute("""INSERT INTO progress VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(collection,work_id,direction) DO UPDATE SET
            offset=excluded.offset,cursor=excluded.cursor,complete=excluded.complete,
            note=excluded.note,updated_at=excluded.updated_at""",
            (collection, work_id(identifier), direction, offset, cursor, int(complete), note, timestamp()))
        self.db.commit()

    def frontier(self, collection: str, rounds: int, max_works: int) -> list[dict]:
        rows = self.db.execute("""SELECT m.work_id,m.depth FROM membership m
            WHERE m.collection=? AND m.depth<? AND (
              NOT EXISTS(SELECT 1 FROM progress p WHERE p.collection=m.collection AND p.work_id=m.work_id AND p.direction='references' AND p.complete=1)
              OR NOT EXISTS(SELECT 1 FROM progress p WHERE p.collection=m.collection AND p.work_id=m.work_id AND p.direction='citers' AND p.complete=1))
            ORDER BY m.depth, m.added_at, m.work_id LIMIT ?""", (collection, rounds, max_works)).fetchall()
        return [dict(x) for x in rows]

    def stats(self, collection: str) -> dict:
        works = self.db.execute("SELECT COUNT(*) FROM membership WHERE collection=?", (collection,)).fetchone()[0]
        edges = self.db.execute("""SELECT COUNT(*) FROM citations c JOIN membership a ON c.citing_id=a.work_id AND a.collection=?
            JOIN membership b ON c.cited_id=b.work_id AND b.collection=?""", (collection,collection)).fetchone()[0]
        pending = len(self.frontier(collection, 10000, 1000000))
        unresolved = self.db.execute("SELECT COUNT(*) FROM unresolved WHERE collection=?", (collection,)).fetchone()[0]
        depths = [dict(row) for row in self.db.execute("SELECT depth,COUNT(*) AS works FROM membership WHERE collection=? GROUP BY depth ORDER BY depth", (collection,))]
        return {"collection": collection, "works": works, "citation_edges": edges,
                "pending_works": pending, "unresolved_refs": unresolved, "by_depth": depths}

    def search(self, collection: str, text: str, limit: int = 30) -> list[dict]:
        rows = self.db.execute("""SELECT w.id,w.title,w.year,w.doi,w.authors,m.depth FROM works w
            JOIN membership m ON m.work_id=w.id
            WHERE m.collection=? AND (w.title LIKE ? OR w.authors LIKE ?)
            ORDER BY m.depth,w.year DESC LIMIT ?""", (collection, "%"+text+"%", "%"+text+"%", min(max(1,limit),500))).fetchall()
        return [dict(r) for r in rows]

    def add_unresolved(self, collection: str, raw_reference: str, citing_id: str | None = None, note: str = "") -> int:
        if citing_id:
            citing_id = work_id(citing_id)
        c = self.db.execute("INSERT INTO unresolved(collection,citing_id,raw_reference,note,created_at) VALUES(?,?,?,?,?)",
                            (collection,citing_id,raw_reference,note,timestamp()))
        self.db.commit()
        return c.lastrowid

    def export(self, collection: str, directory: str):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        queries = {
            "works.csv": ("""SELECT w.id,w.title,w.year,w.doi,w.authors,w.venue,w.language,w.type,
                              m.depth,m.discovered_by,m.added_at FROM works w JOIN membership m ON w.id=m.work_id WHERE m.collection=?""", (collection,)),
            "citations.csv": ("""SELECT c.* FROM citations c JOIN membership a ON a.work_id=c.citing_id AND a.collection=?
                               JOIN membership b ON b.work_id=c.cited_id AND b.collection=?""", (collection,collection)),
            "unresolved.csv": ("SELECT * FROM unresolved WHERE collection=?", (collection,)),
            "progress.csv": ("SELECT * FROM progress WHERE collection=?", (collection,)),
        }
        outputs = []
        for filename, (sql, parameters) in queries.items():
            rows = self.db.execute(sql, parameters)
            fields = [d[0] for d in rows.description]
            with (target/filename).open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(fields)
                writer.writerows(rows)
            outputs.append(str(target/filename))
        return outputs
