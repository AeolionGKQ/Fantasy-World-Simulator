import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { canMutateModelSettings, canStartSettingRequest, invalidateModelCapabilities, isCurrentModelTestResponse, mergeModelTestCapability, mergeSavedModelSettings, mergeSavedNarrationSettings, modelCapabilityKey, resetStructuredOutputCapability, structuredOutputProbePayload, thinkingCapabilityMessage, thinkingStrategyLabel } from "./App";
import { formatChange, isNarrativeJobActive, isStoryReadOnly, orderReputations, questProjectionFromResponse, reputationNames, resourceCondition, resourceExhaustion, validateArcSelection } from "./game/helpers";
import {
  appendPreset,
  chineseRankNumeral,
  emptyDraft,
  groupPresets,
  logicalRequestIdentity,
  mediaPictureSources,
  normalizeAppSettings,
  saveRoute,
  selectedRaceBranch,
  type AppSettings,
  type ModelTestResult,
  type RaceDefinition,
  type ThinkingStrategy,
} from "./types";

afterEach(() => vi.unstubAllGlobals());

describe("appendPreset", () => {
  it("追加并去重预设词", () => {
    expect(appendPreset("银发、长耳", "沉静目光")).toBe("银发、长耳、沉静目光");
    expect(appendPreset("银发、长耳", "银发")).toBe("银发、长耳");
  });

  it("按外貌维度分组并保留输入顺序", () => {
    expect(groupPresets([
      { id: "black", label: "黑发", category: "发色" },
      { id: "blue", label: "蓝色眼眸", category: "眼眸" },
      { id: "long", label: "长发", category: "发型" },
      { id: "silver", label: "银发", category: "发色" },
    ])).toEqual([
      { category: "发色", items: [{ id: "black", label: "黑发", category: "发色" }, { id: "silver", label: "银发", category: "发色" }] },
      { category: "眼眸", items: [{ id: "blue", label: "蓝色眼眸", category: "眼眸" }] },
      { category: "发型", items: [{ id: "long", label: "长发", category: "发型" }] },
    ]);
  });

  it("按性格和天赋类别使用同一分组逻辑", () => {
    expect(groupPresets([
      { id: "calm", label: "沉着", category: "处世基调" },
      { id: "sense", label: "魔力感知敏锐", category: "魔力与施法" },
      { id: "direct", label: "直率", category: "社交方式" },
    ]).map((group) => group.category)).toEqual(["处世基调", "魔力与施法", "社交方式"]);
  });
});

describe("saveRoute", () => {
  it("按存档阶段选择目标页面", () => {
    expect(saveRoute({ id: "a", name: "A", phase: "draft", revision: 1 })).toBe(
      "/saves/a/create/1",
    );
    expect(saveRoute({ id: "b", name: "B", phase: "ready", revision: 2 })).toBe(
      "/saves/b/game",
    );
    expect(saveRoute({ id: "c", name: "C", phase: "draft", revision: 2, current_step: 9 })).toBe(
      "/saves/c/create/9",
    );
  });
});

describe("race catalog helpers", () => {
  const race = {
    image_landscape_path: "/assets/world/races/therian-landscape.webp",
    image_portrait_path: "/assets/world/races/therian-portrait.webp",
    branches: [
      { id: "orc", name: "兽人", ranks: [{ rank: 1, title: null }] },
      { id: "half_orc", name: "半兽人", ranks: [{ rank: 1, title: "初阶者" }] },
    ],
  } as RaceDefinition;

  it("为种族、地点和势力统一生成响应式图片 source", () => {
    expect(mediaPictureSources(race)).toEqual([
      { media: "(max-width: 700px)", srcSet: "/assets/world/races/therian-portrait.webp" },
      { media: "(min-width: 701px)", srcSet: "/assets/world/races/therian-landscape.webp" },
    ]);
    for (const kind of ["locations", "factions"]) {
      expect(mediaPictureSources({
        image_landscape_path: `/assets/world/${kind}/entry-landscape.webp`,
        image_portrait_path: `/assets/world/${kind}/entry-portrait.webp`,
      })).toEqual([
        { media: "(max-width: 700px)", srcSet: `/assets/world/${kind}/entry-portrait.webp` },
        { media: "(min-width: 701px)", srcSet: `/assets/world/${kind}/entry-landscape.webp` },
      ]);
    }
  });

  it("把后端整数阶位转换为中文数字", () => {
    expect([1, 2, 9, 10].map(chineseRankNumeral)).toEqual(["一", "二", "九", "十"]);
    expect(chineseRankNumeral(11)).toBe("11");
  });

  it("只返回当前选择的兽裔分支", () => {
    expect(selectedRaceBranch(race, "half_orc")?.name).toBe("半兽人");
    expect(selectedRaceBranch(race, null)).toBeUndefined();
    expect(selectedRaceBranch(race, "missing")).toBeUndefined();
  });
});

