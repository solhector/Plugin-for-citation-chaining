import csv
import tempfile
import unittest
from pathlib import Path
from citation_chain.store import Store
from citation_chain.engine import Engine
from citation_chain.openalex import work_id, normalize_doi


def paper(n, refs=(), title=None):
    return {"id": f"https://openalex.org/W{n}", "title": title or f"Paper {n}",
            "publication_year": 2000+n, "doi": None, "authorships": [{"author":{"display_name":"Author Test"}}],
            "primary_location": {"source": {"display_name":"Test Journal"}},
            "referenced_works": [f"https://openalex.org/W{x}" for x in refs], "cited_by_count": 0}


class FakeClient:
    def __init__(self, papers, citations):
        self.papers = papers
        self.citations = citations
        self.calls = []

    def get(self, id):
        k = work_id(id)
        self.calls.append(("get",k))
        return self.papers[k]

    def search(self,title,count=5):
        return list(self.papers.values())[:count]

    def batch(self,ids):
        self.calls.append(("batch",tuple(ids)))
        return [self.papers[i] for i in ids if i in self.papers]

    def citing_page(self, cited_id, cursor="*", per_page=100):
        self.calls.append(("citing",cited_id,cursor,per_page))
        ids = self.citations.get(cited_id, [])
        offset = 0 if cursor == "*" else int(cursor)
        picked = ids[offset:offset+per_page]
        nxt = str(offset+len(picked)) if offset+len(picked)<len(ids) else None
        return {"results":[self.papers[i] for i in picked],"meta":{"next_cursor":nxt,"count":len(ids)}}


class CitationChainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name)/"works.sqlite3"))
        raws = [paper(1,[2,3],"Seed"), paper(2,[4]), paper(3,[4]), paper(4), paper(5,[1]), paper(6,[5])]
        self.client = FakeClient({work_id(p["id"]):p for p in raws},
                                 {"W1":["W5"],"W5":["W6"]})
        self.engine = Engine(self.store,self.client)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_double_direction_and_two_rounds(self):
        self.engine.add("W1","demo")
        first = self.engine.expand("demo", rounds=1, max_works=20, per_work=50,max_new=100)
        self.assertEqual(first["stats"]["works"],4)
        self.assertEqual(first["stats"]["citation_edges"],3)
        second = self.engine.expand("demo", rounds=2, max_works=20, per_work=50,max_new=100)
        self.assertEqual(second["stats"]["works"],6)
        self.assertEqual(second["stats"]["citation_edges"],6)
        self.assertEqual(self.store.stats("demo")["by_depth"],
                         [{"depth":0,"works":1},{"depth":1,"works":3},{"depth":2,"works":2}])
        again = self.engine.expand("demo", rounds=1, max_works=20)
        self.assertEqual(again["new_works"],0)

    def test_resume_references(self):
        self.engine.add("W1","demo")
        first=self.engine.expand("demo",rounds=1,max_works=1,per_work=1,max_new=50)
        self.assertEqual(self.store.state("demo","W1","references")["offset"],1)
        self.assertFalse(self.store.state("demo","W1","references")["complete"])
        second=self.engine.expand("demo",rounds=1,max_works=1,per_work=10,max_new=50)
        self.assertTrue(self.store.state("demo","W1","references")["complete"])
        self.assertEqual(self.store.stats("demo")["works"],4)

    def test_resume_citers(self):
        self.client.citations["W1"]=["W5", "W6"]
        self.engine.add("W1","demo")
        first=self.engine.expand("demo",rounds=1,max_works=1,per_work=1,max_new=50)
        self.assertEqual(self.store.state("demo","W1","citers")["offset"],1)
        second=self.engine.expand("demo",rounds=1,max_works=1,per_work=20,max_new=50)
        self.assertTrue(self.store.state("demo","W1","citers")["complete"])
        self.assertEqual(self.store.stats("demo")["works"],5)

    def test_missing_reference_saved(self):
        self.client.papers["W1"]["referenced_works"].append("https://openalex.org/W999")
        self.engine.add("W1","demo")
        result=self.engine.expand("demo",rounds=1)
        self.assertEqual(result["stats"]["unresolved_refs"],1)

    def test_export_utf8_and_search(self):
        self.client.papers["W1"]["title"]="Éthique 与历史"
        self.engine.add("W1","demo")
        self.engine.expand("demo",rounds=1)
        files=self.store.export("demo",str(Path(self.tmp.name)/"out"))
        self.assertEqual(len(files),4)
        self.assertEqual(self.store.search("demo","Éthique")[0]["title"],"Éthique 与历史")
        with open(files[0],encoding="utf-8-sig",newline="") as f:
            self.assertGreater(len(list(csv.DictReader(f))),2)

    def test_lookup_returns_options_not_guess(self):
        options=self.engine.find("ambiguous")
        self.assertEqual(options[0]["id"],"W1")
        self.assertEqual(self.store.stats("demo")["works"],0)

    def test_validation(self):
        self.assertEqual(work_id("https://openalex.org/W123"),"W123")
        self.assertEqual(normalize_doi("doi:10.1000/xyz"),"https://doi.org/10.1000/xyz")
        with self.assertRaises(ValueError):
            self.engine.expand("demo",rounds=0)


if __name__=="__main__":
    unittest.main()
