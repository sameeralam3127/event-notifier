import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("/app/data/event_notifier.db")


def get_db_connection():
    """Get a database connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database with required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # SMTP Configuration table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS smtp_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            from_email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Email History table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_email TEXT NOT NULL,
            recipient_name TEXT,
            subject TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            batch_id TEXT
        )
    """)

    # Batch History table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT UNIQUE NOT NULL,
            total_recipients INTEGER NOT NULL,
            successful INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")


def save_smtp_config(config: Dict) -> bool:
    """Save or update SMTP configuration."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if config exists
        cursor.execute("SELECT id FROM smtp_config LIMIT 1")
        existing = cursor.fetchone()

        if existing:
            # Update existing config
            cursor.execute("""
                UPDATE smtp_config 
                SET host=?, port=?, username=?, password=?, from_email=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                config["host"],
                config["port"],
                config["username"],
                config["password"],
                config["from_email"],
                existing["id"]
            ))
        else:
            # Insert new config
            cursor.execute("""
                INSERT INTO smtp_config 
                (host, port, username, password, from_email)
                VALUES (?, ?, ?, ?, ?)
            """, (
                config["host"],
                config["port"],
                config["username"],
                config["password"],
                config["from_email"]
            ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save SMTP config: {e}")
        return False


def get_smtp_config() -> Optional[Dict]:
    """Retrieve the saved SMTP configuration."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT host, port, username, password, from_email 
            FROM smtp_config 
            ORDER BY updated_at DESC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "host": row["host"],
                "port": row["port"],
                "username": row["username"],
                "password": row["password"],
                "from_email": row["from_email"]
            }
        return None
    except Exception as e:
        logger.error(f"Failed to get SMTP config: {e}")
        return None


def save_email_history(
    recipient_email: str,
    recipient_name: str,
    subject: str,
    status: str,
    error_message: Optional[str] = None,
    batch_id: Optional[str] = None
) -> bool:
    """Save email send history."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO email_history 
            (recipient_email, recipient_name, subject, status, 
             error_message, batch_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            recipient_email,
            recipient_name,
            subject,
            status,
            error_message,
            batch_id
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save email history: {e}")
        return False


def create_batch(batch_id: str, total_recipients: int) -> bool:
    """Create a new batch record."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO batch_history (batch_id, total_recipients)
            VALUES (?, ?)
        """, (batch_id, total_recipients))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to create batch: {e}")
        return False


def update_batch_stats(batch_id: str, successful: int, failed: int) -> bool:
    """Update batch statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE batch_history 
            SET successful=?, failed=?, completed_at=CURRENT_TIMESTAMP
            WHERE batch_id=?
        """, (successful, failed, batch_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to update batch stats: {e}")
        return False


def get_email_history(
    limit: int = 100,
    offset: int = 0,
    batch_id: Optional[str] = None
) -> List[Dict]:
    """Get email send history with pagination."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if batch_id:
            cursor.execute("""
                SELECT * FROM email_history 
                WHERE batch_id=?
                ORDER BY sent_at DESC 
                LIMIT ? OFFSET ?
            """, (batch_id, limit, offset))
        else:
            cursor.execute("""
                SELECT * FROM email_history 
                ORDER BY sent_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get email history: {e}")
        return []


def get_batch_history(limit: int = 50) -> List[Dict]:
    """Get batch send history."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM batch_history 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get batch history: {e}")
        return []


def get_statistics() -> Dict:
    """Get overall statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Total emails sent
        cursor.execute(
            "SELECT COUNT(*) as total FROM email_history"
        )
        total = cursor.fetchone()["total"]

        # Successful emails
        cursor.execute(
            "SELECT COUNT(*) as successful FROM email_history "
            "WHERE status='success'"
        )
        successful = cursor.fetchone()["successful"]

        # Failed emails
        cursor.execute(
            "SELECT COUNT(*) as failed FROM email_history "
            "WHERE status='failed'"
        )
        failed = cursor.fetchone()["failed"]

        # Total batches
        cursor.execute(
            "SELECT COUNT(*) as batches FROM batch_history"
        )
        batches = cursor.fetchone()["batches"]

        conn.close()

        return {
            "total_emails": total,
            "successful_emails": successful,
            "failed_emails": failed,
            "total_batches": batches,
            "success_rate": round(
                (successful / total * 100) if total > 0 else 0, 2
            )
        }
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        return {
            "total_emails": 0,
            "successful_emails": 0,
            "failed_emails": 0,
            "total_batches": 0,
            "success_rate": 0
        }

# Made with Bob
