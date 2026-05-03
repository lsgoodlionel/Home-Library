from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import auth_required
from app.db.session import get_db
from app.schemas.location import LocationCreate, LocationResponse, LocationUpdate
from app.services import location_service

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationResponse])
def list_locations(db: Session = Depends(get_db)) -> list[LocationResponse]:
    """返回位置列表，按 sort_order 排序。"""
    locs = location_service.get_locations(db)
    return [LocationResponse.model_validate(loc) for loc in locs]


@router.post("", response_model=LocationResponse, status_code=201)
def create_location(
    data: LocationCreate,
    db: Session = Depends(get_db),
    _: None = Depends(auth_required),
) -> LocationResponse:
    """新增位置（仅管理员）。full_path 自动生成。"""
    loc = location_service.create_location(db, data)
    return LocationResponse.model_validate(loc)


@router.patch("/{location_id}", response_model=LocationResponse)
def update_location(
    location_id: int,
    data: LocationUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(auth_required),
) -> LocationResponse:
    """更新位置（仅管理员）。full_path 自动重新生成。"""
    loc = location_service.update_location(db, location_id, data)
    return LocationResponse.model_validate(loc)


@router.delete("/{location_id}", status_code=204)
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(auth_required),
) -> None:
    """删除位置（仅管理员）。已被图书引用的位置不可删除。"""
    location_service.delete_location(db, location_id)
