import uuid
from unittest import TestCase
from unittest.mock import Mock, patch

from app.scan.router import _dispatch_scan
from workers.pipeline import ACTIVE_SCANS


class HostedScanDispatchTests(TestCase):
    def test_postgres_scan_uses_single_executor_instead_of_web_background_thread(self):
        background_tasks = Mock()
        project_id = uuid.uuid4()
        job_id = uuid.uuid4()
        future = Mock()
        future.add_done_callback.side_effect = lambda callback: callback(future)

        try:
            with (
                patch("app.scan.router.settings.DATABASE_URL", "postgresql+asyncpg://host/db"),
                patch("app.scan.router._LOCAL_SCAN_EXECUTOR.submit", return_value=future) as submit,
            ):
                task_id = _dispatch_scan(background_tasks, project_id, job_id, False)

            self.assertEqual(task_id, f"local-bounded-{job_id}")
            submit.assert_called_once()
            background_tasks.add_task.assert_not_called()
        finally:
            ACTIVE_SCANS.discard(job_id)
