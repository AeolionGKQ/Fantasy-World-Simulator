import { Link } from "react-router-dom";
import { Icon } from "../../components/Icon";
import { LoadingPanel } from "../../components/LoadingPanel";
import { phaseLabel, saveRoute, type SaveSummary } from "../../types";

export function HomePage({ saves, loading, onNew }: { saves: SaveSummary[]; loading: boolean; onNew: () => void }) {
  return (
    <div className="page home-page">
      <div className="home-heading">
        <span className="archive-glyph" aria-hidden="true">◇</span>
        <div><h1>冒险档案</h1><p>继续已有的冒险，或创建角色，开始一段新旅程。</p></div>
      </div>
      {loading ? <LoadingPanel /> : saves.length ? (
        <section className="recent-list" aria-labelledby="recent-title">
          <div className="section-heading"><h2 id="recent-title">继续最近的档案</h2><button className="primary-button" type="button" onClick={onNew}><Icon name="plus" />新建存档</button></div>
          {saves.slice(0, 5).map((save) => (
            <Link className="recent-row" key={save.id} to={saveRoute(save)}>
              <span className={`phase-shape ${save.phase}`} aria-hidden="true" />
              <span><strong>{save.name}</strong><small>{save.character_name || (save.phase === "draft" ? "角色尚未完成" : "角色待确认")}</small></span>
              <span className="phase-label">{phaseLabel[save.phase]}</span><span aria-hidden="true">→</span>
            </Link>
          ))}
        </section>
      ) : (
        <section className="empty-state">
          <div className="empty-symbol" aria-hidden="true">＋</div>
          <h2>建立第一份档案</h2>
          <p>每个存档记录一个角色和一段独立的冒险。先为存档取名，再创建你的角色。</p>
          <button className="primary-button" type="button" onClick={onNew}><Icon name="plus" />创建存档</button>
        </section>
      )}
    </div>
  );
}
