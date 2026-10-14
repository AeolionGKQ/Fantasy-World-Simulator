import { asApiError } from "../api";
import { playerProblemMessage } from "../playerCopy";

export function ErrorPanel({ error, onRetry, title = "无法完成请求", playerFacing = false }: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  playerFacing?: boolean;
}) {
  const apiError = asApiError(error);
  const conflict = apiError.status === 409 || apiError.problem.code.toLowerCase().includes("conflict");
  return (
    <section className={`state-panel ${conflict ? "warning" : "error"}`} role="alert">
      <span className="state-symbol" aria-hidden="true">{conflict ? "!" : "×"}</span>
      <div>
        <h2>{conflict ? (playerFacing ? "内容已更新" : "检测到版本冲突") : title}</h2>
        <p>{playerFacing ? playerProblemMessage(apiError.problem) : apiError.problem.message}</p>
        {apiError.problem.trace_id && <p className="trace">{playerFacing ? "问题编号" : "追踪编号"}：{apiError.problem.trace_id}</p>}
        {conflict && <p>{playerFacing ? "请重新载入，检查更新后的内容再继续。" : "服务器保留了较新的版本。请重新载入后检查内容，再继续编辑。"}</p>}
        {onRetry && (
          <button className="secondary-button" type="button" onClick={onRetry}>
            {conflict ? (playerFacing ? "载入最新内容" : "载入最新版本") : (playerFacing ? "重试" : "重试请求")}
          </button>
        )}
      </div>
    </section>
  );
}
