# E0 SQLite Workflow

This guide covers DB init, ingest, and running existing E0 tools against the DB.

## 1) Initialize the DB

```bash
python3 footstat_db_init.py \
  --db data/footstat.sqlite3 \
  --show-tables
```

## 2) Plan ingest (no writes)

```bash
python3 e0_ingest_db.py \
  --db data/footstat.sqlite3 \
  --data-dir data/football-data.co.uk \
  --glob "E0*.csv" \
  --dry-run
```

## 3) Ingest data

```bash
python3 e0_ingest_db.py \
  --db data/footstat.sqlite3 \
  --data-dir data/football-data.co.uk \
  --glob "E0*.csv"
```

When a source file has removed rows and you need stale DB rows removed too:

```bash
python3 e0_ingest_db.py \
  --db data/footstat.sqlite3 \
  --data-dir data/football-data.co.uk \
  --replace-source
```

If `E0.csv` season inference is wrong, set it explicitly:

```bash
python3 e0_ingest_db.py \
  --db data/footstat.sqlite3 \
  --data-dir data/football-data.co.uk \
  --current-label 2025-2026
```

## 4) Run E0 tools from DB

### Correlation

```bash
python3 e0_corr.py \
  --source db \
  --db data/footstat.sqlite3 \
  --team Arsenal \
  --seasons 2025-2026
```

### Weekly static SVG

```bash
python3 e0_weekly_halfwin_plot.py \
  --source db \
  --db data/footstat.sqlite3 \
  --team Arsenal \
  --seasons 2025-2026 \
  --out docs/arsenal_weekly_halfwin_db.svg
```

### Weekly animated HTML

```bash
python3 e0_weekly_halfwin_animate.py \
  --source db \
  --db data/footstat.sqlite3 \
  --team Arsenal \
  --seasons 2025-2026 \
  --out docs/arsenal_weekly_halfwin_db_animated.html
```

### Weekly custom metric SVG (example: opponent fouls)

```bash
python3 e0_weekly_metric_plot.py \
  --source db \
  --db data/footstat.sqlite3 \
  --team Arsenal \
  --seasons 2025-2026 \
  --metric opponent_fouls \
  --out docs/arsenal_weekly_opponent_fouls.svg
```

### Weekly custom metric animated HTML (example: opponent fouls)

```bash
python3 e0_weekly_metric_animate.py \
  --source db \
  --db data/footstat.sqlite3 \
  --team Arsenal \
  --seasons 2025-2026 \
  --metric opponent_fouls \
  --interval-ms 500 \
  --out docs/arsenal_weekly_opponent_fouls_animated.html
```

## 5) Compare CSV vs DB behavior

CSV mode remains the default for all existing commands.

```bash
python3 e0_corr.py \
  --source csv \
  --csv data/football-data.co.uk/E0.csv \
  --team Arsenal \
  --limit 10
```

```bash
python3 e0_corr.py \
  --source db \
  --db data/footstat.sqlite3 \
  --team Arsenal \
  --seasons 2025-2026 \
  --limit 10
```

## 6) Multi-season commands

These commands currently read CSV files from `data/football-data.co.uk`:

- `e0_multi_season_halfwin_plot.py`
- `e0_multi_season_halfwin_animate.py`

They are useful for season-over-season overlays while DB-backed E0 workflows run in
parallel.
