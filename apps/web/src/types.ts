export type SavePhase = "draft" | "review" | "ready";
export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancel_requested"
  | "cancelled"
  | "stale"
  | "interrupted";

export interface ApiProblem {
  code: string;
  message: string;
  retryable?: boolean;
  trace_id?: string;
  field_errors?: Record<string, string | string[]>;
  details?: Record<string, unknown>;
}

export interface GenerationSummary {
  job_id: string;
  status: JobStatus;
  updated_at?: string;
}

export interface SaveSummary {
  id: string;
  name: string;
  phase: SavePhase;
  revision: number;
  character_name?: string | null;
  current_step?: number;
  generation?: GenerationSummary | null;
  narration?: StoryNarrationSettings;
  updated_at?: string;
}

export interface RankDefinition {
  rank: number;
  display_rank?: string;
  name?: string;
  title?: string | null;
  base_power?: number;
  next_exp?: number | null;
  disabled?: boolean;
  warning?: string | null;
}

export interface RaceFact {
  label: string;
  value: string;
}

export interface RaceLore {
  tagline: string;
  description: string;
  lifespan_text: string;
  distribution: string;
  magic_affinity: string;
  combat_style: string;
  technology: string;
  society: string;
  creation_notes: string;
  facts: RaceFact[];
  ranks: RankDefinition[];
}

export interface RaceBranch extends RaceLore {
  id: string;
  name: string;
}

export interface RaceDefinition extends RaceLore, MediaPaths {
  id: string;
  name: string;
  branches?: RaceBranch[];
}

export interface MediaPaths {
  image_landscape_path: string;
  image_portrait_path: string;
}

export interface LocationDefinition extends MediaPaths {
  id: string;
  name: string;
  tagline: string;
  description: string;
  region: string;
  environment: string;
  structure: string;
  highlights: string[];
  transport: string;
  access_note: string;
  arrival_point: string;
  safeguards: string[];
  disabled?: boolean;
  warning?: string | null;
}

export interface FactionDefinition extends MediaPaths {
  id: string;
  name: string;
  tagline: string;
  description: string;
  headquarters: string;
  ideology: string;
  organization: string;
  tasks: string[];
  services: string[];
  activities: string[];
  rewards: string[];
  audience: string;
  access_note: string;
}

export interface PresetDefinition {
  id: string;
  label: string;
  category?: string;
  race_ids?: string[];
}

export function groupPresets(presets: PresetDefinition[]): Array<{ category: string; items: PresetDefinition[] }> {
  const groups = new Map<string, PresetDefinition[]>();
  for (const preset of presets) {
    const category = preset.category?.trim() || "推荐词";
    groups.set(category, [...(groups.get(category) ?? []), preset]);
  }
  return [...groups].map(([category, items]) => ({ category, items }));
}

export interface WorldCatalog {
  ruleset_version: string;
  races: RaceDefinition[];
  locations: LocationDefinition[];
  factions: FactionDefinition[];
  faction_notice?: string;
  rank_system: {
    title: string;
    description: string;
    principles: string[];
  };
  ranks: RankDefinition[];
  presets: {
    appearance: PresetDefinition[];
    personality: PresetDefinition[];
    talent: PresetDefinition[];
  };
}

export interface NarrationSettings {
  pace: "slow" | "fast" | "dynamic";
  tendency: "casual" | "balanced" | "combat";
  detail: "concise" | "standard" | "detailed";
  player_address: "full_name" | "given_name" | "second_person";
}

export interface StoryNarrationSettings {
  pace: NarrationSettings["pace"];
  tone: NarrationSettings["tendency"];
  detail: NarrationSettings["detail"];
  player_address: NarrationSettings["player_address"];
}

export interface ModelSettings {
  protocol?: ModelProtocol;
  base_url: string;
  model: string;
  api_key_configured: boolean;
  api_key_mask?: string | null;
  timeout_seconds: number;
  structured_output: boolean;
  structured_output_capability: "supported" | "unsupported" | "unknown";
  structured_output_message?: string;
  structured_output_probed_at?: string | null;
  structured_output_probe_token?: string;
  thinking_enabled: boolean;
  thinking_capability: "controlled" | "unsupported" | "unknown";
  thinking_strategy?: ThinkingStrategy | null;
  thinking_confidence: ThinkingConfidence;
  thinking_message?: string;
  thinking_probed_at?: string | null;
  api_key_persistence?: "windows_dpapi" | "memory_only";
  max_concurrency: number;
}

