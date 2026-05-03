from fastapi import APIRouter

from app.api.routes import books, categories, locations, system

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(books.router)
api_router.include_router(categories.router)
api_router.include_router(locations.router)
