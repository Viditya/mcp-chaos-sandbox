import { useCallback, useEffect, useState } from "react";


export type FaultCategory = "none" | "crash" | "omission" | "value";
export type TriggerStrategy = "single" | "persistent" | "intermittent" | "burst";


export interface TelemetryEventPayload {
  session_id: string;
  call_counter: number;
  fire_counter: number;
  fault_injected: boolean;
  fault_category: FaultCategory;
  strategy: TriggerStrategy;
  http_status: number;
  finish_reason: "stop" | "length" | "tool_calls" | "error" | "fallback_routed";
  token_utilization_ratio: number;
  gatekeeper_action:
    | "proceed"
    | "fallback_low_confidence"
    | "fallback_loop_breaker"
    | "halt_keyword";
  recovered: boolean;
  detail: string;
}


export function useChaosStream(apiBasePath: string, sessionId: string) {
  const [events, setEvents] = useState<TelemetryEventPayload[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [selectedStrategy, setSelectedStrategy] = useState<TriggerStrategy>("burst");
  const [selectedFault, setSelectedFault] = useState<FaultCategory>("omission");


  const startChaosStream = useCallback(() => {
    setIsStreaming(true);
    setEvents([]);


    const streamUrl = `${apiBasePath}/api/v1/chaos/stream?session_id=${encodeURIComponent(
      sessionId
    )}`;
    const eventSource = new EventSource(streamUrl);


    eventSource.onmessage = (event) => {
      try {
        const parsed: TelemetryEventPayload = JSON.parse(event.data);
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // Ignore malformed frame
      }
    };


    eventSource.onerror = () => {
      eventSource.close();
      setIsStreaming(false);
    };


    return () => {
      eventSource.close();
      setIsStreaming(false);
    };
  }, [apiBasePath, sessionId]);


  // Compute pass@1 resilience & omission fault diagnostics
  const totalCalls = events.length;
  const totalFaultsFired = events.filter((e) => e.fault_injected).length;
  const recoveredCalls = events.filter((e) => e.recovered).length;
  const passAtOneRate =
    totalCalls > 0 ? Math.round((recoveredCalls / totalCalls) * 100) : 100;


  const hasOmissionSignature = events.some(
    (e) => e.finish_reason === "length" && e.token_utilization_ratio >= 0.95
  );


  useEffect(() => {
    return () => {
      setIsStreaming(false);
    };
  }, []);


  return {
    events,
    isStreaming,
    selectedStrategy,
    selectedFault,
    totalCalls,
    totalFaultsFired,
    passAtOneRate,
    hasOmissionSignature,
    setSelectedStrategy,
    setSelectedFault,
    startChaosStream,
  };
}