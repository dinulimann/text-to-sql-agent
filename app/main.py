"""uvicorn app.main:app --reload"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agent import ask, schema_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Text-to-SQL Agent", version="1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/ask")
def api_ask(q: Question) -> dict:
    return ask(q.question.strip()).to_dict()


@app.get("/api/schema")
def api_schema() -> dict:
    text, tables = schema_context()
    return {"tables": sorted(tables), "description": text}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": config.MODEL}
