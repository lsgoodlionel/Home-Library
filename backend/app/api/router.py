from fastapi import APIRouter

from app.api.routes import books, system

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(books.router)
