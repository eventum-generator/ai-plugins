# Anomaly chain

An anomaly chain is an ordered sequence of records a detection or alert rule fires on: a burst of failed logons followed by a success from the same address, a role created, granted access to sensitive data and deleted within an hour, a backup repository full followed by failed jobs. The generator mixes recurring episodes of one chain into ordinary activity. The data is useful only if a rule written for the chain fires on episodes and nowhere else, while rules that look at parts of it meet realistic noise.

## Choice

One chain from the brief's candidates: steps, linking fields, time window, detection idea. Every step is a record the source writes in ordinary activity; the chain is expressible in `measure-spec.md` terms, which is also how a rule would see it.

## Actors

The actors of an episode are every entity it uses: accounts, source addresses, hosts, targets. The episode's population is the one whose ordinary activity the episode imitates (external scanners for a brute force, administrators for a privilege change); its addresses and hosts come from that population's pool.

## Presence in background

Every step (by any actor), every actor and every actor pair an episode can use (who and from where: an account with its source address or host, in any record) also occurs in ordinary background, and the actor is active at the hours episodes start; combinations of a step with a particular actor, and pairs with rotating targets, need not. Only the complete ordered sequence is absent from background. Steps linked by a value beyond the chain key (a token created and later revoked, a session opened and closed) occur linked in background too: ordinary actors create, use and close the same kinds of objects, so a rule on the link alone meets noise. Every value an episode writes into a step (each username a spray tries, each host a scan touches) also occurs in that step in background, while its pairs with the episode's source need not; a `presence` spec limited with `when` to the step's records measures it. Steps linked only through the key need no such pairing. An `ne` link counts too: steps that must differ in a value (distinct usernames from one address) need that variety in background. Aim for an expected count of at least 10 per element in a 4-day background capture, and never below 5: absence in one capture then has probability below 1e-4 (below 1% at 5) for independent records; values written in bursts scatter more, so aim higher for them, so presence holds in every capture and in users' data, not only on a lucky run. Where the source's cadence cannot reach that (one run per client per night), episode actors are drawn from the busier part of the population, or the pool of values an episode uses is made smaller.

Episodes of one key are separated by more than the chain window; within an episode the final step may repeat (every further download after the first), and measurement counts it as one chain.

## Recurrence

`event.template.params`: `anomaly_mode` (default `true`; `false` gives background only) and `anomaly_interval_hours` (default 24).

- The first episode starts within min(interval, 24 h) of the start of generation, so a short run or test window contains one.
- Each next episode is due one interval after the actual start of the previous one and starts in a window w = min(interval / 4, 6 h) centred on the due time: wide enough that start times do not look periodic, bounded so that gaps stay within interval ± w/2.
- The start inside a window is drawn with weight proportional to the square of the population's volume at that time (uniform only where the whole window has no activity), so the busiest part of every window dominates, weekends included, and episodes hide in traffic. The first window spans min(interval, 24 h), so the first start lands in busy hours and later windows, one interval on, stay there; a start at night occurs only where the population is active at night at a comparable level.
- With scheduled activity, episodes start at scheduled runs.
- Missed episodes are not replayed.
- An eligible actor is available in every window. The parameter range excludes intervals the design cannot serve: shorter than the chain window, not a multiple of the schedule period, too short for a finite resource (a name pool, a free slot), or such that windows fall in hours the episode population does not act (for a population with a daily cycle: anything but whole days).
- Actor and target rotate between episodes.

## Episode shape

An episode is ordinary activity of its actor with the chain inside:

- within every cap, limit and spacing background respects (sessions of one actor at least as far apart as in background), from addresses and hosts of its population's pool;
- before and after it, the actor behaves as at the same hour on ordinary days;
- it leaves every state (counters, locks, open objects, names in use) as an ordinary session would, and never cancels, delays or takes over the actor's own work in progress; reserving an actor's free time ahead of an episode so that its spacing holds is allowed.

## Guard

Background never completes the chain. Prefer a background design in which it cannot form: cooldowns, caps, disjoint targets. When a guard is unavoidable, it acts only on the exact final step within the chain window, changes its target or outcome to a normal alternative (never reassigns, defers or drops the record), fires rarely, suppresses no noticeable share of an ordinary action, counts the episode's own records, and keeps nothing armed after an episode.
