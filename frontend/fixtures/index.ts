import type { ScenarioKey } from "@/types/contracts";
import type { PackFixture } from "./types";
import { northstar } from "./northstar";
import { harbor } from "./harbor";
import { acme } from "./acme";

/** Labelled synthetic UI-preview packs. Not validated scenario packs (blueprint/16). */
export const PACKS: Record<ScenarioKey, PackFixture> = { northstar, harbor, acme };
export const PACK_ORDER: ScenarioKey[] = ["northstar", "acme", "harbor"];
