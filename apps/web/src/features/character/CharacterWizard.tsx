import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useParams } from "react-router-dom";
import { prefersReducedMotion } from "../../app/viewTransition";
import { NoticeSlot } from "../../app/notice";
import type { ShellActions } from "../../app/shellActions";
import { ErrorPanel } from "../../components/ErrorPanel";
import { LoadingPanel } from "../../components/LoadingPanel";
import { useSlidingIndicator } from "../../components/useSlidingIndicator";
import type { CharacterDraft, WorldCatalog } from "../../types";
import { DraftConflict } from "./DraftConflict";
import { DraftStatus } from "./DraftStatus";
import { AgeStep } from "./steps/AgeStep";
import { FactionStep } from "./steps/FactionStep";
import { GenderStep } from "./steps/GenderStep";
import { GenerationStep } from "./steps/GenerationStep";
import { LocationStep } from "./steps/LocationStep";
import { PresetTextStep } from "./steps/PresetTextStep";
import { RaceStep } from "./steps/RaceStep";
import { RankStep } from "./steps/RankStep";
import { TextStep } from "./steps/TextStep";
import { useCharacterWizard } from "./useCharacterWizard";
import { stepDescription, stepProgressLabel, steps, stepSummary, stepTitle, TOTAL_STEPS } from "./wizardSteps";

