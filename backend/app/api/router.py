from fastapi import APIRouter

from app.api.routes import auth, books, categories, locations, search, system, users

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(books.router)
api_router.include_router(categories.router)
api_router.include_router(locations.router)
api_router.include_router(search.router)
