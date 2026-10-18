import { useParams } from "react-router-dom";
import { Icon } from "../../../components/Icon";
import { useAppNavigate } from "../../../app/viewTransition";
import { ErrorPanel } from "../../../components/ErrorPanel";
import { isActiveJobStatus, jobLabel, type CharacterCandidate, type CharacterDraft, type GenerationJob, type WorldCatalog } from "../../../types";
import { CandidatePanel } from "../candidate/CandidatePanel";
import { RegeneratePanel } from "../candidate/RegeneratePanel";

const failedStatuses = ["failed", "cancelled", "stale", "interrupted"];

export function GenerationStep({ catalog, draft, job, candidate, error, onGenerate, onCancel }: {
  catalog: WorldCatalog;
  draft: CharacterDraft;
  job: GenerationJob | null;
  candidate: CharacterCandidate | null;
  error: unknown;
  onGenerate: (feedback?: string) => Promise<void>;
  onCancel: () => Promise<void>;
}) {
  const navigate = useAppNavigate();
  const { saveId = "" } = useParams();
  const active = job && isActiveJobStatus(job.status);
  const failed = job && failedStatuses.includes(job.status);
  const race = catalog.races.find((item) => item.id === draft.race_id);
  const location = catalog.locations.find((item) => item.id === draft.location_id);
  return (
    <div className="generation-step">
      <section className="input-summary">
        <div className="section-heading"><h3>已填写的内容</h3><button className="text-button" type="button" onClick={() => navigate(`/saves/${saveId}/create/1`)}>返回修改</button></div>
        <dl>
          <div><dt>身份</dt><dd>{draft.name || "未填写"} · {draft.gender || "未填写"} · {draft.age ? `${draft.age} 岁` : "未填写"}</dd></div>
          <div><dt>种族</dt><dd>{race?.name || "未选择"}</dd></div>
          <div><dt>等阶</dt><dd>{draft.rank ? `${draft.rank} 阶` : "未选择"}</dd></div>
          <div><dt>起点</dt><dd>{location?.name || "未选择"}</dd></div>
          <div><dt>外貌</dt><dd>{draft.appearance || "未填写"}</dd></div>
          <div><dt>性格</dt><dd>{draft.personality || "未填写"}</dd></div>
          <div><dt>天赋</dt><dd>{draft.talent || "未填写"}</dd></div>
          {draft.background && <div><dt>身世</dt><dd>{draft.background}</dd></div>}
          {draft.additional && <div><dt>补充</dt><dd>{draft.additional}</dd></div>}
        </dl>
      </section>
      {Boolean(error) && <ErrorPanel error={error} title="生成请求出现问题" />}
      {active && (
        <section className="generation-progress" aria-live="polite">
          <div className="pulse-rune" aria-hidden="true"><Icon name="sparkle" /></div>
          <div>
            <span className="world-label">角色生成</span>
            <h3>{jobLabel[job.status]}</h3>
            <p>{job.progress_message || "AI 正在根据你填写的内容生成角色的属性、资源与战力。你可以先去看其他存档，生成会在后台继续。"}</p>
          </div>
          <button type="button" className="secondary-button" disabled={job.status === "cancel_requested"} onClick={() => void onCancel()}>{job.status === "cancel_requested" ? "正在取消…" : "取消生成"}</button>
        </section>
      )}
      {failed && (
        <section className="state-panel warning">
          <span className="state-symbol" aria-hidden="true">!</span>
          <div>
            <h3>{jobLabel[job.status]}</h3>
            <p>{job.error?.message || (job.status === "stale" ? "你修改了角色设定，这次的结果不会覆盖新内容。" : "可以按当前设定重新生成。")}</p>
            <button className="primary-button" type="button" onClick={() => void onGenerate()}>重试生成</button>
          </div>
        </section>
      )}
      {candidate && (
        <>
          <CandidatePanel candidate={candidate} footer={<div className="candidate-footer"><span /><button className="primary-button" type="button" onClick={() => navigate(`/saves/${saveId}/review`)}>审阅并接受角色</button></div>} />
          <RegeneratePanel onGenerate={onGenerate} />
        </>
      )}
      {!active && !candidate && !failed && (
        <div className="generation-ready">
          <div><h3>准备生成角色</h3><p>AI 会根据以上内容生成角色候选，你可以先查看，再决定是否接受。生成期间切换到其他存档，也不会混入别的角色。</p></div>
          <button className="primary-button" type="button" onClick={() => void onGenerate()}>生成角色</button>
        </div>
      )}
    </div>
  );
}
