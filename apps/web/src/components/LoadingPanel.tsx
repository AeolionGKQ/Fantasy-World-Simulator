/** Skeleton placeholder. `announce` adds aria-live for regions whose loading state should be read out. */
export function LoadingPanel({ label = "正在读取档案", announce = true }: { label?: string; announce?: boolean }) {
  return (
    <div className="loading-panel" role="status" aria-live={announce ? "polite" : undefined}>
      <div className="skeleton wide" />
      <div className="skeleton medium" />
      <div className="skeleton wide" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
