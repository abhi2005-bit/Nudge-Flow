"""Agent runtime bootstrap and initialization layer.

This module is the single point where the agent runtime is assembled and
validated.  It is deliberately separate from individual workflow functions so
that the assembled runtime can be tested in isolation and so that FastAPI's
lifespan hook has one clear place to call.

Design constraints (see requirements):
- No external API calls during bootstrap.
- WhatsApp sending is disabled by default; bootstrap never enables it.
- Bootstrap never executes pending runs or sends messages.
- Every piece of agent functionality is assembled here and injected into
  workflows via FastAPI dependency injection, rather than relying on scattered
  module-level initialization.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request

from nudgeflow.config import Settings, settings as _default_settings
from nudgeflow.services.agent.tools import (
    MessagingTool,
    MockMessagingTool,
    WhatsAppCloudMessagingTool,
)

import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class BootstrapError(RuntimeError):
    """Raised when the agent runtime cannot be assembled safely."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ToolContractError(BootstrapError):
    """Raised when a registered tool violates the MessagingTool contract."""


# ---------------------------------------------------------------------------
# Runtime object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentRuntime:
    """Immutable snapshot of every dependency the agent workflow needs."""

    tool_registry: dict[str, MessagingTool]
    whatsapp_enabled: bool
    settings: Settings

    def get_tool(self, name: str) -> MessagingTool | None:
        return self.tool_registry.get(name)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_tool_contract(tool: object, registry_key: str) -> None:
    """Verify that *tool* satisfies the MessagingTool structural protocol."""
    if not hasattr(tool, "name") or not isinstance(tool.name, str) or not tool.name:
        raise ToolContractError(
            f"Tool registered under '{registry_key}' has no valid 'name' attribute."
        )
    if tool.name != registry_key:
        raise ToolContractError(
            f"Tool registered under '{registry_key}' reports name '{tool.name}'; "
            "the registry key and tool.name must match."
        )
    if not callable(getattr(tool, "send", None)):
        raise ToolContractError(
            f"Tool '{registry_key}' does not implement the required 'send' method."
        )


def _validate_config(cfg: Settings) -> None:
    """Assert that required configuration fields are safe for runtime use.

    No external requests are made; only config values are inspected.
    """
    if cfg.whatsapp_enabled:
        token = cfg.whatsapp_access_token.get_secret_value().strip()
        phone_id = (cfg.whatsapp_phone_number_id or "").strip()
        api_version = (cfg.whatsapp_api_version or "").strip()
        if not token:
            raise BootstrapError(
                "NUDGEFLOW_WHATSAPP_ENABLED is true but "
                "NUDGEFLOW_WHATSAPP_ACCESS_TOKEN is not set."
            )
        if not phone_id or not phone_id.isdigit():
            raise BootstrapError(
                "NUDGEFLOW_WHATSAPP_ENABLED is true but "
                "NUDGEFLOW_WHATSAPP_PHONE_NUMBER_ID is missing or not a digit string."
            )
        if not re.match(r"^v[0-9]+\.[0-9]+$", api_version):
            raise BootstrapError(
                f"NUDGEFLOW_WHATSAPP_API_VERSION '{api_version}' is invalid; expected format 'vXX.X'."
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_agent_runtime(cfg: Settings | None = None) -> AgentRuntime:
    """Construct and validate the agent runtime from *cfg*.

    Parameters
    ----------
    cfg:
        The settings object to use.  Defaults to the module-level singleton.
        Tests pass an isolated `Settings` instance.

    Raises
    ------
    BootstrapError
        If configuration is invalid or a required tool contract is broken.
    ToolContractError
        Subclass of `BootstrapError` for tool-specific violations.
    """
    resolved_cfg: Settings = cfg if cfg is not None else _default_settings

    # Step 1 - validate configuration (no external calls).
    _validate_config(resolved_cfg)

    # Step 2 - assemble tool registry with fresh instances for isolation.
    registry: dict[str, MessagingTool] = {
        MockMessagingTool.name: MockMessagingTool(),
    }
    if resolved_cfg.whatsapp_enabled:
        wa_tool = WhatsAppCloudMessagingTool()
        registry[wa_tool.name] = wa_tool

    # Step 3 - validate every tool in the registry.
    for key, tool in registry.items():
        _validate_tool_contract(tool, key)

    # Step 4 - log a safe summary (no credentials).
    tool_names = sorted(registry)
    logger.info(
        "Agent runtime initialised: whatsapp_enabled=%s, tools=%s, environment=%s",
        resolved_cfg.whatsapp_enabled,
        tool_names,
        resolved_cfg.environment,
    )

    return AgentRuntime(
        tool_registry=registry,
        whatsapp_enabled=resolved_cfg.whatsapp_enabled,
        settings=resolved_cfg,
    )


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def agent_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager for the agent runtime.

    Stores a validated AgentRuntime on app.state.agent_runtime at startup.
    Removes it on shutdown.  If build_agent_runtime() raises BootstrapError
    the exception propagates and the server will not start.

    Bootstrap never executes pending runs or sends messages.
    """
    logger.info("NudgeFlow agent bootstrap starting ...")
    runtime = build_agent_runtime()
    app.state.agent_runtime = runtime
    logger.info("NudgeFlow agent runtime ready.")
    try:
        yield
    finally:
        logger.info("NudgeFlow agent runtime shutting down.")
        if hasattr(app.state, "agent_runtime"):
            del app.state.agent_runtime


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_agent_runtime(request: Request) -> AgentRuntime:
    """FastAPI dependency that retrieves the runtime from app.state.

    Routes that need the runtime should declare it with Depends::

        from fastapi import Depends
        from nudgeflow.bootstrap import AgentRuntime, get_agent_runtime

        @router.post("/example")
        def example(runtime: AgentRuntime = Depends(get_agent_runtime)):
            tool = runtime.get_tool("mock_messaging")
            ...

    Raises ``RuntimeError`` if the lifespan has not run.
    """
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise RuntimeError(
            "AgentRuntime is not initialised. "
            "Ensure the FastAPI application uses agent_lifespan."
        )
    return runtime