describe("API DTO contracts", () => {
  it("默认关闭未声明或未验证支持的结构化输出", () => {
    const settings = {
      model: { base_url: "https://example.test/v1", model: "model", api_key_configured: false,
        timeout_seconds: 30, structured_output: true, thinking_enabled: true, max_concurrency: 1,
        thinking_capability: "unknown" as const, thinking_strategy: null,
        thinking_confidence: "unknown" as const },
      narration: { pace: "dynamic" as const, tendency: "balanced" as const, detail: "standard" as const },
      revision: 1,
    };
    expect(normalizeAppSettings(settings).model).toEqual(expect.objectContaining({
      structured_output: false, structured_output_capability: "unknown",
    }));
  });

  it("发送设置修订和页面中的未保存模型值", async () => {
    const payload = {
      model: { base_url: "https://draft.example/v1", model: "draft-model", api_key_configured: false,
        timeout_seconds: 17, structured_output: true, thinking_enabled: false, max_concurrency: 16,
        thinking_capability: "controlled", thinking_strategy: "enable_thinking", thinking_confidence: "verified" },
      narration: { pace: "dynamic", tendency: "balanced", detail: "standard" }, revision: 4,
    };
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(payload), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await api.testModel({ base_url: "https://draft.example/v1", model: "draft-model",
      timeout_seconds: 17, structured_output: true, thinking_enabled: false, max_concurrency: 16,
      api_key: "draft-key", force_thinking_probe: true });
    await api.updateModel({ base_url: "https://draft.example/v1", model: "draft-model",
      timeout_seconds: 17, structured_output: true, thinking_enabled: false, max_concurrency: 16,
      structured_output_probe_token: "probe-proof" }, 3, "model-request");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(expect.objectContaining({
      base_url: "https://draft.example/v1", model: "draft-model", api_key: "draft-key",
      max_concurrency: 16, structured_output: true, thinking_enabled: false, force_thinking_probe: true,
    }));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual(expect.objectContaining({
      expected_revision: 3, request_id: "model-request",
      structured_output_probe_token: "probe-proof",
    }));
  });

  it("开启结构化输出时发送立即探测标志和未保存设置", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true, message: "ok", thinking_capability: "unknown", thinking_confidence: "unknown",
      thinking_message: "unknown", structured_output_capability: "supported",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const payload = structuredOutputProbePayload({ base_url: "https://draft.example/v1", model: "draft-model",
      api_key: "draft-key", timeout_seconds: 47, max_concurrency: 6, thinking_enabled: false,
      structured_output: false });
    await api.testModel(payload);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      base_url: "https://draft.example/v1", model: "draft-model", api_key: "draft-key",
      timeout_seconds: 47, max_concurrency: 6, thinking_enabled: false,
      structured_output: false, probe_structured_output: true,
    });
  });

  it("转换草稿、生成、删除和导入请求的 wire 字段", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const draft = { ...emptyDraft(), background: "身世", location_id: "san_velia", draft_revision: 2 };
    await api.saveDraft("save", draft, 7, "draft-request");
    await api.startGeneration("save", 3, 8, "调整", "generation-request");
    await api.deleteSave("save", 9, "delete-request");
    await api.importSave({ format: "fantasy-simulator-save" }, "import-request");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(expect.objectContaining({
      background: "身世", location_id: "san_velia", draft_revision: 2,
      expected_save_revision: 7, request_id: "draft-request",
    }));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      draft_revision: 3, expected_save_revision: 8, feedback: "调整", request_id: "generation-request",
    });
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      expected_revision: 9, request_id: "delete-request", confirm: true,
    });
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({
      payload: { format: "fantasy-simulator-save" }, request_id: "import-request",
    });
  });

  it("接收思考能力探测 DTO 并提供三态文案", () => {
    const result: ModelTestResult = {
      ok: true, message: "连接测试通过", model_available: true,
      thinking_capability: "controlled", thinking_strategy: "bundle",
      thinking_confidence: "accepted_bundle",
      thinking_message: "服务接受兼容参数组合，无法逐项证明。",
    };
    expect(result.thinking_confidence).toBe("accepted_bundle");
    expect(thinkingCapabilityMessage("unknown", "unknown")).toContain("先测试连接");
    expect(thinkingCapabilityMessage("unsupported", "unsupported")).toContain("不支持关闭思考");
    expect(thinkingCapabilityMessage("controlled", "accepted_bundle", "bundle")).toContain("无法逐项证明");
    const newStrategies: ThinkingStrategy[] = ["reasoning_enabled", "reasoning_effort_nested", "thinking_budget"];
    expect(newStrategies.map(thinkingStrategyLabel)).toEqual([
      "reasoning.enabled", "reasoning.effort", "thinking_config.thinking_budget",
    ]);
    expect(thinkingStrategyLabel("bundle")).toBe("七种兼容参数组合");
  });

  it("叙事写请求始终携带状态版本和请求 ID", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await api.startOpening("save", 4, "引导", "opening-id");
    await api.startTurn("save", 5, "前进", "walk", "turn-id");
    await api.intervene("save", 6, "降下雨幕", "intervene-id");
    await api.reshape("save", "turn-1", 7, "改写结果", "reshape-id");
    await api.cancelNarrativeJob("save", "job-1", 8, "cancel-id");
    await api.createStoryArc("save", 9, "arc-id");
    await api.mergeStoryArcs("save", 10, ["arc-1", "arc-2"], "merge-id");
    expect(fetchMock.mock.calls.map((call) => JSON.parse(call[1].body))).toEqual([
      { request_id: "opening-id", expected_state_version: 4, guidance: "引导" },
      { request_id: "turn-id", expected_state_version: 5, action: "前进", option_id: "walk" },
      { request_id: "intervene-id", expected_state_version: 6, guidance: "降下雨幕" },
      { request_id: "reshape-id", expected_state_version: 7, guidance: "改写结果" },
      { request_id: "cancel-id", expected_state_version: 8 },
      { request_id: "arc-id", expected_state_version: 9 },
      { request_id: "merge-id", expected_state_version: 10, arc_ids: ["arc-1", "arc-2"] },
    ]);
  });

  it("发送起点前置处理 payload", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ resolved: true }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await api.resolveStartPrerequisite("save", 2, "accept_legacy_protection", null, "legacy-id");
    await api.resolveStartPrerequisite("save", 3, "relocate", "selavia_port", "relocate-id");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      request_id: "legacy-id", expected_state_version: 2,
      resolution: "accept_legacy_protection", location_id: null,
    });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      request_id: "relocate-id", expected_state_version: 3,
      resolution: "relocate", location_id: "selavia_port",
    });
  });

  it("大存档使用直接 JSON body 与请求 ID header", async () => {
    const file = new File(['{"format":"fantasy-simulator-save","schema_version":2}'], "save.json", { type: "application/json", lastModified: 42 });
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ id: "save" }), {
      status: 201, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await api.validateLargeImport(file);
    await api.importLargeSave(file, "large-import-id");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/imports/validate");
    expect(fetchMock.mock.calls[0][1].body).toBe(file);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/imports");
    expect(fetchMock.mock.calls[1][1].body).toBe(file);
    const headers = fetchMock.mock.calls[1][1].headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-Request-Id")).toBe("large-import-id");
  });

  it("待信任导入发送确认版本和稳定请求 ID", async () => {
    const pending = {
      status: "pending" as const, pending_import_id: "pending-1", revision_id: "revision-1",
      expires_at: "2026-09-28T12:00:00Z", confirmation_required: true as const,
      content_revision: { revision_id: "revision-1", prompt_version: "gm-v2", documents: [{
        document_id: "doc-1", source_path: "content/rules.md", raw_sha256: "a".repeat(64),
        text_sha256: "b".repeat(64), byte_count: 42,
      }] }, result: null,
    };
    expect(pending.content_revision.documents[0].byte_count).toBe(42);
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "save" }), {
      status: 201, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await api.trustAndImport(pending.pending_import_id, pending.revision_id, "trust-id");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/imports/pending-1/trust-and-import");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      request_id: "trust-id", confirm_revision_id: "revision-1", confirm: true,
    });
  });

  it("分页接口按需附加 cursor 和 limit", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [], next_cursor: 50 }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    expect((await api.listTurns("save", undefined, { cursor: 0, limit: 50 })).next_cursor).toBe(50);
    await api.getJournals("save", undefined, { cursor: 50, limit: 25 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/saves/save/turns?cursor=0&limit=50");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/saves/save/journals?cursor=50&limit=25");
  });

  it("仅把匹配 endpoint+model 的测试能力合并到当前设置", () => {
    const current = {
      model: { base_url: "https://current.example/v1/", model: "model-a", api_key_configured: false,
        timeout_seconds: 99, structured_output: false, thinking_enabled: false, max_concurrency: 7,
        structured_output_capability: "unknown" as const,
        thinking_capability: "unknown" as const, thinking_strategy: null,
        thinking_confidence: "unknown" as const },
      narration: { pace: "dynamic" as const, tendency: "balanced" as const, detail: "standard" as const },
      revision: 12,
    };
    const result: ModelTestResult = { ok: true, message: "ok", thinking_capability: "controlled",
      thinking_strategy: "reasoning_effort", thinking_confidence: "verified", thinking_message: "verified" };
    const merged = mergeModelTestCapability(current,
      modelCapabilityKey(" https://current.example/v1", "model-a"), result)!;
    expect(merged.revision).toBe(12);
    expect(merged.model.timeout_seconds).toBe(99);
    expect(merged.model.thinking_enabled).toBe(false);
    expect(merged.model.thinking_strategy).toBe("reasoning_effort");
    expect(mergeModelTestCapability(current,
      modelCapabilityKey("https://old.example/v1", "model-a"), result)).toBe(current);
  });

  it("仅在结构化输出探测成功后开启，并保留用户同时编辑的字段", () => {
    const current = {
      model: { base_url: "https://current.example/v1", model: "model-a", api_key_configured: false,
        timeout_seconds: 91, structured_output: false, structured_output_capability: "unknown" as const,
        thinking_enabled: false, max_concurrency: 9, thinking_capability: "unknown" as const,
        thinking_strategy: null, thinking_confidence: "unknown" as const },
      narration: { pace: "dynamic" as const, tendency: "balanced" as const, detail: "standard" as const },
      revision: 5,
    };
    const supported: ModelTestResult = { ok: true, message: "ok", thinking_capability: "controlled",
      thinking_strategy: "enable_thinking", thinking_confidence: "verified", thinking_message: "verified",
      structured_output_capability: "supported", structured_output_message: "supported",
      structured_output_probed_at: "2026-09-28T12:00:00Z",
      structured_output_probe_token: "probe-proof" };
    const merged = mergeModelTestCapability(current, modelCapabilityKey(current.model.base_url, current.model.model), supported, true)!;
    expect(merged.model).toEqual(expect.objectContaining({
      structured_output: true, structured_output_capability: "supported",
      structured_output_message: "supported", structured_output_probe_token: "probe-proof",
      timeout_seconds: 91, max_concurrency: 9,
    }));

    const unsupported = mergeModelTestCapability(current, modelCapabilityKey(current.model.base_url, current.model.model),
      { ...supported, structured_output_capability: "unsupported", structured_output_message: "not supported" }, true)!;
    expect(unsupported.model).toEqual(expect.objectContaining({
      structured_output: false, structured_output_capability: "unsupported",
    }));
    const cachedSupported = { ...current, model: { ...current.model,
      structured_output: true, structured_output_capability: "supported" as const } };
    const ordinaryResult = mergeModelTestCapability(cachedSupported,
      modelCapabilityKey(current.model.base_url, current.model.model),
      { ...supported, structured_output_capability: "unknown" })!;
    expect(ordinaryResult.model).toEqual(expect.objectContaining({
      structured_output: true, structured_output_capability: "supported",
    }));
  });

  it("探测异常、模型身份变化和过期响应都不能开启结构化输出", () => {
    const model = {
      base_url: "https://old.example/v1", model: "model-a", api_key_configured: false,
      timeout_seconds: 30, structured_output: true, structured_output_capability: "supported" as const,
      structured_output_probe_token: "old-proof",
      thinking_enabled: false, max_concurrency: 2, thinking_capability: "controlled" as const,
      thinking_strategy: "enable_thinking" as const, thinking_confidence: "verified" as const,
    };
    expect(resetStructuredOutputCapability({ model, narration: { pace: "dynamic", tendency: "balanced", detail: "standard" }, revision: 1 }, "timeout")!.model)
      .toEqual(expect.objectContaining({ structured_output: false, structured_output_capability: "unknown", structured_output_message: "timeout" }));
    expect(invalidateModelCapabilities({ ...model, base_url: "https://new.example/v1" }))
      .toEqual(expect.objectContaining({ structured_output: false, structured_output_capability: "unknown",
        structured_output_probe_token: undefined }));
    const current = { model: { ...model, base_url: "https://new.example/v1", structured_output: false,
      structured_output_capability: "unknown" as const }, narration: { pace: "dynamic" as const,
      tendency: "balanced" as const, detail: "standard" as const }, revision: 1 };
    const oldKey = modelCapabilityKey("https://old.example/v1", "model-a");
    expect(isCurrentModelTestResponse(current, oldKey, 4, 4)).toBe(false);
    expect(isCurrentModelTestResponse(current, modelCapabilityKey(current.model.base_url, current.model.model), 3, 4)).toBe(false);
    const staleResult: ModelTestResult = { ok: true, message: "ok", thinking_capability: "controlled",
      thinking_confidence: "verified", thinking_message: "ok", structured_output_capability: "supported" };
    expect(mergeModelTestCapability(current, oldKey, staleResult, true)).toBe(current);
  });

  it("模型保存和探测期间锁定所有模型设置变更", () => {
    expect(canMutateModelSettings("idle", "idle")).toBe(true);
    expect(canMutateModelSettings("saved", "idle")).toBe(true);
    expect(canMutateModelSettings("saving", "idle")).toBe(false);
    expect(canMutateModelSettings("idle", "testing")).toBe(false);
    expect(canMutateModelSettings("idle", "probing")).toBe(false);
  });

  it("按分区合并保存响应并更新 revision", () => {
    const current: AppSettings = {
      model: { base_url: "https://draft.example/v1", model: "draft-model", api_key_configured: true,
        timeout_seconds: 45, structured_output: true, structured_output_capability: "supported",
        structured_output_probe_token: "current-probe-token", thinking_enabled: false, max_concurrency: 4,
        thinking_capability: "controlled", thinking_strategy: "enable_thinking", thinking_confidence: "verified" },
      narration: { pace: "slow", tendency: "casual", detail: "detailed" },
      revision: 8,
    };
    const modelResponse: AppSettings = {
      model: { ...current.model, model: "saved-model", api_key_mask: "****" },
      narration: { pace: "fast", tendency: "combat", detail: "concise" },
      revision: 9,
    };
    const savedModel = mergeSavedModelSettings(current, modelResponse);
    expect(savedModel.model).toBe(modelResponse.model);
    expect(savedModel.narration).toBe(current.narration);
    expect(savedModel.revision).toBe(9);

    const narrationResponse: AppSettings = {
      model: { ...current.model, model: "stale-server-model", structured_output_probe_token: undefined },
      narration: { pace: "dynamic", tendency: "balanced", detail: "standard" },
      revision: 10,
    };
    const savedNarration = mergeSavedNarrationSettings(current, narrationResponse);
    expect(savedNarration.narration).toBe(narrationResponse.narration);
    expect(savedNarration.model).toBe(current.model);
    expect(savedNarration.model.model).toBe("draft-model");
    expect(savedNarration.model.structured_output_probe_token).toBe("current-probe-token");
    expect(savedNarration.revision).toBe(10);
  });

  it("任一设置请求进行中时不允许开始另一请求", () => {
    expect(canStartSettingRequest("idle", "idle", "idle")).toBe(true);
    expect(canStartSettingRequest("saving", "idle", "idle")).toBe(false);
    expect(canStartSettingRequest("idle", "saving", "idle")).toBe(false);
    expect(canStartSettingRequest("idle", "idle", "testing")).toBe(false);
    expect(canStartSettingRequest("idle", "idle", "probing")).toBe(false);
  });
});

