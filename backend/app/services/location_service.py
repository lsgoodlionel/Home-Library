"""位置业务逻辑。"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.location import Location
from app.schemas.location import LocationCreate, LocationUpdate


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def build_full_path(room: str, shelf: str, layer: str | None, position: str | None) -> str:
    """拼接完整位置路径，各段以 ' / ' 分隔。"""
    parts = [room, shelf]
    if layer:
        parts.append(layer)
    if position:
        parts.append(position)
    return " / ".join(parts)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def get_location_or_404(db: Session, location_id: int) -> Location:
    loc = db.get(Location, location_id)
    if loc is None:
        raise ApiError("NOT_FOUND", f"位置 {location_id} 不存在", 404)
    return loc


def get_locations(db: Session) -> list[Location]:
    return db.query(Location).order_by(Location.sort_order, Location.id).all()


# ---------------------------------------------------------------------------
# 新增
# ---------------------------------------------------------------------------

def create_location(db: Session, data: LocationCreate) -> Location:
    # 唯一性检查 (room + shelf + layer + position)
    existing = (
        db.query(Location)
        .filter_by(
            room=data.room,
            shelf=data.shelf,
            layer=data.layer,
            position=data.position,
        )
        .first()
    )
    if existing:
        raise ApiError("CONFLICT", "相同路径的位置已存在", 409)

    full_path = build_full_path(data.room, data.shelf, data.layer, data.position)
    now = _now()
    loc = Location(
        room=data.room,
        shelf=data.shelf,
        layer=data.layer,
        position=data.position,
        full_path=full_path,
        description=data.description,
        sort_order=data.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------

def update_location(db: Session, location_id: int, data: LocationUpdate) -> Location:
    loc = get_location_or_404(db, location_id)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(loc, field, value)

    # 重新生成 full_path
    loc.full_path = build_full_path(loc.room, loc.shelf, loc.layer, loc.position)
    loc.updated_at = _now()

    db.commit()
    db.refresh(loc)
    return loc


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------

def delete_location(db: Session, location_id: int) -> None:
    loc = get_location_or_404(db, location_id)

    from app.models.book import Book  # 延迟导入避免循环
    book_count = db.query(Book).filter_by(location_id=location_id).count()
    if book_count > 0:
        raise ApiError(
            "CONFLICT",
            f"该位置下有 {book_count} 本图书，无法删除",
            409,
        )

    db.delete(loc)
    db.commit()
