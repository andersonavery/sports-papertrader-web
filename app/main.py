from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routes import pages, api, actions


app = FastAPI(title="Paper Trader Dashboard")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(actions.router)


def run():
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
