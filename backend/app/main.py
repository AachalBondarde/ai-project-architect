import json
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, Text, create_engine, insert, select, update

from .orchestrator import run_pipeline

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI(title="AI Project Architect")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

database_url = os.getenv("DATABASE_URL", "sqlite:///./architect.db")
if database_url.startswith("/"):
    database_url = "sqlite:///" + database_url
if database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
elif database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
metadata = MetaData()
projects = Table(
    "projects",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("idea", Text, nullable=False),
    Column("users", Integer, nullable=False),
    Column("budget", String(100), nullable=False),
    Column("timeline", String(100), nullable=False),
    Column("status", String(30), nullable=False),
    Column("blueprint", Text),
)
agent_outputs = Table(
    "agent_outputs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("section", String(80), nullable=False),
    Column("payload", Text, nullable=False),
)
agent_events = Table(
    "agent_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("payload", Text, nullable=False),
)
metadata.create_all(engine)

DEMO = "AI-Powered College Event Management Platform with event discovery, registration, QR check-in and AI recommendations"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


class ProjectInput(BaseModel):
    idea: str
    users: int = 5000
    budget: str = "Low"
    timeline: str = "3 months"


def _create(project: ProjectInput):
    with engine.begin() as connection:
        result = connection.execute(
            insert(projects).values(
                idea=project.idea,
                users=project.users,
                budget=project.budget,
                timeline=project.timeline,
                status="created",
            )
        )
        return result.inserted_primary_key[0]


def _save_event(project_id, event):
    with engine.begin() as connection:
        connection.execute(insert(agent_events).values(project_id=project_id, payload=json.dumps(event)))


def _work(project_id, project):
    with engine.begin() as connection:
        connection.execute(update(projects).where(projects.c.id == project_id).values(status="running"))
    try:
        for event in run_pipeline(project.idea, project.users, project.budget, project.timeline):
            _save_event(project_id, event)
            if event["event"] == "complete":
                blueprint = event["blueprint"]
                with engine.begin() as connection:
                    connection.execute(
                        update(projects).where(projects.c.id == project_id).values(
                            status="complete", blueprint=json.dumps(blueprint)
                        )
                    )
                    connection.execute(agent_outputs.delete().where(agent_outputs.c.project_id == project_id))
                    for section, payload in blueprint.items():
                        connection.execute(insert(agent_outputs).values(
                            project_id=project_id, section=section, payload=json.dumps(payload)
                        ))
    except Exception as error:
        _save_event(project_id, {"event": "error", "message": str(error)})
        with engine.begin() as connection:
            connection.execute(update(projects).where(projects.c.id == project_id).values(status="failed"))


def _project_row(project_id):
    with engine.connect() as connection:
        row = connection.execute(select(projects).where(projects.c.id == project_id)).mappings().first()
    if not row:
        raise HTTPException(404, "Project not found")
    return row


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/projects")
def create(project: ProjectInput):
    return {"id": _create(project)}


@app.get("/api/projects")
def list_projects():
    with engine.connect() as connection:
        rows = connection.execute(select(projects).order_by(projects.c.id.desc())).mappings().all()
    return [
        {"id": row["id"], "idea": row["idea"], "users": row["users"], "budget": row["budget"],
         "timeline": row["timeline"], "status": row["status"]}
        for row in rows
    ]


@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    row = _project_row(project_id)
    return {
        "id": row["id"], "idea": row["idea"], "users": row["users"], "budget": row["budget"],
        "timeline": row["timeline"], "status": row["status"],
        "blueprint": json.loads(row["blueprint"]) if row["blueprint"] else None,
    }


@app.post("/api/projects/demo")
def demo():
    project = ProjectInput(idea=DEMO, users=5000)
    project_id = _create(project)
    threading.Thread(target=_work, args=(project_id, project), daemon=True).start()
    return {"id": project_id}


@app.post("/api/projects/{project_id}/analyze")
def analyze(project_id: int):
    row = _project_row(project_id)
    project = ProjectInput(idea=row["idea"], users=row["users"], budget=row["budget"], timeline=row["timeline"])
    with engine.begin() as connection:
        connection.execute(delete_events_statement(project_id))
        connection.execute(update(projects).where(projects.c.id == project_id).values(status="created", blueprint=None))
    threading.Thread(target=_work, args=(project_id, project), daemon=True).start()
    return {"started": project_id}


def delete_events_statement(project_id):
    return agent_events.delete().where(agent_events.c.project_id == project_id)


@app.get("/api/projects/{project_id}/events")
def events(project_id: int):
    _project_row(project_id)

    def generate():
        last_id = 0
        while True:
            with engine.connect() as connection:
                rows = connection.execute(
                    select(agent_events.c.id, agent_events.c.payload)
                    .where(agent_events.c.project_id == project_id, agent_events.c.id > last_id)
                    .order_by(agent_events.c.id)
                ).all()
                status = connection.execute(
                    select(projects.c.status).where(projects.c.id == project_id)
                ).scalar_one_or_none()
            for event_id, payload in rows:
                last_id = event_id
                event = json.loads(payload)
                yield f"data: {json.dumps({k: v for k, v in event.items() if k != 'blueprint'})}\n\n"
                if event["event"] in ("complete", "error"):
                    return
            if status in ("complete", "failed"):
                return
            time.sleep(0.3)

    return StreamingResponse(generate(), media_type="text/event-stream")


def _blueprint(project_id):
    row = _project_row(project_id)
    if not row["blueprint"]:
        raise HTTPException(404, "Blueprint not ready")
    return json.loads(row["blueprint"])


@app.get("/api/projects/{project_id}/blueprint")
def blueprint(project_id: int):
    return _blueprint(project_id)


@app.get("/api/projects/{project_id}/review")
def review(project_id: int):
    return _blueprint(project_id)["reviewer"]


@app.get("/api/projects/{project_id}/roadmap")
def roadmap(project_id: int):
    return _blueprint(project_id)["roadmap"]


@app.get("/api/projects/{project_id}/export")
def export(project_id: int, format: str = "markdown"):
    result = _blueprint(project_id)
    if format == "json":
        return result
    markdown = f"# Project Blueprint\n\n{result['idea']}\n\n" + "".join(
        f"## {section.title()}\n```json\n{json.dumps(payload, indent=2)}\n```\n\n"
        for section, payload in result.items() if section not in ("idea", "logs")
    )
    return PlainTextResponse(markdown, media_type="text/markdown")


@app.get("/api/projects/{project_id}/{section}")
def project_section(project_id: int, section: str):
    key = {"tech-stack": "tech_stack", "apis": "api", "review": "reviewer"}.get(section, section)
    result = _blueprint(project_id)
    if key not in result:
        raise HTTPException(404, "Blueprint section not found")
    return result[key]


@app.get("/")
def index():
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return {"message": "Frontend build not found. Run `npm run build` in the frontend directory."}


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith("api"):
        raise HTTPException(404)
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    raise HTTPException(404)