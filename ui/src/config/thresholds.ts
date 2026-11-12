// The ONE place the UI states the decision-engine thresholds. These mirror the defaults
// in libs/acip-common/src/acip_common/config.py and may differ if the deployment
// overrides them, so labels in the UI always say "default". They are used only for
// labelling, gauge bands and wording. The UI never computes a decision from them.
export const APPROVE_MAX = 0.35;
export const CHALLENGE_MAX = 0.7;
export const FRAUD_BLOCK = 0.85;
export const W_RISK = 0.5;
export const W_FRAUD = 0.5;
export const DECISION_DEADLINE_MS = 800;
