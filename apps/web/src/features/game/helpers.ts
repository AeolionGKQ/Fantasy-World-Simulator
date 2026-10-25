import { playerProblemMessage } from "../../playerCopy";
import { isActiveJobStatus, type AuthoritativeChange, type NarrativeJob, type Quest, type QuestProjection, type Reputation, type ReputationKey, type StoryArc, type Turn } from "../../types";

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

/** Fill colour of a resource bar; the condition is also written out next to it. */
export const resourceLevel = { 状态良好: "good", 轻度影响: "mild", 明显影响: "marked", 严重影响: "severe", 耗尽: "exhausted" } as const;

/** Share of a resource bar to fill, clamped to 0–1. */
export function resourceFill(current: number, maximum: number) {
  return maximum > 0 ? Math.min(1, Math.max(0, current / maximum)) : 0;
}

export function validateArcSelection(arcs: StoryArc[], selectedIds: string[]): { valid: boolean; message: string } {
  if (selectedIds.length < 2) return { valid: false, message: "请选择至少两个故事弧。" };
  const selected = arcs.filter((arc) => selectedIds.includes(arc.id) && arc.status === "current")
    .sort((a, b) => a.start_sequence - b.start_sequence);
  if (selected.length !== selectedIds.length) return { valid: false, message: "只能选择当前有效的故事弧。" };
  const contiguous = selected.every((arc, index) => index === 0 || selected[index - 1].end_sequence + 1 === arc.start_sequence);
  return contiguous
    ? { valid: true, message: `将压缩 ${selected.length} 个连续故事弧。` }
    : { valid: false, message: "请选择在剧情顺序上相邻的故事弧。" };
}

/** The button always names the action; why it cannot run yet goes in the message under it. */
const ARC_COMPRESS_LABEL = "压缩故事弧";

export function currentArcMerge(arcs: StoryArc[]): {
  arcIds: string[];
  valid: boolean;
  label: string;
  message: string;
} {
  const current = arcs.filter((arc) => arc.status === "current")
    .sort((a, b) => a.start_sequence - b.start_sequence);
  const arcIds = current.map((arc) => arc.id);
  const selection = validateArcSelection(current, arcIds);
  if (current.length === 0) {
    return { arcIds, valid: false, label: ARC_COMPRESS_LABEL, message: "较早的剧情每积累到连续 25 段，会自动整理成一个故事弧；有两个以上故事弧时可以压缩。" };
  }
  if (current.length === 1) {
    return { arcIds, valid: false, label: ARC_COMPRESS_LABEL, message: "当前只有一个故事弧。继续冒险，有两个以上故事弧时即可压缩。" };
  }
  const range = `第 ${current[0].start_sequence} 至 ${current[current.length - 1].end_sequence} 段`;
  return {
    arcIds,
    valid: selection.valid,
    label: ARC_COMPRESS_LABEL,
    message: selection.valid ? `将${range}剧情压缩成一份更精简的摘要，完整剧情仍会保留。` : selection.message,
  };
}

