import type { CharacterDraft, WorldCatalog } from "../../types";

export function DraftConflict({ serverDraft, catalog, onUseServer, onReload }: { serverDraft: CharacterDraft | null; catalog: WorldCatalog; onUseServer: () => void; onReload: () => void }) {
  const race = catalog.races.find((item) => item.id === serverDraft?.race_id)?.name;
  const location = catalog.locations.find((item) => item.id === serverDraft?.location_id)?.name;
  return (
    <section className="draft-conflict" role="alert">
      <div className="state-symbol" aria-hidden="true">!</div>
      <div>
        <h3>服务器上存在更新的草稿</h3>
        <p>本地编辑没有覆盖服务器内容。请比较服务器摘要，再决定是否放弃本地更改。</p>
        {serverDraft ? (
          <details>
            <summary>查看服务器修订 {serverDraft.draft_revision} 摘要</summary>
            <dl>
              <div><dt>姓名</dt><dd>{serverDraft.name || "未填写"}</dd></div>
              <div><dt>种族</dt><dd>{race || "未选择"}</dd></div>
              <div><dt>等阶</dt><dd>{serverDraft.rank ? `${serverDraft.rank} 阶` : "未选择"}</dd></div>
              <div><dt>地区</dt><dd>{location || "未选择"}</dd></div>
              <div><dt>当前步骤</dt><dd>{serverDraft.current_step} / 13</dd></div>
            </dl>
          </details>
        ) : <p>暂时无法读取服务器摘要，可以重新请求最新草稿。</p>}
        <div className="conflict-actions">
          <button className="secondary-button" type="button" onClick={onReload}>重新读取服务器草稿</button>
          <button className="danger-button" type="button" disabled={!serverDraft} onClick={onUseServer}>放弃本地更改并使用服务器版本</button>
        </div>
      </div>
    </section>
  );
}
