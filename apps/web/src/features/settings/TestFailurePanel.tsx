import { playerProblemMessage } from "../../playerCopy";
import type { ApiProblem } from "../../types";

/** What kind of failure it was, in words a player can act on. */
const failureKind: Record<string, string> = {
  MODEL_AUTH_FAILED: "鉴权失败（密钥无效或没有权限）",
  MODEL_NETWORK_ERROR: "网络不可达",
  MODEL_TIMEOUT: "请求超时",
  MODEL_NOT_FOUND: "找不到这个模型",
  MODEL_SERVICE_ERROR: "服务端出错",
  MODEL_RATE_LIMITED: "请求过于频繁",
  MODEL_REQUEST_REJECTED: "服务拒绝了请求",
  MODEL_OUTPUT_FORMAT: "返回内容无法识别",
  MODEL_OUTPUT_TOO_LARGE: "返回内容过大",
  MODEL_CONTEXT_LENGTH_EXCEEDED: "上下文超出模型上限",
  MODEL_NOT_CONFIGURED: "尚未配置",
  INVALID_INPUT: "配置填写有误",
};

function detail(problem: ApiProblem, key: string) {
  const value = problem.details?.[key];
  return value === undefined || value === null || value === "" ? null : String(value);
}

/**
 * A failed connection test, shown in the same place as a passing result (next to the test button)
 * with the same kind of fields, so the player sees why it failed without scrolling.
 */
export function TestFailurePanel({ problem, hint }: { problem: ApiProblem; hint: string }) {
  const summary = playerProblemMessage(problem);
  const status = detail(problem, "http_status");
  const providerCode = detail(problem, "provider_code");
  const elapsed = detail(problem, "elapsed_ms");
  const providerMessage = detail(problem, "provider_message");
  // When the service never answered (network, timeout), the server's own message is the detail.
  const raw = providerMessage ?? (problem.message && problem.message !== summary ? problem.message : null);
  return (
    <div className="test-result full error" role="alert">
      <strong>连接测试未通过</strong>
      <p>{summary}</p>
      <div className="capabilities">
        <span>失败类型：{failureKind[problem.code] ?? problem.code}</span>
        {status && <span>HTTP 状态：{status}</span>}
        {providerCode && <span>服务商错误码：{providerCode}</span>}
        {elapsed && <span>测试用时：{(Number(elapsed) / 1000).toFixed(1)} 秒</span>}
      </div>
      {raw && <p className="test-raw"><span>{providerMessage ? "服务商返回：" : "原始信息："}</span>{raw}</p>}
      <p>{hint}</p>
      {problem.trace_id && <small className="test-trace">问题编号：{problem.trace_id}</small>}
    </div>
  );
}
