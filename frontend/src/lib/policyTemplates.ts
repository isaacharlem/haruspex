import type { PolicyDefinition } from './types'

export const KILL_DOOMED_TEMPLATE: PolicyDefinition = {
  name: 'kill-doomed-after-warmup',
  scope: { tags: [] },
  when: { signal: 'p_hit_target', op: '<', value: 0.05, after_progress: 0.1, sustained_evals: 3 },
  action: { type: 'kill', grace_seconds: 120, min_checkpoint_age_seconds: 600, notify: true },
}