export type ModelProtocol = "openai" | "anthropic";

export type ThinkingStrategy =
  | "bundle"
  | "enable_thinking"
  | "thinking"
  | "reasoning_effort"
  | "chat_template_kwargs"
  | "reasoning_enabled"
  | "reasoning_effort_nested"
  | "thinking_budget"
  | "anthropic_adaptive"
  | "anthropic_adaptive_between_tools"
  | "anthropic_enabled"
  | "anthropic_enabled_between_tools";
export type ThinkingConfidence = "verified" | "accepted_bundle" | "unsupported" | "unknown";

export interface AppSettings {
  model: ModelSettings;
  image_model?: ImageModelSettings;
  narration: NarrationSettings;
  revision: number;
}

export interface ImageModelSettings {
  base_url: string;
  model: "gpt-image-2.5-sunburst";
  timeout_seconds: number;
  configured: boolean;
  api_key_configured: boolean;
  api_key_mask?: string | null;
  api_key_persistence?: "windows_dpapi" | "memory_only";
}

export type ImageSize = "1024x1024" | "1536x1024" | "1024x1536";
export type ImageQuality = "low" | "medium" | "high" | "xhigh" | "max" | "auto";
export interface SceneImageSession {
  id: string; save_id: string; source_turn_id: string; status: "active" | "completing" | "completed";
  prompt_draft: string | null; prompt_revision: number; selected_size: ImageSize;
  selected_quality: ImageQuality;
  prompt_attempt: { id: string; status: string; error?: { code: string; message: string; retryable: boolean } | null } | null;
  image_attempt: { id: string; status: string; requested_size: ImageSize; requested_quality: ImageQuality;
    image_available: boolean; error?: { code: string; message: string; retryable: boolean } | null } | null;
  latest_successful_image?: { id: string; status: string; requested_size: ImageSize;
    requested_quality: ImageQuality; image_available: boolean } | null;
}

export interface ModelTestResult {
  ok: boolean;
  message: string;
  latency_ms?: number;
  model_available?: boolean;
  thinking_capability: "controlled" | "unsupported" | "unknown";
  thinking_strategy?: ThinkingStrategy | null;
  thinking_confidence: ThinkingConfidence;
  thinking_message: string;
  thinking_probed_at?: string | null;
  structured_output_capability?: "supported" | "unsupported" | "unknown";
  structured_output_message?: string;
  structured_output_probed_at?: string | null;
  structured_output_probe_token?: string;
  may_have_cost?: boolean;
}

type AppSettingsResponse = Omit<AppSettings, "model" | "narration" | "image_model"> & {
  model: Omit<ModelSettings, "protocol" | "structured_output_capability" | "max_concurrency"> & {
    protocol?: ModelProtocol;
    structured_output_capability?: ModelSettings["structured_output_capability"];
    max_concurrency?: number;
  };
  narration: Omit<NarrationSettings, "player_address"> & {
    player_address?: NarrationSettings["player_address"];
  };
  image_model?: ImageModelSettings;
};

export function normalizeAppSettings(settings: AppSettingsResponse): AppSettings {
  const capability = settings.model.structured_output_capability ?? "unknown";
  return {
    ...settings,
    narration: {
      ...settings.narration,
      player_address: settings.narration.player_address ?? "second_person",
    },
    model: {
      ...settings.model,
      protocol: settings.model.protocol ?? "openai",
      max_concurrency: settings.model.max_concurrency ?? 2,
      structured_output: settings.model.structured_output === true && capability === "supported",
      structured_output_capability: capability,
    },
    image_model: settings.image_model ?? {
      base_url: "https://api.openai.com/v1", model: "gpt-image-2.5-sunburst",
      timeout_seconds: 300, configured: false, api_key_configured: false,
    },
  };
}

export interface CharacterDraft {
  race_id: string;
  race_branch_id?: string | null;
  name: string;
  gender: string;
  age: number | null;
  appearance: string;
  personality: string;
  rank: number | null;
  talent: string;
  background: string;
  location_id: string;
  additional: string;
  current_step: number;
  draft_revision: number;
}

export interface GenerationJob {
  id: string;
  save_id: string;
  status: JobStatus;
  attempt?: number;
  progress_message?: string;
  error?: ApiProblem | null;
  created_at?: string;
  updated_at?: string;
}

