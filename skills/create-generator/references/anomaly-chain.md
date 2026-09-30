# Anomaly chain

An anomaly chain is an ordered sequence of records a detection or alert rule fires on: a burst of failed logons followed by a success from the same address, a role created, granted access to sensitive data and deleted within an hour, a backup repository full followed by failed jobs. The generator mixes recurring episodes of one chain into ordinary activity. The data is useful only if a rule written for the chain fires on episodes and nowhere else, while rules that look at parts of it meet realistic noise.

## Choice

One chain from the brief's candidates: steps, linking fields, time window, detection idea. Every step is a record the source writes in ordinary activity; the chain is expressible in `measure-spec.md` terms, which is also how a rule would see it.

## Actors

The actors of an episode are every entity it uses: accounts, source addresses, hosts, targets. The episode's population is the one whose ordinary activity the episode imitates (external scanners for a brute force, administrators for a privilege change); its addresses and hosts come from that population's pool.

## Presence in background

Every step, and every actor and actor pair an episode can use, also occurs in ordinary background, and the actor is active at the hours episodes start. Only the complete ordered sequence is absent from background. Size it so that each such element's expected count in a 4-day background capture is at least 10: absence in one capture then has probability below 1e-4, so presence holds in every capture and in users' data, not only on a lucky run.

## Recurrence

`event.template.params`: `anomaly_mode` (default `true`; `false` gives background only) and `anomaly_interval_hours` (default 24).

- The first episode starts within min(interval, 24 h) of the start of generation, so a short run or test window contains one.
- Each next episode is due one interval after the actual start of the previous one and starts in a window w = min(interval / 4, 6 h) centred on the due time: wide enough that start times do not look periodic, bounded so that gaps stay within interval ± w/2.
- The start hour inside the window is drawn with weight proportional to the square of the population's hourly volume plus a small floor: episodes concentrate in busy hours, where they hide in traffic, and a start that happens to fall at night does not pin later ones there.
- With scheduled activity, episodes start at scheduled runs.
- Missed episodes are not replayed.
- An eligible actor is available in every window. The parameter range excludes intervals the design cannot serve: shorter than the chain window, not a multiple of the schedule period, or too short for a finite resource (a name pool, a free slot, working hours).
- Actor and target rotate between episodes.

## Episode shape

An episode is ordinary activity of its actor with the chain inside:

- within every cap and limit background respects, from addresses and hosts of its population's pool;
- before and after it, the actor behaves as at the same hour on ordinary days;
- it leaves every state (counters, locks, open objects, names in use) as an ordinary session would, and never cancels, delays or takes over the actor's own work.

## Guard

Background never completes the chain. Prefer a background design in which it cannot form: cooldowns, caps, disjoint targets. When a guard is unavoidable, it acts only on the exact final step within the chain window, changes its target or outcome to a normal alternative (never reassigns, defers or drops the record), fires rarely, suppresses no noticeable share of an ordinary action, counts the episode's own records, and keeps nothing armed after an episode.
