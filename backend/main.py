from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field, field_validator
import os
import uuid
import logging
from pathlib import Path
from .session_store import store
from .excel_parser import (
    read_excel,
    guess_name_column,
    guess_email_column,
    validate_email_column,
)
from .smtp_handler import send_test_email, send_bulk_emails, validate_smtp_config
from .mail_merger import preview_emails
from . import database

logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "production").lower()
SECURE_COOKIES = os.getenv("EVENT_NOTIFIER_SECURE_COOKIES", "false").lower() == "true"
UPLOAD_DIR = Path(os.getenv("EVENT_NOTIFIER_UPLOAD_DIR", "uploads"))
MAX_UPLOAD_MB = int(os.getenv("EVENT_NOTIFIER_MAX_UPLOAD_MB", "10"))
MAX_RECIPIENTS = int(os.getenv("EVENT_NOTIFIER_MAX_RECIPIENTS", "1000"))
MAX_TEMPLATE_CHARS = int(os.getenv("EVENT_NOTIFIER_MAX_TEMPLATE_CHARS", "50000"))

app = FastAPI(
    title="Event Notification Sender",
    docs_url="/docs" if APP_ENV != "production" else None,
    redoc_url="/redoc" if APP_ENV != "production" else None,
)
templates = Jinja2Templates(directory="frontend/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if APP_ENV == "production":
        response.headers["Cache-Control"] = "no-store"
    return response


# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    database.init_database()


# --- Session dependency ---
def get_session_id(request: Request):
    sid = request.cookies.get("session_id")
    if not sid or not store.get(sid):
        sid = store.create_session()
    return sid


def get_session_data(request: Request):
    sid = get_session_id(request)
    data = store.get(sid)
    if data is None:
        data = {}
        store._data[sid] = data
    return data


# --- API models ---
class SMTPConfig(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=2048)
    from_email: EmailStr

    @field_validator("host", "username", "password", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return str(value).strip().replace("\xa0", " ")


class MappingRequest(BaseModel):
    name_col: str = Field(min_length=1, max_length=255)
    email_col: str = Field(min_length=1, max_length=255)


class TemplateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=MAX_TEMPLATE_CHARS)


def set_session_cookie(response: JSONResponse | HTMLResponse, sid: str):
    response.set_cookie(
        "session_id",
        sid,
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIES,
        max_age=12 * 60 * 60,
    )


# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )
    # Set session cookie if not present
    if not request.cookies.get("session_id"):
        sid = store.create_session()
        set_session_cookie(response, sid)
    return response


@app.post("/api/configure-smtp")
async def configure_smtp(config: SMTPConfig, request: Request):
    sid = get_session_id(request)
    data = store.get(sid)
    if data is None:
        data = {}
        store._data[sid] = data

    config_dict = config.model_dump()
    error = validate_smtp_config(config_dict)
    if error:
        raise HTTPException(status_code=400, detail=error)

    data["smtp"] = config_dict

    # Save to database for persistence
    if not database.save_smtp_config(config_dict):
        raise HTTPException(status_code=500, detail="Failed to save SMTP configuration")

    response = JSONResponse({"status": "SMTP configuration saved"})
    set_session_cookie(response, sid)
    return response


@app.get("/api/get-smtp-config")
async def get_smtp_config(request: Request):
    """Get saved SMTP configuration from database."""
    config = database.get_smtp_config()
    if config:
        # Mask password for security
        config["password"] = "********"
        return config
    return {"message": "No SMTP configuration found"}


@app.post("/api/test-smtp")
async def test_smtp(request: Request):
    sid = get_session_id(request)
    data = store.get(sid)

    # Try to get SMTP from session or database
    smtp = None
    if data:
        smtp = data.get("smtp")

    if not smtp:
        smtp = database.get_smtp_config()

    if not smtp:
        raise HTTPException(
            status_code=400,
            detail="SMTP not configured. Please save configuration first."
        )

    # Validate SMTP config
    error = validate_smtp_config(smtp)
    if error:
        raise HTTPException(status_code=400, detail=error)

    result = send_test_email(smtp, smtp["from_email"])
    response = JSONResponse(result)
    set_session_cookie(response, sid)
    return response


@app.post("/api/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    request: Request = None
):
    sid = get_session_id(request)
    # Validate file extension
    if not file.filename:
        raise HTTPException(
            status_code=400, detail="No file provided"
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx or .xls files allowed"
        )

    # Check file size (max 10MB)
    file_content = await file.read()
    if len(file_content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_MB}MB"
        )

    # Save file
    file_path = UPLOAD_DIR / f"{sid}_{uuid.uuid4().hex}{suffix}"
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
    except Exception as e:
        logger.exception("Failed to save uploaded file")
        raise HTTPException(
            status_code=500,
            detail="Failed to save file"
        )

    try:
        columns, rows = read_excel(file_path)
    except Exception as e:
        # Clean up file on error
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Error reading Excel: {str(e)}"
        )

    # Validate data
    if not columns:
        raise HTTPException(
            status_code=400,
            detail="Excel file has no columns"
        )

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="Excel file has no data rows"
        )

    if len(rows) > MAX_RECIPIENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many rows. Maximum is {MAX_RECIPIENTS} recipients per batch"
        )

    # Auto-guess columns
    name_col = guess_name_column(columns)
    email_col = guess_email_column(columns)
    if email_col and not validate_email_column(rows, email_col):
        email_col = None

    # Store in session
    data = store.get(sid)
    if data is None:
        data = {}
        store._data[sid] = data
    
    data["columns"] = columns
    data["rows"] = rows
    data["name_col"] = name_col
    data["email_col"] = email_col
    data["file_path"] = str(file_path)

    response = JSONResponse({
        "columns": columns,
        "guessed_name": name_col,
        "guessed_email": email_col,
        "total_rows": len(rows),
        "preview_rows": rows[:5],
    })
    set_session_cookie(response, sid)
    return response


