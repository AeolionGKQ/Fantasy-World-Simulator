import type { AuthoritativeChange, NarrativeJob, Quest, QuestProjection, Reputation, ReputationKey, StoryArc, Turn } from "../types";

export type ResourceKey = "hp" | "mp" | "sp" | "st";

export const resourceExhaustion: Record<ResourceKey, string> = {
  hp: "生命耗尽代表角色死亡。",
  mp: "魔力耗尽会限制依赖自身魔力供能的能力，并可能产生明显疲劳。",
  sp: "精神耗尽代表严重精神失稳或意识崩溃，不直接等同死亡。",
  st: "精力耗尽时很难继续高强度活动。",
};

export function resourceCondition(current: number, maximum: number): "状态良好" | "轻度影响" | "明显影响" | "严重影响" | "耗尽" {
  if (current <= 0 || maximum <= 0) return "耗尽";
  const percentage = current / maximum * 100;
  if (percentage >= 75) return "状态良好";
  if (percentage >= 50) return "轻度影响";
  if (percentage >= 25) return "明显影响";
  return "严重影响";
}

export function validateArcSelection(arcs: StoryArc[], selectedIds: string[]): { valid: boolean; message: string } {
  if (selectedIds.length < 2) return { valid: false, message: "请选择至少两个故事弧。" };
  const selected = arcs.filter((arc) => selectedIds.includes(arc.id) && arc.status === "current")
    .sort((a, b) => a.start_sequence - b.start_sequence);
  if (selected.length !== selectedIds.length) return { valid: false, message: "只能选择当前有效的故事弧。" };
  const contiguous = selected.every((arc, index) => index === 0 || selected[index - 1].end_sequence + 1 === arc.start_sequence);
  return contiguous
    ? { valid: true, message: `将合并 ${selected.length} 个连续故事弧。` }
    : { valid: false, message: "所选故事弧的节点范围必须首尾连续。" };
}

export function questProjectionFromResponse(payload: unknown): QuestProjection {
  if (!payload || typeof payload !== "object") return { active: [], state_version: 0 };
  const value = payload as { active?: unknown; state_version?: unknown };
  return {
    active: Array.isArray(value.active) ? value.active as Quest[] : [],
    state_version: typeof value.state_version === "number" ? value.state_version : 0,
  };
}

export const REPUTATION_ORDER: ReputationKey[] = [
  "continental_overall",
  "court_of_veiled_night",
  "skycrown_conclave",
  "holy_see_sacred_radiance",
  "court_of_sacred_tree",
  "valkeren_empire",
  "southern_maritime_federation",
];

export const reputationNames: Record<ReputationKey, string> = {
  continental_overall: "大陆综合",
  court_of_veiled_night: "幽夜王庭",
  skycrown_conclave: "天穹议庭",
  holy_see_sacred_radiance: "圣辉教廷",
  court_of_sacred_tree: "圣树王庭",
  valkeren_empire: "瓦尔凯伦帝国",
  southern_maritime_federation: "南海自由联邦",
};

export function orderReputations(items: Reputation[], localKey: ReputationKey | null) {
  const byKey = new Map(items.map((item) => [item.key, item]));
  return REPUTATION_ORDER.map((key) => byKey.get(key)).filter((item): item is Reputation => Boolean(item))
    .map((item) => ({ ...item, local: item.key === localKey }));
}

const changeNames: Record<string, string> = {
  location: "地点", time: "时间", resource: "资源", attribute: "属性", experience: "经验",
  rank: "阶位", item: "物品", currency: "货币", quest: "任务", bond: "羁绊",
  reputation: "声望", skill: "技能", talent: "天赋", world_flag: "世界状态",
};
const keyNames: Record<string, string> = {
  hp: "生命", mp: "魔力", sp: "精神", st: "精力", con: "体质", int: "智力", cha: "魅力",
  exp: "EXP", rank: "阶位", current_location_id: "当前地点", time_label: "当前时间", copper: "铜币",
};

function printable(value: unknown): string {
  if (value === null || value === undefined) return "无";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") {
    const item = value as { name?: unknown; quantity?: unknown };
    if (typeof item.name === "string") return `${item.name}${typeof item.quantity === "number" ? ` × ${item.quantity}` : ""}`;
    return "已更新";
  }
  return String(value);
}

export function formatChange(change: AuthoritativeChange): { label: string; value: string; reason: string } {
  const label = `${changeNames[change.kind] ?? change.kind} · ${keyNames[change.key] ?? reputationNames[change.key as ReputationKey] ?? change.key}`;
  const oldValue = change.old_level ?? printable(change.old);
  const newValue = change.new_level ?? printable(change.new);
  return { label, value: `${oldValue} → ${newValue}`, reason: change.reason };
}

export function isLatestTurn(turn: Turn | null, latestTurnId: string | null): boolean {
  return Boolean(turn && turn.id === latestTurnId);
}

export function isNarrativeJobActive(job: NarrativeJob | null): boolean {
  return Boolean(job && ["queued", "running", "cancel_requested"].includes(job.status));
}

export function isStoryReadOnly(turn: Turn | null, latestTurnId: string | null, job: NarrativeJob | null): boolean {
  return !isLatestTurn(turn, latestTurnId) || isNarrativeJobActive(job);
}

export function narrativeJobMessage(job: NarrativeJob): string {
  if (job.error?.code === "MODEL_CONTEXT_LENGTH_EXCEEDED") {
    return "模型上下文长度不足。请在设置中更换支持更长上下文的模型，再重新提交。本次不会自动裁剪或重试。";
  }
  if (job.status === "stale") return "任务完成前权威状态已变化，迟到结果没有写入存档。";
  if (job.status === "cancelled") return "任务已取消，没有写入剧情或权威状态。";
  return job.error?.message ?? "模型正在生成叙事，期间可以浏览其他页签。";
}