export function questProjectionFromResponse(payload: unknown): QuestProjection {
  if (!payload || typeof payload !== "object") return { active: [], offered: [], finished: [], state_version: 0 };
  const value = payload as { active?: unknown; offered?: unknown; finished?: unknown; state_version?: unknown };
  const list = (items: unknown) => Array.isArray(items) ? items as Quest[] : [];
  return {
    active: list(value.active),
    offered: list(value.offered),
    finished: list(value.finished),
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

const keyNames: Record<string, string> = {
  hp: "生命", mp: "魔力", sp: "精神", st: "精力", con: "体质", int: "智力", cha: "魅力",
  exp: "经验", rank: "阶位", copper: "铜币", effective_power: "战力", age: "年龄",
};
const visibleChangeKinds = new Set([
  "resource", "attribute", "experience", "rank", "item", "currency", "quest",
  "bond", "reputation", "skill", "talent", "power", "condition", "age", "resource_max",
]);
const valueNames: Record<string, string> = {
  untriggered: "未触发", eligible: "可触发", offered: "已提供", active: "进行中",
  completed: "已完成", declined: "已拒绝", failed: "失败", abandoned: "已放弃",
  add: "获得", remove: "移除", update: "更新", equip: "装备", unequip: "卸下",
};
const internalReferencePatterns = [
  /(?:npc|item|quest|bond|skill|talent|dynamic|location|canon|regional_main|world_flag)[.:][0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/gi,
  /[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/gi,
  /(?:npc|item|quest|bond|skill|talent|dynamic|location|canon|regional_main|world_flag)[.:][a-z0-9_.:-]+/gi,
  /\b[a-z][a-z0-9_-]*\.[a-z0-9_.:-]*\d[a-z0-9_.:-]*\b/gi,
];

function cleanDisplayText(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  let result = value;
  for (const pattern of internalReferencePatterns) result = result.replace(pattern, "");
  result = result.replace(/\s{2,}/g, " ").replace(/\s+([，。；：、])/g, "$1")
    .replace(/^(与|和|向|从|由)\s+(?=\S)/, "")
    .replace(/^\s*[·:：,，;；-]+\s*|\s*[·:：,，;；-]+\s*$/g, "").trim();
  return result || fallback;
}

function printable(value: unknown): string {
  if (value === null || value === undefined) return "无";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") {
    const item = value as { name?: unknown; quantity?: unknown };
    if (typeof item.name === "string") return `${item.name}${typeof item.quantity === "number" ? ` × ${item.quantity}` : ""}`;
    return "已更新";
  }
  if (typeof value === "string") return valueNames[value] ?? "已更新";
  return String(value);
}

export function formatChange(change: AuthoritativeChange): { label: string; value: string; reason: string } {
  const label = (() => {
    if (change.kind === "item" && change.key.endsWith(".equipped")) {
      const name = cleanDisplayText(change.display_name, "物品");
      return `${name}装备状态`;
    }
    if (change.display_name) {
      const name = cleanDisplayText(change.display_name, "");
      if (name && change.kind === "bond") return `${name}好感度`;
      if (name) return name;
    }
    if (change.kind === "reputation") {
      const name = reputationNames[change.key as ReputationKey];
      return name ? `${name}声望` : "声望";
    }
    if (change.kind === "bond") return "羁绊好感度";
    if (change.kind === "item") return change.key.endsWith(".equipped") ? "装备状态" : "物品";
    if (change.kind === "quest") return "任务状态";
    if (change.kind === "skill") return "技能";
    if (change.kind === "talent") return "天赋";
    if (change.kind === "condition") return "持续状态";
    if (change.kind === "resource_max") return `${keyNames[change.key] ?? "资源"}上限`;
    return keyNames[change.key] ?? "数值";
  })();
  const oldLevel = cleanDisplayText(change.old_level, "");
  const newLevel = cleanDisplayText(change.new_level, "");
  let oldValue = oldLevel
    ? `${oldLevel}${typeof change.old === "number" ? ` ${change.old}` : ""}`
    : printable(change.old);
  let newValue = newLevel
    ? `${newLevel}${typeof change.new === "number" ? ` ${change.new}` : ""}`
    : printable(change.new);
  if (change.kind === "item" && change.key.endsWith(".equipped")) {
    oldValue = change.old === true ? "已装备" : "未装备";
    newValue = change.new === true ? "已装备" : "未装备";
  }
  if (change.kind === "quest" && change.force_display && oldValue === newValue) {
    return {
      label: cleanDisplayText(label, "任务进度"),
      value: "进度已更新",
      reason: cleanDisplayText(change.reason, "任务进度已更新"),
    };
  }
  return {
    label: cleanDisplayText(label, "状态"),
    value: cleanDisplayText(`${oldValue} → ${newValue}`, "已更新"),
    reason: cleanDisplayText(change.reason, "状态已更新"),
  };
}

export function visibleAuthoritativeChanges(changes: AuthoritativeChange[]) {
  return changes.filter((change) => visibleChangeKinds.has(change.kind))
    .map((source) => ({ source, formatted: formatChange(source) }))
    .filter(({ source, formatted }) => {
      if (source.force_display) return true;
      const [oldValue, newValue] = formatted.value.split(" → ");
      return oldValue === undefined || newValue === undefined || oldValue !== newValue;
    }).map(({ formatted }) => formatted);
}

export function isLatestTurn(turn: Turn | null, latestTurnId: string | null): boolean {
  return Boolean(turn && turn.id === latestTurnId);
}

export function isNarrativeJobActive(job: NarrativeJob | null): boolean {
  return isActiveJobStatus(job?.status);
}

export function isStoryReadOnly(turn: Turn | null, latestTurnId: string | null, job: NarrativeJob | null): boolean {
  return !isLatestTurn(turn, latestTurnId) || isNarrativeJobActive(job);
}

export function refreshedViewedTurn(
  turns: Turn[],
  latestTurn: Turn | null,
  current: Turn | null,
  completedTurnId?: string | null,
): Turn | null {
  if (completedTurnId) {
    return turns.find((turn) => turn.id === completedTurnId) ?? latestTurn;
  }
  return current ? turns.find((turn) => turn.id === current.id) ?? latestTurn : latestTurn;
}

export function narrativeJobMessage(job: NarrativeJob): string {
  if (job.error?.code === "MODEL_CONTEXT_LENGTH_EXCEEDED") {
    return "当前 AI 无法一次读取这么多故事内容。请在设置中换用能读取更长故事的模型，再重新提交。游戏不会删减你的故事来重试。";
  }
  if (job.status === "stale") return "生成期间，存档内容已更新。这次生成的结果未保存，请查看最新剧情后再试。";
  if (job.status === "cancelled") return "已取消生成，剧情和角色状态没有改变。";
  if (job.error) return playerProblemMessage(job.error);
  return job.type === "memory_curation"
    ? "GM 正在回顾全部长期记忆，剔除已经解决、过期或不重要的内容。完成前暂时不能推进剧情。"
    : "GM 正在写下新剧情，等待时可以查看角色、背包等页签。";
}
