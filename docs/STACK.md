# Stack & languages

## Default advice for crucibo v0

**Primary: Python 3.11+**

- Fastest path to **columnar data**, **Parquet**, **HTTP vendor APIs**, **stats**, and **visualization**.
- One language keeps the **mental stack** small while you learn *market structure*, not linker flags.

Recommended libraries (to add when `pyproject.toml` lands):

| Layer | Library | Role |
|-------|---------|------|
| Tables | **Polars** (first) or Pandas | Vectorized transforms |
| SQL over files | **DuckDB** | Ad-hoc queries on Parquet |
| Config | **pydantic** + YAML/TOML | Typed runs |
| HTTP | **httpx** | Vendor pulls |
| Tests | **pytest** | Property & regression tests on sim invariants |

## Do you need C++ or Rust?

**Not on day one.**

| When | Language |
|------|----------|
| Learning architecture, ETL, sim semantics | **Python** |
| Hot path proven slow by **profiler** (not intuition alone) | **Rust** (safe default) or **C++** if you already live there |
| Ultra-low-latency shared-memory rings to exchange | **C++** historically; irrelevant until you have colo + budget |

**Rust** is the modern pick for a **rewrite of inner loops** (decode, book updates, simplified matching engine) with memory safety and great tooling.

**C++** still owns parts of the industry at the wire—but you pay **build complexity** and foot-guns early.

## Rule of thumb

> No second language until **one** full Python pipeline is correct **and** a profiler shows **≥20–30%** of wall time in a **tight** inner function worth extracting.

## Frontend

- **None** for core: Parquet + CSV metrics + optional **Marimo / Jupyter / VS Code** plots.
- Optional later: **FastAPI + minimal React** or **Streamlit** for a read-only run browser—**after** batch truth is solid.

## Where your Mac Studio fits

- **Dev + research + medium Parquet** local.
- When data or sweeps exceed RAM/disk, **partition harder** or push **batch jobs** to cheap cloud CPU—not because the Studio is bad, but because **data gravity** wins.
