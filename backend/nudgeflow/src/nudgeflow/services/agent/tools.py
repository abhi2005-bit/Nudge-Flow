"""Allow-listed tools for deterministic agent workflows."""

from typing import Protocol


class MessagingTool(Protocol):
    name: str

    def send(self, *, run_id: int, message: str) -> dict[str, object]: ...


class MockMessagingTool:
    """Return a deterministic simulated result; never performs network I/O."""

    name = "mock_messaging"

    def send(self, *, run_id: int, message: str) -> dict[str, object]:
        del message  # Do not echo customer content into audit/execution metadata.
        return {
            "provider": "mock",
            "message_id": f"mock-{run_id}",
            "run_id": run_id,
            "accepted": True,
        }


TOOL_REGISTRY: dict[str, MessagingTool] = {
    MockMessagingTool.name: MockMessagingTool(),
}
