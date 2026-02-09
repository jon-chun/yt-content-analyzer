from __future__ import annotations

import json

import re

import click
from pathlib import Path

from .config import Settings, load_settings
from .exceptions import PreflightError
from .utils.logger import setup_cli_logging


@click.group()
@click.option("-v", "--verbose", count=True, help="Increase verbosity (repeat for more).")
@click.option("-q", "--quiet", is_flag=True, default=False, help="Suppress all but warnings.")
@click.pass_context
def main(ctx: click.Context, verbose: int, quiet: bool) -> None:
    """yt-content-analyzer CLI"""
    ctx.ensure_object(dict)
    verbosity = -1 if quiet else verbose
    ctx.obj["verbosity"] = verbosity
    setup_cli_logging(verbosity=verbosity)


@main.command()
@click.option(
    "--config", "config_path",
    type=click.Path(exists=True, dir_okay=False), required=True,
)
@click.option("--output-dir", type=click.Path(), default=None, help="Output directory.")
@click.pass_context
def preflight(ctx: click.Context, config_path: str, output_dir: str | None) -> None:
    """Run preflight checks against a config file."""
    cfg = load_settings(config_path)
    from .preflight.checks import run_preflight

    out = Path(output_dir) if output_dir else None
    result = run_preflight(cfg, output_dir=out)
    if result.ok:
        click.echo("Preflight passed.")
    else:
        click.echo("Preflight FAILED.", err=True)
        raise SystemExit(2)


@main.command("run-all")
@click.option(
    "--config", "config_path",
    type=click.Path(exists=True, dir_okay=False),
    required=False, default=None,
    help="Path to YAML config file (required for new runs).",
)
@click.option(
    "--video-url", type=str, default=None,
    help="Single YouTube video URL (overrides VIDEO_URL in config).",
)
@click.option(
    "--terms", multiple=True,
    help="One or more search terms (overrides SEARCH_TERMS in config).",
)
@click.option(
    "--output-dir", type=click.Path(), default=None,
    help="Base directory for run outputs (default: ./runs).",
)
@click.option(
    "--resume", "resume_run_id", type=str, default=None,
    help="Resume a previous run by RUN_ID.",
)
@click.option(
    "--sort-modes", type=str, default=None,
    help="Comma-separated sort modes, e.g. 'top,newest'.",
)
@click.option(
    "--max-comments", type=int, default=None,
    help="Override MAX_COMMENTS_PER_VIDEO.",
)
@click.option(
    "--no-transcripts", is_flag=True, default=False,
    help="Disable transcript collection.",
)
@click.option(
    "--llm-provider", type=str, default=None,
    help="Override LLM_PROVIDER.",
)
@click.option(
    "--llm-model", type=str, default=None,
    help="Override LLM_MODEL.",
)
@click.option(
    "--on-failure", type=click.Choice(["skip", "abort"]), default=None,
    help="Override ON_VIDEO_FAILURE policy.",
)
@click.option(
    "--channel", multiple=True,
    help="Channel handle/URL (repeatable, shortcut for subscription mode).",
)
@click.option(
    "--subscriptions", is_flag=True, default=False,
    help="Run in subscription mode (use YT_SUBSCRIPTIONS from config).",
)
@click.pass_context
def run_all_cmd(
    ctx: click.Context,
    config_path: str | None,
    video_url: str | None,
    terms: tuple[str, ...],
    output_dir: str | None,
    resume_run_id: str | None,
    sort_modes: str | None,
    max_comments: int | None,
    no_transcripts: bool,
    llm_provider: str | None,
    llm_model: str | None,
    on_failure: str | None,
    channel: tuple[str, ...],
    subscriptions: bool,
) -> None:
    """Run the full collection + enrichment pipeline."""
    from .run import run_all

    # --- Resolve config ---
    if resume_run_id:
        base_dir = Path(output_dir) if output_dir else Path("runs")
        run_dir = base_dir / resume_run_id
        if not run_dir.is_dir():
            raise click.BadParameter(f"Run directory not found: {run_dir}", param_hint="--resume")
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise click.BadParameter(
                f"manifest.json not found in {run_dir}", param_hint="--resume"
            )
        if config_path:
            cfg = load_settings(config_path)
        else:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            cfg = Settings(**manifest_data)
    else:
        if not config_path:
            raise click.BadParameter("--config is required for new runs", param_hint="--config")
        cfg = load_settings(config_path)

    # --- Apply CLI overrides ---
    if video_url:
        video_url = video_url.strip()
        if re.match(r"^[\w-]{11}$", video_url):
            video_url = f"https://www.youtube.com/watch?v={video_url}"
        cfg.VIDEO_URL = video_url
        cfg.SEARCH_TERMS = None
    elif terms:
        cfg.SEARCH_TERMS = list(terms)
        cfg.VIDEO_URL = None

    if sort_modes:
        cfg.COLLECT_SORT_MODES = [s.strip() for s in sort_modes.split(",") if s.strip()]
    if max_comments is not None:
        cfg.MAX_COMMENTS_PER_VIDEO = max_comments
    if no_transcripts:
        cfg.TRANSCRIPTS_ENABLE = False
    if llm_provider is not None:
        cfg.LLM_PROVIDER = llm_provider
    if llm_model is not None:
        cfg.LLM_MODEL = llm_model
    if on_failure is not None:
        cfg.ON_VIDEO_FAILURE = on_failure

    if channel:
        cfg.YT_SUBSCRIPTIONS = [
            {"CHANNEL": c, "MAX_SUB_VIDEOS": cfg.MAX_SUB_VIDEOS} for c in channel
        ]
        cfg.VIDEO_URL = None
        cfg.SEARCH_TERMS = None

    if subscriptions:
        if not cfg.YT_SUBSCRIPTIONS:
            raise click.BadParameter(
                "YT_SUBSCRIPTIONS must be set in config when using --subscriptions",
                param_hint="--subscriptions",
            )
        cfg.VIDEO_URL = None
        cfg.SEARCH_TERMS = None

    # --- Run ---
    try:
        result = run_all(
            cfg,
            output_dir=output_dir,
            resume_run_id=resume_run_id,
        )
    except PreflightError:
        click.echo("Preflight checks FAILED — aborting.", err=True)
        raise SystemExit(2)

    # --- Summary ---
    click.echo(f"\nRun {result.run_id} complete.")
    click.echo(f"  Output dir:          {result.output_dir}")
    click.echo(f"  Videos processed:    {result.videos_processed}")
    click.echo(f"  Comments collected:  {result.comments_collected}")
    click.echo(f"  Transcript chunks:   {result.transcript_chunks}")
    if result.failures:
        click.echo(f"  Failures:            {len(result.failures)}", err=True)


if __name__ == "__main__":
    main()
