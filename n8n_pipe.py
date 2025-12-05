"""
title: n8n Pipe Function
author: Cole Medin
author_url: https://www.youtube.com/@ColeMedin
version: 0.2.0

This module defines a Pipe class that utilizes N8N for an Agent
Supports both standard JSON and streaming NDJSON responses
"""

from typing import Optional, Callable, Awaitable
from pydantic import BaseModel, Field
import os
import time
import json
import requests


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
            default="https://n8n.[your domain].com/webhook/[your webhook URL]"
        )
        n8n_bearer_token: str = Field(default="...")
        input_field: str = Field(default="chatInput")
        response_field: str = Field(default="output")
        emit_interval: float = Field(
            default=2.0, description="Interval in seconds between status emissions"
        )
        enable_status_indicator: bool = Field(
            default=True, description="Enable or disable status indicator emissions"
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "n8n_pipe"
        self.name = "N8N Pipe"
        self.valves = self.Valves()
        self.last_emit_time = 0

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

    def parse_n8n_response(self, response: requests.Response) -> str:
        """
        Parse n8n response handling both formats:
        1. Standard JSON: {"output": "..."}
        2. Streaming NDJSON: {"type":"begin"...}\n{"type":"item","content":"..."}\n{"type":"end"...}
        """
        response_text = response.text.strip()

        # Try standard JSON first
        try:
            data = response.json()
            # Standard format with configured response field
            if isinstance(data, dict) and self.valves.response_field in data:
                return data[self.valves.response_field]
            # Direct string response
            if isinstance(data, str):
                return data
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
                return "".join(content_parts)

        # Fallback: return raw text
        return response_text

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Awaitable[None]] = None,
        __event_call__: Callable[[dict], Awaitable[dict]] = None,
    ) -> Optional[dict]:
        await self.emit_status(
            __event_emitter__, "info", "Calling N8N Workflow...", False
        )
        chat_id, _ = extract_event_info(__event_emitter__)
        messages = body.get("messages", [])

        # Verify a message is available
        if messages:
            question = messages[-1]["content"]
            try:
                # Invoke N8N workflow
                headers = {
                    "Authorization": f"Bearer {self.valves.n8n_bearer_token}",
                    "Content-Type": "application/json",
                }
                payload = {"sessionId": f"{chat_id}"}
                payload[self.valves.input_field] = question

                response = requests.post(
                    self.valves.n8n_url, json=payload, headers=headers
                )

                if response.status_code == 200:
                    n8n_response = self.parse_n8n_response(response)
                else:
                    raise Exception(f"Error: {response.status_code} - {response.text}")

                # Set assistant message with chain reply
                body["messages"].append({"role": "assistant", "content": n8n_response})

            except Exception as e:
                await self.emit_status(
                    __event_emitter__,
                    "error",
                    f"Error during sequence execution: {str(e)}",
                    True,
                )
                return {"error": str(e)}
        # If no message is available alert user
        else:
            await self.emit_status(
                __event_emitter__,
                "error",
                "No messages found in the request body",
                True,
            )
            body["messages"].append(
                {
                    "role": "assistant",
                    "content": "No messages found in the request body",
                }
            )
            return "No messages found in the request body"

        await self.emit_status(__event_emitter__, "info", "Complete", True)
        return n8n_response
