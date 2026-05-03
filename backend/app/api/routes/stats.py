from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stats import (
    CategoryDistItem,
    LocationDistItem,
    OverviewStats,
    ReadingStats,
    TimelineStats,
)
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
def stats_overview(db: Session = Depends(get_db)) -> OverviewStats:
    """首页仪表盘总览统计。"""
    return stats_service.get_overview(db)


@router.get("/categories", response_model=list[CategoryDistItem])
def stats_categories(db: Session = Depends(get_db)) -> list[CategoryDistItem]:
    """分类分布统计。"""
    return stats_service.get_categories_dist(db)


@router.get("/locations", response_model=list[LocationDistItem])
def stats_locations(db: Session = Depends(get_db)) -> list[LocationDistItem]:
    """位置分布统计。"""
    return stats_service.get_locations_dist(db)


@router.get("/reading", response_model=ReadingStats)
def stats_reading(db: Session = Depends(get_db)) -> ReadingStats:
    """阅读状态分布统计。"""
    return stats_service.get_reading_stats(db)


@router.get("/timeline", response_model=TimelineStats)
def stats_timeline(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
) -> TimelineStats:
    """入库时间趋势统计。可选 year 参数按年筛选。"""
    return stats_service.get_timeline(db, year=year)
