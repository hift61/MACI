# Main library
import pygame

# Console library
from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt
from rich.console import Align
from rich import box

# define concole
console = Console()

class GameMap:
    def __init__(self) -> None:
        self.map_width = 500
        self.map_height = 500
        
        self.window_width = self.map_width + 50
        self.window_height = self.map_height + 50
    
    def display_map(self) -> None:
        pygame.init()
        
        screen = pygame.display.set_mode((self.window_width, self.window_height))
        pygame.display.set_caption("MACI")
        
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
        
        pygame.quit()
    
    # Input map data
    def configure_map(self) -> None:
        self.map_width = IntPrompt.ask( "[bold magenta]Width[/]", default=500)
        self.window_width = self.map_width + 50

        self.map_height = IntPrompt.ask("[bold magenta]Height[/]", default=500)
        self.window_width = self.map_height + 50

        console.print(f"[green]Map size:[/] {self.map_width} × {self.map_height}")

if __name__ == "__main__":
    console.print(
        Panel(
            Align.center(
                "[bold bright_white]PROJECT[/]\n"
                "[bold bright_cyan]M A C I[/]"
            ),
            border_style="bright_magenta",
            box = box.DOUBLE,
            padding=(1, 6),
            expand=False
            )
        )
    console.rule()

    game_map = GameMap()
    game_map.configure_map()
    
    game_map.display_map()