from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import concurrent.futures

from script_generator import generate_script, generate_title_and_description
from pipeline import run_pipeline, PipelineResult
from youtube_uploader import get_oauth_url, exchange_code

app = FastAPI(title="Movie Generator", description="Governed AI scripting + Higgins video production")

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_jobs: dict[str, PipelineResult] = {}


class ScriptRequest(BaseModel):
    prompt: str
    title: str


class PipelineRequest(BaseModel):
    prompt: str
    title: str
    description: str = ""
    privacy: str = "private"
    upload: bool = False


@app.get("/healthz")
def health():
    return {
        "status": "ok",
        "service": "movie-generator",
        "faceless_generation": True,
        "direct_publish": False,
        "publish_boundary": "governed_external_publish_required",
    }


@app.post("/script/generate")
def create_script(req: ScriptRequest):
    """Generate a full screenplay through the governed AI scripting path."""
    script = generate_script(req.prompt, req.title)
    meta = generate_title_and_description(script, req.title)
    return {"title": req.title, "script": script, "youtube_meta": meta}


@app.post("/pipeline/start")
def start_pipeline(req: PipelineRequest, bg: BackgroundTasks):
    """Launch internal faceless production without crossing the publish boundary.

    The endpoint may generate script/video/metadata and persist the resulting
    internal job artifact. Public or private YouTube upload is a real external
    side effect and must go through Dominion's separately governed publish path.
    """
    if req.upload:
        raise HTTPException(
            status_code=409,
            detail="Direct YouTube upload is disabled. Use the Founder-gated governed external.publish path.",
        )

    import uuid
    job_id = str(uuid.uuid4())
    _jobs[job_id] = PipelineResult(title=req.title, script="", scene_count=0, status="queued")

    def _run():
        result = run_pipeline(
            prompt=req.prompt,
            title=req.title,
            description=req.description,
            privacy=req.privacy,
            upload=False,
        )
        _jobs[job_id] = result

    bg.add_task(_run)
    return {"job_id": job_id, "status": "queued", "upload": False}


@app.get("/pipeline/status/{job_id}")
def pipeline_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    r = _jobs[job_id]
    return {
        "job_id": job_id,
        "status": r.status,
        "title": r.title,
        "scene_count": r.scene_count,
        "youtube_url": r.youtube_url,
        "errors": r.errors,
    }


@app.get("/youtube/auth")
def youtube_auth():
    """Return the OAuth URL used to establish the future governed upload rail."""
    return {"auth_url": get_oauth_url()}


@app.get("/youtube/callback")
def youtube_callback(code: str):
    """OAuth2 callback — exchanges code for tokens and persists them."""
    tokens = exchange_code(code)
    return {"status": "authorized", "scope": tokens.get("scope", "")}
