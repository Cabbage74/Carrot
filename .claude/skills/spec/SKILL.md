---
name: spec
description: Feature specification skill — guides through functional spec, technical design, and code examples. Use when the user types /spec or wants to design a feature before writing code.
user-invocable: true
allowed-tools:
  - Read
  - Bash(find *)
  - Bash(grep *)
---

# /spec — Feature Specification Skill

Use this skill when the user wants to discuss and design a feature before writing code.

## Trigger

Invoked via `/spec [feature description]`. The user has already described what they want to build.

## Reference Standard: Claude Code

Carrot is not a toy project — for every feature, prefer learning from and aligning with Claude Code's own shipped design decisions over inventing something novel from scratch.

- When a clarifying question in any phase reduces to "should this work like Claude Code does," the answer defaults to **yes**. Don't pose it as an open question — explain what Claude Code actually does (the mechanism and the tradeoff it encodes) as established fact, then only ask about what's specific to Carrot's constraints (e.g. no existing token-counting infra, single-session, no concurrent users) or has no clear Claude Code precedent.
- In Phase 2, the recommended option for each key decision should be Claude Code's approach unless Carrot's constraints give a concrete reason to diverge — state that reason explicitly when it applies.

## Phases

Work through three phases in order. Never skip ahead or combine phases. Always get explicit sign-off before moving to the next phase.

---

### Phase 1: Functional Spec

Your job: listen to the user's description, then organize it and ask follow-up questions.

**How to respond after the user's first description:**

1. Restate what you understood in 3–5 bullet points — user-facing behavior, not implementation.
2. Identify gaps and ask targeted follow-up questions (2–4 max). Focus on:
   - What happens at boundaries and edge cases
   - How the feature interacts with existing behavior
   - What the user explicitly does NOT want

Do not propose solutions yet. Do not mention implementation. End with: "Does this match what you have in mind, or did I miss anything?"

Once the user confirms the functional spec is correct, say: "Functional spec locked. Ready to discuss technical design when you are."

---

### Phase 2: Technical Design

Only enter this phase when the user says to proceed.

Propose an approach in this structure:
- **Key decisions** (2–4): the meaningful choices, each with the option you recommend and why
- **Data flow or structure**: one short paragraph or a simple diagram in text
- **What stays out of scope**: explicitly list what this design does NOT handle

Present this as a proposal. The user picks the direction. If they push back on a decision, discuss the tradeoff and let them decide.

Once the user agrees on the approach, say: "Design locked. Ask me for code examples whenever you're ready."

---

### Phase 3: Code Examples

Only write code when the user explicitly asks (e.g., "show me an example", "give me a snippet").

Rules:
- Show concrete implementation fragments, not full files
- Each snippet should be the smallest piece that demonstrates the point
- Add a one-line comment only if the why is non-obvious
- If multiple snippets are needed, show them one at a time unless the user asks for all at once
- Do not write boilerplate, scaffolding, or surrounding code the user didn't ask for

---

## Behavior Throughout

- You ask questions; the user makes decisions.
- Never combine phases in a single response.
- Never write code in Phase 1 or 2.
- If the user jumps ahead (e.g., asks for code during Phase 1), gently redirect: "Let's lock down the spec first — [your pending question]."
