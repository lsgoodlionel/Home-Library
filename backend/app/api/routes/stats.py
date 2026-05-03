from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stats import DistributionItem, ReadingStats, StatsOverview, TimelinePoint
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverview)
def overview(db: Annotated[Session, Depends(get_db)]) -> StatsOverview:
    return stats_service.get_overview(db)


@router.get("/categories", response_model=list[DistributionItem])
def categories(db: Annotated[Session, Depends(get_db)]) -> list[DistributionItem]:
    return stats_service.get_category_distribution(db)


@router.get("/locations", response_model=list[DistributionItem])
def locations(db: Annotated[Session, Depends(get_db)]) -> list[DistributionItem]:
    return stats_service.get_location_distribution(db)


@router.get("/reading", response_model=ReadingStats)
def reading(db: Annotated[Session, Depends(get_db)]) -> ReadingStats:
    return stats_service.get_reading_stats(db)


@router.get("/timeline", response_model=list[TimelinePoint])
def timeline(
    db: Annotated[Session, Depends(get_db)],
    year: Annotated[int | None, Query(ge=1900, le=9999)] = None,
) -> list[TimelinePoint]:
    return stats_service.get_timeline(db, year=year)
