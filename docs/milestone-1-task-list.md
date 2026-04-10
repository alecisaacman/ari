# Milestone 1 Task List

## Sprint 1

- scaffold the repository
- establish docs as source of truth
- configure Python tooling
- bring up Postgres in Docker Compose
- add migrations baseline
- implement canonical state models centered on daily execution and weekly trajectory
- implement canonical event schema aligned to ARI workflow categories
- implement repositories for `DailyState`, `OpenLoop`, and `Event`
- implement raw input normalization
- implement event classification
- add unit tests for model validation and serialization
- retain explainability fields for signals and alerts

## Sprint 2

- implement daily check routine
- implement basic drift detection
- implement signal generation
- implement alert generation
- expose minimal API endpoints
- build the first hub surface

## Sprint 3

- add one notification channel
- tighten explainability paths
- improve operational tooling
- expand tests into repository and routine coverage
