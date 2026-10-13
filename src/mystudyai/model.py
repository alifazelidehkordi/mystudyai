"""Small dependency-free client for the OpenAI Responses API.

This is used only after a learner explicitly approves sending selected note
excerpts with the --send-notes CLI flag.
"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelError(RuntimeError):
    """Safe, actionable error without exposing private lecture text."""


class OpenAIResponsesClient:
    ENDPOINT = "https://api.openai.com/v1/responses"

    def __init__(self, model: str = "gpt-4.1-mini", api_key: str | None = None,
                 timeout: int = 90):
        self.model = model
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.timeout = timeout
        if not self.api_key:
            raise ModelError("Missing OPENAI_API_KEY. Set an API key before using the tutor.")

    def complete(self, instructions: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "instructions": instructions,
            "input": prompt,
            "store": False,
        }, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.ENDPOINT,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            raise ModelError(f"OpenAI API returned HTTP {exc.code}. Check your model and API account.") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise ModelError("Could not reach the OpenAI API. Check your connection.") from None
        except (ValueError, TypeError) as exc:
            raise ModelError("The OpenAI API returned an invalid response.") from None

        if result.get("status") != "completed":
            raise ModelError(f"Model response was not completed (status: {result.get('status', 'unknown')}).")
        parts = []
        for item in result.get("output", []):
            if item.get("type") == "message":
                for piece in item.get("content", []):
                    if piece.get("type") == "output_text" and isinstance(piece.get("text"), str):
                        parts.append(piece["text"])
        answer = "\n".join(parts).strip()
        if not answer:
            raise ModelError("The model did not return any readable text.")
        return answer
