import unittest
import uuid
from contextlib import nullcontext
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.exc import OperationalError

from workers.pipeline import ACTIVE_SCANS, _scan_is_active
from app.main import app, health, lifespan


class _StatusSession:
    def __init__(self, row=None, error=None):
        self.no_autoflush = nullcontext()
        self._row = row
        self._error = error
        self.closed = False

    def execute(self, _statement):
        if self._error:
            raise self._error
        result = Mock()
        result.first.return_value = self._row
        return result

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class PipelineDatabaseResilienceTests(unittest.TestCase):
    def test_status_check_reconnects_instead_of_reusing_dead_session(self):
        project_id = uuid.uuid4()
        job_id = uuid.uuid4()
        dropped = OperationalError("SELECT status", {}, Exception("SSL connection closed"))
        dead = _StatusSession(error=dropped)
        recovered = _StatusSession(row=("running", "running", datetime.utcnow()))
        stale_session = Mock()

        with (
            patch("workers.pipeline.get_db", side_effect=[dead, recovered]) as get_db,
            patch("workers.pipeline._retry_database_connection") as retry,
        ):
            self.assertTrue(_scan_is_active(stale_session, project_id, job_id))

        self.assertEqual(get_db.call_count, 2)
        retry.assert_called_once()
        stale_session.execute.assert_not_called()
        self.assertTrue(dead.closed)
        self.assertTrue(recovered.closed)

    def test_temporary_database_outage_does_not_abort_active_worker(self):
        project_id = uuid.uuid4()
        job_id = uuid.uuid4()
        dropped = OperationalError("SELECT status", {}, Exception("SSL connection closed"))
        sessions = [_StatusSession(error=dropped) for _ in range(5)]
        ACTIVE_SCANS.add(job_id)
        self.addCleanup(ACTIVE_SCANS.discard, job_id)

        with (
            patch("workers.pipeline.get_db", side_effect=sessions),
            patch("workers.pipeline._retry_database_connection"),
        ):
            self.assertTrue(_scan_is_active(Mock(), project_id, job_id))

        self.assertTrue(all(session.closed for session in sessions))


class ApiStartupResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_outage_does_not_block_api_startup_or_health(self):
        with patch("app.main._initialize_database", new=AsyncMock(side_effect=RuntimeError("database locked"))):
            async with lifespan(app):
                result = await health()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["database"], "reconnecting")


if __name__ == "__main__":
    unittest.main()
