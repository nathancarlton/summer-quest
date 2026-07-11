"""Terminal UI built on rich (cross-platform, Windows-safe)."""
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from . import profile as profile_mod

console = Console()

CATEGORY_LABELS = {
    "vocabulary": "📖 Vocabulary",
    "grammar": "✏️  Grammar",
    "reading": "🔍 Reading",
    "figurative_language": "🎭 Figurative Language",
    "writing_mechanics": "🛠️  Writing Mechanics",
    "math_challenge": "🧮 Math Challenge",
}


def banner():
    console.print(
        Panel.fit(
            Text("SUMMER QUEST", style="bold magenta", justify="center")
            + Text("\nLevel up your brain. 15 minutes a day.", style="cyan"),
            border_style="magenta",
        )
    )


def hud(p):
    num, title, nxt = profile_mod.level_info(p["xp"])
    line = (
        f"[bold yellow]⭐ {p['xp']} XP[/]   "
        f"[bold green]Lv {num} · {title}[/]   "
        f"[bold red]🔥 Streak: {p['streak']}[/]   "
        f"[bold blue]🏅 {len(p['badges'])} badges[/]"
    )
    console.print(Panel(line, border_style="dim"))
    if nxt:
        threshold, next_title = nxt
        prog = Progress(
            TextColumn(f"Next: {next_title}"),
            BarColumn(bar_width=30),
            TextColumn(f"{p['xp']}/{threshold} XP"),
            console=console,
        )
        with prog:
            task = prog.add_task("", total=threshold)
            prog.update(task, completed=p["xp"])


def ask_question(i, total, q, is_boss):
    console.print()
    header = f"[bold]Question {i}/{total}[/] · {CATEGORY_LABELS.get(q['category'], q['category'])}"
    if is_boss:
        header = "[bold red]👹 BOSS BATTLE — double XP![/]  " + header
    console.rule(header)
    if q.get("passage"):
        console.print(Panel(q["passage"], title="📜 Read this", border_style="cyan"))
    console.print(f"\n[bold white]{q['question']}[/]\n")
    if q["type"] == "mc":
        for opt in q["options"]:
            console.print(f"  {opt}")
        return Prompt.ask(
            "\n[bold cyan]Your answer[/]", choices=["a", "b", "c", "d"],
            show_choices=False,
        ).upper()
    return Prompt.ask("\n[bold cyan]Type your answer[/]").strip()


def show_result(correct, feedback, xp_gained):
    if correct:
        console.print(f"\n[bold green]✅ Correct! +{xp_gained} XP[/]")
    else:
        console.print("\n[bold red]❌ Not quite![/]")
    if feedback:
        console.print(f"[italic]{feedback}[/]")


def session_summary(name, correct, total, xp_gained, streak_bonus, new_badges):
    table = Table(title=f"🏁 Quest Complete, {name}!", border_style="magenta")
    table.add_column("Stat", style="cyan")
    table.add_column("Result", style="bold white")
    table.add_row("Score", f"{correct}/{total}")
    table.add_row("XP earned", f"+{xp_gained}")
    if streak_bonus:
        table.add_row("Streak bonus", f"+{streak_bonus}")
    console.print(table)
    for key in new_badges:
        emoji_name, desc = profile_mod.BADGES[key]
        console.print(
            Panel(f"[bold yellow]NEW BADGE UNLOCKED![/]\n{emoji_name} — {desc}",
                  border_style="yellow")
        )


def show_stats(p):
    hud(p)
    table = Table(title="📊 Category Report Card", border_style="cyan")
    table.add_column("Category")
    table.add_column("Correct")
    table.add_column("Accuracy")
    for cat, s in p["categories"].items():
        if s["answered"]:
            acc = s["correct"] / s["answered"]
            color = "green" if acc >= 0.8 else "yellow" if acc >= 0.6 else "red"
            table.add_row(
                CATEGORY_LABELS.get(cat, cat),
                f"{s['correct']}/{s['answered']}",
                f"[{color}]{acc:.0%}[/]",
            )
    console.print(table)
    if p["badges"]:
        badges = "  ".join(profile_mod.BADGES[b][0] for b in p["badges"])
        console.print(Panel(badges, title="🏅 Badge Collection", border_style="yellow"))
