from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel


class Capture(BaseModel):
    payload: str


captures: list[Capture] = []
app = FastAPI(title="Chapter 23 Local Capture Fixture", version="0.1.0")


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "captures": len(captures)}


@app.post("/capture", status_code=202)
def capture(item: Capture) -> dict[str, object]:
    captures.append(item)
    return {"accepted": True, "capture_number": len(captures)}


@app.delete("/captures")
def clear() -> dict[str, int]:
    count = len(captures)
    captures.clear()
    return {"cleared": count}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8024)
