---
name: antigravity-cli
description: Operate and troubleshoot the Antigravity CLI (agy), including sessions, plugins, authentication, and sandbox settings.
license: MIT
metadata:
  author: "Tony Simons (asimons81), Hermes Agent"
  upstream: "https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/autonomous-ai-agents/antigravity-cli"
  adaptation: "Codex: current-host tools, installed CLI help, and task-scoped verification"
---

# Antigravity CLI (`agy`)

Use the current host's shell and file tools to operate `agy`. This is a Codex adaptation of the linked upstream skill; preserve attribution and compare local changes when updating it.

## Establish the installed interface

Check `agy --version` and `agy --help`, then the relevant subcommand's help when needed. Treat the installed CLI and current official documentation as authoritative for commands, flags and defaults.

Shell subcommands and interactive slash commands are different interfaces: `agy plugin` runs in the shell; `/config`, `/permissions` and similar commands belong inside an active CLI session. Use `--print` for a requested one-shot prompt, and a persistent TTY only for work that needs interaction. A prompt may perform work; it is not a neutral availability check.

## Operate within the request

- Use the user's intended working directory and session or project. Inspect the relevant help before resuming a conversation or selecting a project.
- For plugin operations, read the current plugin help and list installed plugins when their identity or state is needed. An empty list is a valid state.
- For authentication, use the CLI's supported login flow. Browser interaction and permission changes follow the current task's authorization; the skill does not authorize weakening sandbox settings or bypassing approval.
- For diagnosis, inspect only relevant settings and bounded log excerpts under `~/.gemini/antigravity-cli/`. Redact secrets and unrelated conversation content.
- For installation, settings, authentication or slash-command details not resolved by local help, consult current official documentation. [Earlier upstream notes](references/cli-docs.md) are historical context and must be checked before relying on version-sensitive commands or defaults.

## Verify the actual operation

Use version and help output for availability, plugin state after plugin changes, or the relevant configuration and logs for diagnosis. A successful version check does not establish authentication or completion of a requested task. Report what changed and which result verifies it.
