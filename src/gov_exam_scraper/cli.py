"""Interactive Command-Line Interface for gov-exam-scraper."""

import csv
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer

from gov_exam_scraper.fetch import ContentFetcher
from gov_exam_scraper.models import ExamRecord, ScraperSettings, Sector
from gov_exam_scraper.parse import GroqParser
from gov_exam_scraper.scraper import DEFAULT_SOURCES, GovExamScraper

app = typer.Typer(
    name="gov-exam-scraper",
    help="🏛️ Production-grade Government Exam Notification Tracker & Notion Sync Engine",
    add_completion=False,
)
console = Console()


def render_table(records: list[ExamRecord], title: str = "Government Exam Notifications") -> None:
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Exam Name", style="bold white", max_width=35)
    table.add_column("Sector", style="cyan")
    table.add_column("Last Date", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Apply Link", style="blue", overflow="ellipsis", max_width=35)

    for exam in records:
        table.add_row(
            exam.exam_name,
            exam.sector.value,
            exam.last_date.isoformat() if exam.last_date else "N/A",
            exam.status.value,
            exam.apply_link,
        )
    console.print(table)


@app.command()
def scrape(
    sync_notion: bool = typer.Option(False, "--sync-notion", "-s", help="Sync extracted exams to Notion database"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Export to JSON or CSV file"),
    workers: int = typer.Option(5, "--workers", "-w", help="Number of concurrent scraper threads"),
) -> None:
    """Scrape all configured government exam portals."""
    scraper = GovExamScraper()
    console.print("[bold cyan]Scraping configured government exam portals...[/bold cyan]")
    records = scraper.scrape_all(max_workers=workers)

    if not records:
        console.print("[yellow]No exam notifications found.[/yellow]")
        return

    render_table(records, f"Extracted Notifications ({len(records)} Unique)")

    if output:
        if output.suffix.lower() == ".json":
            data = [rec.model_dump(mode="json") for rec in records]
            output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            console.print(f"[bold green]Saved JSON to {output.resolve()}[/bold green]")
        elif output.suffix.lower() == ".csv":
            with open(output, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(records[0].model_dump().keys()))
                writer.writeheader()
                for rec in records:
                    writer.writerow(rec.model_dump(mode="json"))
            console.print(f"[bold green]Saved CSV to {output.resolve()}[/bold green]")

    if sync_notion:
        console.print("[bold yellow]Syncing records to Notion...[/bold yellow]")
        stats = scraper.sync_to_notion(records)
        console.print(
            Panel.fit(
                f"[bold green]Sync Complete![/bold green]\n"
                f"• Created: [green]{stats['created']}[/green]\n"
                f"• Updated: [yellow]{stats['updated']}[/yellow]\n"
                f"• Skipped: [dim]{stats['skipped']}[/dim]",
                title="Notion Sync Results",
            )
        )


@app.command()
def test_url(
    url: str = typer.Argument(..., help="Portal URL to scrape and parse"),
    sector: Sector = typer.Option(Sector.OTHER, "--sector", "-s", help="Sector hint for extraction"),
    browser: bool = typer.Option(False, "--browser", "-b", help="Use Playwright headless browser"),
) -> None:
    """Test extraction on a single URL."""
    settings = ScraperSettings()
    fetcher = ContentFetcher(settings=settings)
    parser = GroqParser(settings=settings)

    console.print(f"[bold cyan]Fetching:[/bold cyan] {url}")
    raw_html = fetcher.fetch(url, force_browser=browser)
    cleaned = fetcher.clean_html(raw_html, base_url=url)
    records = parser.parse_exams(cleaned, source_url=url, sector_hint=sector)

    if not records:
        console.print("[yellow]No exams extracted from this page.[/yellow]")
        return

    render_table(records, f"Extracted from {url}")


@app.command()
def sources() -> None:
    """List all default configured government exam sources."""
    table = Table(title="Pre-configured Exam Portals", show_header=True)
    table.add_column("Portal Name", style="bold white")
    table.add_column("Sector", style="cyan")
    table.add_column("Engine", style="magenta")
    table.add_column("URL", style="blue")

    for src in DEFAULT_SOURCES:
        engine = "Playwright (JS)" if src.use_playwright else "Requests (HTTP)"
        table.add_row(src.name, src.sector_hint.value, engine, src.url)

    console.print(table)


if __name__ == "__main__":
    app()
