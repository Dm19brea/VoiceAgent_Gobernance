"""Vapi-backed adapter for the outbound ``AssistantDirectory`` port.

Owns all HTTP concerns against the Vapi API. Fails closed: any failure to
positively confirm the assistant exists (timeout, transport error, non-404
error status) raises ``AssistantDirectoryUnavailable`` rather than returning
``True``. The application layer never imports ``httpx`` directly; it depends
only on the ``AssistantDirectory`` Protocol.
"""

import httpx

from src.application.ports.assistant_directory import AssistantDirectoryUnavailable
from src.infrastructure.config import Settings
from src.infrastructure.config import settings as default_settings

_ASSISTANT_PATH = "/assistant/{assistant_id}"


class VapiAssistantDirectory:
    """Implements ``AssistantDirectory`` against the Vapi assistants API."""

    def __init__(
        self,
        config: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = config or default_settings
        self._client = client

    async def exists(self, assistant_id: str) -> bool:
        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(base_url=self._settings.vapi_base_url)
        try:
            try:
                response = await client.get(
                    _ASSISTANT_PATH.format(assistant_id=assistant_id),
                    headers={"Authorization": self._settings.vapi_api_key},
                    timeout=self._settings.vapi_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise AssistantDirectoryUnavailable(
                    f"Vapi assistant verification failed for {assistant_id}"
                ) from exc

            if response.status_code == 200:
                return True
            if response.status_code == 404:
                return False
            raise AssistantDirectoryUnavailable(
                f"Vapi returned status {response.status_code} for assistant {assistant_id}"
            )
        finally:
            if owns_client:
                await client.aclose()
