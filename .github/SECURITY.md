# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.6.x   | :white_check_mark: |
| < 0.6   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Lucid, please report it responsibly.

**Use GitHub Private Vulnerability Reporting** on this repository:

→ https://github.com/ertugrulakben/lucid/security/advisories/new

Include:
- A clear description of the vulnerability
- Steps to reproduce
- Affected versions
- Suggested fix (if any)

Please do **not** open a public issue for security-sensitive reports - they reach the maintainer through the private advisory channel.

## Disclosure Window

We operate a **90-day coordinated disclosure** window:

1. **Acknowledgement** within 72 hours of report receipt.
2. **Fix & validate** within 90 days (sooner for critical issues).
3. **Public disclosure** after a fix release is available and users have had a reasonable time to update.

We credit reporters in release notes unless they prefer to remain anonymous.

## Security Model & Threats Considered

- Lucid operates on the local desktop with elevated accessibility privileges.
- API keys are stored in the OS keyring, never in plain-text files.
- Destructive actions require explicit user confirmation by default.
- Scheduled tasks run with the same privileges as the user who started Lucid.
- `lucid update check` only reports a newer GitHub release; it never downloads or installs anything. Signed release manifests are planned (ROADMAP Phase 4).

## Out of Scope

- Social engineering or physical access attacks.
- Attacks requiring compromised OS or third-party driver vulnerabilities.
- Denial-of-service via resource exhaustion on the local machine (please open a regular issue instead).

## Code Signing Roadmap

Releases are not signed yet. Planned: an Ed25519-signed release manifest with the public key embedded in the app (ROADMAP Phase 4), then a Windows Authenticode EV certificate once the project reaches sustainable funding.
