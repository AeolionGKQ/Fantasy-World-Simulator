import { Link } from "react-router-dom";
import type { ServiceState, ServiceStatus, ServiceStatuses } from "../types";

const stateText: Record<ServiceState, string> = {
  not_configured: "未配置",
  unverified: "已配置，未测试",
  connected: "已连接",
  failed: "连接失败",
};

/** Short reasons for a failed connection; the settings page shows the full message. */
const failureReason: Record<string, string> = {
  MODEL_AUTH_FAILED: "密钥无效或无权访问",
  MODEL_NETWORK_ERROR: "网络不可达",
  MODEL_TIMEOUT: "连接超时",
  MODEL_NOT_FOUND: "找不到该模型",
  MODEL_SERVICE_ERROR: "服务暂时出错",
};

function describe(name: string, status: ServiceStatus) {
  const model = status.state === "connected" && status.model ? ` · ${status.model}` : "";
  return `${name}${stateText[status.state]}${model}`;
}

function ServiceRow({ name, status, secondary = false }: { name: string; status: ServiceStatus; secondary?: boolean }) {
  // The image service is optional: "not configured" is neutral there, not a warning.
  const state = secondary && status.state === "not_configured" ? "neutral" : status.state;
  return (
    <span className={`service-row ${secondary ? "secondary" : ""}`}>
      <span className="service-dot" data-state={state} aria-hidden="true">{status.state === "failed" ? "!" : ""}</span>
      <span className="service-text" key={status.state}>{describe(name, status)}</span>
    </span>
  );
}

/**
 * Bottom of the save sidebar (D-06): whether the story AI (and the optional image AI) is configured
 * and reachable. The whole block links to the settings page.
 */
export function ServiceStatusPanel({ services, offline }: { services: ServiceStatuses | null; offline: boolean }) {
  if (offline) {
    return (
      <Link viewTransition to="/settings" className="service-status" aria-label="游戏服务未连接，打开设置">
        <span className="service-row"><span className="service-dot" data-state="failed" aria-hidden="true">!</span><span className="service-text">游戏服务未连接</span></span>
      </Link>
    );
  }
  if (!services) return <div className="service-status" aria-hidden="true" />;
  const story = services.story_model;
  const reason = story.state === "failed" ? failureReason[story.error_code ?? ""] ?? "请在设置中重新测试连接" : "";
  const label = `${describe("剧情 AI ", story)}${reason ? `，${reason}` : ""}；${describe("图片 AI ", services.image_model)}。打开设置`;
  return (
    <Link viewTransition to="/settings" className="service-status" aria-label={label}>
      <ServiceRow name="剧情 AI " status={story} />
      <ServiceRow name="图片 AI " status={services.image_model} secondary />
      {reason && <small className="service-reason">{reason}</small>}
    </Link>
  );
}
