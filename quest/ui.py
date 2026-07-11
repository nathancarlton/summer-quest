"""Terminal UI built on rich (cross-platform, Windows-safe)."""
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
import wcwidth

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


def _display_width(text):
    """Terminal-accurate display width.

    An emoji variation sequence (a base glyph followed by U+FE0F) renders
    as 2 columns on older macOS Terminal, but wcwidth counts the base as 1
    and the selector as 0. We promote any narrow glyph carrying a VS16 to
    width 2 so the count matches what the terminal actually draws.
    """
    width = 0
    prev = 0
    for ch in text:
        if ch == "️":  # VS16 — forces emoji (wide) presentation
            if prev == 1:
                width += 1  # promote the preceding narrow glyph to 2 columns
                prev = 2
            continue
        cw = wcwidth.wcwidth(ch)
        cw = cw if cw and cw > 0 else 0
        width += cw
        prev = cw
    return width


def _pad(text, width):
    return text + " " * max(0, width - _display_width(text))


def _boxed(content, color, title=None):
    """Rounded panel sized with the emoji-aware width, drawn by hand so
    rich never re-measures (and thus never mis-sizes) the border."""
    cw = _display_width(content)
    body = max(cw, _display_width(title) + 1) if title else cw
    inner = body + 2  # one space of padding on each side
    if title:
        top = "╭─ " + title + " " + "─" * (inner - _display_width(title) - 3) + "╮"
    else:
        top = "╭" + "─" * inner + "╮"
    bar = f"[{color}]│[/]"
    console.print(f"[{color}]{top}[/]", highlight=False, soft_wrap=True)
    console.print(f"{bar} {_pad(content, body)} {bar}", highlight=False, soft_wrap=True)
    console.print(f"[{color}]╰{'─' * inner}╯[/]", highlight=False, soft_wrap=True)


def show_stats(p):
    hud(p)

    headers = ("Category", "Correct", "Accuracy")
    rows = []
    for cat, s in p["categories"].items():
        if not s["answered"]:
            continue
        acc = s["correct"] / s["answered"]
        color = "green" if acc >= 0.8 else "yellow" if acc >= 0.6 else "red"
        rows.append((CATEGORY_LABELS.get(cat, cat),
                     f"{s['correct']}/{s['answered']}", f"{acc:.0%}", color))

    if rows:
        widths = [max(_display_width(headers[i]),
                      *(_display_width(r[i]) for r in rows)) for i in range(3)]

        def seg(fill, joiner):
            return joiner.join(fill * (w + 2) for w in widths)

        def data_row(cells, bar, color=None):
            b = f"[cyan]{bar}[/]"
            out = [b]
            for i, c in enumerate(cells):
                cell = (f"[{color}]{c}[/]" + " " * max(0, widths[i] - _display_width(c))
                        if color and i == 2 else _pad(c, widths[i]))
                out.append(f" {cell} {b}")
            return "".join(out)

        total = sum(widths) + 10
        title = "📊 Category Report Card"
        console.print(" " * max(0, (total - _display_width(title)) // 2) + f"[bold]{title}[/]",
                      highlight=False, soft_wrap=True)
        console.print(f"[cyan]┏{seg('━', '┳')}┓[/]", highlight=False, soft_wrap=True)
        console.print(data_row(headers, "┃"), highlight=False, soft_wrap=True)
        console.print(f"[cyan]┡{seg('━', '╇')}┩[/]", highlight=False, soft_wrap=True)
        for r in rows:
            console.print(data_row(r[:3], "│", color=r[3]), highlight=False, soft_wrap=True)
        console.print(f"[cyan]└{seg('─', '┴')}┘[/]", highlight=False, soft_wrap=True)

    if p["badges"]:
        badges = "   ".join(profile_mod.BADGES[b][0] for b in p["badges"])
        _boxed(badges, "yellow", title="Badge Collection")
