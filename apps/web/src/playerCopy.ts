import type { ApiProblem } from "./types";

const problemMessages: Record<string, string> = {
  network_error: "无法连接游戏服务，请确认游戏已启动后重试。",
  MODEL_NOT_CONFIGURED: "请先打开设置，填写剧情 AI 的服务地址、模型名称和密钥。",
  MODEL_AUTH_FAILED: "服务密钥未通过验证，请在设置中检查密钥是否正确、是否仍然有效。",
  MODEL_NOT_FOUND: "当前服务中找不到这个模型，请核对服务商提供的模型名称。",
  MODEL_RATE_LIMITED: "AI 服务暂时无法接收更多请求，请稍后再试，或在设置中减少同时生成数量。",
  MODEL_SERVICE_ERROR: "AI 服务暂时不可用，请稍后重试。",
  MODEL_TIMEOUT: "等待 AI 回复的时间已用完。请稍后重试；如果经常出现，可在设置中调高最长等待时间。",
  MODEL_CONTEXT_LENGTH_EXCEEDED: "当前 AI 无法一次读取这么多故事内容。请在设置中换用能读取更长故事的模型后重试。游戏不会删减你的故事。",
  MODEL_OUTPUT_FORMAT: "AI 返回的内容不完整或无法使用，请重新生成。",
  MODEL_OUTPUT_TOO_LARGE: "AI 返回的内容过长，无法读取，请重新生成。",
  STATE_VERSION_CONFLICT: "存档内容已更新，请重新载入，查看最新剧情后再操作。",
  REVISION_CONFLICT: "内容已在其他页面更新，请重新载入后再操作。",
  IDEMPOTENCY_CONFLICT: "这次操作与先前提交的内容不同，请重新载入后再试。",
  NARRATIVE_JOB_ACTIVE: "这个存档正在生成剧情，请等待完成，或先取消当前生成。",
  NARRATIVE_JOB_NOT_FOUND: "找不到这次剧情生成记录，请重新载入存档。",
  SAVE_NOT_READY: "请先完成角色创建并确认角色，再开始冒险。",
  STORY_NOT_STARTED: "请先生成开场剧情，再使用此功能。",
  OPENING_REQUIRED: "请先点击“开始冒险”，生成故事开场。",
  OPENING_ALREADY_EXISTS: "故事开场已经生成，请重新载入并继续冒险。",
  RESHAPE_LATEST_ONLY: "只能重塑最近一段剧情，请先回到最新剧情。",
  TURN_NOT_FOUND: "找不到这段剧情，请重新载入存档。",
  START_LOCATION_PREREQUISITE_REQUIRED: "当前起点需要防护或通行许可，请先确认这些条件，或选择其他起点。",
  START_PREREQUISITE_ALREADY_RESOLVED: "起点条件已确认，请重新载入后开始冒险。",
  ARC_SOURCES_NOT_CONTIGUOUS: "只能合并在剧情顺序上相邻、尚未被合并的故事弧。",
  ARC_SOURCE_NOT_READY: "还没有足够的早期剧情可供整理，请继续冒险。",
  IMAGE_MODEL_NOT_CONFIGURED: "请在设置的“场景图片”中填写 OpenAI 服务地址和密钥。",
  IMAGE_SESSION_NOT_FOUND: "找不到这次图片生成记录，请返回剧情页重新开始。",
  IMAGE_JOB_ACTIVE: "画面描述或图片正在生成，请等待完成，或先取消当前生成。",
  IMAGE_NOT_FOUND: "暂时找不到这张图片，请查看生成进度或重新生成。",
  IMAGE_CORRUPTED: "这张图片无法读取，请重新生成。",
  INVALID_JSON: "无法读取提交的内容。导入存档时，请选择从游戏中导出的完整 .json 文件。",
  UNSUPPORTED_MEDIA_TYPE: "无法读取提交的文件，请使用从游戏中导出的 .json 存档。",
};

const inputMessages: Record<string, string> = {
  "API Base URL 必须是有效的 HTTP/HTTPS 地址": "服务地址填写有误，请复制服务商提供的完整 API 地址。",
  "timeout_seconds必须在1至600秒之间": "最长等待时间需填写 1–600 秒。",
  "max_concurrency必须是1至16的整数": "同时生成数量需填写 1–16 的整数。",
  "结构化输出探测凭证无效或已过期": "回复格式测试已失效，请重新开启“规范回复格式”进行测试。",
  "生图API地址必须是https://api.openai.com": "图片服务仅支持 OpenAI 官方地址：https://api.openai.com/v1。",
  "当前仅支持gpt-image-2.5-sunburst": "图片服务目前只支持设置页中指定的模型。",
  "必须选择合法公开起点": "请从可选起点中选择一个地点。",
  "请先生成或填写提示词": "请先生成或填写画面描述。",
  "图片画幅或质量无效": "请重新选择图片画幅和质量。",
};

export function playerProblemMessage(problem: Pick<ApiProblem, "code" | "message">): string {
  if (inputMessages[problem.message]) return inputMessages[problem.message];
  if (problem.code === "MODEL_REQUEST_REJECTED") {
    if (/结构化输出|response_format|output_config/.test(problem.message)) {
      return "当前服务拒绝了回复格式设置，请在设置中关闭“规范回复格式”，或重新开启进行测试。";
    }
    // Retain the specific service reason, without the HTTP status label.
    return problem.message.replace(/（HTTP \d+）/g, "");
  }
  // Keep service-specific and unknown reasons instead of hiding useful details.
  return problemMessages[problem.code] ?? problem.message;
}
