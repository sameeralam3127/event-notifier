import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Dict, Optional, List, Tuple
import logging
import ssl

logger = logging.getLogger(__name__)


def validate_smtp_config(config: Dict) -> Optional[str]:
    required = ["host", "port", "username", "password", "from_email"]
    for field in required:
        if not config.get(field):
            return f"Missing SMTP field: {field}"
    if int(config["port"]) not in (25, 465, 587):
        return "Invalid port (use 25, 465, or 587)"
    return None


def send_test_email(config: Dict, to_email: str) -> Dict:
    """Send a test email and return status dict."""
    result = {"success": False, "message": ""}
    error = validate_smtp_config(config)
    if error:
        result["message"] = error
        return result

    try:
        # Sanitize credentials to remove non-ASCII characters and whitespace
        username = config["username"].strip().replace('\xa0', ' ').strip()
        password = config["password"].strip().replace('\xa0', ' ').strip()
        
        msg = MIMEMultipart()
        msg["From"] = config["from_email"]
        msg["To"] = to_email
        msg["Subject"] = "Test Email from Event Notifier"
        msg.attach(
            MIMEText("This is a test email to verify your SMTP settings.", "plain")
        )

        use_ssl = int(config["port"]) == 465
        use_tls = int(config["port"]) == 587
        context = ssl.create_default_context()

        if use_ssl:
            server = smtplib.SMTP_SSL(
                config["host"], int(config["port"]), timeout=10, context=context
            )
        else:
            server = smtplib.SMTP(config["host"], int(config["port"]), timeout=10)
            if use_tls:
                server.starttls(context=context)

        server.login(username, password)
        server.send_message(msg)
        server.quit()

        result["success"] = True
        result["message"] = "Test email sent successfully!"
    except smtplib.SMTPAuthenticationError:
        result["message"] = "Authentication failed - check username/password."
    except smtplib.SMTPConnectError:
        result["message"] = "Cannot connect to SMTP server - check host/port."
    except smtplib.SMTPException as e:
        result["message"] = f"SMTP error: {e}"
    except Exception as e:
        logger.exception("Test email failed")
        result["message"] = f"Unexpected error: {e}"

    return result


def _connect_smtp(config: Dict):
    use_ssl = int(config["port"]) == 465
    use_tls = int(config["port"]) == 587
    context = ssl.create_default_context()
    username = config["username"].strip().replace('\xa0', ' ').strip()
    password = config["password"].strip().replace('\xa0', ' ').strip()

    if use_ssl:
        server = smtplib.SMTP_SSL(
            config["host"], int(config["port"]), timeout=15, context=context
        )
    else:
        server = smtplib.SMTP(config["host"], int(config["port"]), timeout=15)
        if use_tls:
            server.starttls(context=context)
    server.login(username, password)
    return server


def _send_recipient(server, config: Dict, row: Dict, subject_template: str, body_template: str) -> Dict:
    from .mail_merger import merge

    to_email = row.get("email", "")
    to_name = row.get("name", "")

    if not to_email:
        return {
            "email": "",
            "name": to_name,
            "status": "failed",
            "error": "Missing email",
        }

    subject = merge(subject_template, row)
    body = merge(body_template, row)
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr(("", config["from_email"]))
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    server.send_message(msg)
    return {"email": to_email, "name": to_name, "status": "success", "error": None}


def _send_chunk(
    indexed_recipients: List[Tuple[int, Dict]],
    config: Dict,
    subject_template: str,
    body_template: str,
) -> List[Tuple[int, Dict]]:
    server = None
    results = []
    try:
        server = _connect_smtp(config)
    except Exception as e:
        logger.exception("SMTP connection failed")
        return [
            (
                index,
                {
                    "email": row.get("email"),
                    "name": row.get("name"),
                    "status": "failed",
                    "error": str(e),
                },
            )
            for index, row in indexed_recipients
        ]

    try:
        for index, row in indexed_recipients:
            try:
                results.append(
                    (
                        index,
                        _send_recipient(server, config, row, subject_template, body_template),
                    )
                )
            except Exception as e:
                to_email = row.get("email", "")
                logger.warning(f"Failed to send to {to_email}: {e}")
                results.append(
                    (
                        index,
                        {
                            "email": to_email,
                            "name": row.get("name", ""),
                            "status": "failed",
                            "error": str(e),
                        },
                    )
                )
    finally:
        try:
            if server:
                server.quit()
        except Exception:
            logger.debug("Failed to close SMTP connection", exc_info=True)
    return results


def send_bulk_emails(
    config: Dict,
    recipients: List[Dict],
    subject_template: str,
    body_template: str,
    max_recipients: int = 1000,
    worker_count: int = 4,
) -> List[Dict]:
    """
    Send personalised emails to all recipients.
    Returns list of dicts: {email, name, status, error}
    """
    if len(recipients) > max_recipients:
        raise ValueError(
            f"Recipient limit {max_recipients} exceeded. Please split the file."
        )

    error = validate_smtp_config(config)
    if error:
        return [
            {
                "email": r.get("email"),
                "name": r.get("name"),
                "status": "failed",
                "error": error,
            }
            for r in recipients
        ]

    worker_count = max(1, min(int(worker_count), 10, len(recipients) or 1))
    chunk_size = (len(recipients) + worker_count - 1) // worker_count
    indexed_recipients = list(enumerate(recipients))
    chunks = [
        indexed_recipients[i:i + chunk_size]
        for i in range(0, len(indexed_recipients), chunk_size)
    ]

    ordered_results = [None] * len(recipients)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_send_chunk, chunk, config, subject_template, body_template)
            for chunk in chunks
        ]
        for future in as_completed(futures):
            for index, result in future.result():
                ordered_results[index] = result

    return ordered_results