@app.post("/api/set-mapping")
async def set_mapping(mapping: MappingRequest, request: Request):
    sid = get_session_id(request)
    data = store.get(sid)
    
    if not data:
        raise HTTPException(
            status_code=400,
            detail="Session expired. Please upload Excel file again."
        )
    
    columns = data.get("columns", [])
    
    if not columns:
        raise HTTPException(
            status_code=400,
            detail="No Excel file uploaded. Please upload a file first."
        )
    
    if mapping.name_col not in columns:
        available = ', '.join(columns)
        raise HTTPException(
            status_code=400,
            detail=(f"Name column '{mapping.name_col}' not found in Excel. "
                    f"Available columns: {available}")
        )
    
    if mapping.email_col not in columns:
        available = ', '.join(columns)
        raise HTTPException(
            status_code=400,
            detail=(f"Email column '{mapping.email_col}' not found in Excel. "
                    f"Available columns: {available}")
        )
    
    data["name_col"] = mapping.name_col
    data["email_col"] = mapping.email_col
    
    response = JSONResponse({"status": "Mapping saved"})
    set_session_cookie(response, sid)
    return response


@app.post("/api/preview")
async def preview(template: TemplateRequest, request: Request):
    data = get_session_data(request)
    rows = data.get("rows", [])
    name_col = data.get("name_col")
    email_col = data.get("email_col")
    
    if not rows or not email_col:
        raise HTTPException(
            status_code=400,
            detail="Excel and mapping required"
        )
    
    # Validate template
    if not template.subject.strip():
        raise HTTPException(
            status_code=400,
            detail="Subject cannot be empty"
        )
    
    if not template.body.strip():
        raise HTTPException(
            status_code=400,
            detail="Body cannot be empty"
        )
    
    # Prepare row dictionaries with 'name' and 'email' keys
    prepared_rows = []
    for r in rows:
        prepared_rows.append(
            {
                "name": r.get(name_col, ""),
                "email": r.get(email_col, ""),
                **r,
            }
        )
    
    previews = preview_emails(
        prepared_rows,
        template.subject,
        template.body,
        count=5
    )
    return previews


@app.post("/api/send-emails")
async def send_emails(template: TemplateRequest, request: Request):
    data = get_session_data(request)
    smtp = data.get("smtp")
    if not smtp:
        # Try to load from database
        smtp = database.get_smtp_config()
        if not smtp:
            raise HTTPException(
                status_code=400, detail="SMTP not configured"
            )
        data["smtp"] = smtp

    rows = data.get("rows", [])
    name_col = data.get("name_col")
    email_col = data.get("email_col")
    
    if not rows or not email_col:
        raise HTTPException(
            status_code=400,
            detail="Excel and mapping required"
        )
    
    # Validate template
    if not template.subject.strip():
        raise HTTPException(
            status_code=400,
            detail="Subject cannot be empty"
        )
    
    if not template.body.strip():
        raise HTTPException(
            status_code=400,
            detail="Body cannot be empty"
        )

    # Prepare recipients
    recipients = []
    for r in rows:
        recipients.append(
            {"name": r.get(name_col, ""), "email": r.get(email_col, ""), **r}
        )

    # Create batch ID for tracking
    batch_id = str(uuid.uuid4())
    database.create_batch(batch_id, len(recipients))

    try:
        results = send_bulk_emails(
            smtp, recipients, template.subject, template.body
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    # Save email history to database
    successful = 0
    failed = 0
    for result in results:
        status = result.get("status", "failed")
        if status == "success":
            successful += 1
        else:
            failed += 1

        database.save_email_history(
            recipient_email=result.get("email", ""),
            recipient_name=result.get("name", ""),
            subject=template.subject,
            status=status,
            error_message=result.get("error"),
            batch_id=batch_id
        )

    # Update batch statistics
    database.update_batch_stats(batch_id, successful, failed)

    # Store results in session for later retrieval
    data["last_results"] = results
    return {
        "total": len(results),
        "success": successful,
        "failed": failed,
        "batch_id": batch_id,
        "results": results,
    }


@app.get("/api/email-history")
async def get_email_history(
    limit: int = 100,
    offset: int = 0,
    batch_id: str | None = None
):
    """Get email send history with pagination."""
    history = database.get_email_history(limit, offset, batch_id)
    return {"history": history, "count": len(history)}


@app.get("/api/batch-history")
async def get_batch_history(limit: int = 50):
    """Get batch send history."""
    batches = database.get_batch_history(limit)
    return {"batches": batches, "count": len(batches)}


@app.get("/api/statistics")
async def get_statistics():
    """Get overall email sending statistics."""
    stats = database.get_statistics()
    return stats


@app.get("/health")
async def health():
    return {"status": "ok"}

# Made with Bob
