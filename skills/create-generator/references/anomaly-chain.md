# Anomaly chain

An anomaly chain is an ordered sequence of records a detection or alert rule fires on, for example a role created, granted access to a sensitive table and deleted within an hour, or a backup repository full followed by failed jobs. The generator mixes recurring episodes of one chain into ordinary activity; `chain-spec.md` describes the chain for the checker.

## Choice

One chain from the brief's candidates: steps, linking fields, time window, detection idea. Every step is a record the source writes in ordinary activity.

## Actors

The actors of an episode are every entity it uses: accounts, source addresses, hosts, targets. The episode's population is the one whose ordinary activity the episode imitates (external scanners for a brute force, administrators for a privilege change); its addresses and hosts come from that population's pool.

## Presence in background

Every step, and every actor and actor pair an episode can use, also occurs in ordinary background often enough to appear in every capture of the acceptance protocol, and the actor is active at the hours episodes start. Only the complete ordered sequence is absent from background, so a detection that fires on part of the chain or on a rare actor produces false positives, as it would on real data.

## Recurrence

`event.template.params`: `anomaly_mode` (default `true`; `false` gives background only) and `anomaly_interval_hours` (default 24).

- The first episode starts within min(interval, 24 h).
- Each next episode is due one interval after the actual start of the previous one and starts in a window w = min(interval / 4, 6 h) centred on the due time.
- Start hours follow the activity curve of the episode's population; with scheduled activity, episodes start at scheduled runs.
- Missed episodes are not replayed.
- An eligible actor is available in every window. The parameter range excludes intervals the design cannot serve: shorter than the chain window, not a multiple of the schedule period, or too short for a finite resource (a name pool, a free slot, working hours).
- Actor and target rotate between episodes.

## Episode shape

An episode is ordinary activity of its actor with the chain inside:

- within every cap and limit background respects, from addresses and hosts of its population's pool;
- before and after it, the actor behaves as at the same hour on ordinary days;
- it leaves every state (counters, locks, open objects, names in use) as an ordinary session would and never cancels, delays or takes over the actor's own work.

## Guard

Background never completes the chain. Prefer a background design in which it cannot form (cooldowns, caps, disjoint targets). When a guard is unavoidable, it acts only on the exact final step within the chain window, changes its target or outcome to a normal alternative (never reassigns, defers or drops the record), fires rarely, suppresses no noticeable share of an ordinary action, counts the episode's own records, and keeps nothing armed after an episode.
