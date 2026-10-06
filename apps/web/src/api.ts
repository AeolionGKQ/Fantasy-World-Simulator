import type {
  ApiProblem,
  AppSettings,
  CharacterCandidate,
  CharacterDraft,
  ConfirmedCharacterBootstrap,
  GameBootstrap,
  GameProjections,
  GenerationJob,
  ImportPreview,
  ImportResult,
  NarrativeJob,
  ModelSettings,
  ImageModelSettings,
  ImageQuality,
  ImageSize,
  SceneImageSession,
  ModelTestResult,
  NarrationSettings,
  SaveSummary,
  StartPrerequisiteResolution,
  StartPrerequisiteResult,
  StoryView,
  Turn,
  PaginatedResult,
  JournalEntry,
  WorldCatalog,
} from "./types";
import { normalizeAppSettings } from "./types";
import { questProjectionFromResponse } from "./game/helpers";

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ApiProblem;

  constructor(status: number, problem: ApiProblem) {
    super(problem.message || "请求失败");
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  directBody?: BodyInit;
}

function paginationQuery(options?: { cursor: number; limit: number }): string {
  return options ? `?cursor=${encodeURIComponent(options.cursor)}&limit=${encodeURIComponent(options.limit)}` : "";
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body: bodyValue, directBody, ...fetchOptions } = options;
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  let body: BodyInit | undefined;
  if (directBody !== undefined) {
    headers.set("Content-Type", "application/json");
    body = directBody;
  } else if (bodyValue !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(bodyValue);
  }

  let response: Response;
  try {
    response = await fetch(path, { ...fetchOptions, headers, body });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, {
      code: "network_error",
      message: "无法连接后端。请确认 API 服务已启动后重试。",
      retryable: true,
    });
  }

  if (!response.ok) {
    let problem: ApiProblem = {
      code: `http_${response.status}`,
      message: `请求失败（HTTP ${response.status}）`,
      retryable: response.status >= 500,
    };
    try {
      const payload = (await response.json()) as ApiProblem | { error?: ApiProblem; detail?: unknown };
      if ("error" in payload && payload.error) problem = payload.error;
      else if ("code" in payload && "message" in payload) problem = payload as ApiProblem;
      else if ("detail" in payload && typeof payload.detail === "string") {
        problem.message = payload.detail;
      }
    } catch {
      // Keep the stable HTTP fallback when a proxy returns non-JSON content.
    }
    throw new ApiError(response.status, problem);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function unwrapList(payload: SaveSummary[] | { items: SaveSummary[] }): SaveSummary[] {
  return Array.isArray(payload) ? payload : payload.items;
}

export const api = {
  getCatalog: (signal?: AbortSignal) =>
    request<WorldCatalog>("/api/world/catalog", { signal }),

  getSettings: async () => normalizeAppSettings(await request<AppSettings>("/api/settings")),
  updateModel: (settings: Pick<ModelSettings, "base_url" | "model" | "timeout_seconds" | "structured_output" | "thinking_enabled" | "max_concurrency"> & { protocol?: ModelSettings["protocol"]; api_key?: string; structured_output_probe_token?: string }, expectedRevision: number, requestId: string) =>
    request<AppSettings>("/api/settings/model", {
      method: "PUT",
      body: { ...settings, expected_revision: expectedRevision, request_id: requestId },
    }).then(normalizeAppSettings),
  testModel: (settings: Pick<ModelSettings, "base_url" | "model" | "timeout_seconds" | "structured_output" | "thinking_enabled" | "max_concurrency"> & { protocol?: ModelSettings["protocol"]; api_key?: string; force_thinking_probe?: boolean; probe_structured_output?: boolean }) =>
    request<ModelTestResult>("/api/settings/model/test", { method: "POST", body: settings }),
  updateNarration: (settings: NarrationSettings, expectedRevision: number, requestId: string) =>
    request<AppSettings>("/api/settings/narration", {
      method: "PUT",
      body: { ...settings, expected_revision: expectedRevision, request_id: requestId },
    }).then(normalizeAppSettings),
  updateImageModel: (settings: Pick<ImageModelSettings, "base_url" | "model" | "timeout_seconds"> & { api_key?: string }, expectedRevision: number, requestId: string) =>
    request<AppSettings>("/api/settings/image-model", { method: "PUT",
      body: { ...settings, expected_revision: expectedRevision, request_id: requestId } }).then(normalizeAppSettings),
  testImageModel: (settings: Pick<ImageModelSettings, "base_url" | "model" | "timeout_seconds"> & { api_key?: string }) =>
    request<{ ok: boolean; message: string }>("/api/settings/image-model/test", { method: "POST", body: settings }),

  listSaves: async () => unwrapList(await request<SaveSummary[] | { items: SaveSummary[] }>("/api/saves")),
  getSave: (saveId: string, signal?: AbortSignal) =>
    request<SaveSummary>(`/api/saves/${encodeURIComponent(saveId)}`, { signal }),
  createSave: (name: string, requestId: string) =>
    request<SaveSummary>("/api/saves", {
      method: "POST",
      body: { name, request_id: requestId },
    }),
  renameSave: (saveId: string, name: string, expectedRevision: number, requestId: string) =>
    request<SaveSummary>(`/api/saves/${encodeURIComponent(saveId)}`, {
      method: "PATCH",
      body: { name, expected_revision: expectedRevision, request_id: requestId },
    }),
  updateSavePreferences: (saveId: string, settings: import("./types").StoryNarrationSettings, expectedRevision: number, requestId: string, signal?: AbortSignal) =>
    request<SaveSummary>(`/api/saves/${encodeURIComponent(saveId)}/preferences`, {
      method: "PUT", signal,
      body: { ...settings, expected_revision: expectedRevision, request_id: requestId },
    }),
  deleteSave: (saveId: string, expectedRevision: number, requestId: string) =>
    request<void>(`/api/saves/${encodeURIComponent(saveId)}`, {
      method: "DELETE",
      body: { expected_revision: expectedRevision, request_id: requestId, confirm: true },
    }),
  exportSave: async (saveId: string): Promise<{ blob: Blob; filename: string }> => {
    let response: Response;
    try {
      response = await fetch(`/api/saves/${encodeURIComponent(saveId)}/export`, {
        headers: { Accept: "application/json" },
      });
    } catch {
      throw new ApiError(0, { code: "network_error", message: "无法连接后端，未能导出存档。", retryable: true });
    }
    if (!response.ok) {
      throw new ApiError(response.status, {
        code: `http_${response.status}`,
        message: `导出失败（HTTP ${response.status}）`,
        retryable: response.status >= 500,
      });
    }
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const match = /filename\*?=(?:UTF-8'')?["']?([^"';]+)/i.exec(disposition);
    const filename = match ? decodeURIComponent(match[1]) : `fantasy-save-${saveId}.json`;
    return { blob: await response.blob(), filename };
  },
  validateImport: (document: unknown) =>
    request<ImportPreview>("/api/saves/import/validate", { method: "POST", body: document }),
  importSave: (document: unknown, requestId: string) =>
    request<SaveSummary>("/api/saves/import", { method: "POST", body: { payload: document, request_id: requestId } }),
  validateLargeImport: (file: Blob) =>
    request<ImportPreview>("/api/imports/validate", {
      method: "POST", directBody: file,
    }),
  importLargeSave: (file: Blob, requestId: string) =>
    request<ImportResult>("/api/imports", {
      method: "POST", headers: { "X-Request-Id": requestId }, directBody: file,
    }),
  trustAndImport: (pendingId: string, revisionId: string, requestId: string) =>
    request<SaveSummary>(`/api/imports/${encodeURIComponent(pendingId)}/trust-and-import`, {
      method: "POST", body: { request_id: requestId, confirm_revision_id: revisionId, confirm: true },
    }),

  getDraft: (saveId: string, signal?: AbortSignal) =>
    request<CharacterDraft>(`/api/saves/${encodeURIComponent(saveId)}/character-draft`, { signal }),
  saveDraft: (saveId: string, draft: CharacterDraft, expectedSaveRevision: number, requestId: string, signal?: AbortSignal) =>
    request<CharacterDraft>(`/api/saves/${encodeURIComponent(saveId)}/character-draft`, {
      method: "PUT",
      signal,
      body: { ...draft, expected_save_revision: expectedSaveRevision, request_id: requestId },
    }),
  startGeneration: (saveId: string, draftRevision: number, expectedSaveRevision: number, feedback = "", requestId: string = crypto.randomUUID()) =>
    request<GenerationJob>(`/api/saves/${encodeURIComponent(saveId)}/character-generations`, {
      method: "POST",
      body: { draft_revision: draftRevision, expected_save_revision: expectedSaveRevision, feedback, request_id: requestId },
    }),
  getGeneration: (saveId: string, jobId: string, signal?: AbortSignal) =>
    request<GenerationJob>(
      `/api/saves/${encodeURIComponent(saveId)}/character-generations/${encodeURIComponent(jobId)}`,
      { signal },
    ),
  cancelGeneration: (saveId: string, jobId: string, requestId: string) =>
    request<GenerationJob>(
      `/api/saves/${encodeURIComponent(saveId)}/character-generations/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST", body: { request_id: requestId } },
    ),
  getCandidate: (saveId: string, signal?: AbortSignal) =>
    request<CharacterCandidate>(`/api/saves/${encodeURIComponent(saveId)}/character-candidate`, { signal }),
  confirmCharacter: (
    saveId: string,
    candidateId: string,
    expectedSaveRevision: number,
    expectedDraftRevision: number,
    requestId: string,
  ) =>
    request<ConfirmedCharacterBootstrap>(`/api/saves/${encodeURIComponent(saveId)}/character/confirm`, {
      method: "POST",
      body: {
        candidate_id: candidateId,
        expected_save_revision: expectedSaveRevision,
        expected_draft_revision: expectedDraftRevision,
        request_id: requestId,
      },
    }),
  getGameBootstrap: (saveId: string, signal?: AbortSignal) =>
    request<GameBootstrap>(`/api/saves/${encodeURIComponent(saveId)}/game-bootstrap`, { signal }),

  getStory: (saveId: string, signal?: AbortSignal) =>
    request<StoryView>(`/api/saves/${encodeURIComponent(saveId)}/story`, { signal }),
  getImageSession: (saveId: string, signal?: AbortSignal) =>
    request<{ session: SceneImageSession | null }>(`/api/saves/${encodeURIComponent(saveId)}/image-session`, { signal }),
  createImageSession: (saveId: string, sourceTurnId: string, stateVersion: number, requestId: string) =>
    request<SceneImageSession>(`/api/saves/${encodeURIComponent(saveId)}/image-session`, { method: "POST",
      body: { request_id: requestId, source_turn_id: sourceTurnId, expected_state_version: stateVersion } }),
  updateImagePrompt: (saveId: string, sessionId: string, prompt: string, revision: number, size: ImageSize, quality: ImageQuality) =>
    request<SceneImageSession>(`/api/saves/${encodeURIComponent(saveId)}/image-session/${encodeURIComponent(sessionId)}/prompt`, { method: "PATCH",
      body: { prompt, expected_prompt_revision: revision, size, quality } }),
  generateSceneImage: (saveId: string, sessionId: string, revision: number, requestId: string) =>
    request<SceneImageSession["image_attempt"]>(`/api/saves/${encodeURIComponent(saveId)}/image-session/${encodeURIComponent(sessionId)}/generate`, { method: "POST",
      body: { request_id: requestId, expected_prompt_revision: revision } }),
  retryImagePrompt: (saveId: string, sessionId: string, requestId: string) =>
    request<{ attempt_id: string }>(`/api/saves/${encodeURIComponent(saveId)}/image-session/${encodeURIComponent(sessionId)}/retry-prompt`, { method: "POST", body: { request_id: requestId } }),
  cancelImageSessionJob: (saveId: string, sessionId: string) =>
    request<SceneImageSession>(`/api/saves/${encodeURIComponent(saveId)}/image-session/${encodeURIComponent(sessionId)}/cancel`, { method: "POST", body: {} }),
  completeImageSession: (saveId: string, sessionId: string, abandon = false) =>
    request<void>(`/api/saves/${encodeURIComponent(saveId)}/image-session/${encodeURIComponent(sessionId)}/complete`, { method: "POST", body: { abandon } }),
  sceneImageUrl: (saveId: string, sessionId: string) =>
    `/api/saves/${encodeURIComponent(saveId)}/image-session/${encodeURIComponent(sessionId)}/image`,
  sceneImageDownloadUrl: (saveId: string, sessionId: string) =>
    `/api/saves/${encodeURIComponent(saveId)}/image-session/${encodeURIComponent(sessionId)}/download`,
  resolveStartPrerequisite: (saveId: string, expectedStateVersion: number, resolution: StartPrerequisiteResolution, locationId: string | null, requestId: string, signal?: AbortSignal) =>
    request<StartPrerequisiteResult>(`/api/saves/${encodeURIComponent(saveId)}/story/start-prerequisite`, {
      method: "POST", signal,
      body: { request_id: requestId, expected_state_version: expectedStateVersion, resolution, location_id: locationId },
    }),
  startOpening: (saveId: string, expectedStateVersion: number, guidance = "", requestId: string = crypto.randomUUID(), signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/story/opening`, {
      method: "POST", signal, body: { request_id: requestId, expected_state_version: expectedStateVersion, guidance },
    }),
  startTurn: (saveId: string, expectedStateVersion: number, action: string, optionId: string | null, requestId: string = crypto.randomUUID(), signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/turns`, {
      method: "POST", signal, body: { request_id: requestId, expected_state_version: expectedStateVersion, action, option_id: optionId },
    }),
  intervene: (saveId: string, expectedStateVersion: number, guidance: string, requestId: string = crypto.randomUUID(), signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/turns/intervene`, {
      method: "POST", signal, body: { request_id: requestId, expected_state_version: expectedStateVersion, guidance },
    }),
  reshape: (saveId: string, turnId: string, expectedStateVersion: number, guidance: string, requestId: string = crypto.randomUUID(), signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/turns/${encodeURIComponent(turnId)}/reshape`, {
      method: "POST", signal, body: { request_id: requestId, expected_state_version: expectedStateVersion, guidance },
    }),
  listTurns: (saveId: string, signal?: AbortSignal, pagination?: { cursor: number; limit: number }) =>
    request<PaginatedResult<Turn>>(`/api/saves/${encodeURIComponent(saveId)}/turns${paginationQuery(pagination)}`, { signal }),
  getTurn: (saveId: string, turnId: string, signal?: AbortSignal) =>
    request<Turn>(`/api/saves/${encodeURIComponent(saveId)}/turns/${encodeURIComponent(turnId)}`, { signal }),
  getNarrativeJob: (saveId: string, jobId: string, signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/narrative-jobs/${encodeURIComponent(jobId)}`, { signal }),
  cancelNarrativeJob: (saveId: string, jobId: string, expectedStateVersion: number, requestId: string = crypto.randomUUID(), signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/narrative-jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST", signal, body: { request_id: requestId, expected_state_version: expectedStateVersion },
    }),
  getCharacterState: (saveId: string, signal?: AbortSignal) =>
    request<GameProjections["character"]>(`/api/saves/${encodeURIComponent(saveId)}/character-state`, { signal }),
  getInventory: (saveId: string, signal?: AbortSignal) =>
    request<GameProjections["inventory"]>(`/api/saves/${encodeURIComponent(saveId)}/inventory`, { signal }),
  getQuests: async (saveId: string, signal?: AbortSignal) =>
    questProjectionFromResponse(await request<unknown>(`/api/saves/${encodeURIComponent(saveId)}/quests`, { signal })),
  getJournals: (saveId: string, signal?: AbortSignal, pagination?: { cursor: number; limit: number }) =>
    request<PaginatedResult<JournalEntry>>(`/api/saves/${encodeURIComponent(saveId)}/journals${paginationQuery(pagination)}`, { signal }),
  getMemory: (saveId: string, signal?: AbortSignal) =>
    request<GameProjections["memory"]>(`/api/saves/${encodeURIComponent(saveId)}/memory`, { signal }),
  getMemories: (saveId: string, signal?: AbortSignal) =>
    request<GameProjections["memories"]>(`/api/saves/${encodeURIComponent(saveId)}/memories`, { signal }),
  getBonds: (saveId: string, signal?: AbortSignal) =>
    request<GameProjections["bonds"]>(`/api/saves/${encodeURIComponent(saveId)}/bonds`, { signal }),
  getReputations: (saveId: string, signal?: AbortSignal) =>
    request<GameProjections["reputations"]>(`/api/saves/${encodeURIComponent(saveId)}/reputations`, { signal }),
  createStoryArc: (saveId: string, expectedStateVersion: number, requestId: string = crypto.randomUUID(), signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/story-arcs`, {
      method: "POST", signal, body: { request_id: requestId, expected_state_version: expectedStateVersion },
    }),
  mergeStoryArcs: (saveId: string, expectedStateVersion: number, arcIds: string[], requestId: string = crypto.randomUUID(), signal?: AbortSignal) =>
    request<NarrativeJob>(`/api/saves/${encodeURIComponent(saveId)}/story-arcs/merge`, {
      method: "POST", signal, body: { request_id: requestId, expected_state_version: expectedStateVersion, arc_ids: arcIds },
    }),
};

export function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, {
    code: "unknown_error",
    message: error instanceof Error ? error.message : "发生未知错误。",
    retryable: false,
  });
}
