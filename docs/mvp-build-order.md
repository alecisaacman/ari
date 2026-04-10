# MVP Build Order

## Sequence

1. Establish docs, repo contract, and Python tooling.
2. Define canonical shared state models.
3. Stand up Postgres, migrations, and repository layer.
4. Implement event normalization and classification.
5. Implement the daily check routine and drift detection baseline.
6. Expose minimal API endpoints over state and events.
7. Build a minimal hub that reads the canonical state.
8. Add one meaningful notification path.

## Why This Order

- Shared models are needed before persistence.
- Persistence is needed before routines can be durable.
- Explainable signals depend on canonical state and events.
- Surfaces should consume the spine rather than define it.
