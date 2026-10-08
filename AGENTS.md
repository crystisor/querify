# Instructions for Codex

## Scope

These instructions apply to this repository (`F:\Projects\Queryfi`) and all its subdirectories. Follow applicable instructions in nested `AGENTS.md` files as well.

## Required local skills

Every new Codex session used to code in this repository must discover and use the applicable skills in `.agents`, without requiring the user to request them again.

Before starting a coding task:

1. Locate all `SKILL.md` files recursively under `.agents` (normally `.agents/skills/<skill-name>/SKILL.md`). Resolve paths from the repository root, even when working in a subdirectory.
2. Read each skill's name, description, and applicability criteria to determine which skills apply to the task.
3. Read the full instructions of each applicable skill before doing the work it governs. Follow required references and consult optional supporting resources when needed, resolving relative paths from the skill's directory.
4. Briefly state which skills you are applying, then follow their workflows throughout implementation and verification.

Apply all relevant skills together. Do not apply unrelated skills merely because they exist. Discover skills again in each new session so newly added local skills are included; during a session, recheck when the task changes or skills are added or updated.

Local skills apply to writing code, implementing features, fixing bugs, refactoring, creating tests, debugging, reviewing code, and making architecture decisions, according to each skill's applicability criteria. Higher-priority instructions and explicit user instructions take precedence over skill guidance.

If `.agents`, an applicable skill, or a required reference cannot be read, report the exact missing or inaccessible path and its impact. Do not silently skip required instructions or claim to have applied an unread skill.

## SOLID coding standard

Always apply `.agents/skills/solid/SKILL.md` to coding tasks covered by that skill. All new and modified code must follow its SOLID guidance:

- **Single Responsibility:** Keep responsibilities cohesive; separate business logic, I/O, and presentation.
- **Open/Closed:** Provide appropriate extension points for behavior that actually varies.
- **Liskov Substitution:** Preserve behavioral contracts across implementations.
- **Interface Segregation:** Keep interfaces focused on their consumers' needs.
- **Dependency Inversion:** Keep high-level policy independent of infrastructure details through suitable boundaries.

Use idiomatic constructs and keep abstractions proportional to the requirements. Preserve requested behavior and avoid unrelated refactoring.

Before completing a coding task, review the changes against the applicable skills, address violations introduced by the changes, run relevant checks, and report the results and any verification limitations.
