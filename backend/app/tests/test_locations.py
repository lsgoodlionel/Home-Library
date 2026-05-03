"""位置接口测试。"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.location import Location
from app.models.book import Book


def _make_location(
    db: Session,
    room: str = "书房",
    shelf: str = "A架",
    layer: str | None = None,
    position: str | None = None,
    sort_order: int = 0,
) -> Location:
    now = datetime.now(tz=timezone.utc)
    parts = [room, shelf]
    if layer:
        parts.append(layer)
    if position:
        parts.append(position)
    full_path = " / ".join(parts)
    loc = Location(
        room=room,
        shelf=shelf,
        layer=layer,
        position=position,
        full_path=full_path,
        sort_order=sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def _make_book(db: Session, title: str, location_id: int) -> Book:
    now = datetime.now(tz=timezone.utc)
    book = Book(
        title=title,
        status="available",
        read_status="unread",
        source="manual",
        is_favorite=False,
        location_id=location_id,
        created_at=now,
        updated_at=now,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


# ---------------------------------------------------------------------------
# GET /api/locations
# ---------------------------------------------------------------------------

class TestListLocations:
    def test_empty_returns_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/locations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_location_list(self, client: TestClient, db_session: Session) -> None:
        _make_location(db_session, "书房", "A架", sort_order=1)
        _make_location(db_session, "客厅", "B架", sort_order=2)

        resp = client.get("/api/locations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_sorts_by_sort_order(self, client: TestClient, db_session: Session) -> None:
        _make_location(db_session, "卧室", "C架", sort_order=10)
        _make_location(db_session, "书房", "A架", sort_order=1)

        resp = client.get("/api/locations")
        rooms = [loc["room"] for loc in resp.json()]
        assert rooms == ["书房", "卧室"]

    def test_response_has_full_path(self, client: TestClient, db_session: Session) -> None:
        _make_location(db_session, "书房", "A架", "第1层", "左侧")

        resp = client.get("/api/locations")
        item = resp.json()[0]
        assert item["full_path"] == "书房 / A架 / 第1层 / 左侧"

    def test_response_has_required_fields(self, client: TestClient, db_session: Session) -> None:
        _make_location(db_session)

        resp = client.get("/api/locations")
        item = resp.json()[0]
        for field in ("id", "room", "shelf", "layer", "position",
                      "full_path", "sort_order", "created_at", "updated_at"):
            assert field in item, f"缺少字段: {field}"


# ---------------------------------------------------------------------------
# POST /api/locations
# ---------------------------------------------------------------------------

class TestCreateLocation:
    def test_create_minimal_location(self, client: TestClient) -> None:
        resp = client.post("/api/locations", json={"room": "书房", "shelf": "A架"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["room"] == "书房"
        assert data["shelf"] == "A架"
        assert data["full_path"] == "书房 / A架"

    def test_full_path_with_layer(self, client: TestClient) -> None:
        resp = client.post("/api/locations", json={
            "room": "书房", "shelf": "A架", "layer": "第2层"
        })
        assert resp.status_code == 201
        assert resp.json()["full_path"] == "书房 / A架 / 第2层"

    def test_full_path_with_layer_and_position(self, client: TestClient) -> None:
        resp = client.post("/api/locations", json={
            "room": "书房", "shelf": "A架", "layer": "第2层", "position": "右侧"
        })
        assert resp.status_code == 201
        assert resp.json()["full_path"] == "书房 / A架 / 第2层 / 右侧"

    def test_duplicate_path_returns_409(self, client: TestClient, db_session: Session) -> None:
        _make_location(db_session, "书房", "A架")

        resp = client.post("/api/locations", json={"room": "书房", "shelf": "A架"})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_missing_required_fields_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/locations", json={"room": "书房"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/locations/{id}
# ---------------------------------------------------------------------------

class TestUpdateLocation:
    def test_update_room(self, client: TestClient, db_session: Session) -> None:
        loc = _make_location(db_session, "书房", "A架")

        resp = client.patch(f"/api/locations/{loc.id}", json={"room": "客厅"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["room"] == "客厅"
        assert data["full_path"] == "客厅 / A架"   # full_path 自动更新

    def test_update_regenerates_full_path(self, client: TestClient, db_session: Session) -> None:
        loc = _make_location(db_session, "书房", "A架", "第1层")

        resp = client.patch(f"/api/locations/{loc.id}", json={"layer": "第3层"})
        assert resp.status_code == 200
        assert resp.json()["full_path"] == "书房 / A架 / 第3层"

    def test_update_sort_order(self, client: TestClient, db_session: Session) -> None:
        loc = _make_location(db_session, "书房", "A架", sort_order=0)

        resp = client.patch(f"/api/locations/{loc.id}", json={"sort_order": 5})
        assert resp.status_code == 200
        assert resp.json()["sort_order"] == 5

    def test_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.patch("/api/locations/99999", json={"room": "新房间"})
        assert resp.status_code == 404

    def test_clear_layer_updates_full_path(self, client: TestClient, db_session: Session) -> None:
        loc = _make_location(db_session, "书房", "A架", "第1层")

        resp = client.patch(f"/api/locations/{loc.id}", json={"layer": None})
        assert resp.status_code == 200
        assert resp.json()["full_path"] == "书房 / A架"


# ---------------------------------------------------------------------------
# DELETE /api/locations/{id}
# ---------------------------------------------------------------------------

class TestDeleteLocation:
    def test_delete_unused_location(self, client: TestClient, db_session: Session) -> None:
        loc = _make_location(db_session, "书房", "B架")

        resp = client.delete(f"/api/locations/{loc.id}")
        assert resp.status_code == 204

        get_resp = client.get("/api/locations")
        assert get_resp.json() == []

    def test_delete_location_with_books_returns_409(
        self, client: TestClient, db_session: Session
    ) -> None:
        loc = _make_location(db_session, "书房", "C架")
        _make_book(db_session, "测试图书", loc.id)

        resp = client.delete(f"/api/locations/{loc.id}")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_delete_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/locations/99999")
        assert resp.status_code == 404
