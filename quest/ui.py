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
    "vocabulary": "Vocabulary 📖",
    "grammar": "Grammar ✏️",
    "reading": "Reading 🔍",
    "figurative_language": "Figurative Language 🎭",
    "writing_mechanics": "Writing Mechanics 🛠️",
    "math_challenge": "Math Challenge 🧮",
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
            Panel.fit(f"[bold yellow]NEW BADGE UNLOCKED![/]\n{emoji_name} — {desc}",
                      border_style="yellow")
        )


def _split_emoji(label):
    """Split a "Name 📖" label into ("Name", "📖").

    macOS Terminal renders emoji at widths no width-table predicts, so we
    keep them OUT of anything with a right border. Category labels put the
    emoji last; badge labels put it first."""
    head, _, tail = label.rpartition(" ")
    if head and tail and not tail.isascii():
        return head, tail
    lead, _, rest = label.partition(" ")
    if rest and not lead.isascii():
        return rest.strip(), lead
    return label, ""


def show_stats(p):
    hud(p)

    headers = ("Category", "Correct", "Accuracy")
    rows = []
    for cat, s in p["categories"].items():
        if not s["answered"]:
            continue
        acc = s["correct"] / s["answered"]
        color = "green" if acc >= 0.8 else "yellow" if acc >= 0.6 else "red"
        name, emoji = _split_emoji(CATEGORY_LABELS.get(cat, cat))
        rows.append((name, f"{s['correct']}/{s['answered']}", f"{acc:.0%}", color, emoji))

    if rows:
        # Columns hold ASCII only, so plain len() is the true width and the
        # borders always line up. Emoji ride outside the closing border.
        widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(3)]

        def seg(fill, joiner):
            return joiner.join(fill * (w + 2) for w in widths)

        def data_row(cells, bar, color=None, emoji=""):
            b = f"[cyan]{bar}[/]"
            out = [b]
            for i, c in enumerate(cells):
                cell = (f"[{color}]{c}[/]" + " " * (widths[i] - len(c))
                        if color and i == 2 else c.ljust(widths[i]))
                out.append(f" {cell} {b}")
            if emoji:
                out.append(f" {emoji}")
            return "".join(out)

        console.print(f"[cyan]┏{seg('━', '┳')}┓[/]", highlight=False, soft_wrap=True)
        console.print(data_row(headers, "┃"), highlight=False, soft_wrap=True)
        console.print(f"[cyan]┡{seg('━', '╇')}┩[/]", highlight=False, soft_wrap=True)
        for name, correct, acc, color, emoji in rows:
            console.print(data_row((name, correct, acc), "│", color=color, emoji=emoji),
                          highlight=False, soft_wrap=True)
        console.print(f"[cyan]└{seg('─', '┴')}┘[/]", highlight=False, soft_wrap=True)

    if p["badges"]:
        parsed = [_split_emoji(profile_mod.BADGES[b][0]) for b in p["badges"]]
        title = "Badge Collection"
        body = max([len(name) for name, _ in parsed] + [len(title) + 1])
        inner = body + 2
        top = "╭─ " + title + " " + "─" * (inner - len(title) - 3) + "╮"
        console.print(f"[yellow]{top}[/]", highlight=False, soft_wrap=True)
        for name, emoji in parsed:
            tail = f" {emoji}" if emoji else ""
            console.print(f"[yellow]│[/] {name.ljust(body)} [yellow]│[/]{tail}",
                          highlight=False, soft_wrap=True)
        console.print(f"[yellow]╰{'─' * inner}╯[/]", highlight=False, soft_wrap=True)
