# Decisions (ADR log)

| # | Date | Decision | Rationale | Revisit when |
|---|------|----------|-----------|--------------|
| 001 | 2026-05 | Python-first, batch CLI | Fast iteration, pytest, no frontend | Need live dashboard |
| 002 | 2026-05 | Parquet silver + JSON manifests | Immutable slices, reproducible runs | Catalog grows → consider DuckDB |
| 003 | 2026-05 | Polygon as optional tick vendor | Best-documented US trades API | Cheaper tick source appears |
| 004 | 2026-06 | **Alpha Vantage as default data source** | Free daily bars for honest OOS research; removed fake data paths | Need tick microstructure |
| 005 | 2026-06 | RSS news as parallel silver stream | Free macro headlines; merge in replay later | Historical news archive exists |

Supersedes: prior fake-data ingest path — **retracted 2026-06** in favor of real market data only.
