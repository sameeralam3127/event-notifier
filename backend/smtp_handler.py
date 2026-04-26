import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


def validate_smtp_config(config: Dict) -> Optional[str]:
    required = ["host", "port", "username", "password", "from_email"]
    for field in required:
        if not config.get(field):
            return f"Missing SMTP field: {field}"
    if config["port"] not in (25, 465, 587):
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

        use_ssl = config["port"] == 465
        use_tls = config["port"] == 587

        if use_ssl:
            server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=10)
        else:
            server = smtplib.SMTP(config["host"], config["port"], timeout=10)
            if use_tls:
                server.starttls()

        server.login(username, password)
        server.send_message(msg)
        server.quit()

        result["success"] = True
        result["message"] = "Test email sent successfully!"
    except smtplib.SMTPAuthenticationError:
        result["message"] = "Authentication failed – check username/password."
    except smtplib.SMTPConnectError:
        result["message"] = "Cannot connect to SMTP server – check host/port."
    except smtplib.SMTPException as e:
        result["message"] = f"SMTP error: {e}"
    except Exception as e:
        logger.exception("Test email failed")
        result["message"] = f"Unexpected error: {e}"

    return result


def send_bulk_emails(
    config: Dict,
    recipients: List[Dict],
    subject_template: str,
    body_template: str,
    max_recipients: int = 500,
) -> List[Dict]:
    """
    Send personalised emails to all recipients.
    Returns list of dicts: {email, name, status, error}
    """
    from .mail_merger import merge

    results = []
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

    use_ssl = config["port"] == 465
    use_tls = config["port"] == 587

    # Sanitize credentials to remove non-ASCII characters and whitespace
    username = config["username"].strip().replace('\xa0', ' ').strip()
    password = config["password"].strip().replace('\xa0', ' ').strip()

    server = None
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=15)
        else:
            server = smtplib.SMTP(config["host"], config["port"], timeout=15)
            if use_tls:
                server.starttls()
        server.login(username, password)
    except Exception as e:
        logger.exception("SMTP connection failed")
        return [
            {
                "email": r.get("email"),
                "name": r.get("name"),
                "status": "failed",
                "error": str(e),
            }
            for r in recipients
        ]

    for row in recipients:
        try:
            subject = merge(subject_template, row)
            body = merge(body_template, row)
            to_email = row.get("email", "")
            to_name = row.get("name", "")

            if not to_email:
                results.append(
                    {
                        "email": "",
                        "name": to_name,
                        "status": "failed",
                        "error": "Missing email",
                    }
                )
                continue

            msg = MIMEMultipart("alternative")
            msg["From"] = config["from_email"]
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html"))

            server.send_message(msg)
            results.append(
                {"email": to_email, "name": to_name, "status": "success", "error": None}
            )
        except Exception as e:
            logger.warning(f"Failed to send to {to_email}: {e}")
            results.append(
                {
                    "email": to_email,
                    "name": to_name,
                    "status": "failed",
                    "error": str(e),
                }
            )

    try:
        server.quit()
    except:
        pass
    return results
