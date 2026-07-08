# test_project_workflow.py
"""Tests for the TaskFlow workflow using the OpenClaw TaskFlow skill.

This script demonstrates the typical lifecycle of a managed TaskFlow:
1. Create a managed flow
2. Run a dummy child task
3. Put the flow into a waiting state
4. Resume the flow
5. Finish the flow

The test is written with `unittest` and uses the OpenClaw runtime API. If the
runtime libraries are not available, the test will be skipped gracefully.
"""

import unittest
import os
import json

# Attempt to import the OpenClaw taskflow runtime. If unavailable, the tests will be
# marked as skipped so the file can still be committed without breaking CI.
try:
    from openclaw.runtime import tasks as taskflow
except Exception:  # pragma: no cover
    taskflow = None


@unittest.skipIf(taskflow is None, "OpenClaw taskflow runtime not available")
class TaskFlowLifecycleTest(unittest.TestCase):
    def setUp(self):
        # Create a fresh managed flow for each test case
        self.flow = taskflow.createManaged(
            controllerId="test/project-workflow",
            goal="demo workflow for unit tests",
            currentStep="init",
            stateJson={"counter": 0},
        )
        self.assertTrue(self.flow.created, msg=self.flow.reason)
        self.flow_id = self.flow.flowId
        self.revision = self.flow.revision

    def test_run_child_task(self):
        # Simulate a dummy child task (could be an ACP or sub‑agent). Here we just use a
        # placeholder payload that the runtime accepts for demonstration.
        child = taskflow.runTask(
            flowId=self.flow_id,
            runtime="agentTurn",  # using an isolated agent turn as a dummy task
            childSessionKey="agent:main:subagent:dummy",
            runId="dummy-task-1",
            task="Dummy test task",
            status="running",
            startedAt=int(os.time() * 1000) if hasattr(os, "time") else 0,
            lastEventAt=int(os.time() * 1000) if hasattr(os, "time") else 0,
        )
        self.assertTrue(child.created, msg=child.reason)

    def test_wait_and_resume(self):
        # Put the flow into a waiting state
        wait = taskflow.setWaiting(
            flowId=self.flow_id,
            expectedRevision=self.revision,
            currentStep="await_dummy",
            stateJson={"counter": 1},
            waitJson={
                "kind": "reply",
                "channel": "test",
                "threadKey": "test-thread",
            },
        )
        self.assertTrue(wait.applied, msg=wait.code)
        # Update revision after waiting
        self.revision = wait.flow.revision
        # Resume the flow
        resumed = taskflow.resume(
            flowId=self.flow_id,
            expectedRevision=self.revision,
            status="running",
            currentStep="final",
            stateJson=wait.flow.stateJson,
        )
        self.assertTrue(resumed.applied, msg=resumed.code)
        self.revision = resumed.flow.revision

    def test_finish_flow(self):
        # Directly finish the flow (no waiting) – this demonstrates the happy path.
        finished = taskflow.finish(
            flowId=self.flow_id,
            expectedRevision=self.revision,
            stateJson={"counter": 2, "status": "completed"},
        )
        self.assertTrue(finished.applied, msg=finished.code)

    def tearDown(self):
        # Attempt to clean up the flow if it still exists (e.g., if a test failed).
        try:
            taskflow.cancel(flowId=self.flow_id, expectedRevision=self.revision)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
