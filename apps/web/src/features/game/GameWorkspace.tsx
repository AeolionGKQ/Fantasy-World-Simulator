import { useEffect, type KeyboardEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { prefersReducedMotion } from "../../app/viewTransition";
import { LoadingPanel } from "../../components/LoadingPanel";
import { usePresence } from "../../components/usePresence";
import { useSlidingIndicator } from "../../components/useSlidingIndicator";
import { playerProblemMessage } from "../../playerCopy";
import type { ApiProblem } from "../../types";
import { gameTabs, type GameTab } from "./gameTabs";
import { isNarrativeJobActive } from "./helpers";
import { BondsPanel } from "./panels/BondsPanel";
import { CharacterPanel } from "./panels/CharacterPanel";
import { InventoryPanel } from "./panels/InventoryPanel";
import { JournalsPanel } from "./panels/JournalsPanel";
import { MemoryPanel } from "./panels/MemoryPanel";
import { QuestsPanel } from "./panels/QuestsPanel";
import { ReputationsPanel } from "./panels/ReputationsPanel";
import { StoryPanel } from "./panels/StoryPanel";
import { useGameWorkspace, type GameNotice } from "./useGameWorkspace";

function LoadingGame() {
  return <div className="page game-page page-loading" key="loading"><LoadingPanel label="正在载入冒险" announce={false} /></div>;
}

function ProblemPanel({ problem, onRetry }: { problem: ApiProblem; onRetry: () => void }) {
  const conflict = problem.code.includes("CONFLICT") || problem.code === "NARRATIVE_JOB_ACTIVE";
  const contextExceeded = problem.code === "MODEL_CONTEXT_LENGTH_EXCEEDED";
  return (
    <section className={`state-panel ${conflict ? "warning" : "error"}`} role="alert">
      <span className="state-symbol" aria-hidden="true">{conflict ? "!" : "×"}</span>
      <div>
        <h2>{contextExceeded ? "故事内容超出模型可读取的长度" : conflict ? "存档内容已更新" : "无法载入冒险"}</h2>
        <p>{contextExceeded ? "请在设置中换用能读取更长故事的模型，再重新提交。游戏不会删减你的故事来重试。" : playerProblemMessage(problem)}</p>
        {problem.trace_id && <p className="trace">问题编号：{problem.trace_id}</p>}
        <button className="secondary-button" type="button" onClick={onRetry}>重新载入</button>
      </div>
    </section>
  );
}

function GameNoticeBar({ notice, leaving, onDismiss }: { notice: GameNotice; leaving: boolean; onDismiss: () => void }) {
  return (
    <div className={`game-notice ${notice.tone} ${leaving ? "leaving" : ""}`} role={notice.tone === "error" ? "alert" : "status"}>
      <span aria-hidden="true">{notice.tone === "error" ? "!" : "◇"}</span>
      <p>{notice.text}{notice.traceId && <small>问题编号：{notice.traceId}</small>}</p>
      <button type="button" onClick={onDismiss} aria-label="关闭游戏提示">×</button>
    </div>
  );
}

/** Arrow / Home / End move focus between tabs and activate them (WAI-ARIA tabs pattern). */
function handleTabKeys(event: KeyboardEvent<HTMLElement>) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const tabs = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  const current = tabs.indexOf(document.activeElement as HTMLButtonElement);
  if (current < 0) return;
  event.preventDefault();
  const target = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
    (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  tabs[target].focus(); tabs[target].click();
}

function GameTabs({ tab, onSelect }: { tab: GameTab; onSelect: (tab: GameTab) => void }) {
  const { containerRef, indicator } = useSlidingIndicator<HTMLElement>('[role="tab"][aria-selected="true"]', [tab]);
  // On narrow screens the tab strip scrolls; keep the selected tab visible.
  useEffect(() => {
    containerRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [containerRef, tab]);
  return (
    <nav className="game-tabs" role="tablist" aria-label="游戏页签" onKeyDown={handleTabKeys} ref={containerRef}>
      <span className={`slide-indicator game-tab-indicator ${indicator.className}`} style={indicator.style} aria-hidden="true" />
      {gameTabs.map((item) => <button id={`tab-${item.id}`} aria-controls={`panel-${item.id}`} aria-selected={tab === item.id} role="tab" tabIndex={tab === item.id ? 0 : -1} type="button" key={item.id} onClick={() => onSelect(item.id)}>{item.label}</button>)}
    </nav>
  );
}

export default function GameWorkspace({ onSaveChanged }: { onSaveChanged: () => Promise<void> }) {
  const { saveId = "" } = useParams();
  const game = useGameWorkspace(saveId, onSaveChanged);
  const { data, tab } = game;
  const notice = usePresence(game.notice);

  if (game.loading && !data) return <LoadingGame />;
  if (game.problem && !data) return <div className="page game-page page-enter" key="problem"><ProblemPanel problem={game.problem} onRetry={() => void game.refresh()} /></div>;
  if (!data) return null;
  if (data.bootstrap.save_id !== saveId) return <LoadingGame />;
  const stateBusy = game.submittingState || isNarrativeJobActive(data.story.active_job);
  const arcBusy = game.submittingArc || isNarrativeJobActive(data.story.active_arc_job);
  const latestTurn = data.story.latest_turn;
  return (
    <div className="page game-page page-enter" key="ready">
      <header className="game-header">
        <div>
          <h1>{data.projections.character.identity.name || data.bootstrap.character.identity?.name || "未命名角色"}</h1>
          <p>{data.story.state.time.label} · {data.story.state.location.name}</p>
        </div>
        {data.imageSessionId
          ? <Link viewTransition className="secondary-button scene-image-button" to={`/saves/${saveId}/game/image`}>查看场景图片</Link>
          : <button className={`secondary-button scene-image-button ${data.imageConfigured ? "" : "unconfigured"}`} type="button" disabled={!latestTurn || game.startingImage} onClick={() => void game.startImageSession()}>{game.startingImage ? "正在创建…" : "生成此刻图片"}</button>}
      </header>
      {notice.current && <GameNoticeBar key={notice.current.id} notice={notice.current} leaving={notice.leaving} onDismiss={() => game.setNotice(null)} />}
      <GameTabs tab={tab} onSelect={game.selectTab} />
      <section className="game-panel" id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0}>
        {tab === "story" && (
          <StoryPanel
            story={data.story}
            turns={data.turns}
            viewedTurn={game.viewedTurn}
            busy={stateBusy}
            catalog={data.catalog}
            onNavigate={game.showTurn}
            onOpen={(guidance) => void game.startStateJob((version, signal) => api.startOpening(saveId, version, guidance, crypto.randomUUID(), signal))}
            onResolvePrerequisite={(resolution, locationId) => void game.resolveStartPrerequisite(resolution, locationId)}
            onTurn={(action, optionId) => void game.startStateJob((version, signal) => api.startTurn(saveId, version, action, optionId, crypto.randomUUID(), signal))}
            onIntervene={(guidance) => void game.startStateJob((version, signal) => api.intervene(saveId, version, guidance, crypto.randomUUID(), signal))}
            onReshape={(guidance) => latestTurn && void game.startStateJob((version, signal) => api.reshape(saveId, latestTurn.id, version, guidance, crypto.randomUUID(), signal))}
            onCancel={() => void game.cancelJob()}
          />
        )}
        {tab === "character" && <CharacterPanel character={data.projections.character} catalog={data.catalog} playerAddress={data.save.narration?.player_address ?? data.story.state.narration.player_address} addressBusy={game.savingPreferences || stateBusy} onPlayerAddress={(value) => void game.updatePlayerAddress(value)} />}
        {tab === "inventory" && <InventoryPanel inventory={data.projections.inventory} />}
        {tab === "quests" && <QuestsPanel active={data.projections.quests.active} />}
        {tab === "journals" && <JournalsPanel items={data.projections.journals.items} onRead={(id) => void game.readJournalTurn(id)} />}
        {tab === "memory" && <MemoryPanel memory={data.projections.memory} memories={data.projections.memories.items} arcBusy={arcBusy} arcJob={data.story.active_arc_job} onMerge={(ids) => void game.startArcJob((version, signal) => api.mergeStoryArcs(saveId, version, ids, crypto.randomUUID(), signal))} />}
        {tab === "bonds" && <BondsPanel items={data.projections.bonds.items} />}
        {tab === "reputations" && <ReputationsPanel data={data.projections.reputations} />}
      </section>
    </div>
  );
}
