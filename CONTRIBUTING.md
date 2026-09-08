# Contributing to Mercury Hive

## Development Workflow

1. Create a feature branch from `main`
2. Implement changes with tests
3. Run `make lint` and `make test`
4. Run `make security-check`
5. Submit for review

## Rules

- All database changes require forward migrations
- All features require tests
- Security-sensitive changes require security tests
- Never commit `.env` or secrets
- Never weaken security to make a test pass
- If a feature cannot be implemented safely, leave it disabled and document the limitation

## Testing

- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- Security tests: `tests/security/`

All tests must pass before merging.
