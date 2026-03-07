# Engineering Excellence: Extracted Best Practices

A consolidated guide to the high-signal patterns, CI/CD optimizations, and architectural standards extracted from the workspace.

---

## 1. Efficiency & Automation (DevEx)

### CI/CD Performance & Pre-baked Images
- **Dependency Acceleration:** Use `uv` (`uv pip install`) for near-instant dependency resolution compared to standard `pip`.
- **Pre-baked CI Base Images:** Maintain a dedicated `Dockerfile.ci` to pre-install 90% of project dependencies.
  - **Trick:** Use `uv pip compile` to generate a `requirements.lock` inside the image to isolate build dependencies from project source.
  - **Content-Hash Tagging:** Only rebuild the CI image if the `Dockerfile.ci` content hash changes (`sha256sum Dockerfile.ci`).
- **Global Tool Caching:** Cache `.ruff_cache`, `.mypy_cache`, and `UV_CACHE_DIR` based on `uv.lock` hashes.
- **Interruptible Pipelines:** Set `interruptible: true` to kill stale builds on new pushes to the same branch/MR.

### Standardized Tooling
- **Unified Interface:** Use a `Makefile` for core tasks (`install-dev`, `test-cov`, `security`, `audit`) to provide a consistent DX across diverse projects.
- **Ruff (All-in-One):** Replace Black, Isort, Flake8, and Bandit with `ruff` for 10-100x faster linting and formatting.
- **Multi-Repo Sync:** Use recursive PowerShell/Bash scripts (`fetch_all_repos.ps1`) to keep microservices synchronized with a single command.

---

## 2. Containerization & Orchestration

### Docker Best Practices
- **Layer Optimization:** Always combine `apt-get update` with `apt-get install` and follow up with `rm -rf /var/lib/apt/lists/*` to minimize image size.
- **Secure Private Installs:** Use Docker `ARG` to pass temporary access tokens (e.g., `FETCH_SHARED_APP`) for installing private repositories from GitLab/GitHub during build time.
- **Optimized Python Environments:** Set `PYTHONUNBUFFERED=1` for real-time log streaming and `PYTHONDONTWRITEBYTECODE=1` for cleaner images.

### Orchestration with `docker-compose`
- **Healthcheck-Based Dependencies:** Use `pg_isready` for Postgres healthchecks and `depends_on: {condition: service_healthy}` to ensure the app doesn't crash while waiting for the database.
- **Service Separation:** Use the same image with different entrypoints/commands for API servers and background workers (e.g., `taskiq worker`) to ensure environment parity.
- **Named Volumes:** Use named volumes for persistent data (e.g., `postgres_data`) to prevent data loss on container recreation.

---

## 3. Architectural Resilience & Scalability

### Advanced Caching (Multi-Tenant)
- **Tenant Isolation:** Always include tenant identifiers in cache keys (`prefix:{tenant}:{key}`) to prevent cross-tenant leaks.
- **Stampede Protection:** Use atomic `cache.add()` as a distributed lock to prevent "Thundering Herd" recomputations.
- **Manifest Invalidation:** Track all cache keys for a resource in a "manifest" key for precise bulk invalidation.
- **Version-Based Staleness:** Use global version counters for structural data (like OU trees) to implicitly invalidate user-specific caches.

### Service Layer & Decoupling
- **Logic Isolation:** Move business logic into standalone `services/` (e.g., `performance_cache_service.py`), keeping framework models and views lean and testable.

---

## 4. AI/LLM Engineering & Agent Excellence

### Maker-Checker Architecture
- **Dual-Agent Pattern:** Separate generation ("Maker") from validation ("Checker") to ensure high-fidelity outputs.
- **Self-Healing Loops:** Use a `retry_feedback_prompt.txt` to feed checker suggestions back into the generator for automatic error correction.
- **Strict JSON Enforcement:** Explicitly command LLMs to return deterministic JSON schemas with confidence scores.

### Agent-Specific Instructions (`CLAUDE.md`)
- **Minimalist Context:** Instruct AI agents to avoid writing docstrings for existing code and to focus only on targeted changes.
- **Lazy Dependencies:** Import heavy libraries (like `openai` or `redis`) only when needed to optimize startup time.
- **Pydantic V2:** Use Pydantic as the universal standard for schema validation and LLM structured outputs.
- **Prompt Artifacts:** Store prompts in versioned `.txt` files rather than hardcoded strings.

---

## 5. Security & Reliability (Robustness)

> **Template implementation status** (as of last update)
>
> | Practice | FastAPI | Django |
> |---|---|---|
> | `uv` dependency management | Done | Done |
> | `.ruff_cache` / `.mypy_cache` cached in CI | Done | Done |
> | `interruptible: true` on all GitLab jobs | Done | Done |
> | `--junit-xml` passed to pytest | Done | Done |
> | `# pragma: allowlist secret` on CI keys | Done | Done |
> | `Makefile` (`install-dev`, `test-cov`, `security`, `audit`) | Done | Done |
> | `Dockerfile` (layer-optimized, `PYTHONUNBUFFERED`) | Done | Done |
> | `docker-compose.yml` (healthchecks, named volumes, worker service) | Done | Done |
> | Pre-baked `Dockerfile.ci` with content-hash tagging | N/A — `uv` fast enough | N/A |
> | Multi-repo sync script | N/A — workspace-level | N/A |
> | Tenant cache patterns | N/A — no business logic | N/A |
> | Memory leak detection (`psutil`/`gc`) | N/A — no domain code | N/A |
> | Maker-Checker / Prompt artifacts | N/A — no LLM features | N/A |

### In-MR Reporting
- **Visual Coverage:** Output Cobertura XML to allow line-by-line coverage diffs in the GitLab/GitHub MR UI.
- **JUnit Visibility:** Upload JUnit XML artifacts to provide a dedicated "Tests" tab for failure analysis.

### Hardened Code Standards
- **Memory Leak Detection:** Automated `pytest` suites using `psutil` and `gc` to measure RSS growth during object lifecycles.
- **Static Type Safety:** `mypy` is mandatory; `type: ignore` is treated as a last resort.
- **Safe Secrets:** Use specific pragmas (`# pragma: allowlist secret`) for test-keys to satisfy security scanners without leaking real credentials.
- **Logging Integrity:** Use `ruff` rules to ban f-strings in logger calls, enforcing structured/lazy formatting for performance and log-aggregation safety.
