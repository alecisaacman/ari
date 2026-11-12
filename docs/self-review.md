# Morning and Night Reviews, and ARI's Build List

Twice a day ARI looks at where I am and where it falls short.

- **Morning (8:00):** the day's calendar, what matters today on GET DONE and in my open
  loops, and what to start with.
- **Night (21:00):** what I checked off and what moved, what's still open, and how
  tomorrow starts.

When Anthropic refuses a review because the API credits are used up, ARI texts me once
that day, since reviews, stories, and replies that need a model stop until I top them
up (the nightly self-evaluation and builds run on my Claude plan and keep going), and
the desktop pets show it. A review missed while the Mac slept still goes out when ARI next runs, until noon for
the morning and midnight for the night. "ARI review" asks for one any time. The times
come from `ARI_REVIEW_MORNING` and `ARI_REVIEW_NIGHT` in `~/ARI/ari.env` (`off` turns
one off). Each review is kept as an ARI note.

## How a review is written

ARI gathers facts deterministically from its own records and Apple's: open loops,
state, reminders, GET DONE, the calendar, what was checked off, today's conversation,
its build list, and what shipped in the last day (the build log). Only the writing calls
a model (about 2 cents a review), and the model may use only those facts.

## The build list, and the nightly self-evaluation

Proposals come from a nightly self-evaluation, not from the reviews. The reviews are
short, about my day, and written through the API; asked to propose a build too, they
almost always proposed nothing, so in a month the list got one entry.

Each night the "ARI builds" session (below), when nothing approved is waiting, evaluates
ARI instead, on my Claude plan rather than API credits. `python -m ari_core.self_evaluation
evidence` prints what ARI's records show for the last two weeks: tool use and errors,
what I said to ARI, what shipped and whether it got used, what the watchdog has open,
and API spend by channel. The session reads the code it needs to judge, then runs
`propose` with the one build that would help me most. Only one proposal waits at a time.
ARI texts it to me once, after quiet hours: "yes" approves it and the next night builds
it; "hold" leaves it. When I ask ARI for something it can't do, it still offers to add it
to the list (`build_proposals`, which the hub shows).

## Approved builds build themselves

With the builder on (`ari-live connect-builds`), a scheduled task in the Claude app,
"ARI builds", starts a session I can watch, steer, or stop, each night at 10:45 PM,
after the night review ("Run now" on the task starts one sooner). It ran hourly at
first; each session loads the full Claude Code context (about $0.27 at API rates), so
24 sessions a day mostly spent my plan's usage finding nothing approved. The session runs
`python -m ari_core.builder claim`. At most every 5 hours (`ARI_BUILD_EVERY_HOURS`) that
takes the oldest approved build, makes a fresh worktree on branch `ari/build-<id>` from
GitHub's main under `~/ARI/builds`, and prints the brief. The session builds it there,
commits, and runs `finish`, where ARI runs the tests itself: new commits and passing
tests make the build `built`; anything else makes it `stuck`, with the reason. A session
out of credits runs `give-back`, and the next night's run tries again. A build left half-done for 3 hours goes back on the list.

ARI texts me each result once. Nothing goes live until I say "ship it": ARI then brings
the branch up to date with main, tests it again, pushes it to main, and installs it as
the live release. Scheduled tasks run while the Claude app is open; one that was due
while it was closed runs when it opens.

## The build log

Every release `ari-live install` puts live is recorded in ARI's build log (`build_log`):
the commits it shipped since the release before, in their own words, and the files
they touched. Reviews read it beside tool use, so ARI can judge what was worth building
and what to build next, and "what did we build this week?" answers from it. It is also
the raw material for telling the story of building ARI.

## The build story (the content engine)

The series is "Day N of building ARI": Day 1 is the first day ARI's repository has
commits (April 10, 2026), and each later day with commits is the next day. At 9:30 PM on
a day with work, or when I text "ARI story", ARI turns that day's commits into a story
(`ari_core.build_story`): one to three lessons about what was worth building and what
broke; the day in 80 to 160 words; and one or two short-form video outlines (hook, beats,
caption). The lessons come first because ARI's next reviews read them, so the story feeds
its self-improvement before it feeds any post. ARI texts me the story; it never posts
anything.

