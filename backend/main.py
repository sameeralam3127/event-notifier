from fastapi import FastAPI, Request, File, UploadFile, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import shutil
from .session_store import store
from .excel_parser import (
    read_excel,
    guess_name_column,
    guess_email_column,
    validate_email_column,
)
from .smtp_handler import send_test_email, send_bulk_emails
from .mail_merger import preview_emails

app = FastAPI(title="Event Notification Sender")
templates = Jinja2Templates(directory="frontend/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    response = templates.TemplateResponse("index.html", {"request": request})
    # Set session cookie if not present
    if not request.cookies.get("session_id"):
        sid = store.create_session()
        response.set_cookie("session_id", sid, httponly=True)
    return response


@app.post("/api/configure-smtp")
async def configure_smtp(config: SMTPConfig, request: Request):
    data = get_session_data(request)
    data["smtp"] = config.dict()
    return {"status": "SMTP configuration saved"}


@app.post("/api/test-smtp")
async def test_smtp(request: Request):
    data = get_session_data(request)
    smtp = data.get("smtp")
    if not smtp:
        raise HTTPException(status_code=400, detail="SMTP not configured")
    result = send_test_email(smtp, smtp["from_email"])  # test to self
    return result


@app.post("/api/upload-excel")
async def upload_excel(file: UploadFile = File(...), request: Request = None):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx or .xls files allowed")
    # Save file
    file_path = os.path.join(UPLOAD_DIR, f"temp_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        columns, rows = read_excel(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading Excel: {str(e)}")

    # Auto-guess columns
    name_col = guess_name_column(columns)
    email_col = guess_email_column(columns)
    if email_col and not validate_email_column(rows, email_col):
        email_col = None  # Auto-guess not confident

    # Store in session
    data = get_session_data(request)
    data["columns"] = columns
    data["rows"] = rows
    data["name_col"] = name_col
    data["email_col"] = email_col

    return {
        "columns": columns,
        "guessed_name": name_col,
        "guessed_email": email_col,
        "total_rows": len(rows),
        "preview_rows": rows[:5],  # first 5 rows for display
    }


@app.post("/api/set-mapping")
async def set_mapping(mapping: MappingRequest, request: Request):
    data = get_session_data(request)
    columns = data.get("columns", [])
    if mapping.name_col not in columns or mapping.email_col not in columns:
        raise HTTPException(status_code=400, detail="Column not found in Excel")
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
        raise HTTPException(status_code=400, detail="Excel and mapping required")
    # Prepare row dictionaries with 'name' and 'email' keys
    prepared_rows = []
    for r in rows:
        prepared_rows.append(
            {
                "name": r.get(name_col, ""),
                "email": r.get(email_col, ""),
                **r,  # include all columns for advanced placeholders
            }
        )
    previews = preview_emails(prepared_rows, template.subject, template.body, count=5)
    return previews


@app.post("/api/send-emails")
async def send_emails(template: TemplateRequest, request: Request):
    data = get_session_data(request)
    smtp = data.get("smtp")
    if not smtp:
        raise HTTPException(status_code=400, detail="SMTP not configured")

    rows = data.get("rows", [])
    name_col = data.get("name_col")
    email_col = data.get("email_col")
    if not rows or not email_col:
        raise HTTPException(status_code=400, detail="Excel and mapping required")

    # Prepare recipients
    recipients = []
    for r in rows:
        recipients.append(
            {"name": r.get(name_col, ""), "email": r.get(email_col, ""), **r}
        )

    try:
        results = send_bulk_emails(smtp, recipients, template.subject, template.body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    # Store results in session for later retrieval
    data["last_results"] = results
    return {
        "total": len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results,
    }
