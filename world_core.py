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

class Wall():
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.rect = pygame.Rect(x, y, width, height)
        self.is_solid = True

class GameMap:
    def __init__(self) -> None:
        self.map_width = 500
        self.map_height = 500
        
        self.window_width = self.map_width + 50
        self.window_height = self.map_height + 50
    
    def _generate_walls(self, wall_c: int, seed: int) -> list[Wall]:
        rng = random.Random(seed)
        walls: list[Wall] = []
        
        i = 0
        while len(walls) < wall_c and i < wall_c * 20:
            i += 1
            
            tmp = self._make_random_wall(rng)
            
            if any(tmp.rect.colliderect(wall.rect) for wall in walls):
                continue
            
            walls.append(tmp)
        
        return walls
    
    def _make_random_wall(self, rng: random.Random) -> Wall:
        orientation = rng.choice(["h", "v"])
        
        if orientation == "h":
            width = rng.randint(80, 200)
            height = rng.randint(10, 25)
        else:
            width = rng.randint(10, 25)
            height = rng.randint(80, 200)
        
        x = rng.randint(25, 25 + self.map_width - width)
        y = rng.randint(25, 25 + self.map_height - height)
        
        return Wall(x, y, width, height)
    
    def display_map(self) -> None:
        pygame.init()
        
        screen = pygame.display.set_mode((self.window_width, self.window_height))
        pygame.display.set_caption("MACI")
        
        border = [
            # 위쪽 경계
            Wall(25, 25, self.map_width, 10),
            # 오른쪽 경계
            Wall(self.map_width + 15, 25, 10, self.map_height),
            # 아래쪽 경계
            Wall(25, self.map_height + 15, self.map_width, 10),
            # 왼쪽 경계
            Wall(25, 25, 10, self.map_height)
        ]
        
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            screen.fill("black")
            
            for b in border:
                pygame.draw.rect(screen, "white", b.rect)
            
            for wall in self._generate_walls():
                pygame.draw.rect(screen, "white", wall.rect)
            
            pygame.display.flip()
        
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
        self.map_width = IntPrompt.ask("[bold magenta]Width[/]", default=500)
        self.window_width = self.map_width + 50

        self.map_height = IntPrompt.ask("[bold magenta]Height[/]", default=500)
        self.window_height = self.map_height + 50

        console.print(f"[green]Map size:[/] {self.map_width} × {self.map_height}")

if __name__ == "__main__":
    console.print(
        Panel(
            Align.center(
                "[bold bright_white]PROJECT[/]\n"
                "[bold bright_cyan]M A C I[/]"
            ),
            border_style="bright_magenta",
            box=box.DOUBLE,
            padding=(1, 6),
            expand=False
        )
    )
    console.rule()
    
    # 맵 정의
    game_map = GameMap()
    game_map.configure_map()
    
    print(game_map.window_width, game_map.window_height)
    
    game_map.display_map()