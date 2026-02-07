from __future__ import annotations
import click
from pathlib import Path
from .config import load_settings
from .preflight.checks import run_preflight
from .run import run_all

@click.group()
def main() -> None:
    """yt-content-analyzer CLI"""

@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False), required=True)
def preflight(config_path: str) -> None:
    cfg = load_settings(config_path)
    ok = run_preflight(cfg, output_dir=None)
    raise SystemExit(0 if ok else 2)

@main.command("run-all")
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--terms", multiple=True, help="One or more search terms (overrides SEARCH_TERMS in config).")
def run_all_cmd(config_path: str, terms: tuple[str, ...]) -> None:
    cfg = load_settings(config_path)
    if terms:
        cfg.SEARCH_TERMS = list(terms)
        cfg.VIDEO_URL = None
    run_all(cfg)

if __name__ == "__main__":
    main()
