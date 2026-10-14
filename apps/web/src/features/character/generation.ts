import type { CharacterCandidate, GenerationJob, SaveSummary } from "../../types";

/**
 * When a generation job succeeds, load the candidate and save before publishing the job,
 * so the UI never shows "succeeded" without the matching candidate.
 */
export async function resolveCompletedGeneration(
  next: GenerationJob,
  loadCandidate: () => Promise<CharacterCandidate>,
  loadSave: () => Promise<SaveSummary>,
  publishJob: (job: GenerationJob) => void,
): Promise<{ candidate: CharacterCandidate; save: SaveSummary } | null> {
  if (next.status !== "succeeded") {
    publishJob(next);
    return null;
  }
  const [candidate, save] = await Promise.all([loadCandidate(), loadSave()]);
  publishJob(next);
  return { candidate, save };
}
