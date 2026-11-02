"""
schemas.py — Domain DTOs, Bounded MCP Input/Output Contracts, and MCP-38 Security Validators.
Design Pattern: Schema-First Contract Pattern + Pre-Registration Security Validator.
"""


from enum import Enum
import re
from typing import Annotated, Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator




class FaultCategory(str, Enum):
    NONE = "none"
    CRASH = "crash"
    OMISSION = "omission"
    VALUE = "value"




class TriggerStrategy(str, Enum):
    SINGLE = "single"
    PERSISTENT = "persistent"
    INTERMITTENT = "intermittent"
    BURST = "burst"




class ChaosConfig(BaseModel):
    experiment_id: str = Field(..., min_length=3, max_length=64)
    fault_category: FaultCategory = Field(default=FaultCategory.NONE)
    strategy: TriggerStrategy = Field(default=TriggerStrategy.SINGLE)
    target_call_index: Annotated[int, Field(ge=1, le=100)] = 1
    intermittent_probability: Annotated[float, Field(ge=0.0, le=1.0)] = 0.30
    burst_length: Annotated[int, Field(ge=1, le=10)] = 3




class ToolMetadataContract(BaseModel):
    """
    Hardens MCP tool registration against MCP-38 Tool Description Poisoning
    and enforces single-purpose atomic tool descriptions.
    """
    tool_name: str = Field(..., pattern=r"^[a-z][a-z0-9_]{2,48}$")
    description: str = Field(..., min_length=10, max_length=240)
    allowed_scopes: List[Literal["sandbox:read", "sandbox:exec", "telemetry:read"]]


    @field_validator("description")
    @classmethod
    def validate_mcp38_and_single_purpose(cls, v: str) -> str:
        poison_patterns = [
            r"ignore\s+previous",
            r"system\s+prompt",
            r"~/.ssh",
            r"/etc/passwd",
            r"exfiltrate",
            r"env\s*vars",
            r"<script",
        ]
        lowered = v.lower()
        for pattern in poison_patterns:
            if re.search(pattern, lowered):
                raise ValueError(f"MCP-38 Security Violation: directive pattern '{pattern}' blocked.")
        if " and " in lowered:
            raise ValueError(
                "Single-Responsibility Violation: Tool description must not contain 'and'. Split into atomic tools."
            )
        return v




class SandboxTaskRequest(BaseModel):
    session_id: str = Field(..., min_length=4, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    intent_query: str = Field(..., min_length=3, max_length=1000)
    intent_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    target_sandbox: Literal["mcp-core", "chaos-harness", "mcp-chaos-prod"] = "mcp-core"
    chaos_config: Optional[ChaosConfig] = None




class TelemetryEvent(BaseModel):
    session_id: str
    call_counter: Annotated[int, Field(ge=0)]
    fire_counter: Annotated[int, Field(ge=0)]
    fault_injected: bool
    fault_category: FaultCategory
    strategy: TriggerStrategy
    http_status: Annotated[int, Field(ge=100, le=599)]
    finish_reason: Literal["stop", "length", "tool_calls", "error", "fallback_routed"]
    token_utilization_ratio: Annotated[float, Field(ge=0.0, le=1.0)]
    gatekeeper_action: Literal["proceed", "fallback_low_confidence", "fallback_loop_breaker", "halt_keyword"]
    recovered: bool
    detail: str




class AggregatorVerificationReport(BaseModel):
    experiment_id: str
    fault_triggered_in_run: bool
    worker_outputs: List[float]
    aggregator_reported_sum: float
    ground_truth_sum: float
    stage_validation_passed: bool
    final_verified_value: float
    remediation_note: str