describe("game workspace helpers", () => {
  it("声望固定排序并只标记当前地区补正", () => {
    const items = [
      { key: "southern_maritime_federation" as const, value: 20, level: "中立" },
      { key: "continental_overall" as const, value: 5, level: "中立" },
      { key: "court_of_veiled_night" as const, value: 0, level: "中立" },
    ];
    const sorted = orderReputations(items, "southern_maritime_federation");
    expect(sorted.map((item) => item.key)).toEqual([
      "continental_overall", "court_of_veiled_night", "southern_maritime_federation",
    ]);
    expect(sorted.filter((item) => item.local).map((item) => item.key)).toEqual(["southern_maritime_federation"]);
  });

  it("格式化权威变化中的层级和基础值", () => {
    expect(formatChange({ kind: "resource", key: "hp", old: 100, new: 72, reason: "受伤" })).toEqual({
      label: "资源 · 生命", value: "100 → 72", reason: "受伤",
    });
    expect(formatChange({ kind: "reputation", key: "continental_overall", old: 0, new: 30,
      old_level: "中立", new_level: "声名良好", reason: "公开善举" }).value).toBe("中立 → 声名良好");
  });

  it("历史节点只读，活动任务锁定最新节点", () => {
    const turn = { id: "old" } as Parameters<typeof isStoryReadOnly>[0];
    expect(isStoryReadOnly(turn, "latest", null)).toBe(true);
    expect(isStoryReadOnly({ id: "latest" } as typeof turn, "latest", null)).toBe(false);
    const job = { status: "running" } as Parameters<typeof isNarrativeJobActive>[0];
    expect(isNarrativeJobActive(job)).toBe(true);
    expect(isStoryReadOnly({ id: "latest" } as typeof turn, "latest", job)).toBe(true);
  });

  it("按真实任务响应只保留进行中任务", () => {
    const response = questProjectionFromResponse({ active: [{ id: "quest.active", name: "巡查",
      description: "检查城门", status: "active", progress: "东门", objectives: ["检查西门"], regional: false }],
      state_version: 3 });
    expect(response).toEqual({ active: [expect.objectContaining({ id: "quest.active" })], state_version: 3 });
    expect("terminal" in response).toBe(false);
    expect(questProjectionFromResponse({ state_version: 4 })).toEqual({ active: [], state_version: 4 });
  });

  it("同一逻辑请求复用 ID，payload 变化后换 ID", () => {
    const ids = ["request-a", "request-b"];
    const createId = () => ids.shift()!;
    const first = logicalRequestIdentity(null, "same-payload", createId);
    const retry = logicalRequestIdentity(first, "same-payload", createId);
    const changed = logicalRequestIdentity(retry, "changed-payload", createId);
    expect(retry).toBe(first);
    expect(retry.request_id).toBe("request-a");
    expect(changed.request_id).toBe("request-b");
  });

  it("按资源比例边界返回固定状态并保留耗尽语义", () => {
    expect([75, 50, 25, 1, 0].map((value) => resourceCondition(value, 100))).toEqual([
      "状态良好", "轻度影响", "明显影响", "严重影响", "耗尽",
    ]);
    expect(resourceExhaustion.hp).toContain("死亡");
    expect(resourceExhaustion.mp).toContain("魔力供能");
    expect(resourceExhaustion.sp).toContain("意识崩溃");
    expect(resourceExhaustion.st).toContain("高强度活动");
  });

  it("只允许选择两个以上连续的当前故事弧", () => {
    const arcs = [
      { id: "a", start_sequence: 1, end_sequence: 25, status: "current" },
      { id: "b", start_sequence: 26, end_sequence: 50, status: "current" },
      { id: "c", start_sequence: 76, end_sequence: 100, status: "current" },
    ] as Parameters<typeof validateArcSelection>[0];
    expect(validateArcSelection(arcs, ["a"]).valid).toBe(false);
    expect(validateArcSelection(arcs, ["a", "b"])).toEqual({ valid: true, message: "将合并 2 个连续故事弧。" });
    expect(validateArcSelection(arcs, ["a", "c"]).message).toContain("首尾连续");
  });

  it("固定声望键映射到准确中文名称", () => {
    expect(reputationNames).toEqual({
      continental_overall: "大陆综合",
      court_of_veiled_night: "幽夜王庭",
      skycrown_conclave: "天穹议庭",
      holy_see_sacred_radiance: "圣辉教廷",
      court_of_sacred_tree: "圣树王庭",
      valkeren_empire: "瓦尔凯伦帝国",
      southern_maritime_federation: "南海自由联邦",
    });
  });
});
