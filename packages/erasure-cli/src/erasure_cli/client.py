"""HTTP client for the erasure-executor API."""
from __future__ import annotations

from typing import Any

import httpx


class ExecutorClient:
    """Thin wrapper around the erasure-executor REST API."""

    def __init__(self, base_url: str, auth_token: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {auth_token}"}
        self._timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.request(method, self._url(path), headers=self._headers, **kwargs)
            resp.raise_for_status()
            return resp

    # -- Profiles -------------------------------------------------------------

    def create_profile(self, label: str, profile_data: dict[str, Any]) -> dict:
        resp = self._request("POST", "/v1/profiles", json={"label": label, "profile": profile_data})
        return resp.json()

    def get_profile(self, profile_id: str) -> dict:
        return self._request("GET", f"/v1/profiles/{profile_id}").json()

    def delete_profile(self, profile_id: str) -> None:
        self._request("DELETE", f"/v1/profiles/{profile_id}")

    # -- Brokers / Status -----------------------------------------------------

    def list_brokers(self) -> list[dict]:
        return self._request("GET", "/v1/brokers").json()

    def list_broker_listings(self, broker_id: str) -> list[dict]:
        return self._request("GET", f"/v1/brokers/{broker_id}/listings").json()

    # -- Runs -----------------------------------------------------------------

    def start_run(self, plan_id: str, params: dict[str, Any] | None = None) -> dict:
        body: dict[str, Any] = {"plan_id": plan_id}
        if params:
            body["params"] = params
        return self._request("POST", "/v1/runs", json=body).json()

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/v1/runs/{run_id}").json()

    # -- Schedule -------------------------------------------------------------

    def list_schedule(self) -> list[dict]:
        return self._request("GET", "/v1/schedule").json()

    def trigger_schedule(self, schedule_id: str) -> None:
        self._request("POST", f"/v1/schedule/{schedule_id}/trigger")

    # -- Human Queue ----------------------------------------------------------

    def list_queue(self) -> list[dict]:
        return self._request("GET", "/v1/queue").json()

    def complete_queue_item(self, queue_id: str, notes: str | None = None) -> None:
        self._request("POST", f"/v1/queue/{queue_id}/complete", json={"notes": notes})

    # -- Health ---------------------------------------------------------------

    def healthz(self) -> dict:
        return self._request("GET", "/healthz").json()

    def check_plan(self, plan_id: str) -> dict:
        return self._request("POST", f"/v1/plans/{plan_id}/check").json()
