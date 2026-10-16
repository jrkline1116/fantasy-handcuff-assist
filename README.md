# Fantasy Handcuff Assist

Every NFL backfield sorted by workload, with usage trends, startable backs, and the true handcuffs to own.

## What it shows

- **Tiers**: Every Down (a back with 69%+ of RB carries + targets, season or last 4 games), Committee (three backs at 15%+ with nobody at 50%), Split (everything else).
- **Usage** counts only games each back played, so missed games don't drag his share down.
- **Trend**: last-4-game share minus season share; arrows at ±5 points.
- **RB1 / RB2** badges: top 12 / top 24 in points per game (PPR, Half-PPR, Standard tabs).
- **Handcuff**: the next healthy back behind an every-down starter.
- **Injury**: IR/PUP from weekly rosters; Out/Doubtful/Questionable and DNP/limited practice from the weekly injury report.

## Data

Built from [nflverse](https://github.com/nflverse/nflverse-data) weekly player stats, injury reports and rosters by `scripts/build_data.py`, which writes `data/backfields.js`. The GitHub Action in `.github/workflows/update-data.yml` reruns it Tuesday and Friday mornings (Arizona time) and commits any changes. Run it by hand from the Actions tab with **Run workflow**.

## Local build

```
python3 scripts/build_data.py
```

Then open `index.html`.
