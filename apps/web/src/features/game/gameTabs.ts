export type GameTab = "story" | "character" | "inventory" | "quests" | "journals" | "memory" | "bonds" | "reputations";

export const gameTabs: Array<{ id: GameTab; label: string }> = [
  { id: "story", label: "剧情" }, { id: "character", label: "角色" },
  { id: "inventory", label: "背包" }, { id: "quests", label: "任务栏" },
  { id: "journals", label: "纪事" }, { id: "memory", label: "记忆管理" },
  { id: "bonds", label: "羁绊" }, { id: "reputations", label: "声望" },
];
