from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import auth_required
from app.db.session import get_db
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryTree, CategoryUpdate
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryTree])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryTree]:
    """返回完整分类树，按 sort_order 排序。"""
    return category_service.get_category_tree(db)


@router.post("", response_model=CategoryResponse, status_code=201)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    _: None = Depends(auth_required),
) -> CategoryResponse:
    """新增分类（仅管理员）。"""
    cat = category_service.create_category(db, data)
    return CategoryResponse.model_validate(cat)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(auth_required),
) -> CategoryResponse:
    """更新分类（仅管理员）。"""
    cat = category_service.update_category(db, category_id, data)
    return CategoryResponse.model_validate(cat)


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(auth_required),
) -> None:
    """删除分类（仅管理员）。系统分类及已被图书引用的分类不可删除。"""
    category_service.delete_category(db, category_id)
