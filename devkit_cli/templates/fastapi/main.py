"""{{project_name}} — FastAPI application entry point."""

from fastapi import FastAPI
from app.routers import health

app = FastAPI(title="{{project_name}}", version="0.1.0")

app.include_router(health.router)


@app.get("/")
async def root():
    return {"message": "Welcome to {{project_name}}"}
