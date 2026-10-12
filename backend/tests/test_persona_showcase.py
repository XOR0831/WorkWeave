"""Featured personas and their showcase on the demo page (migration 0011)."""

import copy
import json
from pathlib import Path

from app.cli import validate_pack
from tests.test_demo_slice import open_company

PACKS = Path(__file__).resolve().parents[2] / "seed" / "packs"


def test_the_demo_page_gets_four_featured_personas_and_everyone_stays_switchable(client):
    for company, featured in (("northstar", ["Sam", "Alex", "Jamie", "Morgan"]), ("harbor", ["Nora", "Leo", "Mia", "Ravi"]), ("acme", ["Alex", "Pat", "Morgan", "Sam"])):
        open_company(client, company, intent="FRESH")
        people = client.get("/api/personas").json()["data"]
        shown = [p["first_name"] for p in people if p["featured"]]
        assert sorted(shown) == sorted(featured) and len(people) > 4  # the others remain in the list
        for p in people:
            if p["featured"]:
                assert p["showcase"]["headline"].startswith("Use ") and p["showcase"]["features"]
            else:
                assert "showcase" not in p
    alex = next(p for p in people if p["first_name"] == "Alex")
    assert {f["module"] for f in alex["showcase"]["features"]} == {"COMPANION", "HANDOVER"}


def test_the_importer_rejects_a_bad_showcase(engine):
    pack = json.loads((PACKS / "northstar-manufacturing" / "catalog.json").read_text())
    with engine.connect() as conn:
        assert validate_pack(conn, pack) == []
        too_many = copy.deepcopy(pack)
        for p in too_many["personas"]:
            p["featured"], p["showcase"] = True, pack["personas"][0]["showcase"]
        assert "feature one to four personas on the demo page (featured: true)" in validate_pack(conn, too_many)
        bad = copy.deepcopy(pack)
        bad["personas"][0]["showcase"]["features"][0]["module"] = "PAYROLL"
        assert any("each showcase feature needs a module" in x for x in validate_pack(conn, bad))
        # Personas that aren't featured may have a showcase too (shown under "Show all"), checked the same way.
        assert pack["personas"][4]["showcase"] and not pack["personas"][4]["featured"]  # Priya
        stray = copy.deepcopy(pack)
        stray["personas"][4]["showcase"]["features"] = []
        assert any("needs one to five entries" in x for x in validate_pack(conn, stray))
        missing = copy.deepcopy(pack)
        del missing["personas"][0]["showcase"]
        assert any("a featured persona needs a showcase" in x for x in validate_pack(conn, missing))
