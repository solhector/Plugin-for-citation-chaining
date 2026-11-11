"""Auditable, resumable citation chaining with conservative collection limits."""
from .openalex import OpenAlex, OpenAlexError, work_id
from .store import Store


class Engine:
    def __init__(self, store: Store, client: OpenAlex | None = None):
        self.store = store
        self.client = client or OpenAlex()

    def add(self, identifier: str, collection: str) -> dict:
        raw = self.client.get(identifier)
        identifier = self.store.put_work(raw)
        added = self.store.member(collection, identifier, 0)
        return {"id": identifier, "title": raw.get("title"), "collection": collection, "new": added}

    def find(self, title: str) -> list[dict]:
        # Do not auto-select a fuzzy match. A researcher must confirm identity.
        return [{"id": work_id(x["id"]), "title": x.get("title"),
                 "year": x.get("publication_year"), "doi": x.get("doi")}
                for x in self.client.search(title)]

    def _references(self, collection: str, parent: str, depth: int, per_work: int, budget: int) -> dict:
        state = self.store.state(collection, parent, "references")
        if state["complete"]:
            return {"new": 0, "seen": 0, "done": True}
        raw = self.store.raw(parent)
        if not raw:
            raw = self.client.get(parent)
            self.store.put_work(raw)
        refs = list(dict.fromkeys(work_id(x) for x in raw.get("referenced_works", []) if x))
        offset = int(state["offset"])
        seen = 0
        new = 0
        missing = 0
        while offset < len(refs) and seen < per_work and new < budget:
            count = min(100, per_work - seen, len(refs) - offset, max(1, budget - new))
            ids = refs[offset:offset + count]
            # Fetch before advancing progress. Failure means the work can be retried.
            fetched = self.client.batch(ids)
            got = set()
            for paper in fetched:
                cited = self.store.put_work(paper)
                got.add(cited)
                self.store.link(parent, cited)
                if self.store.member(collection, cited, depth + 1, parent):
                    new += 1
            for key in ids:
                if key not in got:
                    missing += 1
                    self.store.add_unresolved(collection, f"OpenAlex reference ID {key} could not be fetched", parent,
                                              "Unmatched OpenAlex reference; verify manually")
            offset += len(ids)
            seen += len(ids)
            self.store.save_state(collection, parent, "references", offset=offset,
                                  complete=offset >= len(refs), note=f"missing={missing}" if missing else None)
        if offset >= len(refs):
            self.store.save_state(collection, parent, "references", offset=offset, complete=True)
        return {"new": new, "seen": seen, "done": offset >= len(refs), "unresolved": missing}

    def _citers(self, collection: str, parent: str, depth: int, per_work: int, budget: int) -> dict:
        state = self.store.state(collection, parent, "citers")
        if state["complete"]:
            return {"new": 0, "seen": 0, "done": True}
        cursor = state["cursor"]
        seen = new = 0
        total = int(state["offset"])
        complete = False
        while seen < per_work and new < budget:
            size = min(100, per_work - seen, max(1, budget - new))
            page = self.client.citing_page(parent, cursor=cursor, per_page=size)
            items = page.get("results", [])
            for paper in items:
                citing = self.store.put_work(paper)
                self.store.link(citing, parent)
                if self.store.member(collection, citing, depth + 1, parent):
                    new += 1
            seen += len(items)
            total += len(items)
            next_cursor = (page.get("meta") or {}).get("next_cursor")
            count = (page.get("meta") or {}).get("count")
            complete = not items or not next_cursor or (count is not None and total >= int(count))
            cursor = next_cursor or cursor
            self.store.save_state(collection, parent, "citers", offset=total,
                                  cursor=cursor, complete=complete)
            if complete:
                break
        return {"new": new, "seen": seen, "done": complete}

    def expand(self, collection: str, rounds: int = 1, max_works: int = 10,
               per_work: int = 50, max_new: int = 300) -> dict:
        if not 1 <= rounds <= 20:
            raise ValueError("rounds must be between 1 and 20")
        if not 1 <= max_works <= 10000 or not 1 <= per_work <= 10000 or not 1 <= max_new <= 100000:
            raise ValueError("limits must be positive and within safety bounds")
        results = []
        added = 0
        parents = self.store.frontier(collection, rounds, max_works)
        for parent in parents:
            if added >= max_new:
                break
            item = {"id": parent["work_id"], "depth": parent["depth"]}
            for direction, method in (("references", self._references), ("citers", self._citers)):
                if added >= max_new:
                    break
                try:
                    outcome = method(collection, parent["work_id"], parent["depth"], per_work, max_new - added)
                    item[direction] = outcome
                    added += outcome["new"]
                except (OpenAlexError, ValueError) as exc:
                    item[direction] = {"error": str(exc), "resume_possible": True}
            results.append(item)
        return {"collection": collection, "rounds": rounds, "parents_attempted": len(results),
                "new_works": added, "details": results, "stats": self.store.stats(collection)}
