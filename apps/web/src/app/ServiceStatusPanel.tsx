import { useEffect, useRef, useState, type MouseEvent } from "react";
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

/** Model name to reveal on hover or tap; none while the service is not configured. */
function modelName(status: ServiceStatus) {
  return status.state === "not_configured" ? "" : status.model;
}

function describe(name: string, status: ServiceStatus) {
  const model = modelName(status);
  return `${name}${stateText[status.state]}${model ? `，模型 ${model}` : ""}`;
}

type ServiceKey = "story" | "image";

function ServiceRow({ id, name, status, revealed, secondary = false }: { id: ServiceKey; name: string; status: ServiceStatus; revealed: boolean; secondary?: boolean }) {
  // The image service is optional: "not configured" is neutral there, not a warning.
  const state = secondary && status.state === "not_configured" ? "neutral" : status.state;
  const model = modelName(status);
  return (
    <span className={`service-row ${secondary ? "secondary" : ""} ${revealed ? "revealed" : ""}`} data-service={id}>
      <span className="service-dot" data-state={state} aria-hidden="true">{status.state === "failed" ? "!" : ""}</span>
      <span className="service-body">
        <span className="service-text" key={status.state}>{name}{stateText[status.state]}</span>
        {/* Hidden until this row is hovered or tapped (or the block has keyboard focus); wraps instead of being cut off. */}
        {model && <span className="service-model"><span>{model}</span></span>}
      </span>
    </span>
  );
}

/**
 * Bottom of the save sidebar (D-06): whether the story AI (and the optional image AI) is configured
 * and reachable. The whole block links to the settings page. Each row shows its model name on hover;
 * on touch screens the first tap on a row reveals that row's model, and a tap on a revealed row opens settings.
 */
export function ServiceStatusPanel({ services, offline }: { services: ServiceStatuses | null; offline: boolean }) {
  const [revealed, setRevealed] = useState<ReadonlySet<ServiceKey>>(() => new Set());
  const blockRef = useRef<HTMLAnchorElement>(null);
  // A tap anywhere outside the block hides the model names again.
  useEffect(() => {
    if (!revealed.size) return;
    const hide = (event: PointerEvent) => { if (!blockRef.current?.contains(event.target as Node)) setRevealed(new Set()); };
    document.addEventListener("pointerdown", hide);
    return () => document.removeEventListener("pointerdown", hide);
  }, [revealed]);
  if (offline) {
    return (
      <Link viewTransition to="/settings" className="service-status" aria-label="游戏服务未连接，打开设置">
        <span className="service-row"><span className="service-dot" data-state="failed" aria-hidden="true">!</span><span className="service-text">游戏服务未连接</span></span>
      </Link>
    );
  }
  if (!services) return <div className="service-status" aria-hidden="true" />;
  const story = services.story_model;
  const image = services.image_model;
  const reason = story.state === "failed" ? failureReason[story.error_code ?? ""] ?? "请在设置中重新测试连接" : "";
  const label = `${describe("剧情模型", story)}${reason ? `，${reason}` : ""}；${describe("生图模型", image)}。打开设置`;
  const modelOf: Record<ServiceKey, string> = { story: modelName(story), image: modelName(image) };
  const revealOnTap = (event: MouseEvent) => {
    if (!window.matchMedia("(hover: none)").matches) return;
    const key = (event.target as Element).closest<HTMLElement>("[data-service]")?.dataset.service as ServiceKey | undefined;
    if (!key || revealed.has(key) || !modelOf[key]) return;
    event.preventDefault();
    setRevealed((current) => new Set(current).add(key));
  };
  return (
    <Link viewTransition to="/settings" ref={blockRef} className="service-status" aria-label={label} onClick={revealOnTap}>
      <ServiceRow id="story" name="剧情模型" status={story} revealed={revealed.has("story")} />
      <ServiceRow id="image" name="生图模型" status={image} revealed={revealed.has("image")} secondary />
      {reason && <small className="service-reason">{reason}</small>}
    </Link>
  );
}
