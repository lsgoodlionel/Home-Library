"""分类业务逻辑。"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryTree, CategoryUpdate


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def get_category_or_404(db: Session, category_id: int) -> Category:
    cat = db.get(Category, category_id)
    if cat is None:
        raise ApiError("NOT_FOUND", f"分类 {category_id} 不存在", 404)
    return cat


def get_category_tree(db: Session) -> list[CategoryTree]:
    """返回完整分类树，按 sort_order 排序。"""
    rows: list[Category] = (
        db.query(Category).order_by(Category.sort_order, Category.id).all()
    )

    # 构建 id → node 映射
    # 注意：必须显式传入 children=[]，否则 model_validate(from_attributes=True)
    # 会读取 SQLAlchemy relationship 中已加载的子对象，导致后续手动 append 重复。
    nodes: dict[int, CategoryTree] = {}
    for row in rows:
        node = CategoryTree.model_validate(row)
        node.children = []          # 重置，完全由下方手动构建
        nodes[row.id] = node

    roots: list[CategoryTree] = []
    for row in rows:
        node = nodes[row.id]
        if row.parent_id is None:
            roots.append(node)
        else:
            parent = nodes.get(row.parent_id)
            if parent is not None:
                parent.children.append(node)

    return roots


# ---------------------------------------------------------------------------
# 新增
# ---------------------------------------------------------------------------

def create_category(db: Session, data: CategoryCreate) -> Category:
    # code 唯一性检查
    existing = db.query(Category).filter_by(code=data.code).first()
    if existing:
        raise ApiError("CONFLICT", f"分类号 '{data.code}' 已存在", 409)

    # parent 存在性检查
    if data.parent_id is not None:
        get_category_or_404(db, data.parent_id)

    now = _now()
    cat = Category(
        code=data.code,
        name=data.name,
        parent_id=data.parent_id,
        description=data.description,
        sort_order=data.sort_order,
        is_system=False,
        created_at=now,
        updated_at=now,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------

def update_category(db: Session, category_id: int, data: CategoryUpdate) -> Category:
    cat = get_category_or_404(db, category_id)

    # 防止把分类设为自身的父分类（直接循环）
    if data.parent_id is not None:
        if data.parent_id == category_id:
            raise ApiError("VALIDATION_ERROR", "分类不能将自身设为父分类", 422)
        get_category_or_404(db, data.parent_id)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cat, field, value)
    cat.updated_at = _now()

    db.commit()
    db.refresh(cat)
    return cat


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------

def delete_category(db: Session, category_id: int) -> None:
    cat = get_category_or_404(db, category_id)

    # 系统内置分类不允许删除
    if cat.is_system:
        raise ApiError("FORBIDDEN", "系统内置分类不允许删除", 403)

    # 已被图书引用不允许删除
    from app.models.book import Book  # 延迟导入避免循环
    book_count = db.query(Book).filter_by(category_id=category_id).count()
    if book_count > 0:
        raise ApiError(
            "CONFLICT",
            f"该分类下有 {book_count} 本图书，无法删除",
            409,
        )

    # 有子分类不允许删除
    child_count = db.query(Category).filter_by(parent_id=category_id).count()
    if child_count > 0:
        raise ApiError("CONFLICT", "该分类下有子分类，请先删除子分类", 409)

    db.delete(cat)
    db.commit()
