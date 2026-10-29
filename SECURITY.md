# Security policy

Email [gerardrecinto@gmail.com](mailto:gerardrecinto@gmail.com?subject=genai-gateway%20security%20report) privately with the affected version or commit, source paths, a minimal redacted reproduction, and the impact you observed.

Keep API keys, private prompts, and response content out of public issues. A sanitized fixture is enough to start.

Reports can cover policy ordering, cache behavior, log or credential exposure, provider boundaries, and repository workflows. The [implementation notes](docs/SECURITY.md) explain the current limits, including the unauthenticated local API and caller-supplied client identity.

Fixes target `main` and the latest release when one exists. Older versions may require an upgrade.
