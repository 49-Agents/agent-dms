# agent-dms launch preparation

Prepared 2026-10-03 UTC. Draft strategy and copy; no post, upload, spend or
customer contact has occurred. The destination is the repository README and
working local demo, once public. This is a developer-tool launch within 49Agents.

## Audience and demand hypothesis

Working hypothesis: a developer already runs two or more coding agents on one
Linux project and needs them to exchange questions, work status and results
without the developer relaying every message. Success means the agents complete
one useful, traceable exchange in that developer's real project.

The owner's request is evidence of an internal workflow need. The 49Agents
business context positions tools as demonstrations that bring traffic and
credibility; service buyers are a distinct audience. Neither the product request,
competitor stars nor another 49Agents product's launch establishes external
agent-dms demand. No curated creative case studies were available for this brief.

PULL framing for this launch:

| Question | Current answer |
| --- | --- |
| Project | Coordinate existing agents while completing a real software task. |
| Present priority | Hypothesis: repeated handoffs/questions interrupt the developer. No external customer incident is verified yet. |
| Options | Manual copy/paste, shared files, existing orchestration tools, MCP Agent Mail, Concord MCP, or keep the current workflow. |
| Limitations | Hypothesis: the developer wants separate clients with durable messaging and visible current work. Alternatives may already be adequate. |
| Credible offer | A small MIT-licensed project mailbox: install, run the demo, then connect separately provisioned MCP clients. |
| Main adoption risk | Setup friction and whether native clients reliably check their inbox; native interoperability needs acceptance evidence. |

Keep the competitor report's dated evidence and license qualifications. Do not
claim first, largest, unique, faster or better without a direct test. No new
customer interviews or adoption results were invented during preparation.

## Release sequence

1. Review the source/readiness checklist; complete native acceptance or keep
   explicit SDK-only limitations. Establish a maintainer/security contact and
   the PyPI publisher. Get exact-action publication approval.
2. Merge the reviewed source through the maintainer release workflow. Verify
   exact main/CI, then build and rehearse the package. Review history before
   making the repo public; do not expose a placeholder-only main branch.
3. Make the approved source public, publish the reviewed PyPI version and
   GitHub release, and confirm a fresh download can complete the demo.
4. Add the MCP Registry entry after package ownership, namespace and consumer
   invocation checks. A registry listing is optional for the initial release.
5. Offer the working demo through one owner-approved developer channel. Record
   real setup feedback before repeating the same announcement across channels.

## Channel plan

| Channel | Draft/action | Condition |
| --- | --- | --- |
| GitHub | README, MIT, release notes, issue forms, demo and support policy | Public exact reviewed source; security reporting enabled. |
| PyPI | 0.1.0 package, metadata and attestations | Owner/account + OIDC configured; exact artifacts reviewed. |
| MCP Registry | server.json and README ownership marker | Real PyPI version, org Owner auth, consumer validation. |
| Show HN | Title/intro below linking directly to the working repository | Owner has worked on it, can discuss it, and others can try it without signup. Recheck HN rules; no solicited votes. |
| X or LinkedIn | One selected short post plus repository link | Owner chooses account/copy; adapt format and disclose authorship plainly. |
| Reddit | Answer a relevant coordination discussion or a permitted project post | Check the specific community's current self-promotion rules; no bulk posting. |
| Product Hunt / additional launchpads | Optional later batch | Native demo and feedback first; coordinate timing with other 49Agents launches. No paid listing assumed. |

The order is a recommendation, not a booking or account action. There is no
promised traffic, star count, revenue, launch-day ranking or conversion rate.

## Drafts for review

Owner-selected headline: **let agents DM each other** (`headline-04-C`, revision 2),
using the owner's exact wording. It revises the headline selected in round 1;
the previous wording and review history remain in that round. Recommended short
post: `post-01-A` (not owner-selected). Full gallery source is
[candidates.json](candidates.json):
8 distinct concepts × 4 options for each of two text elements, 64 candidates.
All use the same neutral rendering. No image/video asset was commissioned.

Suggested Show HN title:

> Show HN: agent-dms, let agents DM each other

Suggested opening comment, to adapt to the actual release state before posting:

> We built agent-dms at 49Agents for projects where separately running agents
> need to find each other, share their current work and exchange messages.
>
> It is one local MCP daemon with a SQLite mailbox. Each conversation has its
> own identity. Agents publish a 1–30-word status; messages remain pending until
> explicitly acknowledged. It also supports Manager/Worker questions and reviews.
>
> The README includes a temporary two-client demo that runs without a provider
> account. The code is MIT-licensed. Linux/Python 3.11 and 3.12 and official SDK
> HTTP/stdio clients are tested; native client verification is tracked separately.
>
> If you try it on a multi-agent project, I would like to hear where setup or
> inbox handling gets in the way, and what you use for this today.

Do not post the native limitation unchanged if new evidence has superseded it;
update to the exact observed client versions, avoiding a universal claim.
The HN title must stay within its current UI limit; recheck at submission.

## Demo and conversation guide

Run `python examples/demo.py` in a clean environment, record actual terminal
output, then explain: directory, status, DM, exact claim, reply with parent ACK,
reply ACK. Say clearly that these are SDK clients. A native Claude/Codex screen
recording is a later asset after the acceptance procedure, not simulated output.

Useful first feedback prompts: what task were your agents doing; what did you
use before; where did installation stop; did the peer actually handle the DM;
would you use it on the next task and why? Ask these after an actual attempt,
not as a survey that presumes demand. Do not contact anyone without authorization.

## Launch-day and follow-up log

The owner chooses the date and account. Before posting: verify public clone,
package ownership/hash, fresh install/demo, security contact, exact copy and
working destination. After posting: retain post URL/time and respond to real
setup issues. Stop amplification if a security/data-loss issue appears; fix,
review and communicate the concrete affected versions.

Record opt-in reports of installation started/completed, first successful real
DM, next-task reuse and reasons for abandonment. GitHub views/stars and PyPI
downloads are secondary, noisy indicators; downloads can be automated. There is
no phone-home telemetry in this launch preparation. Review the first few real
attempts before deciding whether to broaden distribution or change onboarding.

Reference: [Show HN guidelines](https://news.ycombinator.com/showhn.html), retrieved
2026-10-03. Other platforms' eligibility/rules must be checked at posting time.
