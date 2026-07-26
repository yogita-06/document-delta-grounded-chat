from pathlib import Path
import json
import os
import tempfile
import uuid

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
)
from pydantic import BaseModel

from src.canonical.models import DeltaReport
from src.config.settings import settings
from src.delta.engine import compute_delta
from src.orchestration.service import (
    METRICS,
    Trace,
    chat,
    ingest,
    metrics_text,
    reports,
)
from src.storage.store import Store


settings.ensure_dirs()
store = Store()

app = FastAPI(
    title="Document Delta & Grounded Chat",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {
        "status": "ok",
        "message": "Document Delta & Grounded Chat API",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "ocr_configured": bool(settings.tesseract_cmd),
    }


@app.exception_handler(Exception)
async def handle_errors(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request

    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        message = str(exc.detail)
    else:
        status_code = 500
        message = str(exc)

    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": (
                "HTTP_ERROR"
                if status_code < 500
                else type(exc).__name__.upper()
            ),
            "message": message,
            "trace_id": str(uuid.uuid4()),
            "detail": (
                None
                if status_code < 500
                else "See server trace"
            ),
        },
    )


@app.get(
    "/metrics",
    response_class=PlainTextResponse,
)
def metrics() -> str:
    return metrics_text()


@app.post("/api/v1/documents")
async def upload_document(
    file: UploadFile = File(...),
    revision: str = Form(...),
    pid: str | None = Form(None),
) -> dict:
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in {".pdf", ".dwg"}:
        raise HTTPException(
            status_code=415,
            detail="Only PDF and DWG are supported",
        )

    max_upload_bytes = (
        settings.max_upload_mb
        * 1024
        * 1024
    )

    content = await file.read(max_upload_bytes + 1)

    if len(content) > max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Upload exceeds "
                f"{settings.max_upload_mb} MB limit"
            ),
        )

    if (
        suffix == ".pdf"
        and not content.startswith(b"%PDF")
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "File extension is PDF, "
                "but the content is not a PDF"
            ),
        )

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    ) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)

    try:
        new_pid = store.save_upload(
            temporary_path,
            revision,
            pid,
        )
    finally:
        temporary_path.unlink(missing_ok=True)

    document = store.document(new_pid)

    if not document:
        raise HTTPException(
            status_code=500,
            detail="Uploaded document could not be saved",
        )

    return document


@app.get("/api/v1/documents/{pid}")
def get_document(pid: str) -> dict:
    document = store.document(pid)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return document


class CompareRequest(BaseModel):
    base_pid: str
    revised_pid: str


@app.post("/api/v1/comparisons")
def create_comparison(
    request: CompareRequest,
) -> dict:
    base_document = store.document(
        request.base_pid
    )
    revised_document = store.document(
        request.revised_pid
    )

    if not base_document or not revised_document:
        raise HTTPException(
            status_code=404,
            detail="Base or revised PID not found",
        )

    trace = Trace("comparison.run")

    comparison_id = store.create_comparison(
        request.base_pid,
        request.revised_pid,
        trace.trace_id,
    )

    try:
        with trace.span(
            "request.validate",
            {"comparison_id": comparison_id},
        ):
            pass

        with trace.span(
            "pid.resolve.base",
            {"pid": request.base_pid},
        ):
            pass

        with trace.span(
            "pid.resolve.revised",
            {"pid": request.revised_pid},
        ):
            pass

        with trace.span(
            "format.detect.base",
            {
                "suffix": Path(
                    base_document["path"]
                ).suffix
            },
        ):
            pass

        with trace.span(
            "format.detect.revised",
            {
                "suffix": Path(
                    revised_document["path"]
                ).suffix
            },
        ):
            pass

        with trace.span("ingest.base"):
            (
                base_canonical,
                base_canonical_path,
            ) = ingest(base_document)

            store.set_canonical(
                base_document["pid"],
                base_canonical_path,
            )

        with trace.span("ingest.revised"):
            (
                revised_canonical,
                revised_canonical_path,
            ) = ingest(revised_document)

            store.set_canonical(
                revised_document["pid"],
                revised_canonical_path,
            )

        with trace.span(
            "page.align",
            {
                "base_pages":
                    base_canonical.page_count,
                "revised_pages":
                    revised_canonical.page_count,
            },
        ):
            pass

        with trace.span("candidate.generate"):
            pass

        with trace.span("element.assign"):
            result = compute_delta(
                comparison_id,
                base_canonical,
                revised_canonical,
                settings.element_alignment_min_score,
                settings.move_distance_threshold,
            )

        with trace.span(
            "delta.classify",
            {
                "meaningful":
                    len(result.deltas)
            },
        ):
            pass

        with trace.span(
            "delta.significance",
            {
                "ignored":
                    len(result.ignored_deltas)
            },
        ):
            pass

        with trace.span("report.generate"):
            report_file_path = reports(result)

        with trace.span(
            "index.build",
            {
                "implementation":
                    "structured in-memory"
            },
        ):
            pass

        store.finish(
            comparison_id,
            report_file_path,
        )

        comparison = store.comparison(
            comparison_id
        )

        if not comparison:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Comparison result could not "
                    "be saved"
                ),
            )

        METRICS["comparisons"] += 1
        METRICS["deltas"] += len(
            result.deltas
        )

        return {
            **comparison,
            "summary": result.metadata["summary"],
        }

    except Exception:
        METRICS["failures"] += 1
        raise

    finally:
        trace.save()


