# momentum-invest

## Subagent delegation

Default subagent model is Haiku (`CLAUDE_CODE_SUBAGENT_MODEL` in
`.claude/settings.json`). Always pass an explicit `subagent_type` so routing
does not depend on that default.

| Work | Agent | Model |
|---|---|---|
| find files, explore the repo, read logs and CI output, simple lookups | `scout` | Haiku |
| implement, refactor, review code against a given spec | `builder` | Sonnet |
| design and deep analysis that needs heavy reading, kept out of main context | `architect` | Opus |

Reasoning about the strategy, the metrics and production decisions stays in the
main session. It already runs on Opus with a warm cache, so delegating it costs
more than doing it here.

Rules:
- One agent per task. Never run several on the same question.
- Pass only what is needed: paths, names, the question. Do not paste file
  contents the agent can read itself.
- Require a short result: conclusions and `path:line`, not file dumps.
- Do not delegate what two or three of your own tool calls would settle.
- Do not redo analysis an agent already did.
