"""Run `citation-chain --help` after installation."""
import argparse
import json
import os
from .engine import Engine
from .store import Store


def main():
    p = argparse.ArgumentParser(description="Persistent scholarly citation chaining")
    p.add_argument("--db", default=os.getenv("CITATION_CHAIN_DB", "./literature.sqlite3"))
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add", help="Seed a collection using an OpenAlex ID or DOI")
    a.add_argument("identifier"); a.add_argument("--collection", default="medieval-epistemology")
    s = sub.add_parser("lookup", help="Search OpenAlex; choose an exact ID before adding")
    s.add_argument("title")
    e = sub.add_parser("expand", help="One bounded, resumable expansion job")
    e.add_argument("--collection", default="medieval-epistemology")
    e.add_argument("--rounds", type=int, default=1)
    e.add_argument("--max-works", type=int, default=10)
    e.add_argument("--per-work", type=int, default=50)
    e.add_argument("--max-new", type=int, default=300)
    z = sub.add_parser("stats"); z.add_argument("--collection", default="medieval-epistemology")
    q = sub.add_parser("search"); q.add_argument("term"); q.add_argument("--collection", default="medieval-epistemology")
    x = sub.add_parser("export"); x.add_argument("directory"); x.add_argument("--collection", default="medieval-epistemology")
    u = sub.add_parser("unresolved", help="Record reference text that OpenAlex did not match")
    u.add_argument("raw_reference"); u.add_argument("--collection", default="medieval-epistemology")
    u.add_argument("--citing-id", default=None)
    args = p.parse_args()
    store = Store(args.db)
    try:
        engine = Engine(store)
        if args.command == "add":
            result = engine.add(args.identifier, args.collection)
        elif args.command == "lookup":
            result = engine.find(args.title)
        elif args.command == "expand":
            result = engine.expand(args.collection, args.rounds,args.max_works,args.per_work,args.max_new)
        elif args.command == "stats":
            result = store.stats(args.collection)
        elif args.command == "search":
            result = store.search(args.collection,args.term)
        elif args.command == "export":
            result = {"files": store.export(args.collection,args.directory)}
        elif args.command == "unresolved":
            result = {"unresolved_id": store.add_unresolved(args.collection,args.raw_reference,args.citing_id)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
