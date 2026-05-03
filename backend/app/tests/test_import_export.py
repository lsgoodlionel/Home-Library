from __future__ import annotations

import io
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Book, Category, Location
from app.schemas.book import BookCreate
from app.services import book_service, import_export_service


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _seed_refs(db: Session) -> tuple[Category, Location]:
    now = _now()
    category = Category(code="C91", name="社会学", is_system=True, created_at=now, updated_at=now)
    location = Location(
        room="书房",
        shelf="A 架",
        layer="第 2 层",
        position="右侧",
        full_path="书房 / A 架 / 第 2 层 / 右侧",
        created_at=now,
        updated_at=now,
    )
    db.add_all([category, location])
    db.commit()
    db.refresh(category)
    db.refresh(location)
    return category, location


def _upload(content: str | bytes, filename: str, file_format: str) -> dict:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return {
        "files": {"file": (filename, data)},
        "data": {"format": file_format},
    }


def _csv(rows: list[str]) -> str:
    return "\n".join(rows) + "\n"


def test_csv_preview_reports_valid_rows(client: TestClient, db: Session) -> None:
    category, location = _seed_refs(db)
    content = _csv(
        [
            "title,author,isbn,category_id,location_id,tag_names",
            f"乡土中国,费孝通,978-7-108-04526-9,{category.id},{location.id},社会学;经典",
        ]
    )

    response = client.post("/api/books/import/preview", **_upload(content, "books.csv", "csv"))

    assert response.status_code == 200
    data = response.json()
    assert data["total_rows"] == 1
    assert data["valid_rows"] == 1
    assert data["rows"][0]["data"]["isbn"] == "9787108045269"
    assert data["rows"][0]["data"]["tag_names"] == ["社会学", "经典"]


def test_json_preview_supports_field_mapping(client: TestClient, db: Session) -> None:
    category, location = _seed_refs(db)
    content = json.dumps(
        {
            "items": [
                {
                    "书名": "经济学原理",
                    "作者": "曼昆",
                    "ISBN": "9787301256909",
                    "分类号": category.code,
                    "位置": location.full_path,
                }
            ]
        },
        ensure_ascii=False,
    )

    response = client.post("/api/books/import/preview", **_upload(content, "books.json", "json"))

    assert response.status_code == 200
    data = response.json()
    assert data["valid_rows"] == 1
    assert data["rows"][0]["data"]["category_id"] == category.id
    assert data["rows"][0]["data"]["location_id"] == location.id


def test_import_success_creates_books(client: TestClient, db: Session) -> None:
    category, location = _seed_refs(db)
    content = _csv(
        [
            "title,author,isbn,category_id,location_id",
            f"乡土中国,费孝通,9787108045269,{category.id},{location.id}",
        ]
    )

    response = client.post("/api/books/import", **_upload(content, "books.csv", "csv"))

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    book = db.query(Book).one()
    assert book.title == "乡土中国"
    assert book.source == "import"


def test_import_failure_rolls_back_all_rows(client: TestClient, db: Session, monkeypatch) -> None:
    category, location = _seed_refs(db)
    content = _csv(
        [
            "title,author,isbn,category_id,location_id",
            f"第一本,作者,9787108045269,{category.id},{location.id}",
            f"第二本,作者,9787301256909,{category.id},{location.id}",
        ]
    )
    calls = {"count": 0}
    original_create_book = book_service.create_book

    def fail_on_second(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated failure")
        return original_create_book(*args, **kwargs)

    monkeypatch.setattr(import_export_service.book_service, "create_book", fail_on_second)

    response = client.post("/api/books/import", **_upload(content, "books.csv", "csv"))

    assert response.status_code == 500
    assert db.query(Book).count() == 0


def test_export_csv(client: TestClient, db: Session) -> None:
    category, location = _seed_refs(db)
    book_service.create_book(
        db,
        BookCreate(title="乡土中国", author="费孝通", isbn="9787108045269", category_id=category.id, location_id=location.id),
    )

    response = client.get("/api/books/export", params={"format": "csv"})

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="books.csv"'
    assert "乡土中国" in response.content.decode("utf-8-sig")
    assert "9787108045269" in response.content.decode("utf-8-sig")


def test_export_json_can_be_previewed_again(client: TestClient, db: Session) -> None:
    category, location = _seed_refs(db)
    book_service.create_book(
        db,
        BookCreate(title="经济学原理", author="曼昆", isbn="9787301256909", category_id=category.id, location_id=location.id),
    )

    response = client.get("/api/books/export", params={"format": "json"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["title"] == "经济学原理"

    db.query(Book).delete()
    db.commit()
    preview = client.post("/api/books/import/preview", **_upload(response.content, "books.json", "json"))
    assert preview.status_code == 200
    assert preview.json()["valid_rows"] == 1


def test_duplicate_isbn_detection(client: TestClient, db: Session) -> None:
    category, location = _seed_refs(db)
    book_service.create_book(db, BookCreate(title="已存在", isbn="9787108045269"))
    content = _csv(
        [
            "title,isbn,category_id,location_id",
            f"新书,978-7-108-04526-9,{category.id},{location.id}",
            f"同文件重复,9787301256909,{category.id},{location.id}",
            f"同文件重复二,978-7-301-25690-9,{category.id},{location.id}",
        ]
    )

    response = client.post("/api/books/import/preview", **_upload(content, "books.csv", "csv"))

    assert response.status_code == 200
    data = response.json()
    assert data["invalid_rows"] == 3
    assert [error["code"] for error in data["errors"]] == ["DUPLICATE_ISBN", "DUPLICATE_ISBN", "DUPLICATE_ISBN"]


def test_excel_preview(client: TestClient, db: Session) -> None:
    from openpyxl import Workbook

    category, location = _seed_refs(db)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["title", "isbn", "category_id", "location_id"])
    sheet.append(["Excel 书", "9787108045269", category.id, location.id])
    buffer = io.BytesIO()
    workbook.save(buffer)

    response = client.post("/api/books/import/preview", **_upload(buffer.getvalue(), "books.xlsx", "xlsx"))

    assert response.status_code == 200
    assert response.json()["valid_rows"] == 1
