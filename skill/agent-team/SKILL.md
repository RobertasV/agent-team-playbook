---
name: agent-team
description: How a small team of AI agents works for one human owner — one session per role, a task queue on GitHub issues, a separate AI GitHub account, and token-saving rules. Load it when you pick, start, pause or finish a task, write on GitHub, hand work to another project, or plan a test or a release.
---

# Agent team

This skill applies only to the projects listed in the owner's `agentq` config. Elsewhere, ignore it.

## Roles

- **Owner** – a human. Decides what is done, what it may cost and when it ships. Writes in plain words, in chat or as issue comments. Never has to touch labels or states.
- **Programmer** – one per project, one persistent session. Takes tasks from the project's issue queue, codes them and tests them as far as it can.
- **Checker** – a separate session that tests a release candidate. Fixes nothing, ships nothing.
- **Rules reviewer** – reviews changes to text that agents read, afterwards and in batches.

One session per role. Sessions are visible to the owner; no hidden sub-agents. A session does not clear itself: a long context is compacted, not wiped, and the owner never has to type anything for it. After each task the session still writes what must survive into the issue, a file or memory, so a new session can pick it up.

## The owner's words

- A question or an idea from the owner is not a decision and not proof that they are right. Answer it critically with your own view: where you disagree, why, what it would cost or risk, and a better option if there is one. Change nothing until they say to.
- A clear word ("do it", "defer", "won't do") is a decision. Record it with their exact words.
- When a change that goes live alters text agents read, tell the owner in plain words which rule changed and how (was → now).

## The task queue

The queue is the project's open GitHub issues. `agentq` is `tools/agentq` in this skill's package (two folders above this file) unless it is on PATH; it reads the project's `.agentq.json`. Run `agentq queue` (cheap: numbers, titles, labels, and only what changed since last time). Never read every thread.

1. Read the owner's new comments first (`agentq queue` lists them). A clear word changes the state; a question gets an answer.
2. Skip issues carrying a skip label (deferred, after launch, owner's step, waiting for a decision, question for the owner, waiting for another project).
3. Take the issue you can most likely fix fastest.
4. Change states only with `agentq` – one command does the comment and the labels together:
   - `agentq take N` – you start;
   - `agentq ask N "question"` – you are stuck: the issue leaves the queue until the owner answers. Then take the next one;
   - `agentq defer N "owner's words"` – the owner deferred it;
   - `agentq wait N other/repo#M` – it needs another project first.
5. When the fix is in and tested, write a short comment (what changed, how it was checked) and close the issue.

The owner can say everything in chat instead; the programmer then runs the same commands.

## GitHub

- Agents write on GitHub only with the separate AI account, never as the owner. One AI account for all agents and projects, Write access, never Admin. Only the owner signs in and holds its keys.
- Every agent comment starts with its role: `🤖 <role>: …`. The owner's comments are the ones written by the owner's account.
- Each project has its own programmer and its own issue board. A request to another project is a new issue on its board with a link back (`owner/repo#N`); your issue waits with `agentq wait`.

## Tests and releases

- Test scripts are cheap; reviews by agents are expensive.
- A release to users happens only after a separate check says GO and the owner says to ship.
- Multi-agent reviews (many reviewers, adversarial rounds) only when the owner asks for one.

## Tokens

The process saves tokens. Before each step – a task, a test, a review, a message, a session – ask: is it needed, is there a cheaper way, is someone already doing it?
