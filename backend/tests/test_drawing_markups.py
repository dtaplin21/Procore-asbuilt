import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from api.routes import drawing_markups as routes
from models.drawing_markup import DrawingMarkup
from models.models import Company, Drawing, Project
from services import drawing_markups as svc


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    database.Base.metadata.create_all(
        engine,
        tables=[
            Company.__table__,
            Project.__table__,
            Drawing.__table__,
            DrawingMarkup.__table__,
        ],
    )
    monkeypatch.setattr(routes, "SessionLocal", Session)
    s = Session()
    s.add(Company(id=1, name="Co", procore_company_id="co-markups"))
    s.add(Project(id=1, company_id=1, procore_project_id="1348", name="Markups"))
    s.add(Drawing(id=1722, project_id=1, source="upload", name="Master.pdf"))
    s.commit()
    s.close()
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


BODY = {"kind": "polyline", "points": [[0.26, 0.79], [0.35, 0.81]], "inspection_type": "underground piping", "status": "open"}


def test_create_list_roundtrip_and_vocabulary_is_canonical(client):
    r = client.post("/api/drawings/1722/markups", json=BODY, headers={"X-Procore-User": "Dom"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["inspectionType"] == "Underground Piping" and out["status"] == "Open" and out["createdBy"] == "Dom"
    rows = client.get("/api/drawings/1722/markups", params={"inspection_type": "Underground Piping"}).json()
    assert [x["id"] for x in rows] == [out["id"]]
    assert client.get("/api/drawings/1722/markups", params={"inspection_type": "Final"}).json() == []


@pytest.mark.parametrize(
    "patch",
    [
        {"kind": "polyline", "points": [[0.1, 0.1]]},
        {"kind": "polyline", "points": [[0.1, 0.1], [0.2, 1.4]]},
        {"kind": "arrow", "points": [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]]},
        {"kind": "text", "points": [[0.1, 0.1]]},
        {"kind": "blob", "points": [[0.1, 0.1], [0.2, 0.2]]},
        {"kind": "rect", "points": [[0.1, 0.1], [0.2, 0.2]], "status": "Maybe"},
        {"kind": "rect", "points": [[0.1, 0.1], [0.2, 0.2]], "color": "red"},
    ],
)
def test_bad_input_is_rejected(client, patch):
    assert client.post("/api/drawings/1722/markups", json=patch).status_code == 422


def test_unknown_drawing_and_unknown_markup(client):
    assert client.post("/api/drawings/9/markups", json=BODY).status_code == 404
    assert client.patch("/api/markups/99", json={"label": "x"}).status_code == 404
    assert client.delete("/api/markups/99").status_code == 404


def test_patch_validates_against_the_stored_kind_and_rejects_extras(client):
    mid = client.post("/api/drawings/1722/markups", json=BODY).json()["id"]
    ok = client.patch(f"/api/markups/{mid}", json={"status": "Closed", "points": [[0.3, 0.3], [0.4, 0.4], [0.5, 0.5]]})
    assert ok.status_code == 200 and ok.json()["status"] == "Closed" and len(ok.json()["points"]) == 3
    assert client.patch(f"/api/markups/{mid}", json={"points": [[0.3, 0.3]]}).status_code == 422
    assert client.patch(f"/api/markups/{mid}", json={"kind": "cloud"}).status_code == 422


def test_delete_is_soft_and_summary_counts_live_rows(client):
    a = client.post("/api/drawings/1722/markups", json=BODY).json()["id"]
    client.post("/api/drawings/1722/markups", json={**BODY, "status": "Closed"})
    client.post("/api/drawings/1722/markups", json={**BODY, "page": 2})
    assert client.delete(f"/api/markups/{a}").status_code == 204
    assert client.get("/api/drawings/1722/markups").json().__len__() == 2
    assert client.delete(f"/api/markups/{a}").status_code == 404
    s = client.get("/api/drawings/1722/markups/summary", params={"page": 1}).json()
    assert s == [{"inspection_type": "Underground Piping", "status": "Closed", "count": 1}]


def test_service_rejects_non_numbers_and_nan():
    with pytest.raises(svc.MarkupError):
        svc.clean_points("polyline", [[0, 0], ["a", 1]])
    with pytest.raises(svc.MarkupError):
        svc.clean_points("polyline", [[0, 0], [float("nan"), 0.5]])
