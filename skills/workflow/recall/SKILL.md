---
name: recall
description: "Reconstruct your recent working context from your own chat history, live state, and the shared record (user reports, prior fixes, incidents), then hand back a tight current-state brief. Use for 'recall my work on X', 'catch me up', 'what have I been working on', 'where did I leave off', before starting or resuming work."
disable-model-invocation: true
---

# Recall

**Before you start or resume work, you rebuild the user's recent working context and hand back a tight capsule of where things stand now and what to do next.**

Keep it tight and on-topic. Read only what the in-scope threads need, then stop.

Your context lives in two records. Your own chat history holds what you did and decided. The shared record holds everything that happened around the same code under other names: the symptoms users keep reporting, the fixes that shipped and got reverted, the errors still firing in prod. That second record lives in source control, the issue tracker, chat and issue channels, long-form docs, and error tracking. A feature with a long bug tail keeps most of its story there, so don't reconstruct it from your transcripts alone.

Use the current client's conversation tools. In Codex, discover `list_threads` and `read_thread`, filter by the active project and time window, and read matching conversations. If tools are unavailable, use only a documented, project-scoped transcript source. Do not assume Cursor paths or scan unrelated projects. State any unavailable history; absence of access is not absence of work.

1. Classify, then route. For one named prior chat, read that chat and recover its latest state directly. Turning habits into a durable skill is `automate-me`. A human-readable summary of your work is a different task. Recall loads working context across recent chats before you act. If the user already gave you a full state capsule (paths, branch, the change), use it and skip the mining.
2. Lock the scope before searching. Pin the window ("recent" is a real range, default the last 7 days), the topic if named, and the workspace (default the active one. Never read another project's transcripts without being asked). State the scope back. Never quietly turn "all" into "recent N".
3. Search matching conversations by actual update time, not UUID order. Start with the topic, then read relevant regions. Skip the current chat plus obvious noise (subagent, eval, and test chats). Return one block per chat: topic, the user's goal, decisions, open threads, struggles and corrections, and artifacts (PRs, tickets, branches), each citing the chat ID. Read one or two chats directly. For independent slices that benefit from delegation, use available local agents under the current delegation rules, with explicit source bounds. Models and reasoning settings come from local role configuration, not this skill. Keep raw transcripts with the reader; combine only findings.
4. Sweep the relevant shared record whenever the topic names a feature, file, subsystem, area, or bug. This is the default, and "my work on X" does not exempt it. Ask of each available source: "what's the current state, what's been tried and didn't hold, and what are users still reporting". Independent source reads may run in parallel; use a local investigator only when useful and able to access the source. Otherwise read it directly. Null results are findings. Skip an unavailable connector and say so. Fold what comes back into the brief. Skip this step only for pure activity recall with no named target ("what did I do this week"), where your own history and live state are the entire answer.
5. Verify against live state through read-only tools. Check surfaced PRs, branches, and tickets with the project's connector or `git`/`gh` where applicable. This step does not run tests or modify the project. When the answer hinges on what an agent actually did (the tools it ran, files it read, errors it hit), read the original transcript, not just a summary. State truncation or unavailable tool events rather than claiming full coverage.
6. Write the brief to the contract below. Group by thread. Stay on the named topic.

## Output contract

Lead with the capsule, then the thread status, then the problems, then the next move. Deeper detail goes below or gets cut.

- **Capsule.** At most 5 bullets. What this work is and where it stands overall.
- **Threads.** One line each, prefixed with one supported status: `[merged #N]`, `[open PR #N]`, `[in flight <branch>]`, `[verified, uncommitted]`, `[changed, unverified]`, `[reverted #N]`, `[planned, not started]`, or `[unknown]`. Use verified only with recorded evidence. Don't invent a branch or completion state to fit a tag.
- **Problems.** At most 5, the recurring ones. Include the symptoms users keep reporting and any fix that shipped and was reverted, so the next attempt starts where the last one failed.
- **Next move.** The single most useful next action, concrete.

An adjacent feature or ticket stays out unless it blocks this one. When the capsule and thread lines outgrow a screen, cut detail before you cut threads. Write the brief through the **unslop** skill, cite chat findings by UUID and shared-record findings by their source (PR #, ticket ID, chat permalink, error-tracker issue), and sanitize private context before any public output.

**Reply:** the brief, to the contract above.
