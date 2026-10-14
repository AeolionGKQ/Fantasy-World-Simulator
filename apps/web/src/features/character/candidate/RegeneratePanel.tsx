import { useState } from "react";

export function RegeneratePanel({ onGenerate }: { onGenerate: (feedback?: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const submit = async () => {
    const requestedFeedback = feedback.trim();
    if (!requestedFeedback) return;
    setOpen(false);
    setFeedback("");
    await onGenerate(requestedFeedback);
  };
  return (
    <section className="regenerate-panel">
      <div><h3>需要调整候选？</h3><p>提供明确修改意见会创建新的生成任务，当前候选在新结果完成前仍会保留。</p></div>
      {open ? (
        <div className="regenerate-form">
          <label className="field"><span>修改意见</span><textarea rows={4} maxLength={1200} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="例如：提高魅力，但降低体质，并保留当前背景解释。" /></label>
          <div className="form-actions">
            <button className="secondary-button" type="button" onClick={() => setOpen(false)}>取消修改</button>
            <button className="primary-button" type="button" disabled={!feedback.trim()} onClick={() => void submit()}>按意见重新生成</button>
          </div>
        </div>
      ) : <button className="secondary-button" type="button" onClick={() => setOpen(true)}>填写修改意见</button>}
    </section>
  );
}
