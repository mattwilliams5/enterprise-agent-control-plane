"""Trusted entry point for StoreGuard AI investigations.

Development integration: credentials and store scope are supplied
by trusted backend code, never by an LLM or a browser request.
"""

from dataclasses import dataclass
from typing import Callable

from identity.execution_gate import execute_investigation, ExecutionDenied, _record, _event


AGENT_NAME = "sre-troubleshooting-agent"


@dataclass(frozen=True)
class InvestigationRequest:
    store_id: str
    incident_id: str
    health: object
    elapsed_minutes: int
    rto_minutes: int
    question: str


class InvestigationController:
    def __init__(
        self,
        *,
        vault_addr: str,
        credential_provider: Callable[[], tuple[str, str]],
        allowed_store_ids: frozenset[str],
        investigation_runner: Callable,
        db_path: str = "data/storeguard_security_audit.sqlite3",
    ):
        self._vault_addr = vault_addr
        self._credential_provider = credential_provider
        self._allowed_store_ids = frozenset(allowed_store_ids)
        self._investigation_runner = investigation_runner
        self._db_path = db_path

    def investigate(self, request: InvestigationRequest):
        if not isinstance(request, InvestigationRequest):
            raise TypeError("Expected InvestigationRequest")

        if not request.store_id or not request.incident_id:
            raise ValueError("Store and incident identifiers are required")

        # Fail closed before requesting credentials for invalid scope.
        if request.store_id not in self._allowed_store_ids:
            import uuid

            run_id = str(uuid.uuid4())
            _record(
                self._db_path,
                _event(
                    run_id,
                    AGENT_NAME,
                    request.store_id,
                    request.incident_id,
                    "DENIED",
                    "Store outside trusted controller scope",
                ),
            )
            raise ExecutionDenied("Store outside trusted controller scope")

        role_id, secret_id = self._credential_provider()

        return execute_investigation(
            agent_name=AGENT_NAME,
            store_id=request.store_id,
            incident_id=request.incident_id,
            vault_addr=self._vault_addr,
            role_id=role_id,
            secret_id=secret_id,
            allowed_store_ids=self._allowed_store_ids,
            investigation=lambda: self._investigation_runner(
                store_id=request.store_id,
                health=request.health,
                elapsed_minutes=request.elapsed_minutes,
                rto_minutes=request.rto_minutes,
                question=request.question,
            ),
            db_path=self._db_path,
        )
