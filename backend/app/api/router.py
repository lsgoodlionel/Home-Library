from fastapi import APIRouter

from app.api.routes import ai, auth, books, borrow, categories, import_export, locations, reading, search, system, users

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(ai.router)
api_router.include_router(import_export.router)
api_router.include_router(borrow.router)
api_router.include_router(books.router)
api_router.include_router(reading.router)
api_router.include_router(categories.router)
api_router.include_router(locations.router)
api_router.include_router(search.router)