export interface AttributeValue {
  value: number;
  reason?: string;
}

export interface ResourceValue {
  current: number;
  max: number;
  reason?: string;
}

export interface CharacterCandidate {
  id: string;
  save_id: string;
  job_id?: string;
  draft_revision: number;
  identity?: {
    name?: string;
    gender?: string;
    age?: number;
    race_name?: string;
    race_branch_name?: string;
    location_name?: string;
    rank_name?: string;
  };
  description?: {
    appearance?: string;
    personality?: string;
    talent?: string;
    background?: string;
    additional?: string;
  };
  attributes: {
    con: AttributeValue;
    int: AttributeValue;
    cha: AttributeValue;
  };
  resources?: {
    hp?: ResourceValue;
    mp?: ResourceValue;
    sp?: ResourceValue;
    st?: ResourceValue;
  };
  starting_currency?: {
    copper: number;
    reason: string;
  };
  power: {
    base: number;
    effective: number;
    modifiers?: Array<{ label: string; value: number; reason?: string }>;
    explanation?: string;
  };
  exp: number;
  next_exp?: number | null;
  summary?: string;
  strengths?: string[];
  limitations?: string[];
  valid?: boolean;
}

export interface ConfirmedCharacterBootstrap {
  save_id: string;
  save_revision: number;
  character: CharacterCandidate & { confirmed_at?: string };
  location: LocationDefinition | { id: string; name: string; description?: string };
  phase: "ready";
  ruleset_version?: string;
}

export interface GameBootstrap extends ConfirmedCharacterBootstrap {
  story: StoryView;
  gm_turns_available: boolean;
}

export type StartPrerequisiteResolution = "relocate" | "accept_legacy_protection";

export type StartPrerequisiteOption =
  | { kind: "relocate"; location_ids: string[] }
  | { kind: "accept_legacy_protection"; grants: string[] };

export interface StartPrerequisite {
  status: "required" | "satisfied";
  requirements: string[];
  resolution: StartPrerequisiteResolution | null;
  options: StartPrerequisiteOption[];
}

export interface StartPrerequisiteResult {
  save_id: string;
  state_version: number;
  location: StoryLocation;
  resolved: true;
}

export interface StoryIdentity {
  race_id?: string;
  race_branch_id?: string | null;
  name?: string;
  gender?: string;
  age?: number;
  appearance?: string;
  personality?: string;
  rank?: number;
  talent?: string;
  backstory?: string;
  start_location_id?: string;
  additional?: string;
}

export interface AbilityEntry {
  id: string;
  name: string;
  description: string;
  source: string;
}

export interface PowerModifier {
  id: string;
  value: number;
  reason: string;
  temporary: boolean;
}

export interface CharacterState {
  id: string;
  identity: StoryIdentity;
  attributes: Record<"con" | "int" | "cha", AttributeValue>;
  resources: Record<"hp" | "mp" | "sp" | "st", ResourceValue>;
  rank: number;
  exp: number;
  exp_to_next: number | null;
  breakthrough_eligible: boolean;
  base_power: number;
  equipment_power: number;
  effective_power: number;
  power_modifiers: PowerModifier[];
  conditions: Record<string, {
    id: string;
    name: string;
    description: string;
    temporary: boolean;
    expires_at: string | null;
    source: string;
  }>;
  profession: string | null;
  growth_path: string | null;
  talents: AbilityEntry[];
  skills: AbilityEntry[];
  alive: boolean;
  status: string;
  state_version?: number;
}

export interface StoryLocation {
  id: string;
  name: string;
  type?: string;
  scope?: "world" | "region" | "place";
  parent_id?: string | null;
  region_id?: string;
  jurisdiction_id?: ReputationKey | null;
  description?: string;
  canonical?: boolean;
  created_turn_version_id?: string | null;
  safeguards?: string[];
  legacy_start_protection?: boolean;
  prerequisite?: StartPrerequisite;
}

export interface StoryState {
  schema_version: "story-state/1";
  state_version: number;
  content_revision_id: string;
  current_turn_id: string | null;
  narration: StoryNarrationSettings;
  time: { label: string; elapsed_minutes: number };
  location: StoryLocation;
  character: CharacterState;
  inventory: Record<string, InventoryItem>;
  currency_copper: number;
  quests: Record<string, Quest>;
  regional_quests: Record<string, Quest>;
  bonds: Record<string, Bond>;
  reputations: Record<ReputationKey, Reputation>;
  locations: Record<string, StoryLocation>;
  location_statuses: Record<string, {
    status: string;
    accessible: boolean;
    description: string;
    reason: string;
  }>;
  world_flags: Record<string, string | number | boolean | null>;
}

