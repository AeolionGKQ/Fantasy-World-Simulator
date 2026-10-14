export type StatusDotState = "online" | "offline" | "busy";

export function StatusDot({ state }: { state: StatusDotState }) {
  return <span className={`status-dot ${state}`} aria-hidden="true" />;
}
