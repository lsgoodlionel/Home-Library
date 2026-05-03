"""分类接口测试。"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.book import Book


def _make_category(
    db: Session,
    code: str,
    name: str,
    parent_id: int | None = None,
    is_system: bool = False,
    sort_order: int = 0,
) -> Category:
    now = datetime.now(tz=timezone.utc)
    cat = Category(
        code=code,
        name=name,
        parent_id=parent_id,
        is_system=is_system,
        sort_order=sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _make_book(db: Session, title: str, category_id: int) -> Book:
    now = datetime.now(tz=timezone.utc)
    book = Book(
        title=title,
        status="available",
        read_status="unread",
        source="manual",
        is_favorite=False,
        category_id=category_id,
        created_at=now,
        updated_at=now,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


# ---------------------------------------------------------------------------
# GET /api/categories
# ---------------------------------------------------------------------------

class TestListCategories:
    def test_empty_returns_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_tree_structure(self, client: TestClient, db_session: Session) -> None:
        parent = _make_category(db_session, "I", "文学", sort_order=1)
        _make_category(db_session, "I2", "中国文学", parent_id=parent.id, sort_order=1)
        _make_category(db_session, "I5", "欧洲文学", parent_id=parent.id, sort_order=2)

        resp = client.get("/api/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["code"] == "I"
        children = data[0]["children"]
        assert len(children) == 2
        assert children[0]["code"] == "I2"
        assert children[1]["code"] == "I5"

    def test_sorts_by_sort_order(self, client: TestClient, db_session: Session) -> None:
        _make_category(db_session, "Z", "综合", sort_order=20)
        _make_category(db_session, "A", "马克思主义", sort_order=1)

        resp = client.get("/api/categories")
        codes = [c["code"] for c in resp.json()]
        assert codes == ["A", "Z"]

    def test_response_has_required_fields(self, client: TestClient, db_session: Session) -> None:
        _make_category(db_session, "B", "哲学", is_system=True)

        resp = client.get("/api/categories")
        item = resp.json()[0]
        for field in ("id", "code", "name", "parent_id", "is_system", "sort_order",
                      "created_at", "updated_at", "children"):
            assert field in item, f"缺少字段: {field}"


# ---------------------------------------------------------------------------
# POST /api/categories
# ---------------------------------------------------------------------------

class TestCreateCategory:
    def test_create_root_category(self, client: TestClient) -> None:
        resp = client.post("/api/categories", json={
            "code": "X", "name": "环境科学", "sort_order": 5
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "X"
        assert data["name"] == "环境科学"
        assert data["is_system"] is False
        assert data["parent_id"] is None

    def test_create_child_category(self, client: TestClient, db_session: Session) -> None:
        parent = _make_category(db_session, "F", "经济")

        resp = client.post("/api/categories", json={
            "code": "F8", "name": "金融", "parent_id": parent.id
        })
        assert resp.status_code == 201
        assert resp.json()["parent_id"] == parent.id

    def test_duplicate_code_returns_409(self, client: TestClient, db_session: Session) -> None:
        _make_category(db_session, "G", "文化教育")

        resp = client.post("/api/categories", json={"code": "G", "name": "重复"})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_nonexistent_parent_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/categories", json={
            "code": "X9", "name": "子分类", "parent_id": 99999
        })
        assert resp.status_code == 404

    def test_missing_required_fields_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/categories", json={"name": "无 code"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/categories/{id}
# ---------------------------------------------------------------------------

class TestUpdateCategory:
    def test_update_name(self, client: TestClient, db_session: Session) -> None:
        cat = _make_category(db_session, "H", "语言文字")

        resp = client.patch(f"/api/categories/{cat.id}", json={"name": "语言、文字"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "语言、文字"

    def test_update_sort_order(self, client: TestClient, db_session: Session) -> None:
        cat = _make_category(db_session, "K", "历史地理", sort_order=0)

        resp = client.patch(f"/api/categories/{cat.id}", json={"sort_order": 99})
        assert resp.status_code == 200
        assert resp.json()["sort_order"] == 99

    def test_self_as_parent_returns_422(self, client: TestClient, db_session: Session) -> None:
        cat = _make_category(db_session, "N", "自然科学")

        resp = client.patch(f"/api/categories/{cat.id}", json={"parent_id": cat.id})
        assert resp.status_code == 422

    def test_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.patch("/api/categories/99999", json={"name": "不存在"})
        assert resp.status_code == 404

    def test_partial_update_preserves_other_fields(self, client: TestClient, db_session: Session) -> None:
        cat = _make_category(db_session, "O", "数理化学", sort_order=7)

        resp = client.patch(f"/api/categories/{cat.id}", json={"sort_order": 8})
        data = resp.json()
        assert data["code"] == "O"          # 未改变
        assert data["sort_order"] == 8


# ---------------------------------------------------------------------------
# DELETE /api/categories/{id}
# ---------------------------------------------------------------------------

class TestDeleteCategory:
    def test_delete_user_category(self, client: TestClient, db_session: Session) -> None:
        cat = _make_category(db_session, "Q", "生物科学")

        resp = client.delete(f"/api/categories/{cat.id}")
        assert resp.status_code == 204

        # 验证已删除
        get_resp = client.get("/api/categories")
        codes = [c["code"] for c in get_resp.json()]
        assert "Q" not in codes

    def test_delete_system_category_returns_403(self, client: TestClient, db_session: Session) -> None:
        cat = _make_category(db_session, "R", "医药卫生", is_system=True)

        resp = client.delete(f"/api/categories/{cat.id}")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    def test_delete_category_with_books_returns_409(
        self, client: TestClient, db_session: Session
    ) -> None:
        cat = _make_category(db_session, "S", "农业科学")
        _make_book(db_session, "农业概论", cat.id)

        resp = client.delete(f"/api/categories/{cat.id}")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_delete_category_with_children_returns_409(
        self, client: TestClient, db_session: Session
    ) -> None:
        parent = _make_category(db_session, "T", "工业技术")
        _make_category(db_session, "T9", "计算机", parent_id=parent.id)

        resp = client.delete(f"/api/categories/{parent.id}")
        assert resp.status_code == 409

    def test_delete_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/categories/99999")
        assert resp.status_code == 404
