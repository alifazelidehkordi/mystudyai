# Medical tutor instructions

The project now runs the teaching workflow **inside the authenticated agent harness** (Codex CLI, Pi, or a compatible alternative), not through an OpenAI API client.

- Codex skill: `.agents/skills/medical-study/SKILL.md`
- Pi skill: `.pi/skills/medical-study/SKILL.md`
- Shared project policy: `AGENTS.md`
- Local professor-note context: `mystudyai context "topic"`
- Local lecture diagrams: `mystudyai figures "topic"`

The medical-study skill is the canonical teaching specification for **probe → plan → teach → check → reinforce**. Keep its Codex/Pi mirrors byte-identical. Do not reintroduce a second model client or require `OPENAI_API_KEY`.
