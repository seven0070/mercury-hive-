# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly. Do not open a public issue.

## Security Design

Mercury Hive follows these security principles:

- **Deny by default**: All access must be explicitly granted
- **Least privilege**: Database roles use column-level grants
- **No secret exposure**: Secrets never appear in logs, errors, or API responses
- **Forward-only migrations**: Database changes cannot be rolled back without explicit action
- **Fail closed**: Missing configuration causes startup failure, not permissive defaults
- **Generic errors**: Authentication failures return uniform 401 responses
- **Audit trail**: All authentication and authorization events are logged

## Known Limitations (Phase 1)

- No MFA (single-factor authentication only)
- No login rate limiting
- No HTTPS (requires reverse proxy for production)
- No key rotation mechanism
- HS256 JWT (symmetric key)
- Audit write access not isolated from runtime role
- No breach-list password checking

## Production Requirements (Not Yet Implemented)

- Multi-factor authentication
- Login and refresh rate limiting
- HTTPS with TLS termination
- JWT key rotation
- Separate audit-write database role
- Breach-list password validation
- Security alerting and monitoring
- Backup and disaster recovery
- External security review
