# Main library
import pygame
import random

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
    
    def make_seed(self, wall_c: int, seed: int) -> str:
        return f"{self.map_width}x{self.map_height}-{wall_c}-{seed}"
    
    def read_seed(self, code: str) -> tuple[int, int, int, int]:
        size, wall_c, seed = code.split("-")
        width, height = size.split("x")
        
        return (int(width), int(height), int(wall_c), int(seed))
    
    def make_rseed(self) -> str:
        seed = random.randint(100000, 999999)
        random.seed(seed)
        
        min_wall_c = max(3, self.map_width * self.map_height // 50000)
        max_wall_c = max(8, self.map_width * self.map_height // 15000)
        
        wall_c = random.randint(min_wall_c, max_wall_c)
        
        return self.make_seed(wall_c, seed)
    
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
    
    code = game_map.make_seed(12, 483921)
    game_map.display_map()