export function CharacterWizard({ actions }: { actions: ShellActions }) {
  const { saveId = "", step: stepParam = "1" } = useParams();
  const step = Math.min(TOTAL_STEPS, Math.max(1, Number(stepParam) || 1));
  const wizard = useCharacterWizard(saveId, step, actions);
  const { catalog, save, draft, saveStatus } = wizard;

  if (wizard.loading) return <div className="page page-loading" key="loading"><LoadingPanel label="正在载入角色草稿" /></div>;
  if (wizard.error || !catalog || !save) return <div className="page page-enter" key="error"><ErrorPanel error={wizard.error} onRetry={() => void wizard.load()} title="无法载入角色草稿" /></div>;

  return (
    <div className="page wizard-page page-enter" key="ready">
      <header className="wizard-header">
        {/* One heading per step (D-04): progress above, the step's title as the page h1. */}
        <div className="wizard-heading">
          <div className="wizard-progress">
            <span className="step-count" id="wizard-progress-label">{stepProgressLabel(step)}</span>
            <div className="progress-track" role="progressbar" aria-valuemin={1} aria-valuemax={TOTAL_STEPS} aria-valuenow={step} aria-labelledby="wizard-progress-label">
              <span style={{ "--progress": step / TOTAL_STEPS } as CSSProperties} />
            </div>
          </div>
          <h1 id="step-title">{stepTitle(step)}</h1>
        </div>
        <DraftStatus status={saveStatus} onRetry={() => void wizard.persistDraft()} onReload={() => void wizard.load()} />
      </header>
      <NoticeSlot />
      <div className="wizard-layout">
        <WizardStepNav step={step} draft={draft} catalog={catalog} onSelect={(number) => void wizard.go(number)} />
        <section className="step-content" aria-labelledby="step-title">
          {/* step-body slides when the step changes; the action row below stays in place */}
          <div className="step-body">
            <p className="step-description">{stepDescription(step)}</p>
            {wizard.validationError && <p className="validation-banner" role="alert">{wizard.validationError}</p>}
            {saveStatus === "conflict" && <DraftConflict serverDraft={wizard.serverDraft} catalog={catalog} onUseServer={wizard.adoptServerDraft} onReload={() => void wizard.load()} />}
            {/* keyed so every step mounts fresh (autofocus, local state), as separate steps always have */}
            <WizardStepBody key={step} step={step} catalog={catalog} wizard={wizard} />
          </div>
          {step < TOTAL_STEPS && (
            <div className="wizard-actions">
              <button className="secondary-button" type="button" disabled={step === 1 || saveStatus === "saving"} onClick={() => void wizard.go(step - 1)}>上一步</button>
              <button className="primary-button" type="button" disabled={saveStatus === "saving"} onClick={() => void wizard.go(step + 1)}>{saveStatus === "saving" ? "正在保存…" : "保存并下一步"}</button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function WizardStepNav({ step, draft, catalog, onSelect }: { step: number; draft: CharacterDraft; catalog: WorldCatalog; onSelect: (step: number) => void }) {
  const { containerRef, indicator } = useSlidingIndicator<HTMLElement>("button.active", [step]);
  // The step just left by moving forward gets a one-off check-mark pop, kept until it finishes.
  const previousStep = useRef(step);
  const [justCompleted, setJustCompleted] = useState<number | null>(null);
  useEffect(() => {
    if (step > previousStep.current) setJustCompleted(previousStep.current);
    previousStep.current = step;
    // On the mobile strip, keep the current step visible.
    containerRef.current?.querySelector("button.active")?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [containerRef, step]);
  return (
    <nav className="step-nav" aria-label="角色创建步骤" ref={containerRef}>
      <span className={`slide-indicator step-nav-indicator ${indicator.className}`} style={indicator.style} aria-hidden="true" />
      {steps.map((label, index) => {
        const number = index + 1;
        return (
          <button type="button" key={label} className={`${number === step ? "active" : ""} ${number < step ? "complete" : ""} ${number === justCompleted ? "just-completed" : ""}`} aria-current={number === step ? "step" : undefined} onClick={() => onSelect(number)}>
            <span onAnimationEnd={() => setJustCompleted(null)}>{number < step ? "✓" : number}</span>
            <span>{label}<small>{stepSummary(number, draft, catalog)}</small></span>
          </button>
        );
      })}
    </nav>
  );
}

function WizardStepBody({ step, catalog, wizard }: { step: number; catalog: WorldCatalog; wizard: ReturnType<typeof useCharacterWizard> }) {
  const { draft, updateDraft } = wizard;
  switch (step) {
    case 1: return <RaceStep catalog={catalog} draft={draft} update={updateDraft} />;
    case 2: return <TextStep label="角色姓名" value={draft.name} onChange={(value) => updateDraft("name", value)} maxLength={80} placeholder="输入角色姓名" />;
    case 3: return <GenderStep draft={draft} update={updateDraft} />;
    case 4: return <AgeStep catalog={catalog} draft={draft} update={updateDraft} />;
    case 5: return <PresetTextStep label="外貌描述" presets={catalog.presets.appearance} raceId={draft.race_id} value={draft.appearance} update={(value) => updateDraft("appearance", value)} placeholder="描述体态、面容、发色、衣着或显著特征" />;
    case 6: return <PresetTextStep label="性格描述" presets={catalog.presets.personality} raceId={draft.race_id} value={draft.personality} update={(value) => updateDraft("personality", value)} placeholder="描述性情、习惯、价值观与待人方式" />;
    case 7: return <RankStep catalog={catalog} draft={draft} update={updateDraft} />;
    case 8: return <PresetTextStep label="天赋描述" presets={catalog.presets.talent} raceId={draft.race_id} value={draft.talent} update={(value) => updateDraft("talent", value)} placeholder="描述与生俱来或后天形成的突出能力" note="预设词只是描述，本身不会直接提高属性。角色的最终属性由 AI 根据完整设定生成，并按世界规则检查。" />;
    case 9: return <TextStep label="身世与经历" value={draft.background} onChange={(value) => updateDraft("background", value)} maxLength={4000} optional multiline placeholder="可以留空。写下角色的成长环境、重要经历或未解心结。" />;
    case 10: return <FactionStep factions={catalog.factions} activeId={wizard.browsedFactionId} setActiveId={wizard.setBrowsedFactionId} />;
    case 11: return <LocationStep catalog={catalog} draft={draft} update={updateDraft} />;
    case 12: return <TextStep label="其他补充" value={draft.additional} onChange={(value) => updateDraft("additional", value)} maxLength={4000} optional multiline placeholder="可以留空。补充前面没有提到、但希望 AI 了解的角色信息。" />;
    case 13: return <GenerationStep catalog={catalog} draft={draft} job={wizard.job} candidate={wizard.candidate} error={wizard.generationError} onGenerate={wizard.startGeneration} onCancel={wizard.cancelGeneration} />;
    default: return null;
  }
}
