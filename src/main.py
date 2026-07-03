"""Typer CLI for PlayPhrase Video Builder."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Callable

import typer
from rich.table import Table

from src.commons import CommonsBrollService
from src.config import Settings, get_settings
from src.downloader import DownloadManager
from src.enhancer import VideoEnhancer, default_broll_queries
from src.merger import VideoMerger
from src.search import SearchResult, SearchService
from src.translations import TranslationService
from src.utils import AppError, console, normalize_whitespace, setup_logging

app = typer.Typer(
    name="playphrase-video-builder",
    help="Search PlayPhrase, download matching clips, and build English learning videos.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

logger = logging.getLogger(__name__)
MAX_BATCH_PHRASES = 5


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


def _resolve_path(settings: Settings, path: Path) -> Path:
    """Resolve a possibly relative user-provided path."""

    if path.is_absolute():
        return path
    return (settings.project_root / path).resolve()


def _resolve_video_output(settings: Settings, output: Path | None, result: SearchResult) -> Path:
    """Resolve the normal horizontal video output path."""

    if output is None:
        return settings.video_output_folder / f"{result.slug}.mp4"
    return _resolve_path(settings, output)


def _resolve_reel_output(settings: Settings, output: Path | None, result: SearchResult) -> Path:
    """Resolve the vertical Reel/Shorts output path."""

    if output is None:
        return settings.reel_output_folder / f"{result.slug}-reel.mp4"
    return _resolve_path(settings, output)


def _resolve_enhance_input(
    settings: Settings,
    input_path: Path | None,
    result: SearchResult,
) -> Path:
    """Resolve the source video for enhance, with compatibility for old outputs."""

    if input_path is not None:
        return _resolve_path(settings, input_path)

    default_path = settings.video_output_folder / f"{result.slug}.mp4"
    if default_path.is_file():
        return default_path

    legacy_path = settings.output_folder / f"{result.slug}.mp4"
    if legacy_path.is_file():
        return legacy_path

    return default_path


def _load_result(service: SearchService, phrase: str | None) -> SearchResult:
    """Load a result by phrase or fall back to latest-search.json."""

    if phrase:
        cached = service.load_cached(phrase)
        if cached:
            return cached
        raise AppError(f"No cached search found for {phrase!r}. Run `python main.py search` first.")
    return service.load_latest()


def _normalize_phrase_arguments(
    phrases: list[str] | None,
    *,
    allow_empty: bool = False,
) -> list[str]:
    """Normalize one or more CLI phrase arguments and enforce the batch limit."""

    if phrases is None or len(phrases) == 0:
        if allow_empty:
            return []
        raise AppError("Please provide at least one English phrase.")

    normalized: list[str] = []
    for phrase in phrases:
        for line in phrase.splitlines():
            for part in line.split(";"):
                text = normalize_whitespace(part)
                if text:
                    normalized.append(text)

    if not normalized:
        raise AppError("Please provide at least one non-empty English phrase.")

    if len(normalized) > MAX_BATCH_PHRASES:
        raise AppError(
            f"Please provide at most {MAX_BATCH_PHRASES} phrases per command. "
            f"Received {len(normalized)}."
        )

    return normalized


def _run_phrase_batch(
    phrases: list[str],
    *,
    action_name: str,
    worker: Callable[[str], Path],
) -> list[Path]:
    """Run a worker for each phrase in order, continuing through batch failures."""

    paths: list[Path] = []
    failures: list[tuple[str, str]] = []
    total = len(phrases)

    for index, phrase in enumerate(phrases, start=1):
        if total > 1:
            console.print(f"\n[bold cyan]{action_name} {index}/{total}:[/bold cyan] {phrase}")
        try:
            paths.append(worker(phrase))
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - batch boundary reports and continues
            logger.exception("%s failed for phrase %r", action_name, phrase)
            message = str(exc) or exc.__class__.__name__
            failures.append((phrase, message))
            console.print(f"[bold red]Failed:[/bold red] {phrase} - {message}")
            if total == 1:
                raise

    if failures:
        summary = "; ".join(f"{phrase}: {message}" for phrase, message in failures)
        raise AppError(f"{len(failures)} of {total} phrases failed. {summary}")

    return paths


def _build_video(
    settings: Settings,
    service: SearchService,
    phrase: str,
    *,
    force_search: bool,
    output: Path | None,
    intro: bool,
    outro: bool,
    subtitles: bool,
) -> Path:
    """Search, download, and merge one horizontal video."""

    console.print(f"[bold]Searching:[/bold] {phrase}")
    result = asyncio.run(service.search(phrase, force=force_search))
    _print_search_summary(result, service.result_path_for(result))

    console.print("[bold]Downloading clips[/bold]")
    report = asyncio.run(DownloadManager(settings).download_all(result))
    console.print(f"[green]Downloaded:[/green] {len(report.clips)} clips")

    console.print("[bold]Merging final video[/bold]")
    destination = _resolve_video_output(settings, output, result)
    final_path = VideoMerger(settings).merge_result(
        result,
        output_path=destination,
        add_intro=intro,
        add_outro=outro,
        subtitles=subtitles,
    )

    console.print(f"[bold green]Done:[/bold green] {final_path}")
    return final_path


def _create_reel(
    settings: Settings,
    service: SearchService,
    phrase: str | None,
    *,
    input_path: Path | None,
    output: Path | None,
    broll: bool,
    broll_query: str | None,
    force_broll: bool,
) -> Path:
    """Create one vertical Reel/Shorts video from a built horizontal video."""

    result = _load_result(service, phrase)
    source_path = _resolve_enhance_input(settings, input_path, result)
    destination = _resolve_reel_output(settings, output, result)

    broll_path: Path | None = None
    broll_credit: str | None = None
    if broll and settings.commons_broll_enabled:
        queries = [broll_query] if broll_query else default_broll_queries(result.phrase)
        console.print(f"[bold]Finding b-roll:[/bold] {' / '.join(queries[:4])}")
        try:
            asset = asyncio.run(
                CommonsBrollService(settings).download_best(
                    queries,
                    slug=result.slug,
                    force=force_broll,
                )
            )
        except Exception as exc:  # noqa: BLE001 - b-roll is optional enhancement
            logger.warning("Wikimedia Commons b-roll failed; continuing without it: %s", exc)
            asset = None
        if asset and asset.local_path:
            broll_path = Path(asset.local_path)
            broll_credit = asset.credit
            console.print(f"[green]B-roll:[/green] {asset.title}")

    console.print("[bold]Rendering enhanced reel[/bold]")
    final_path = VideoEnhancer(settings).create_reel(
        input_path=source_path,
        phrase=result.phrase,
        output_path=destination,
        broll_path=broll_path,
        broll_credit=broll_credit,
        translations=TranslationService(settings).get(result.phrase) if broll_path else None,
    )
    console.print(f"[bold green]Enhanced video:[/bold green] {final_path}")
    return final_path


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
        destination = _resolve_video_output(settings, output, result)
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


@app.command("enhance")
def enhance_command(
    phrases: Annotated[
        list[str] | None,
        typer.Argument(
            help=(
                "Optional phrase(s). If omitted, enhances the latest built video. "
                "Pass up to 5 phrases as separate quoted arguments or separated by semicolons."
            )
        ),
    ] = None,
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            "-i",
            help="Existing MP4 to enhance. Defaults to outputs/videos/<slug>.mp4.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Enhanced MP4 path. Defaults to outputs/reels/<slug>-reel.mp4.",
        ),
    ] = None,
    broll: Annotated[
        bool,
        typer.Option("--broll/--no-broll", help="Add a short Wikimedia Commons b-roll hook."),
    ] = True,
    broll_query: Annotated[
        str | None,
        typer.Option("--broll-query", help="Custom Wikimedia Commons video search query."),
    ] = None,
    force_broll: Annotated[
        bool,
        typer.Option("--force-broll", help="Ignore cached b-roll and download a fresh candidate."),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logs.")] = False,
) -> None:
    """Create a more dynamic vertical Reel/Shorts version of a built video."""

    settings, log_path = _prepare(verbose)
    try:
        phrase_list = _normalize_phrase_arguments(phrases, allow_empty=True)
        if len(phrase_list) > 1 and input_path is not None:
            raise AppError("Do not use --input with multiple phrases.")
        if len(phrase_list) > 1 and output is not None:
            raise AppError("Do not use --output with multiple phrases.")

        service = SearchService(settings)

        if not phrase_list:
            _create_reel(
                settings,
                service,
                None,
                input_path=input_path,
                output=output,
                broll=broll,
                broll_query=broll_query,
                force_broll=force_broll,
            )
        else:
            def create_one(phrase: str) -> Path:
                return _create_reel(
                    settings,
                    service,
                    phrase,
                    input_path=input_path,
                    output=output,
                    broll=broll,
                    broll_query=broll_query,
                    force_broll=force_broll,
                )

            _run_phrase_batch(phrase_list, action_name="Reel", worker=create_one)

        console.print(f"[dim]Log file: {log_path}[/dim]")
    except Exception as exc:  # noqa: BLE001
        _fail(exc)


@app.command("build")
def build_command(
    phrases: Annotated[
        list[str],
        typer.Argument(
            help=(
                "English phrase(s) to build into video. Pass up to 5 phrases as separate "
                "quoted arguments or separated by semicolons."
            )
        ),
    ],
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
        phrase_list = _normalize_phrase_arguments(phrases)
        if len(phrase_list) > 1 and output is not None:
            raise AppError("Do not use --output with multiple phrases.")

        service = SearchService(settings)

        def build_one(phrase: str) -> Path:
            return _build_video(
                settings,
                service,
                phrase,
                force_search=force_search,
                output=output,
                intro=intro,
                outro=outro,
                subtitles=subtitles,
            )

        _run_phrase_batch(phrase_list, action_name="Video", worker=build_one)
        console.print(f"[dim]Log file: {log_path}[/dim]")
    except Exception as exc:  # noqa: BLE001
        _fail(exc)


if __name__ == "__main__":
    cli()
