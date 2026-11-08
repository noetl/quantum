# Bot Tower

<https://dg-create.com/tower/> is the team's bot-activity dashboard. The saved
page title is "Bot Tower". Its description is: "A skyscraper of offices, one
per Grok bot: see who is busy, who is idle and who is waiting on you." The
header clock is labeled New York.

What the page shows:

- A building of floors. Each office is a bot. Search is labeled "Find a bot,
  role or floor". An elevator control is labeled "Elevator: go to floor".
- Lobby counts for busy, waiting, active in the last 24 hours, and idle.
- A lobby ticker.
- An office panel with status, floor, name, role, last active, current task,
  progress, a section titled "Waiting on Dimitri", a timeline, and a link
  labeled "Open in Grok Bot".
- Statuses used by the page: busy, idle, waiting on Dimitri, and recently
  active (an idle bot with activity in a rolling 24 hour window).
- Zoom, refresh, a tilt control, and a motion control ("Motion: full" in the
  saved markup).
- A chip labeled "sample data", hidden unless the page is showing its fallback.

The page loads live JSON from `/tower/tower.json`, then tries `./tower.json`.
If both fail, it renders sample data embedded in the page and shows the
"sample data" chip. This repository does not copy that sample roster. The
saved page does not name this competition, and the counts in the static HTML
are the empty placeholders (`0` busy, waiting, active, and idle) before a
fetch runs.

Nothing beyond that layout is claimed here. Open the URL for whoever is busy
right now.
