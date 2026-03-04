from fastapi import APIRouter
from app import db

router = APIRouter(prefix="/api")


@router.get("/pnl")
async def pnl_data():
    return db.get_pnl_series()


@router.get("/calibration")
async def calibration_data():
    cal, brier = db.get_calibration_data()
    return {"calibration": cal, "brier": brier}


@router.get("/stats")
async def stats():
    return db.get_summary_stats()


@router.get("/ratings/{league}")
async def ratings(league: str):
    return db.get_elo_ratings(league)
