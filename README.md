# Mercury Hive

A governed virtual AI company operated by one human system owner.

## Overview

Mercury Hive is a platform for operating a virtual AI company with a strict governance hierarchy:

```
System Owner (human)
    ↓
Digital CEO (AI)
    ↓
Digital HR Executives (AI)
    ↓
Department Managers (AI)
    ↓
Worker Agents (AI)
    ↓
Temporary Sub-Agents (AI)
```

The system is designed to be secure, auditable, reversible, permissioned, test-driven, and controlled.

## Core Principles

- The owner has final authority
- Access is denied by default
- Agents cannot modify their own permissions
- Every important action is logged
- High-risk actions require approval
- Failed work is preserved and classified

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local development/testing)
- Git

### Setup

```bash
# 1. Generate secrets
python scripts/generate_secrets.py

# 2. Start infrastructure and run migrations
make setup

# 3. Create the owner account
make bootstrap-owner

# 4. Start the API
make dev
```

### Development Commands

| Command | Description |
|---------|-------------|
| `make setup` | Initial setup: build, start DB, migrate |
| `make dev` | Start API with auto-reload |
| `make migrate` | Run database migrations + apply privileges |
| `make bootstrap-owner` | Create the system owner account |
| `make test` | Run all tests |
| `make lint` | Check code style |
| `make format` | Auto-format code |
| `make security-check` | Run security audits |
| `make stop` | Stop all containers |

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full architecture overview.

## Security

See [SECURITY.md](SECURITY.md) for security policy and responsible disclosure.

## License

All Rights Reserved. License to be determined.
