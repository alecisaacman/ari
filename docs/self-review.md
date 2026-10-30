# Morning and Night Reviews, and ARI's Build List

Twice a day ARI looks at where I am and where it falls short.

- **Morning (8:00):** the day's calendar, what matters today on GET DONE and in my open
  loops, and what to start with.
- **Night (21:00):** what I checked off and what moved, what's still open, and how
  tomorrow starts.

A review missed while the Mac slept still goes out when ARI next runs, until noon for
the morning and midnight for the night. "ARI review" asks for one any time. The times
come from `ARI_REVIEW_MORNING` and `ARI_REVIEW_NIGHT` in `~/ARI/ari.env` (`off` turns
one off). Each review is kept as an ARI note.

## How a review is written

ARI gathers facts deterministically from its own records and Apple's: open loops,
state, reminders, GET DONE, the calendar, what was checked off, today's conversation,
tool errors, the skills it doesn't have yet, its build list, what shipped in the last
day (the build log), and how often each of its tools was used this week. Only the writing calls
a model (about 2 cents a review), and the model may use only those facts.

## The build list

A review may propose one build: something ARI should be able to do and can't. It goes
on the build list (`build_proposals`), which the hub shows. I answer "yes" or "hold" in
the conversation, and ARI records it. When I ask for something it can't do, ARI offers
to add it to the list.

## Approved builds build themselves

With the builder on (`ari-live connect-builds`), an hourly scheduled task in the Claude
app, "ARI builds", starts a session I can watch, steer, or stop. The session runs
`python -m ari_core.builder claim`. At most every 5 hours (`ARI_BUILD_EVERY_HOURS`) that
takes the oldest approved build, makes a fresh worktree on branch `ari/build-<id>` from
GitHub's main under `~/ARI/builds`, and prints the brief. The session builds it there,
commits, and runs `finish`, where ARI runs the tests itself: new commits and passing
tests make the build `built`; anything else makes it `stuck`, with the reason. A session
out of credits runs `give-back`, and the next hourly run tries again, so the build starts
when the credits refresh. A build left half-done for 3 hours goes back on the list.

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
