"""Entry point: python -m quest"""
from rich.prompt import Prompt

from . import profile as profile_mod, session, sync, ui


def main():
    ui.banner()
    p = profile_mod.load()
    if p is None:
        name = Prompt.ask("[bold cyan]What's your name, adventurer?[/]").strip()
        p = profile_mod.create(name or "Adventurer")
        ui.console.print(f"\n[green]Welcome, {p['name']}! Your quest begins.[/]\n")
    else:
        ui.console.print(f"\n[green]Welcome back, {p['name']}![/]\n")

    sent = sync.flush_queue()
    if sent:
        ui.console.print(f"[dim]☁ Synced {sent} queued session(s).[/]")

    ui.hud(p)

    while True:
        ui.console.print(
            "\n[bold]1[/] Start today's quest   "
            "[bold]2[/] My stats   [bold]3[/] Quit"
        )
        choice = Prompt.ask("Choose", choices=["1", "2", "3"], show_choices=False)
        if choice == "1":
            session.run(p)
        elif choice == "2":
            ui.show_stats(p)
        else:
            ui.console.print("\n[magenta]See you tomorrow — keep that streak alive! 🔥[/]\n")
            break


if __name__ == "__main__":
    main()
