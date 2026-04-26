from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import shutil
import uuid
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

app = FastAPI(title="Event Notification Sender")
templates = Jinja2Templates(directory="frontend/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    host: str
    port: int
    username: str
    password: str
    from_email: str


class MappingRequest(BaseModel):
    name_col: str
    email_col: str


class TemplateRequest(BaseModel):
    subject: str
    body: str


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
        response.set_cookie("session_id", sid, httponly=True)
    return response


@app.post("/api/configure-smtp")
async def configure_smtp(config: SMTPConfig, request: Request):
    sid = get_session_id(request)
    data = store.get(sid)
    if data is None:
        data = {}
        store._data[sid] = data

    config_dict = config.dict()
    data["smtp"] = config_dict

    # Save to database for persistence
    database.save_smtp_config(config_dict)

    response = JSONResponse({"status": "SMTP configuration saved"})
    response.set_cookie("session_id", sid, httponly=True)
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
    response.set_cookie("session_id", sid, httponly=True)
    return response


@app.post("/api/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    request: Request = None
):
    # Validate file extension
    if not file.filename:
        raise HTTPException(
            status_code=400, detail="No file provided"
        )

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx or .xls files allowed"
        )

    # Check file size (max 10MB)
    file_content = await file.read()
    if len(file_content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 10MB"
        )

    # Save file
    file_path = os.path.join(UPLOAD_DIR, f"temp_{file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {str(e)}"
        )

    try:
        columns, rows = read_excel(file_path)
    except Exception as e:
        # Clean up file on error
        if os.path.exists(file_path):
            os.remove(file_path)
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

    if len(rows) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Too many rows. Maximum is 1000 recipients per batch"
        )

    # Auto-guess columns
    name_col = guess_name_column(columns)
    email_col = guess_email_column(columns)
    if email_col and not validate_email_column(rows, email_col):
        email_col = None

    # Store in session
    data = get_session_data(request)
    data["columns"] = columns
    data["rows"] = rows
    data["name_col"] = name_col
    data["email_col"] = email_col
    data["file_path"] = file_path

    return {
        "columns": columns,
        "guessed_name": name_col,
        "guessed_email": email_col,
        "total_rows": len(rows),
        "preview_rows": rows[:5],
    }


@app.post("/api/set-mapping")
async def set_mapping(mapping: MappingRequest, request: Request):
    data = get_session_data(request)
    columns = data.get("columns", [])
    if mapping.name_col not in columns or mapping.email_col not in columns:
        raise HTTPException(
            status_code=400,
            detail="Column not found in Excel"
        )
    data["name_col"] = mapping.name_col
    data["email_col"] = mapping.email_col
    return {"status": "Mapping saved"}


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

# Made with Bob
