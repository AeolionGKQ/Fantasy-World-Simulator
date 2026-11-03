import { useEffect, useRef, useState } from "react";
import { api, asApiError } from "../../api";
import { Modal } from "../../components/Modal";
import { playerProblemMessage } from "../../playerCopy";
import type { NarrativeJob, NarrativeJobFailureAttempt, NarrativeJobFailureDetails, NarrativeJobType } from "../../types";

const jobNames: Record<NarrativeJobType, string> = {
  opening: "开场剧情", turn: "剧情推进", intervene: "干预剧情", reshape: "重塑命运",
  turns_to_arc: "整理故事弧", arcs_to_arc: "压缩故事弧", memory_curation: "整理长期记忆",
};

const responseLabel = (attempt: NarrativeJobFailureAttempt) =>
  attempt.response_kind === "raw" ? "模型原始回复" : "模型返回（程序解析出的 JSON）";

/** Plain text of everything in the dialog, for pasting into a bug report. */
function reportText(details: NarrativeJobFailureDetails) {
  const lines = [
    `任务：${jobNames[details.type] ?? details.type}（${details.job_id}）`,
    `错误代码：${details.code}`, `时间：${details.failed_at}`, `汇总：${details.message}`,
  ];
  for (const attempt of details.attempts) {
    lines.push("", `===== 第 ${attempt.attempt} 次尝试 · ${attempt.stage} =====`, "【未通过的原因】", attempt.error);
    if (attempt.correction_prompt) lines.push("", "【本次附带的修正提示】", attempt.correction_prompt);
    lines.push("", `【${responseLabel(attempt)}】`, attempt.response ?? "（没有收到可显示的内容）");
  }
  return lines.join("\n");
}

/** Clipboard API first; where it is refused (some WebViews), the older select-and-copy inside the dialog. */
async function copyText(text: string, host: HTMLElement | null) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    if (!host) return false;
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    host.append(area);
    area.select();
    try {
      return document.execCommand("copy");
    } finally {
      area.remove();
    }
  }
}

/**
 * The model replies a failed generation rejected, with each validation error: for debugging and
 * for players to attach to a bug report.
 */
export function FailureDetailsModal({ saveId, job, onClose }: { saveId: string; job: NarrativeJob; onClose: () => void }) {
  const [details, setDetails] = useState<NarrativeJobFailureDetails | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState<"" | "done" | "failed">("");
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    api.getNarrativeJobFailureDetails(saveId, job.id, controller.signal)
      .then(setDetails)
      .catch((reason) => { if (!controller.signal.aborted) setError(playerProblemMessage(asApiError(reason).problem)); });
    return () => controller.abort();
  }, [saveId, job.id]);
  const copy = async () => {
    if (!details) return;
    setCopied(await copyText(reportText(details), body.current) ? "done" : "failed");
  };
  return (
    <Modal title="生成失败详情" labelledBy="failure-details-title" className="failure-details-modal" onClose={onClose}>
      <div className="failure-details" ref={body}>
        {error && <p className="field-error">{error}</p>}
        {!details && !error && <p className="muted-copy">正在读取…</p>}
        {details && (
          <>
            <dl className="failure-facts">
              <div><dt>任务</dt><dd>{jobNames[details.type] ?? details.type}</dd></div>
              <div><dt>错误代码</dt><dd><code>{details.code}</code></dd></div>
              <div><dt>时间</dt><dd>{new Date(details.failed_at).toLocaleString()}</dd></div>
              <div><dt>任务编号</dt><dd><code>{details.job_id}</code></dd></div>
            </dl>
            <p className="muted-copy">程序最多让模型回复两次：第一次没通过时，会把出错位置告诉模型再试一次。下面是每次被拒绝的回复和原因。反馈问题时，可以点“复制全部”后一并发送。</p>
            {details.attempts.map((attempt) => (
              <section className="failure-attempt" key={attempt.attempt}>
                <h3>第 {attempt.attempt} 次尝试 · {attempt.stage}</h3>
                <h4>未通过的原因</h4>
                <pre className="failure-error">{attempt.error}</pre>
                {attempt.correction_prompt && (
                  <details>
                    <summary>本次附带的修正提示</summary>
                    <pre>{attempt.correction_prompt}</pre>
                  </details>
                )}
                <h4>{responseLabel(attempt)}</h4>
                {attempt.response ? <pre className="failure-response">{attempt.response}</pre> : <p className="muted-copy">没有收到可显示的内容。</p>}
              </section>
            ))}
            {details.attempts.length < 2 && <p className="muted-copy">另一次尝试没有留下回复，因其他错误中止：{details.message}</p>}
          </>
        )}
        <div className="modal-actions">
          {copied && <span className="copy-status" role="status">{copied === "done" ? "已复制到剪贴板" : "无法访问剪贴板，请手动选择文字复制"}</span>}
          <button className="secondary-button" type="button" disabled={!details} onClick={() => void copy()}>复制全部</button>
          <button className="primary-button" type="button" data-modal-close>关闭</button>
        </div>
      </div>
    </Modal>
  );
}
