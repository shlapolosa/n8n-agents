"""
title: n8n TOGAF Pipe Function
author: Cole Medin
author_url: https://www.youtube.com/@ColeMedin
version: 0.5.0

This module defines a Pipe class that utilizes N8N for an Agent
Supports both standard JSON and streaming NDJSON responses
Now includes polling-based status updates for async workflows
v0.5.0: Uses message streaming for live status updates in chat
"""

from typing import Optional, Callable, Awaitable
from pydantic import BaseModel, Field
import os
import time
import json
import asyncio
import aiohttp


def extract_event_info(event_emitter) -> tuple[Optional[str], Optional[str]]:
    if not event_emitter or not event_emitter.__closure__:
        return None, None
    for cell in event_emitter.__closure__:
        if isinstance(request_info := cell.cell_contents, dict):
            chat_id = request_info.get("chat_id")
            message_id = request_info.get("message_id")
            return chat_id, message_id
    return None, None


class Pipe:
    class Valves(BaseModel):
        n8n_url: str = Field(
            default="https://n8n.socrates-hlapolosa.org/webhook/togaf-architect-v2",
            description="n8n webhook URL for TOGAF workflow"
        )
        n8n_status_url: str = Field(
            default="https://n8n.socrates-hlapolosa.org/webhook/togaf-status",
            description="Status polling endpoint URL for async workflows"
        )
        n8n_bearer_token: str = Field(
            default="testAuth",
            description="Bearer token for n8n authentication"
        )
        input_field: str = Field(default="chatInput")
        response_field: str = Field(default="output")
        emit_interval: float = Field(
            default=1.0, description="Interval in seconds between status emissions"
        )
        enable_status_indicator: bool = Field(
            default=True, description="Enable or disable status indicator emissions"
        )
        poll_interval: float = Field(
            default=5.0, description="Interval in seconds between status polls"
        )
        max_poll_time: float = Field(
            default=600.0, description="Maximum polling duration in seconds (10 min default)"
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "togaf_pipe"
        self.name = "TOGAF Architect"
        self.valves = self.Valves()
        self.last_emit_time = 0
        self.streamed_messages = []  # Track streamed status messages

    async def emit_message(
        self,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        content: str,
    ):
        """Emit a message that streams into the chat response."""
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {"content": content},
                }
            )

    async def emit_status(
        self,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        level: str,
        message: str,
        done: bool,
    ):
        current_time = time.time()
        if (
            __event_emitter__
            and self.valves.enable_status_indicator
            and (
                current_time - self.last_emit_time >= self.valves.emit_interval or done
            )
        ):
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "status": "complete" if done else "in_progress",
                        "level": level,
                        "description": message,
                        "done": done,
                    },
                }
            )
            self.last_emit_time = current_time

    def parse_response_text(self, response_text: str) -> tuple[str, Optional[str]]:
        """
        Parse n8n response handling both formats:
        1. Standard JSON: {"output": "..."} or {"executionId": "...", ...}
        2. Streaming NDJSON: {"type":"begin"...}\n{"type":"item","content":"..."}\n{"type":"end"...}

        Returns: (content, executionId) - executionId may be None for sync responses
        """
        response_text = response_text.strip()
        execution_id = None

        # Try standard JSON first
        try:
            data = json.loads(response_text)
            # Check for executionId (polling mode)
            if isinstance(data, dict):
                execution_id = data.get("executionId")
                # Standard format with configured response field
                if self.valves.response_field in data:
                    return data[self.valves.response_field], execution_id
                # If executionId present, return initial message
                if execution_id:
                    return data.get("message", "Workflow started..."), execution_id
            # Direct string response
            if isinstance(data, str):
                return data, None
        except json.JSONDecodeError:
            pass

        # Handle NDJSON streaming format
        if "\n" in response_text or response_text.startswith('{"type":'):
            content_parts = []
            for line in response_text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("type")

                    # Check for executionId in any event
                    if event.get("executionId"):
                        execution_id = event.get("executionId")

                    if event_type == "item":
                        # Streaming content chunks
                        content = event.get("content", "")
                        if content:
                            content_parts.append(content)
                    elif event_type == "message":
                        # Alternative message format
                        content = event.get("content", "") or event.get("data", "")
                        if content:
                            content_parts.append(content)
                except json.JSONDecodeError:
                    # Not JSON, might be plain text chunk
                    content_parts.append(line)

            if content_parts:
                return "".join(content_parts), execution_id

        # Fallback: return raw text
        return response_text, execution_id

    async def poll_for_status(
        self,
        session: aiohttp.ClientSession,
        execution_id: str,
        headers: dict,
        __event_emitter__: Callable[[dict], Awaitable[None]],
    ) -> str:
        """Poll the status endpoint until workflow completes or times out.

        Uses message streaming to show live status updates in the chat.
        """
        start_time = time.time()
        last_message = ""
        poll_count = 0
        self.streamed_messages = []  # Reset for this execution

        # Stream initial status into chat
        await self.emit_message(
            __event_emitter__,
            f"🚀 **TOGAF Workflow Started**\n\n_Execution ID: {execution_id[:20]}..._\n\n---\n\n"
        )

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.valves.max_poll_time:
                await self.emit_message(
                    __event_emitter__,
                    f"\n\n⏱️ **Workflow timed out** after {int(elapsed)}s. It may still be running in the background.\n"
                )
                return ""  # Return empty since we already streamed the message

            poll_count += 1

            try:
                status_url = f"{self.valves.n8n_status_url}?executionId={execution_id}"
                async with session.get(status_url, headers=headers) as status_response:
                    if status_response.status == 200:
                        status = await status_response.json()

                        # Check for error (execution not found means it was cleaned up or never existed)
                        if status.get("error"):
                            error_msg = status.get("error")
                            if "not found" in error_msg.lower():
                                # Execution was cleaned up or doesn't exist yet
                                # Keep polling for a bit in case it's just not created yet
                                if poll_count < 3:
                                    await asyncio.sleep(self.valves.poll_interval)
                                    continue
                                await self.emit_message(
                                    __event_emitter__,
                                    f"\n\n⚠️ **Workflow execution not found.** It may have completed or expired.\n"
                                )
                                return ""
                            await self.emit_message(
                                __event_emitter__,
                                f"\n\n❌ **Workflow error:** {error_msg}\n"
                            )
                            return ""

                        # Get current status message
                        current_message = status.get("message", "")
                        phase = status.get("phase", "unknown")
                        progress = status.get("progress", 0)

                        # Stream status update if message changed
                        if current_message and current_message != last_message:
                            last_message = current_message
                            self.streamed_messages.append(current_message)

                            # Format the status message for streaming
                            # The message from n8n already has emojis and formatting
                            formatted_message = current_message.replace("\\n", "\n")
                            await self.emit_message(
                                __event_emitter__,
                                f"{formatted_message}\n\n---\n\n"
                            )

                            # Also emit status indicator for the UI bar
                            await self.emit_status(
                                __event_emitter__,
                                "info",
                                f"Phase: {phase} | Progress: {progress}%",
                                status.get("done", False)
                            )

                        # Check if workflow completed
                        if status.get("done"):
                            result = status.get("result")
                            if result:
                                final_response = self.format_final_response(result)
                                await self.emit_message(
                                    __event_emitter__,
                                    f"\n{final_response}"
                                )
                                return ""  # Return empty since we streamed the response
                            # Return the last message as the result (already streamed)
                            return ""

                    else:
                        # Status endpoint returned non-200, log but continue
                        pass

            except aiohttp.ClientError as e:
                # Network error, continue polling
                await self.emit_message(
                    __event_emitter__,
                    f"\n⚠️ _Network issue, retrying... ({poll_count})_\n"
                )

            await asyncio.sleep(self.valves.poll_interval)

    def format_final_response(self, result: dict) -> str:
        """Format the final result as human-readable message."""
        if isinstance(result, str):
            return result

        project = result.get("projectName", "Unknown")
        repo = result.get("repositoryName", "unknown")
        artifacts = result.get("artifacts", [])
        domain = result.get("domain", "Technology")

        return f"""**TOGAF Enterprise Architecture Complete**

**Repository:** `{repo}`
**Project:** {project}
**Domain:** {domain}

**Generated Artifacts ({len(artifacts)} files):**

**ArchiMate 3.1 Models:**
- docs/architecture/compliance.archimate
- docs/architecture/business-canvas.archimate
- docs/architecture/business-architecture.archimate
- docs/architecture/technology-recommendations.archimate
- docs/architecture/application-architecture.archimate
- docs/architecture/infrastructure-architecture.archimate
- docs/architecture/implementation-plan.archimate

**Documentation:**
- docs/requirements.md
- docs/PRD.md

**Deployment:**
- docs/deployment/application.oam.yaml

[View Repository](https://github.com/shlapolosa/{repo})
"""

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Awaitable[None]] = None,
        __event_call__: Callable[[dict], Awaitable[dict]] = None,
    ) -> Optional[str]:
        await self.emit_status(
            __event_emitter__, "info", "Starting TOGAF Workflow...", False
        )
        chat_id, _ = extract_event_info(__event_emitter__)
        messages = body.get("messages", [])

        # Verify a message is available
        if not messages:
            await self.emit_status(
                __event_emitter__,
                "error",
                "No messages found in the request body",
                True,
            )
            return "No messages found in the request body"

        question = messages[-1]["content"]
        headers = {
            "Authorization": f"Bearer {self.valves.n8n_bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {"sessionId": f"{chat_id}"}
        payload[self.valves.input_field] = question

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Start the workflow
                await self.emit_status(
                    __event_emitter__, "info", "Sending request to n8n...", False
                )

                async with session.post(
                    self.valves.n8n_url, json=payload, headers=headers
                ) as response:
                    # Accept both 200 (OK) and 202 (Accepted) as valid responses
                    # 202 is used for async workflows that return immediately with executionId
                    if response.status not in (200, 202):
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")

                    response_text = await response.text()
                    n8n_response, execution_id = self.parse_response_text(response_text)

                # Step 2: If we have an execution ID and status URL, poll for updates
                if execution_id and self.valves.n8n_status_url:
                    await self.emit_status(
                        __event_emitter__,
                        "info",
                        "Workflow accepted, polling for status...",
                        False
                    )
                    # poll_for_status now streams messages directly to chat
                    # Returns empty string since all content is streamed
                    n8n_response = await self.poll_for_status(
                        session, execution_id, headers, __event_emitter__
                    )
                else:
                    # No polling - return immediate response (non-async workflow)
                    pass

                # Only append to messages if we have a response (non-streaming case)
                if n8n_response:
                    body["messages"].append({"role": "assistant", "content": n8n_response})

        except Exception as e:
            error_msg = str(e)
            await self.emit_status(
                __event_emitter__,
                "error",
                f"Error: {error_msg}",
                True,
            )
            # Stream error message to chat
            await self.emit_message(
                __event_emitter__,
                f"\n\n❌ **Error:** {error_msg}\n"
            )
            return ""  # Return empty since we streamed the error

        await self.emit_status(__event_emitter__, "info", "Complete", True)
        return n8n_response if n8n_response else ""
