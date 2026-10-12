import hmac, json, time, uuid, threading, joblib
from functools import lru_cache
import pandas as pd
from fastapi import FastAPI, Depends, Header, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from ..config import FEATURES, DATA, RUNTIME, ADMIN_TOKEN, SCHEMA_VERSION
from ..storage import db, sql, models, model, state, audit
from ..data.ingest import simulate, save_dataset, load_dataset
from ..training.train import train
from ..registry.promote import gate, promote, rollback
from ..monitoring.drift import monitor
from ..monitoring.performance import performance
from .schemas import Reading, Prepare, DatasetChoice, ModelChoice, MonitorRequest, Label

app = FastAPI(title="ModelForge / Predictive Maintenance", version="0.1.0")
COUNTER = Counter(
    "modelforge_predictions_total", "Scored sensor readings", ["model_id"]
)
LATENCY = Histogram(
    "modelforge_prediction_seconds",
    "Prediction request computation duration",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
_pipeline_lock = threading.Lock()
_job = {"status": "idle", "error": None}


def admin(x_admin_token: str | None = Header(default=None)):
    if (
        not ADMIN_TOKEN
        or not x_admin_token
        or not hmac.compare_digest(ADMIN_TOKEN, x_admin_token)
    ):
        raise HTTPException(403, "An administrator token is required")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "champion": state("champion") or None,
        "schema": SCHEMA_VERSION,
        "pipeline": _job,
        "storage": "postgresql"
        if __import__("modelforge.storage", fromlist=["PG"]).PG
        else "sqlite",
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/overview")
def overview():
    allmodels = models()
    champion = state("champion")
    with db() as conn:
        readings = conn.execute(
            "SELECT model_id,risk,predicted,label,latency,created FROM predictions ORDER BY created DESC LIMIT 500"
        ).fetchall()
        count = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        reports = conn.execute(
            "SELECT kind,payload FROM reports ORDER BY created DESC LIMIT 20"
        ).fetchall()
        events = conn.execute(
            "SELECT action,payload,created FROM audit ORDER BY created DESC LIMIT 20"
        ).fetchall()
    times = sorted(r[4] for r in readings)
    return {
        "champion": champion or None,
        "previous": state("previous") or None,
        "models": [{**m, "gate": gate(m)} for m in allmodels],
        "predictions": count,
        "recent_predictions": [
            dict(
                model_id=r[0],
                risk=r[1],
                predicted=r[2],
                label=r[3],
                latency_ms=r[4],
                created=r[5],
            )
            for r in readings[:80]
        ],
        "p95_ms": times[int((len(times) - 1) * 0.95)] if times else None,
        "datasets": [json.loads(p.read_text()) for p in DATA.glob("*.json")],
        "reports": [{"kind": kind, **json.loads(payload)} for kind, payload in reports],
        "audit": [
            {"action": a, "payload": json.loads(p), "created": t} for a, p, t in events
        ],
        "pipeline": _job,
        "label_performance": performance(champion) if champion else None,
    }


@app.post("/api/datasets/prepare", dependencies=[Depends(admin)])
def prepare(req: Prepare):
    return save_dataset(
        simulate(req.rows, req.seed, req.shifted),
        {
            "generator": "simulator-v1",
            "seed": req.seed,
            "shifted": req.shifted,
            "rows": req.rows,
        },
    )


@app.post("/api/datasets/approve", dependencies=[Depends(admin)])
def approve_dataset(req: DatasetChoice):
    try:
        load_dataset(req.dataset_id)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    with db() as conn:
        sql(
            conn,
            "UPDATE state SET value=? WHERE key=?",
            (req.dataset_id, "approved_dataset"),
        )
        audit("dataset_approved", {"dataset": req.dataset_id}, conn)
    return {"approved": req.dataset_id}


def execute_training(dataset_id):
    try:
        _job.update(status="running", error=None)
        train(dataset_id)
        _job.update(status="completed", error=None)
    except Exception as error:
        import logging

        logging.exception("Training failed")
        _job.update(status="failed", error=str(error))
    finally:
        _pipeline_lock.release()


@app.post("/api/train", dependencies=[Depends(admin)], status_code=202)
def training(background: BackgroundTasks):
    dataset = state("approved_dataset")
    if not dataset:
        raise HTTPException(409, "Approve a dataset before training")
    if not _pipeline_lock.acquire(blocking=False):
        raise HTTPException(409, "A training pipeline is already running")
    _job.update(status="queued", error=None)
    background.add_task(execute_training, dataset)
    return {"status": "queued", "dataset": dataset, "auto_promote": False}


@app.post("/api/models/promote", dependencies=[Depends(admin)])
def promotion(req: ModelChoice):
    try:
        result = promote(req.model_id, approved=True)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not result["passed"]:
        raise HTTPException(409, result)
    return result


@app.post("/api/models/rollback", dependencies=[Depends(admin)])
def model_rollback():
    try:
        return rollback(approved=True)
    except ValueError as e:
        raise HTTPException(409, str(e))


@lru_cache(maxsize=8)
def load_model(mid):
    return joblib.load(model(mid)["artifact"])


@app.post("/api/predict")
def predict(req: Reading):
    start = time.perf_counter()
    mid = state("champion")
    if not mid:
        raise HTTPException(503, "No approved champion model is deployed")
    metadata = model(mid)
    estimator = load_model(mid)
    reading = req.model_dump()
    risk = float(
        estimator.predict_proba(pd.DataFrame([reading], columns=FEATURES))[0, 1]
    )
    predicted = int(risk >= metadata["threshold"])
    pid = str(uuid.uuid4())
    latency = (time.perf_counter() - start) * 1000
    with db() as conn:
        sql(
            conn,
            "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?)",
            (
                pid,
                mid,
                json.dumps(reading),
                risk,
                predicted,
                None,
                latency,
                time.time(),
            ),
        )
    COUNTER.labels(model_id=mid).inc()
    LATENCY.observe((time.perf_counter() - start))
    return {
        "prediction_id": pid,
        "risk": risk,
        "failure_predicted": bool(predicted),
        "threshold": metadata["threshold"],
        "model_id": mid,
        "registry_version": metadata["registry_version"],
        "schema": SCHEMA_VERSION,
        "latency_ms": round(latency, 3),
    }


@app.post("/api/labels", dependencies=[Depends(admin)])
def label(req: Label):
    with db() as conn:
        row = sql(
            conn, "SELECT label FROM predictions WHERE id=?", (req.prediction_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Prediction not found")
        if row[0] is not None:
            raise HTTPException(409, "This prediction already has a ground-truth label")
        sql(
            conn,
            "UPDATE predictions SET label=? WHERE id=?",
            (req.failure, req.prediction_id),
        )
        audit(
            "label_received",
            {"prediction": req.prediction_id, "failure": req.failure},
            conn,
        )
    return {"recorded": True}


@app.post("/api/monitor", dependencies=[Depends(admin)])
def monitoring(req: MonitorRequest):
    try:
        return monitor(req.reference_id, req.current_id)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/reports/{rid}/html")
def report_html(rid: str):
    try:
        uuid.UUID(rid)
    except ValueError:
        raise HTTPException(404, "Report not found")
    path = RUNTIME / "reports" / (rid + ".html")
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(path, media_type="text/html")
