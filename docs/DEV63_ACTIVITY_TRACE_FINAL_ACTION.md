# dev.63 — Activity native attribution + exact final action

## Terrain motivating the change

Dev.62 is broadly successful, but several repeated failures share one narrow pattern: Home Assistant Activity identifies the source automation, while Investigator either loses that attribution on the terminal state row or falls back to the automation start trigger instead of the exact action-releasing step.

Confirmed examples include:

- Yaourtière OFF: Activity attributes `Aaaayaourt`, Investigator returned `unknown`.
- Volet salon repositioning: Activity attributes the automation, terminal state lost attribution.
- Charge lampes évier OFF: exact execution ended on the 4 h wait timeout, Investigator returned the initial off-peak trigger.
- Chargeur téléphone ON: more than one runtime-proven condition can jointly explain the chosen branch.

## Scope

Dev.63 remains a thin Activity reader. It may only use:

1. the selected Home Assistant Activity fact;
2. native Activity attribution linked by explicit Home Assistant context IDs;
3. the exact trace of that identified automation/script execution;
4. the exact action path, wait result, and runtime-proven branch conditions from that trace.

No broad time correlation, no causal graph, no unrelated-entity search, no recursive reconstruction.

## New bounded selectors

- Linked Activity attribution may come from a non-state Activity row when it shares an explicit `context.id` / `parent_id` with the terminal fact.
- A `wait_for_trigger` timeout is accepted as cause only when `wait.completed == false`, a timeout is configured, and the immediately following unique executed command matches the investigated effect.
- A chosen `choose` branch may expose 1–4 supported `state` / `numeric_state` conditions only when HA's exact trace proves the branch true, every condition runtime true, and the branch action matches the investigated effect.

Unsupported or ambiguous shapes fail closed and retain the dev.62 fallback behavior.

## Fallback

Dev.54 remains the official frozen fallback. Dev.63 is a terrain candidate only until real-event validation is complete.
