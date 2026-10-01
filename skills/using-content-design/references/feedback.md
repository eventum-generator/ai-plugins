# Feedback

The last step of every stage: report what cost time or quality, so the skills, the scripts and Eventum improve from real work. Report only friction: a wrong or missing fact, an unclear or contradictory instruction, a script bug or missing feature, a step that did no useful work, an Eventum defect. Nothing else: no praise, no summaries, no notes about the generator's own design.

- Repository: skills and scripts - `eventum-generator/ai-plugins`; Eventum itself (a crash, wrong behaviour, a missing feature) - `eventum-generator/eventum`.
- Duplicates: search first (`gh issue list -R <repo> --state open --search "<keywords>"`); when an issue already covers the problem, add a comment with the new evidence instead of opening another.
- Issue: title `<skill, script or Eventum component>: <the problem in one line>`; body: what happened (command, output excerpt, file and line), what was expected, the smallest reproduction, the proposed change, Eventum and plugin versions; label `agent-feedback` when the repository has it. No secrets, customer data or private paths.
- Consent: issues are public. Open them only when the user has allowed it; otherwise append the same text to `.content-design/<name>/feedback.md` under a heading naming the stage (research, build, review, publish) and mention it at hand-over.
