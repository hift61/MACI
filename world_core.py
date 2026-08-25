# Main library
import sys
import pygame

# Console library
from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt

console = Console()

class GameMap:
    def __init__(self):
        self.map_width = 500
        self.map_height = 500

    def configure_map(self):
        # Input map data
        self.map_width = IntPrompt.ask(
            "[bold magenta]Width[/]",
            default=500
        )

        self.map_height = IntPrompt.ask(
            "[bold magenta]Height[/]",
            default=500
        )

        console.print(
            f"[green]Map size:[/] {self.map_width} × {self.map_height}"
        )


if __name__ == "__main__":
    console.print("[bold cyan italic]Project MACI[/]")
    console.rule()

    game_map = GameMap()
    game_map.configure_map()