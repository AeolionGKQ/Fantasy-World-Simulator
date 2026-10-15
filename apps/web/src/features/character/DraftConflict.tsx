import type { CharacterDraft, WorldCatalog } from "../../types";

export function DraftConflict({ serverDraft, catalog, onUseServer, onReload }: { serverDraft: CharacterDraft | null; catalog: WorldCatalog; onUseServer: () => void; onReload: () => void }) {
  const race = catalog.races.find((item) => item.id === serverDraft?.race_id)?.name;
  const location = catalog.locations.find((item) => item.id === serverDraft?.location_id)?.name;
  return (
    <section className="draft-conflict" role="alert">
      <div className="state-symbol" aria-hidden="true">!</div>
      <div>
        <h3>这份草稿有更新的版本</h3>
        <p>这份草稿已在别处更新，你在这里的修改没有覆盖它。请先查看新版本的摘要，再决定是否放弃当前修改。</p>
        {serverDraft ? (
          <details>
            <summary>查看新版本摘要</summary>
            <dl>
              <div><dt>姓名</dt><dd>{serverDraft.name || "未填写"}</dd></div>
              <div><dt>种族</dt><dd>{race || "未选择"}</dd></div>
              <div><dt>等阶</dt><dd>{serverDraft.rank ? `${serverDraft.rank} 阶` : "未选择"}</dd></div>
              <div><dt>地区</dt><dd>{location || "未选择"}</dd></div>
              <div><dt>当前步骤</dt><dd>{serverDraft.current_step} / 13</dd></div>
            </dl>
          </details>
        ) : <p>暂时无法读取新版本的摘要，可以重新载入最新草稿。</p>}
        <div className="conflict-actions">
          <button className="secondary-button" type="button" onClick={onReload}>重新载入最新草稿</button>
          <button className="danger-button" type="button" disabled={!serverDraft} onClick={onUseServer}>放弃当前修改，使用新版本</button>
        </div>
      </div>
    </section>
  );
}
