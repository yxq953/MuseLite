"""Scheduled tasks stay separate from conversations until they run."""

import tempfile
import time
import unittest
from pathlib import Path

from muselite_py.storage import Store


class ScheduledTaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.folder.name) / "tasks.sqlite3")

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def test_create_toggle_and_trigger_one_time_task(self):
        when = int(time.time() * 1000) + 60000
        task = self.store.create_scheduled_task("提醒", "检查邮件", when, False)
        self.assertEqual(self.store.sessions(), [])
        self.assertEqual(task["prompt"], "检查邮件")
        self.store.set_scheduled_task_enabled(task["id"], False)
        self.assertEqual(self.store.scheduled_task(task["id"])["enabled"], 0)
        self.store.set_scheduled_task_enabled(task["id"], True)
        self.store.mark_scheduled_task_triggered(task["id"])
        self.assertEqual(self.store.scheduled_task(task["id"])["enabled"], 0)
        self.store.delete_scheduled_task(task["id"])
        self.assertIsNone(self.store.scheduled_task(task["id"]))

    def test_daily_task_stays_enabled_after_trigger(self):
        task = self.store.create_scheduled_task("日报", "总结今天", 0, True)
        self.store.mark_scheduled_task_triggered(task["id"])
        self.assertEqual(self.store.scheduled_task(task["id"])["enabled"], 1)


if __name__ == "__main__":
    unittest.main()
