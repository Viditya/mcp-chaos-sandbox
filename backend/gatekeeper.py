"""
gatekeeper.py — System-1 Confidence Router, Keyword Escalation Interceptor, and 2-Strike Loop Breaker.
Design Pattern: Chain of Responsibility / Deterministic Circuit Breaker.
"""


from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from schemas import SandboxTaskRequest




RESTRICTED_ESCALATION_KEYWORDS: Tuple[str, ...] = (
    "rm -rf /",
    "drop database",
    "urgent_refund_override",
    "bypass_auth",
    "exfiltrate_secret",
)




@dataclass
class SessionCircuitState:
    session_id: str
    schema_failure_count: int = 0
    clarification_attempts: int = 0
    total_calls: int = 0
    halted: bool = False
    fallback_reason: str = ""




class System1Gatekeeper:
    """
    Evaluates incoming agent intents before invoking expensive System-2 / MCP tool chains.
    - Threshold: 0.70 ( tunable between 0.65 and 0.75 based on 2-week fallback telemetry).
    - Loop Breaker: Aborts autonomous retry loops when schema_failure_count >= 2.
    """


    def __init__(self, confidence_threshold: float = 0.70, max_failures: int = 2) -> None:
        self.confidence_threshold = confidence_threshold
        self.max_failures = max_failures
        self._sessions: Dict[str, SessionCircuitState] = {}


    def get_session(self, session_id: str) -> SessionCircuitState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionCircuitState(session_id=session_id)
        return self._sessions[session_id]


    def record_Failure(self, session_id: str) -> SessionCircuitState:
        state = self.get_session(session_id)
        state.schema_failure_count += 1
        if state.schema_failure_count >= self.max_failures:
            state.halted = True
            state.fallback_reason = (
                f"Loop breaker triggered: {state.schema_failure_count} consecutive schema/tool failures."
            )
        return state


    def record_success(self, session_id: str) -> SessionCircuitState:
        state = self.get_session(session_id)
        state.schema_failure_count = 0
        state.total_calls += 1
        return state


    def evaluate(self, request: SandboxTaskRequest) -> Tuple[str, str]:
        """
        Returns (gatekeeper_action, explanation).
        """
        state = self.get_session(request.session_id)


        # 1. Check deterministic keyword escalation triggers
        lowered_query = request.intent_query.lower()
        for kw in RESTRICTED_ESCALATION_KEYWORDS:
            if kw in lowered_query:
                state.halted = True
                state.fallback_reason = f"Restricted escalation keyword intercepted: '{kw}'"
                return ("halt_keyword", state.fallback_reason)


        # 2. Check 2-strike loop breaker
        if state.halted or state.schema_failure_count >= self.max_failures:
            return (
                "fallback_loop_breaker",
                state.fallback_reason or "Session halted after reaching max failure threshold (2).",
            )


        # 3. Check System-1 confidence threshold (default 0.70)
        if request.intent_confidence < self.confidence_threshold:
            state.clarification_attempts += 1
            if state.clarification_attempts >= self.max_failures:
                state.halted = True
                return (
                    "fallback_loop_breaker",
                    f"Clarification loop broken after {state.clarification_attempts} low-confidence turns.",
                )
            return (
                "fallback_low_confidence",
                f"Confidence {request.intent_confidence:.2f} below {self.confidence_threshold:.2f} floor; routed to deterministic fallback.",
            )


        return ("proceed", "System-1 gatekeeper passed.")