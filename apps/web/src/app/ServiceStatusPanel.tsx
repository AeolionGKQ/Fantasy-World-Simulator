import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";
import type { ServiceState, ServiceStatus, ServiceStatuses } from "../types";

const stateText: Record<ServiceState, string> = {
  not_configured: "未配置",
  unverified: "已配置，未测试",
  connected: "已连接",
  failed: "连接失败",
  disabled: "已关闭",
};

/** Short reasons for a failed connection; the settings page shows the full message. */
const failureReason: Record<string, string> = {
  MODEL_AUTH_FAILED: "密钥无效或无权访问",
  MODEL_NETWORK_ERROR: "网络不可达",
  MODEL_TIMEOUT: "连接超时",
  MODEL_NOT_FOUND: "找不到该模型",
  MODEL_SERVICE_ERROR: "服务暂时出错",
};

type ServiceKey = "story" | "image" | "embedding";

/** Each row opens its own section of the settings page (ids set on the sections there). */
const services: Record<ServiceKey, { name: string; section: string; sectionName: string }> = {
  story: { name: "剧情模型", section: "story-model", sectionName: "剧情模型配置" },
  image: { name: "生图模型", section: "image-model", sectionName: "生图模型配置" },
  embedding: { name: "嵌入模型", section: "embedding-model", sectionName: "嵌入模型配置" },
};

/** Model name to reveal on hover or tap; none while the service is not configured. */
function modelName(status: ServiceStatus) {
  return status.state === "not_configured" || status.state === "disabled" ? "" : status.model;
}

function ServiceRow({ id, status, reason, revealed, onReveal }: {
  id: ServiceKey;
  status: ServiceStatus;
  reason?: string;
  revealed: boolean;
  onReveal: (id: ServiceKey) => void;
}) {
  const { name, section, sectionName } = services[id];
  const secondary = id !== "story";
  // The image and embedding services are optional: "not configured" is neutral there, not a warning.
  const dotState = (secondary && status.state === "not_configured") || status.state === "disabled" ? "neutral" : status.state;
  const model = modelName(status);
  const label = `${name}${stateText[status.state]}${model ? `，模型 ${model}` : ""}${reason ? `，${reason}` : ""}。打开${sectionName}`;
  // On touch screens the first tap reveals the model name (and highlights the row); a tap on a revealed row opens settings.
  const onClick = (event: MouseEvent) => {
    if (revealed || !model || !window.matchMedia("(hover: none)").matches) return;
    event.preventDefault();
    onReveal(id);
  };
  return (
    <Link viewTransition to={`/settings#${section}`} className={`service-row ${secondary ? "secondary" : ""} ${revealed ? "revealed" : ""}`} aria-label={label} onClick={onClick}>
      <span className="service-dot" data-state={dotState} aria-hidden="true">{status.state === "failed" ? "!" : ""}</span>
      <span className="service-body">
        <span className="service-text" key={status.state}>{name}{stateText[status.state]}</span>
        {/* Hidden until this row is hovered, focused or tapped; wraps instead of being cut off. */}
        {model && <span className="service-model"><span>{model}</span></span>}
        {reason && <small className="service-reason">{reason}</small>}
      </span>
    </Link>
  );
}

/**
 * Bottom of the save sidebar (D-06): whether the story model (and the optional image and embedding models) is
 * configured and reachable. Each row is its own link to its section of the settings page.
 */
export function ServiceStatusPanel({ services: statuses, offline }: { services: ServiceStatuses | null; offline: boolean }) {
  const [revealed, setRevealed] = useState<ServiceKey | null>(null);
  const blockRef = useRef<HTMLDivElement>(null);
  // A tap anywhere outside the block hides the model name again.
  useEffect(() => {
    if (!revealed) return;
    const hide = (event: PointerEvent) => { if (!blockRef.current?.contains(event.target as Node)) setRevealed(null); };
    document.addEventListener("pointerdown", hide);
    return () => document.removeEventListener("pointerdown", hide);
  }, [revealed]);
  if (offline) {
    return (
      <div className="service-status">
        <Link viewTransition to="/settings" className="service-row" aria-label="游戏服务未连接，打开设置">
          <span className="service-dot" data-state="failed" aria-hidden="true">!</span>
          <span className="service-body"><span className="service-text">游戏服务未连接</span></span>
        </Link>
      </div>
    );
  }
  if (!statuses) return <div className="service-status" aria-hidden="true" />;
  const story = statuses.story_model;
  const reason = story.state === "failed" ? failureReason[story.error_code ?? ""] ?? "请在设置中重新测试连接" : "";
  return (
    <div className="service-status" ref={blockRef}>
      <ServiceRow id="story" status={story} reason={reason} revealed={revealed === "story"} onReveal={setRevealed} />
      <ServiceRow id="image" status={statuses.image_model} revealed={revealed === "image"} onReveal={setRevealed} />
      {statuses.embedding_model && <ServiceRow id="embedding" status={statuses.embedding_model} revealed={revealed === "embedding"} onReveal={setRevealed} />}
    </div>
  );
}
