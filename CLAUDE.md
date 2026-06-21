# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Claude Code plugin marketplace** that distributes a single plugin (`teamropp-skills`) made up of agent skills. There is no application to build or run — the repo *is* the deliverable. Each skill is a self-contained directory under `skills/` that gets installed into a user's `~/.claude/skills/` when they install the plugin.

Install on another machine:
```
claude plugin marketplace add cropp/skills
claude plugin install teamropp-skills@teamropp-agent-skills
```
Skills are registered at Claude Code **startup only** — changes require restarting Claude Code, then `/plugin` to confirm the plugin is enabled.

## Layout & the two-file version rule

- `.claude-plugin/marketplace.json` — marketplace manifest (lists the plugin, marketplace name `teamropp-agent-skills`).
- `.claude-plugin/plugin.json` — plugin manifest.
- Both files carry a `version`. **They must be bumped together** — every release commit changes the version in both (see git history). Don't update one without the other.
- `skills/<name>/SKILL.md` — the skill itself (required). Optional sibling dirs: `scripts/`, `references/`, `strategies/`, `evals/`.

## SKILL.md conventions

Each `SKILL.md` starts with YAML frontmatter. The `description` (and optional `triggers` list) is what Claude Code matches against user phrasing to decide when to activate the skill, so descriptions are written to be trigger-rich — they enumerate concrete phrases a user might say. When editing a skill's purpose, keep the description's trigger phrases in sync with the behavior.

**Path convention:** SKILL.md bodies reference runtime paths as `~/.claude/skills/<name>/...` (the *installed* location), not the repo-relative path. Preserve this when editing — the skill runs from the installed copy, not from this repo.

## The skills

- **alpaca-trading** (Python) — Alpaca Markets automated trading. The most complex skill.
  - `scripts/*.py` are CLI entry points invoked with argparse flags (e.g. `run_strategy.py --account paper --strategy rsi_mean_reversion`, `dashboard.py` serves a Flask UI on port 7432, `self_analyze.py` tunes strategy params, `backtest.py` simulates bar-by-bar).
  - State lives in a SQLite DB (`scripts/db.py`) at `~/.claude/skills/alpaca-trading/data/trading.db` — config, strategy params, and an `analysis_log` audit table.
  - **Strategies are a plugin pattern:** every strategy subclasses `BaseStrategy` (`strategies/base.py`) and implements `signals()`, `should_exit()`, and optionally `position_size()`. Shared indicator math (RSI via Wilder's smoothing, SMA, EMA) lives as static methods on `BaseStrategy` — reuse those rather than reimplementing. Add a new strategy by adding a subclass under `strategies/`.
  - Deps in `requirements.txt` (alpaca-py, flask, yfinance).
  - `evals/evals.json` holds prompt→expected-behavior eval cases; update it when skill behavior changes.

- **home-assistant** (Python) — Home Assistant expert. `scripts/ha_client.py` is a REST API client (CLI subcommands; config at `~/.ha_skill_config.json`), `scripts/ha_setup.py` is the connection wizard. `references/*.md` are HA automation syntax docs the skill reads from. The skill checks `ha_client.py status` before acting and runs setup if unconfigured.

- **jenv** (bash) — verify/use jenv for Java & Maven version selection. `scripts/verify-jenv.sh` is the verification entry point. Note: this aligns with the global rule that Java/Maven versions on this machine are managed exclusively by jenv.

## Working in this repo

- There are no build/lint/test commands for the repo itself. Python skills are run directly with `python3` against their script CLIs; jenv is a shell script.
- To test a skill change end-to-end you must reinstall/reload the plugin in Claude Code (startup-only registration).