Every day lives in ARI's content library (`ari_content_items`,
`modules/self_documentation/library.py`), the one place content is kept. Each item goes
through the content process in order: idea (ARI wrote it, or I rewrote it), script
(approved), production (recording, voice, editing), ready (the finished short-form or
long-form piece exists), posted; or it's skipped. Nothing reaches ready without
production and nothing is posted that wasn't ready; an item steps back one stage at a
time. A day ARI writes starts as an idea, because hooks come from commits, which say
what ARI could do, not what I did. The hub shows the library on its own page, /content;
texting "what's in production" or "approve day 19's script" works through ARI's tools.
The older self-documentation idea bank reads the library too.

On the Content page I can rewrite any day's script (hook, beats, caption) and ask ARI
to review it (`ari_core.script_review`). ARI checks it two ways: rules without a model
(a hook of 16 words or fewer, three to six beats, about 20 to 75 seconds spoken, a
caption that opens "Day N of building ARI") and an editor's read by the deeper model
against that day's commits (every claim true to what was built, a hook that earns
attention without overstating, a flow from problem to build to what changed, plain
words). It passes the script or returns notes. "Approve script" only works on a
version that passed; editing an approved script sends it back to idea for a new
review, and scripts are locked once production starts. Rewriting a day keeps its
stage. `python -m ari_core.build_story import-notes` moved the days first written as
ARI notes into the library. `python -m ari_core.build_story backfill --repo
PATH` writes every day so far. Only the writing calls a model, and only with the commits'
own words.

## Production: ARI's studio

Starting production on a day ("Start production" on the Content page, or telling ARI)
has ARI's studio (`tools/ari-studio/studio.py`, through `ari_core.content_production`)
make the video in the background:

1. **Narration** in my voice: Chatterbox, an open-source voice-cloning model, speaks
   each line of the approved script (the hook, each beat, a sign-off) from my one-minute
   sample at `~/ARI/media/voice/alec-sample.wav` (recorded once with
   `~/ARI/media/voice/record.sh`). Without the sample it uses the model's default voice.
   This Mac (an M1 with 8 GB) can't hold the model, so it runs on Replicate's GPUs, paid
   per second with no subscription (`ari-live connect-replicate`). Every second is
   counted at Replicate's dearest GPU rate against a monthly cap,
   `ARI_STUDIO_MONTHLY_USD` ($5); past it the studio stops. `ARI_STUDIO_VOICE=local`
   runs it on this machine instead, for a bigger Mac. Locally I chose to leave
   Chatterbox's inaudible AI watermark off (`ARI_STUDIO_WATERMARK=1` turns it on);
   Replicate's hosted copy always adds it. Posts get the platform's own AI-generated
   label either way.
2. **Footage** chosen per beat: the diff of the day's commit that shares the most
   words with the beat, with the matching lines lit; a big-number card for a beat
   with a number; a re-created ARI message (labelled as one) for a beat about
   texting; a lesson card; otherwise the beat's own words, never unrelated code.
   The hook gets a title card and the sign-off ARI's hummingbird. Nothing personal goes
   in (no texts, calendar, or to-dos), because the video is public.
3. **Captions** a few words at a time, timed across each spoken line.
4. **The cut**: ffmpeg pushes slowly into each shot, lays the captions over it, and
   joins it all with the narration into a 1080 x 1920 MP4 in `~/ARI/media/out`.

Cards and captions are drawn by headless Chrome, because this Mac's ffmpeg has no text
drawing. The model and its dependencies live in their own environment
(`~/ARI/media/venv`), never in ARI's runtime. When the video is done the studio
attaches it to the day (`ari api content video`), and it plays on the Content page. A
day can't be marked ready to post until it has a video; that step stays mine. A
floating-head narrator (an open-source lip-sync model) is the next layer, once the base
video is right.

