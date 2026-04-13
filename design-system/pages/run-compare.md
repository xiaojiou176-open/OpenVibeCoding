# Run Compare Override

This page is the **compare truth room**.

## Primary job

Tell the operator:

1. whether a compare verdict exists
2. what the most material delta is
3. what action is safe next

## Rules

- Lead with a verdict band before any detailed breakdown.
- Keep one compact signal strip for the highest-risk compare deltas.
- The copilot stays secondary to the verdict; it explains the room, but it does not outrank the decision.
- The raw evidence archive must remain collapsed and visually subordinate.
- When no compare report exists, the room must explicitly read as observation mode rather than pretending a verdict exists.
- Observation mode must never show synthetic failure posture. Use `Missing`, `Pending`, or `Unavailable` until the compare report exists.
- In observation mode, the second primary card should read like a `Recovery path`, not like a duplicate delta explainer.

## Avoid

- raw JSON in the first scan layer
- duplicate summary cards saying the same thing
- AI copilot panels that visually outrank the compare verdict
- report-page hierarchy instead of operator-room hierarchy
