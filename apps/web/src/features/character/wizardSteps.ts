import type { CharacterDraft, WorldCatalog } from "../../types";

export const steps = [
  "种族",
  "姓名",
  "性别",
  "年龄",
  "外貌",
  "性格",
  "等阶",
  "天赋",
  "身世",
  "地区",
  "势力",
  "其他补充",
  "模型生成",
] as const;

export const TOTAL_STEPS = steps.length;

/** "第 N 步，共 13 步": shared by the wizard header, the save sidebar and the home page. */
export function stepProgressLabel(step: number) {
  return `第 ${step} 步，共 ${TOTAL_STEPS} 步`;
}

/** Steps the player must complete before a character can be generated. */
const requiredSteps = [1, 2, 3, 4, 5, 6, 7, 8, 10];

export type DraftUpdater = <K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) => void;

export function validateStep(step: number, draft: CharacterDraft, catalog: WorldCatalog | null): string {
  if (step === 1 && !draft.race_id) return "请选择角色种族。";
  const race = catalog?.races.find((item) => item.id === draft.race_id);
  if (step === 1 && race?.branches?.length && !draft.race_branch_id) return "请选择该种族的分支。";
  if (step === 2 && !draft.name.trim()) return "请输入角色姓名。";
  if (step === 3 && !draft.gender.trim()) return "请选择或输入角色性别。";
  if (step === 4 && (!draft.age || draft.age < 1)) return "请输入大于 0 的整数年龄。";
  if (step === 5 && !draft.appearance.trim()) return "请补充角色外貌。";
  if (step === 6 && !draft.personality.trim()) return "请补充角色性格。";
  if (step === 7 && !draft.rank) return "请选择角色等阶。";
  if (step === 8 && !draft.talent.trim()) return "请补充角色天赋。";
  if (step === 10 && !draft.location_id) return "请选择初始地点。";
  return "";
}

export function validateDraft(draft: CharacterDraft, catalog: WorldCatalog): { step: number; message: string } | null {
  for (const step of requiredSteps) {
    const message = validateStep(step, draft, catalog);
    if (message) return { step, message };
  }
  return null;
}

const stepTitles = ["选择角色种族", "为角色命名", "确定角色性别", "填写角色年龄", "描绘角色外貌", "塑造角色性格", "选择初始等阶", "描述角色天赋", "补充角色身世", "选择初始地点", "浏览世界势力", "添加其他信息", "生成并确认角色"];

const stepDescriptions = ["浏览可玩种族的特征与寿命提示，然后作出选择。", "姓名将进入正式角色档案，确认前仍可修改。", "使用预设选项，或直接输入更符合角色的描述。", "平均寿命仅供参考，不作为年龄上限。", "预设词会追加到文本中，你可以继续编辑。", "用明确的性格特征帮助模型理解角色。", "选择角色开局时的战斗实力，了解各阶的能力范围与冒险侧重。", "预设词只提供方向，最终文本由你决定。", "此项可留空，不会阻止后续生成。", "浏览地点资料并选择角色开始冒险的位置。", "认识这片大陆上的主要势力。", "此项可留空，用于记录额外约束或想法。", "检查输入，发起异步生成，并在接受前审阅完整候选。"];

export function stepTitle(step: number) {
  return stepTitles[step - 1];
}

export function stepDescription(step: number) {
  return stepDescriptions[step - 1];
}

export function stepSummary(step: number, draft: CharacterDraft, catalog: WorldCatalog) {
  if (step === 1) return catalog.races.find((r) => r.id === draft.race_id)?.name ?? "未选择";
  if (step === 2) return draft.name || "未填写";
  if (step === 3) return draft.gender || "未填写";
  if (step === 4) return draft.age ? `${draft.age} 岁` : "未填写";
  if (step === 7) return draft.rank ? `${draft.rank} 阶` : "未选择";
  if (step === 10) return catalog.locations.find((l) => l.id === draft.location_id)?.name ?? "未选择";
  if (step === 11) return "只读浏览";
  if ([5, 6, 8, 9, 12].includes(step)) {
    const value = ({ 5: draft.appearance, 6: draft.personality, 8: draft.talent, 9: draft.background, 12: draft.additional } as Record<number, string>)[step];
    return value ? "已填写" : "未填写";
  }
  return "";
}
