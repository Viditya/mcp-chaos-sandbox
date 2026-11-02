"""
chaos_harness.py — AgentChaos HTTP-Layer Fault Injection Harness with ContextVars Isolation.
Design Pattern: Proxy / Decorator Pattern + Context-Local State Machine.
"""


from contextvars import ContextVar
import copy
import random
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple
from schemas import ChaosConfig, FaultCategory, TriggerStrategy


# Task-scoped state isolation so parallel microVM workers never bleed counters
call_counter_var: ContextVar[int] = ContextVar("call_counter_var", default=0)
fire_counter_var: ContextVar[int] = ContextVar("fire_counter_var", default=0)
active_chaos_config_var: ContextVar[Optional[ChaosConfig]] = ContextVar(
    "active_chaos_config_var", default=None
)




def reset_task_chaos_state(config: Optional[ChaosConfig] = None) -> None:
    call_counter_var.set(0)
    fire_counter_var.set(0)
    active_chaos_config_var.set(config)




def get_task_chaos_counters() -> Tuple[int, int]:
    return call_counter_var.get(), fire_counter_var.get()




def should_fire_fault(config: ChaosConfig, current_call: int) -> bool:
    """
    Determines whether the fault triggers on the current LLM HTTP call
    based on Single, Persistent, Intermittent (0.3), or Burst (3) strategy.
    """
    if config.fault_category == FaultCategory.NONE:
        return False


    if config.strategy == TriggerStrategy.SINGLE:
        return current_call == config.target_call_index


    if config.strategy == TriggerStrategy.PERSISTENT:
        return current_call >= config.target_call_index


    if config.strategy == TriggerStrategy.INTERMITTENT:
        return random.random() < config.intermittent_probability


    if config.strategy == TriggerStrategy.BURST:
        end_call = config.target_call_index + config.burst_length - 1
        return config.target_call_index <= current_call <= end_call


    return False




def mutate_llm_response(
    raw_payload: Dict[str, Any], config: ChaosConfig
) -> Tuple[int, Dict[str, Any], float]:
    """
    Mutates standard LLM JSON payload (choices[0].message) deterministically.
    Returns (http_status_code, mutated_payload, token_utilization_ratio).
    """
    mutated = copy.deepcopy(raw_payload)
    choice = mutated.setdefault("choices", [{}])[0]
    message = choice.setdefault("message", {"role": "assistant", "content": ""})


    if config.fault_category == FaultCategory.CRASH:
        message["content"] = ""
        message["tool_calls"] = []
        choice["finish_reason"] = "error"
        mutated["error"] = {"type": "upstream_crash_fault", "code": 500}
        return 500, mutated, 0.0


    if config.fault_category == FaultCategory.OMISSION:
        # Truncate content and tool_call arguments to 30% length and force finish_reason='length'
        original_content = str(message.get("content") or "")
        cutoff = max(1, int(len(original_content) * 0.30))
        message["content"] = original_content[:cutoff]
        if "tool_calls" in message and isinstance(message["tool_calls"], list):
            for tc in message["tool_calls"]:
                args_str = str(tc.get("function", {}).get("arguments", ""))
                arg_cutoff = max(1, int(len(args_str) * 0.30))
                tc.setdefault("function", {})["arguments"] = args_str[:arg_cutoff]
        choice["finish_reason"] = "length"
        return 200, mutated, 1.00


    if config.fault_category == FaultCategory.VALUE:
        # Corrupt structured tool_calls JSON or invert numerical value
        if "value" in mutated:
            mutated["value"] = -abs(float(mutated["value"]))
        message["content"] = "MALFORMED_PLAIN_TEXT_PAYLOAD_NOT_JSON::{broken_bracket"
        choice["finish_reason"] = "stop"
        return 200, mutated, 0.65


    choice["finish_reason"] = choice.get("finish_reason", "stop")
    return 200, mutated, 0.45




async def execute_with_chaos_harness(
    llm_Coroutine: Callable[[], Coroutine[Any, Any, Dict[str, Any]]]
) -> Tuple[int, Dict[str, Any], float, bool]:
    """
    Wraps an async LLM/MCP transport call, increments task-isolated counters,
    and applies fault injection if triggered.
    """
    current_call = call_counter_var.get() + 1
    call_counter_var.set(current_call)


    raw_response = await llm_Coroutine()
    config = active_chaos_config_var.get()


    if config is not None and should_fire_fault(config, current_call):
        fire_counter_var.set(fire_counter_var.get() + 1)
        status, mutated, ratio = mutate_llm_response(raw_response, config)
        return status, mutated, ratio, True


    return 200, raw_response, 0.42, False