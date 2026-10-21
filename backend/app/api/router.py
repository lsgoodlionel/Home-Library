from fastapi import APIRouter

from app.api.routes import (
    ai,
    ai_providers,
    auth,
    books,
    borrow,
    categories,
    import_export,
    locations,
    reading,
    search,
    stats,
    system,
    system_ai_settings,
    users,
)

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(system_ai_settings.router)
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(ai.router)
api_router.include_router(ai_providers.router)
api_router.include_router(import_export.router)
api_router.include_router(borrow.router)
api_router.include_router(books.router)
api_router.include_router(reading.router)
api_router.include_router(categories.router)
api_router.include_router(locations.router)
api_router.include_router(search.router)
api_router.include_router(stats.router)
