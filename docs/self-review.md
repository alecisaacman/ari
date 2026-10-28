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
tool errors, the skills it doesn't have yet, and its build list. Only the writing calls
a model (about 2 cents a review), and the model may use only those facts.

## The build list

A review may propose one build: something ARI should be able to do and can't. It goes
on the build list (`build_proposals`), which the hub shows. I answer "yes" or "hold" in
the conversation, and ARI records it. An approved build is a brief for a coding agent.
ARI never starts building on its own. When I ask for something it can't do, ARI offers
to add it to the list.