export interface SuggestedOption {
  id: string;
  text: string;
  intent: string;
}

export interface AuthoritativeChange {
  kind: string;
  key: string;
  old: unknown;
  new: unknown;
  reason: string;
  display_name?: string;
  force_display?: boolean;
  old_level?: string;
  new_level?: string;
}

export interface TurnVersion {
  id: string;
  version_number: number;
  prompt_version: string;
  content_revision_id: string;
  model: string;
  created_at: string;
}

export interface Turn {
  id: string;
  save_id: string;
  sequence: number;
  current_version_id: string;
  action_type: "opening" | "turn" | "intervene" | "reshape";
  action: Record<string, unknown>;
  title: string;
  body: string;
  summary: string;
  suggested_options: SuggestedOption[];
  authoritative_changes: AuthoritativeChange[];
  warnings?: string[];
  state_version_before: number;
  state_version_after: number;
  created_at: string;
  updated_at: string;
  versions?: TurnVersion[];
}

export type NarrativeJobType = "opening" | "turn" | "intervene" | "reshape" | "turns_to_arc" | "arcs_to_arc";

export interface NarrativeJob {
  id: string;
  save_id: string;
  request_id: string;
  type: NarrativeJobType;
  source_state_version: number;
  target_turn_id: string | null;
  status: JobStatus;
  error: ApiProblem | null;
  result: { turn_id?: string; sequence?: number; state_version?: number; story_arc_id?: string; start_sequence?: number; end_sequence?: number } | null;
  context_manifest: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface StoryView {
  state: StoryState;
  latest_turn: Turn | null;
  active_job: NarrativeJob | null;
  active_arc_job: NarrativeJob | null;
  start_prerequisite: StartPrerequisite | null;
  can_open: boolean;
  can_act: boolean;
  can_reshape: boolean;
}

export interface InventoryItem {
  id: string;
  name: string;
  description: string;
  quantity: number;
  power: number;
  power_class: "ordinary" | "high_rank" | "exceptional";
  power_basis: string;
  equipped: boolean;
  source: string;
}

export interface InventoryProjection {
  items: InventoryItem[];
  currency_copper: number;
  currency: { gold: number; silver: number; copper: number };
  state_version: number;
}

export type QuestStatus = "untriggered" | "eligible" | "offered" | "active" | "completed" | "declined" | "failed" | "abandoned";

export interface Quest {
  id: string;
  name: string;
  description: string;
  status: QuestStatus;
  progress: string;
  objectives: string[];
  regional: boolean;
  breakthrough?: boolean;
}

export interface QuestProjection {
  active: Quest[];
  state_version: number;
}

export interface JournalEntry {
  turn_id: string;
  sequence: number;
  title: string;
  summary: string;
  location_id: string;
  time_label: string;
  changes: AuthoritativeChange[];
}

export interface MemoryEntry {
  id: string;
  memory_number: number;
  save_id: string;
  status: "active" | "resolved" | "superseded";
  kind: string;
  summary: string;
  importance: number;
  people: string[];
  locations: string[];
  keywords: string[];
  facts: string[];
  unresolved: string[];
  superseded_by: string | null;
  source_turn_id: string;
  source_turn_version_id: string;
  updated_at: string;
  recall_reason?: string;
}

export interface StoryArc {
  id: string;
  level: number;
  start_sequence: number;
  end_sequence: number;
  title: string;
  summary: string;
  key_events: string[];
  unresolved: string[];
  status: "current" | "superseded";
  job_id: string;
  created_at: string;
}

export interface MemoryProjection {
  recent_full_turns: Turn[];
  summary_buffer: Turn[];
  story_arcs: StoryArc[];
  policy: { recent_full_count: number; arc_turn_count: number; original_history_preserved: boolean };
}

export interface Bond {
  id: string;
  npc_id: string;
  npc_name: string;
  value: number;
  relation_type: string;
  listed: boolean;
  level?: string;
}

export type ReputationKey =
  | "continental_overall"
  | "court_of_veiled_night"
  | "skycrown_conclave"
  | "holy_see_sacred_radiance"
  | "court_of_sacred_tree"
  | "valkeren_empire"
  | "southern_maritime_federation";

export interface Reputation {
  key: ReputationKey;
  value: number;
  level: string;
}

export interface ReputationProjection {
  items: Reputation[];
  primary_key: ReputationKey;
  local_modifier_key: ReputationKey | null;
  state_version: number;
}

export interface GameProjections {
  character: CharacterState;
  inventory: InventoryProjection;
  quests: QuestProjection;
  journals: PaginatedResult<JournalEntry>;
  memory: MemoryProjection;
  memories: { items: MemoryEntry[] };
  bonds: { items: Bond[]; state_version: number };
  reputations: ReputationProjection;
}

export interface ImportPreview {
  valid: boolean;
  schema_version?: number;
  source_save_id?: string;
  save_name?: string;
  character_name?: string | null;
  phase?: SavePhase;
  ruleset_version?: string;
  warnings?: string[];
  confirmation_required?: boolean;
  content_revision?: ImportContentRevision | null;
}

export interface ImportRevisionDocument {
  document_id: string;
  source_path: string;
  raw_sha256: string;
  text_sha256: string;
  byte_count: number;
}

export interface ImportContentRevision {
  revision_id: string;
  prompt_version?: string | null;
  documents: ImportRevisionDocument[];
}

export interface PendingImport {
  status: "pending";
  pending_import_id: string;
  revision_id: string;
  expires_at: string;
  confirmation_required: true;
  content_revision: ImportContentRevision;
  result: SaveSummary | null;
}

export type ImportResult = SaveSummary | PendingImport;

export function isPendingImport(result: ImportResult): result is PendingImport {
  return "status" in result && result.status === "pending";
}

export interface PaginationOptions {
  cursor: number;
  limit: number;
}

export interface PaginatedResult<T> {
  items: T[];
  next_cursor?: number | null;
}

export const emptyDraft = (): CharacterDraft => ({
  race_id: "",
  race_branch_id: null,
  name: "",
  gender: "",
  age: null,
  appearance: "",
  personality: "",
  rank: null,
  talent: "",
  background: "",
  location_id: "",
  additional: "",
  current_step: 1,
  draft_revision: 0,
});

export interface LogicalRequestIdentity {
  payload_key: string;
  request_id: string;
}

export function logicalRequestIdentity(
  current: LogicalRequestIdentity | null,
  payloadKey: string,
  createId: () => string = () => crypto.randomUUID(),
): LogicalRequestIdentity {
  return current?.payload_key === payloadKey
    ? current
    : { payload_key: payloadKey, request_id: createId() };
}

export const phaseLabel: Record<SavePhase, string> = {
  draft: "创建中",
  review: "待确认",
  ready: "已就绪",
};

export const jobLabel: Record<JobStatus, string> = {
  queued: "等待生成",
  running: "正在生成",
  succeeded: "生成完成",
  failed: "生成失败",
  cancel_requested: "正在取消",
  cancelled: "已取消",
  stale: "结果已过期",
  interrupted: "生成已中断",
};

export function appendPreset(current: string, value: string): string {
  const normalized = value.trim();
  if (!normalized) return current;
  const parts = current
    .split(/[、,，;；\n]/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.includes(normalized)) return current;
  return [...parts, normalized].join("、");
}

export function mediaPictureSources(
  media: MediaPaths,
): Array<{ media: string; srcSet: string }> {
  return [
    { media: "(max-width: 700px)", srcSet: media.image_portrait_path },
    { media: "(min-width: 701px)", srcSet: media.image_landscape_path },
  ];
}

export function chineseRankNumeral(rank: number): string {
  return ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][rank - 1] ?? String(rank);
}

export function selectedRaceBranch(
  race: Pick<RaceDefinition, "branches"> | undefined,
  branchId: string | null | undefined,
): RaceBranch | undefined {
  return branchId ? race?.branches?.find((branch) => branch.id === branchId) : undefined;
}

export function saveRoute(save: SaveSummary): string {
  if (save.phase === "ready") return `/saves/${save.id}/game`;
  if (save.phase === "review") return `/saves/${save.id}/review`;
  const step = Math.min(13, Math.max(1, save.current_step ?? 1));
  return `/saves/${save.id}/create/${step}`;
}
