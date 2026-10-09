from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router
from .generation_routes import router as generation_router
from .review_routes import router as review_router
from .analytics_routes import router as analytics_router
from .shot_specs import router as shot_specs_router

app = FastAPI(title="TakeOne AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Workspace-Id", "X-User-Id", "Idempotency-Key"],
)
app.include_router(router)
app.include_router(generation_router)
app.include_router(review_router)
app.include_router(analytics_router)
app.include_router(shot_specs_router)


@app.get("/health")
def health():
    return {"status": "ok"}
