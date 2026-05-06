"""数据库初始化：建表、写入种子分类、创建默认管理员。全部操作具备幂等保护。"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Base, User, Category
from .session import engine
from .seeds import L1_CATEGORIES, L2_CATEGORIES, L3_CATEGORIES

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表已就绪")


def seed_categories(db: Session) -> None:
    existing_codes = {row[0] for row in db.query(Category.code).all()}

    code_to_id: dict[str, int] = {
        row[0]: row[1] for row in db.query(Category.code, Category.id).all()
    }

    now = _now()

    # 一级分类
    for code, name, sort_order in L1_CATEGORIES:
        if code not in existing_codes:
            cat = Category(
                code=code,
                name=name,
                parent_id=None,
                sort_order=sort_order,
                is_system=True,
                created_at=now,
                updated_at=now,
            )
            db.add(cat)
            existing_codes.add(code)

    db.flush()

    # 刷新后重新取 id 映射（一级）
    code_to_id = {
        row[0]: row[1] for row in db.query(Category.code, Category.id).all()
    }

    # 二级分类
    for code, parent_code, name, sort_order in L2_CATEGORIES:
        if code not in existing_codes:
            parent_id = code_to_id.get(parent_code)
            cat = Category(
                code=code,
                name=name,
                parent_id=parent_id,
                sort_order=sort_order,
                is_system=True,
                created_at=now,
                updated_at=now,
            )
            db.add(cat)
            existing_codes.add(code)

    db.flush()

    # 刷新后重新取 id 映射（含二级）
    code_to_id = {
        row[0]: row[1] for row in db.query(Category.code, Category.id).all()
    }

    # 三级分类
    for code, parent_code, name, sort_order in L3_CATEGORIES:
        if code not in existing_codes:
            parent_id = code_to_id.get(parent_code)
            cat = Category(
                code=code,
                name=name,
                parent_id=parent_id,
                sort_order=sort_order,
                is_system=True,
                created_at=now,
                updated_at=now,
            )
            db.add(cat)
            existing_codes.add(code)

    db.commit()
    logger.info("分类种子数据已写入（L1: %d, L2: %d, L3: %d）",
                len(L1_CATEGORIES), len(L2_CATEGORIES), len(L3_CATEGORIES))


def seed_admin(db: Session) -> None:
    from passlib.context import CryptContext

    settings = get_settings()
    username = settings.initial_admin_username
    password = settings.initial_admin_password

    existing = db.query(User).filter_by(username=username).first()
    if existing:
        logger.info("管理员 '%s' 已存在，跳过创建", username)
        return

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    now = _now()
    admin = User(
        username=username,
        password_hash=pwd_ctx.hash(password),
        display_name="管理员",
        role="admin",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(admin)
    db.commit()
    logger.info("默认管理员 '%s' 已创建", username)


def init_db(db: Session) -> None:
    create_tables()
    seed_categories(db)
    seed_admin(db)
    logger.info("数据库初始化完成")