@app.get("/api/v1/comparisons/{comparison_id}")
def get_comparison(
    comparison_id: str,
) -> dict:
    comparison = store.comparison(
        comparison_id
    )

    if not comparison:
        raise HTTPException(
            status_code=404,
            detail="Comparison not found",
        )

    return comparison


def get_report_path(
    comparison_id: str,
    extension: str,
) -> Path:
    path = (
        settings.data_dir
        / "reports"
        / f"{comparison_id}.{extension}"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Report not found",
        )

    return path


@app.get(
    "/api/v1/comparisons/"
    "{comparison_id}/delta"
)
def get_delta_report(
    comparison_id: str,
) -> dict:
    report_path = get_report_path(
        comparison_id,
        "json",
    )

    return json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )


@app.get(
    "/api/v1/comparisons/"
    "{comparison_id}/report/{kind}"
)
def download_report(
    comparison_id: str,
    kind: str,
) -> FileResponse:
    report_extensions = {
        "json": "json",
        "markdown": "md",
        "html": "html",
    }

    extension = report_extensions.get(kind)

    if not extension:
        raise HTTPException(
            status_code=404,
            detail="Unknown report type",
        )

    report_path = get_report_path(
        comparison_id,
        extension,
    )

    return FileResponse(
        path=report_path,
        filename=(
            f"{comparison_id}.{extension}"
        ),
    )


class QuestionRequest(BaseModel):
    question: str


@app.post(
    "/api/v1/comparisons/"
    "{comparison_id}/chat"
)
def ask_question(
    comparison_id: str,
    request: QuestionRequest,
) -> dict:
    report_path = get_report_path(
        comparison_id,
        "json",
    )

    delta_report = (
        DeltaReport.model_validate_json(
            report_path.read_text(
                encoding="utf-8"
            )
        )
    )

    return chat(
        delta_report,
        request.question,
    )


@app.get(
    "/api/v1/comparisons/"
    "{comparison_id}/markup/{side}"
)
def get_markup(
    comparison_id: str,
    side: str,
) -> None:
    del comparison_id
    del side

    raise HTTPException(
        status_code=501,
        detail=(
            "Visual PDF markup is "
            "intentionally scoped out"
        ),
    )


@app.get("/api/v1/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    trace_path = (
        settings.data_dir
        / "traces"
        / f"{trace_id}.json"
    )

    if not trace_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Trace not found",
        )

    return json.loads(
        trace_path.read_text(
            encoding="utf-8"
        )
    )


@app.post("/api/v1/evaluations/run")
def run_evaluation() -> dict:
    from eval.run_eval import run

    return run()


@app.get("/api/v1/evaluations/latest")
def get_latest_evaluation() -> dict:
    evaluation_path = (
        settings.data_dir
        / "reports"
        / "evaluation.json"
    )

    if not evaluation_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Evaluation report not found",
        )

    return json.loads(
        evaluation_path.read_text(
            encoding="utf-8"
        )
    )