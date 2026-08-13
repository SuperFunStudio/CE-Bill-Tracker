# Current focus

<!--
Three or four lines on what's actively being worked. This is the one part of
CODEBASE_CONTEXT.md that can't be derived — everything else describes what exists, not what
matters. Rewrite it when the week's work changes; the generator stamps this file's git age
and marks it stale after 21 days, and prints the directories git says are actually moving
so a reader can see whether this prose still matches reality.
-->

- **Launch comms and measurement.** Email has just moved to Postmark (both streams, compliant
  footer, verifiable sender); GA4 is now queryable from the terminal, with a pre-post traffic
  baseline recorded so a launch spike has something to be measured against.
- **The exposure calculator.** Speccing and building producer attribution — answering "who owes
  this" before "how much", starting from the OR/CO fee schedules.
- **Corpus text integrity.** Reversible repair paths for wrong-text bills, split by which failure
  actually happened, and extraction running against the enacted version rather than the
  introduced draft.
- **Conversion surfaces.** Paywalls all reporting themselves the same way, referral in email,
  and the pricing page argued rather than listed.
