import sqlite3
from typing import Optional, Dict, Any, List
import datetime

class JobDatabase:
    """
    SQLite-backed job application tracker for deduplication and logging.
    """
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the jobs table if it doesn't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    job_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def is_job_applied(self, job_id: str) -> bool:
        """
        Check if a job has already been successfully applied to.
        Returns True if a record exists with status 'APPLIED'.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM jobs WHERE job_id = ? AND status = 'APPLIED'",
                (job_id,)
            )
            return cursor.fetchone() is not None

    def record_job(
        self,
        job_id: str,
        title: str,
        company: str,
        job_url: str,
        status: str,
        notes: Optional[str] = None
    ) -> None:
        """
        Record or update a job application status in the database.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO jobs (job_id, title, company, job_url, status, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    job_url = excluded.job_url,
                    status = excluded.status,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
            """, (job_id, title, company, job_url, status, notes, now))
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve details for a specific job."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded jobs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]


if __name__ == "__main__":
    # Self-test / Verification
    db = JobDatabase("test_jobs.db")
    
    print("Testing record_job APPLIED...")
    db.record_job(
        job_id="dice-12345",
        title="Software Engineer",
        company="Acme Corp",
        job_url="https://dice.com/job/12345",
        status="APPLIED"
    )
    
    assert db.is_job_applied("dice-12345") is True, "Expected is_job_applied to be True"
    assert db.is_job_applied("dice-99999") is False, "Expected is_job_applied to be False"
    
    print("Testing record_job FAILED...")
    db.record_job(
        job_id="dice-67890",
        title="Frontend Developer",
        company="TechInc",
        job_url="https://dice.com/job/67890",
        status="FAILED",
        notes="Form required additional questions"
    )
    assert db.is_job_applied("dice-67890") is False, "FAILED status should not count as APPLIED"
    
    print("All JobDatabase self-tests passed!")
