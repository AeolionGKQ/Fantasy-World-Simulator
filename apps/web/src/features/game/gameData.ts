import { api } from "../../api";
import type { GameBootstrap, GameProjections, SaveSummary, StoryView, Turn, WorldCatalog } from "../../types";

export interface GameData {
  save: SaveSummary;
  bootstrap: GameBootstrap;
  catalog: WorldCatalog;
  story: StoryView;
  turns: Turn[];
  projections: GameProjections;
  imageConfigured: boolean;
  imageSessionId: string | null;
}

/** Load everything the game workspace shows, in parallel, for one save. */
export async function getAllGameData(saveId: string, signal?: AbortSignal): Promise<GameData> {
  const [save, bootstrap, catalog, story, turns, character, inventory, quests, journals, memory, memories, bonds, reputations, settings, imageSession] = await Promise.all([
    api.getSave(saveId, signal), api.getGameBootstrap(saveId, signal), api.getCatalog(signal), api.getStory(saveId, signal), api.listTurns(saveId, signal),
    api.getCharacterState(saveId, signal), api.getInventory(saveId, signal), api.getQuests(saveId, signal),
    api.getJournals(saveId, signal), api.getMemory(saveId, signal), api.getMemories(saveId, signal),
    api.getBonds(saveId, signal), api.getReputations(saveId, signal),
    api.getSettings(), api.getImageSession(saveId, signal),
  ]);
  return { save, bootstrap, catalog, story, turns: turns.items, imageConfigured: settings.image_model?.configured ?? false,
    imageSessionId: imageSession.session?.id ?? null,
    projections: { character, inventory, quests, journals, memory, memories, bonds, reputations } };
}
