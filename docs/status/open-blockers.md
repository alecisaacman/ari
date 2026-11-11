# Open Blockers

Updated 2026-11-10.

## Highest priority
1. ARI's API credits. Reviews, build proposals, and the build stories all call the
   model; with the credits used up, the self-improvement loop stops. Plain requests
   still work without a model (`ari_core.local_intents`).
2. Proposals depend on the API. The build list has had one entry. A review that
   can't be written proposes nothing, so the builder has nothing to build.

## Waiting on setup only Alec can do
- The one-minute voice sample (`~/ARI/media/voice/record.sh`).
- Replicate for the studio (`ari-live connect-replicate`).

## Known limits
- The builder runs from a scheduled task in the Claude app, only while the app is
  open; the watchdog says when an approved build waited 30 hours.
- A failure to send through Messages can't be texted; it stays in the log.
- The hub and iMessage keep separate threads over shared records.
