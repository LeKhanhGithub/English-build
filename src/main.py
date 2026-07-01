"""Typer CLI for PlayPhrase Video Builder."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from src.config import Settings, get_settings
from src.downloader import DownloadManager
from src.merger import VideoMerger
from src.search import SearchResult, SearchService
from src.utils import AppError, console, setup_logging

app = typer.Typer(
    name="playphrase-video-builder",
    help="Search PlayPhrase, download matching clips, and build English learning videos.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

logger = logging.getLogger(__name__)


def cli() -> None:
    """Console script entry point."""

    app()


def _prepare(verbose: bool) -> tuple[Settings, Path]:
    """Load settings, create folders, and configure logging."""

    settings = get_settings()
    settings.ensure_folders()
    log_path = setup_logging(settings.logs_folder, verbose=verbose)
    logger.info("Using project root: %s", settings.project_root)
    return settings, log_path


def _fail(exc: Exception) -> None:
    """Log and display a command failure."""

    if isinstance(exc, KeyboardInterrupt):
        console.print("[bold yellow]Cancelled.[/bold yellow]")
        raise typer.Exit(130) from exc

    logger.exception("Command failed")
    message = str(exc) or exc.__class__.__name__
    console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(1) from exc


def _resolve_output(settings: Settings, output: Path | None, result: SearchResult) -> Path:
    """Resolve an optional output path."""

    if output is None:
        return settings.output_folder / f"{result.slug}.mp4"
    if output.is_absolute():
        return output
    return (settings.project_root / output).resolve()


def _load_result(service: SearchService, phrase: str | None) -> SearchResult:
    """Load a result by phrase or fall back to latest-search.json."""

    if phrase:
        cached = service.load_cached(phrase)
        if cached:
            return cached
        raise AppError(f"No cached search found for {phrase!r}. Run `python main.py search` first.")
    return service.load_latest()


def _print_search_summary(result: SearchResult, path: Path) -> None:
    """Render a compact search result table."""

    table = Table(title=f"Search results for: {result.phrase}")
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Source", style="magenta", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Movie", style="green")
    table.add_column("Duration", justify="right")
    table.add_column("Download URL", overflow="fold")

    for clip in result.clips[:20]:
        duration = f"{clip.duration:.1f}s" if clip.duration else "-"
        url = clip.download_url or clip.video_url or "-"
        table.add_row(
            f"{clip.index:03d}",
            clip.source,
            clip.title or "-",
            clip.movie_name or "-",
            duration,
            url,
        )

    console.print(table)
    if len(result.clips) > 20:
        console.print(f"[dim]Showing first 20 of {len(result.clips)} clips.[/dim]")
    console.print(f"[green]Saved JSON:[/green] {path}")


@app.command("search")
def search_command(
    phrase: Annotated[str, typer.Argument(help="English phrase to search on PlayPhrase.")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Ignore cached search results and search again."),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logs.")] = False,
) -> None:
    """Search PlayPhrase and save results as JSON."""

    settings, log_path = _prepare(verbose)
    try:
        service = SearchService(settings)
        result = asyncio.run(service.search(phrase, force=force))
        _print_search_summary(result, service.result_path_for(result))
        console.print(f"[dim]Log file: {log_path}[/dim]")
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts to friendly output
        _fail(exc)


@app.command("download")
def download_command(
    phrase: Annotated[
        str | None,
        typer.Argument(help="Optional phrase. If omitted, downloads the latest search."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logs.")] = False,
) -> None:
    """Download clips from the latest or named cached search."""

    settings, log_path = _prepare(verbose)
    try:
        service = SearchService(settings)
        result = _load_result(service, phrase)
        report = asyncio.run(DownloadManager(settings).download_all(result))
        console.print(
            f"[green]Downloaded:[/green] {len(report.clips)} clips to "
            f"{service.clip_root_for(result)}"
        )
        console.print(f"[dim]Log file: {log_path}[/dim]")
    except Exception as exc:  # noqa: BLE001
        _fail(exc)


@app.command("merge")
def merge_command(
    phrase: Annotated[
        str | None,
        typer.Argument(help="Optional phrase. If omitted, merges the latest search downloads."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output MP4 path."),
    ] = None,
    intro: Annotated[
        bool,
        typer.Option("--intro/--no-intro", help="Add a two-second phrase intro screen."),
    ] = True,
    outro: Annotated[
        bool,
        typer.Option("--outro/--no-outro", help="Add a two-second outro screen."),
    ] = False,
    subtitles: Annotated[
        bool,
        typer.Option("--subtitles/--no-subtitles", help="Overlay the searched phrase on clips."),
    ] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logs.")] = False,
) -> None:
    """Merge downloaded clips into a final MP4."""

    settings, log_path = _prepare(verbose)
    try:
        service = SearchService(settings)
        result = _load_result(service, phrase)
        destination = _resolve_output(settings, output, result)
        final_path = VideoMerger(settings).merge_result(
            result,
            output_path=destination,
            add_intro=intro,
            add_outro=outro,
            subtitles=subtitles,
        )
        console.print(f"[green]Final video:[/green] {final_path}")
        console.print(f"[dim]Log file: {log_path}[/dim]")
    except Exception as exc:  # noqa: BLE001
        _fail(exc)


@app.command("build")
def build_command(
    phrase: Annotated[str, typer.Argument(help="English phrase to build into one video.")],
    force_search: Annotated[
        bool,
        typer.Option("--force-search", "-f", help="Ignore cached search results."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output MP4 path."),
    ] = None,
    intro: Annotated[
        bool,
        typer.Option("--intro/--no-intro", help="Add a two-second phrase intro screen."),
    ] = True,
    outro: Annotated[
        bool,
        typer.Option("--outro/--no-outro", help="Add a two-second outro screen."),
    ] = False,
    subtitles: Annotated[
        bool,
        typer.Option("--subtitles/--no-subtitles", help="Overlay the searched phrase on clips."),
    ] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logs.")] = False,
) -> None:
    """Search, download, merge, and export one final MP4."""

    settings, log_path = _prepare(verbose)
    try:
        service = SearchService(settings)
        console.print(f"[bold]Searching:[/bold] {phrase}")
        result = asyncio.run(service.search(phrase, force=force_search))
        _print_search_summary(result, service.result_path_for(result))

        console.print("[bold]Downloading clips[/bold]")
        report = asyncio.run(DownloadManager(settings).download_all(result))
        console.print(f"[green]Downloaded:[/green] {len(report.clips)} clips")

        console.print("[bold]Merging final video[/bold]")
        destination = _resolve_output(settings, output, result)
        final_path = VideoMerger(settings).merge_result(
            result,
            output_path=destination,
            add_intro=intro,
            add_outro=outro,
            subtitles=subtitles,
        )

        console.print(f"[bold green]Done:[/bold green] {final_path}")
        console.print(f"[dim]Log file: {log_path}[/dim]")
    except Exception as exc:  # noqa: BLE001
        _fail(exc)


if __name__ == "__main__":
    cli()
