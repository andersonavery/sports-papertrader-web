from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app import services

router = APIRouter(prefix="/actions")
templates = Jinja2Templates(directory="app/templates")


@router.post("/scan", response_class=HTMLResponse)
async def scan(request: Request):
    success, output = services.run_scan()
    return templates.TemplateResponse("partials/action_result.html", {
        "request": request,
        "action": "Scan",
        "success": success,
        "output": output,
    })


@router.post("/resolve", response_class=HTMLResponse)
async def resolve(request: Request):
    success, output = services.run_resolve()
    return templates.TemplateResponse("partials/action_result.html", {
        "request": request,
        "action": "Resolve",
        "success": success,
        "output": output,
    })


@router.post("/update-elo", response_class=HTMLResponse)
async def update_elo(request: Request):
    success, output = services.run_update_elo()
    return templates.TemplateResponse("partials/action_result.html", {
        "request": request,
        "action": "Update Elo",
        "success": success,
        "output": output,
    })
