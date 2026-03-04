from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app import db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = db.get_summary_stats()
    trades = db.get_trades(limit=30)
    nba_ratings = db.get_elo_ratings("nba")[:15]
    nhl_ratings = db.get_elo_ratings("nhl")[:15]
    calibration, brier = db.get_calibration_data()
    sport_breakdown = db.get_sport_breakdown()
    risk = db.get_risk_metrics()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "trades": trades,
        "nba_ratings": nba_ratings,
        "nhl_ratings": nhl_ratings,
        "calibration": calibration,
        "brier": brier,
        "sport_breakdown": sport_breakdown,
        "risk": risk,
    })


@router.get("/partials/trades", response_class=HTMLResponse)
async def trades_partial(request: Request):
    trades = db.get_trades(limit=30)
    stats = db.get_summary_stats()
    return templates.TemplateResponse("partials/trades_table.html", {
        "request": request,
        "trades": trades,
        "stats": stats,
    })


@router.get("/partials/performance", response_class=HTMLResponse)
async def performance_partial(request: Request):
    stats = db.get_summary_stats()
    calibration, brier = db.get_calibration_data()
    sport_breakdown = db.get_sport_breakdown()
    risk = db.get_risk_metrics()
    return templates.TemplateResponse("partials/performance.html", {
        "request": request,
        "stats": stats,
        "calibration": calibration,
        "brier": brier,
        "sport_breakdown": sport_breakdown,
        "risk": risk,
    })
