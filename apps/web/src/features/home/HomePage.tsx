import { Link } from "react-router-dom";
import { NoticeSlot } from "../../app/notice";
import { Icon } from "../../components/Icon";
import { LoadingPanel } from "../../components/LoadingPanel";
import { phaseLabel, saveRoute, type SaveSummary } from "../../types";
import { stepProgressLabel } from "../character/wizardSteps";
import { relativeTime } from "./relativeTime";

/** Where the save stands: the latest story segment, the creation step, or the pending review. */
function storyLine(save: SaveSummary) {
  if (save.phase === "draft") return stepProgressLabel(save.current_step ?? 1);
  if (save.phase === "review") return "角色候选待确认";
  if (!save.latest_turn) return "尚未开始冒险";
  return [save.latest_turn.title, save.latest_turn.location_name].filter(Boolean).join(" · ");
}

export function HomePage({ saves, loading, onNew }: { saves: SaveSummary[]; loading: boolean; onNew: () => void }) {
  return (
    <div className="page home-page">
      <header className="home-heading">
        <h1>冒险档案</h1>
        <p>继续已有的冒险，或创建角色，开始一段新旅程。</p>
      </header>
      <NoticeSlot />
      {loading ? <LoadingPanel /> : saves.length ? (
        <section className="recent-list" aria-labelledby="recent-title">
          <div className="section-heading"><h2 id="recent-title">继续最近的档案</h2><button className="primary-button" type="button" onClick={onNew}><Icon name="plus" />新建存档</button></div>
          <ul className="recent-cards">
            {saves.slice(0, 5).map((save) => (
              <li key={save.id}>
                <Link viewTransition className="recent-row" to={saveRoute(save)}>
                  <span className={`phase-shape ${save.phase}`} aria-hidden="true" />
                  <span className="recent-main">
                    <strong>{save.name}</strong>
                    <span className="recent-story">{storyLine(save)}</span>
                    {save.character_name && <small>{save.character_name}</small>}
                  </span>
                  <span className="recent-meta">
                    <span className="phase-label">{phaseLabel[save.phase]}</span>
                    {save.updated_at && <time dateTime={save.updated_at}>{relativeTime(save.updated_at)}</time>}
                  </span>
                  <span className="row-arrow" aria-hidden="true">→</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section className="empty-state">
          <div className="empty-symbol" aria-hidden="true"><Icon name="book" /></div>
          <h2>建立第一份档案</h2>
          <p>每个存档记录一个角色和一段独立的冒险。先为存档取名，再创建你的角色。</p>
          <button className="primary-button" type="button" onClick={onNew}><Icon name="plus" />创建存档</button>
        </section>
      )}
    </div>
  );
}
