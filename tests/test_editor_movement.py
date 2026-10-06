"""Headless pygame checks for free placement and body-relative controls."""
import math
import os
from pathlib import Path
import tempfile
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

from mapgen.editor import EditorApp, PAD, COLORS
from mapgen.editor_model import EditorModel
from mapgen.spec import MapSpec


class EditorMovementTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "map.json")
        self.model = EditorModel(MapSpec(seed=0, width=500, height=500))
        self.app = EditorApp(self.model, self.path)

    def tearDown(self):
        pygame.quit()
        self.temp.cleanup()

    def key(self, key, mod=0):
        self.app.handle(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))

    def test_fractional_placement_drag_and_save_round_trip(self):
        self.app.tool = "agent"
        self.app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(123, 137), button=1))
        agent = self.model.spec.agents[0]
        self.assertAlmostEqual(agent["x"], (123 - PAD) / self.app.scale)
        self.assertNotEqual(agent["x"] % 5, 0)
        self.app.tool = "select"
        self.app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(123, 137), button=1))
        self.app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=(126, 141)))
        self.app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(126, 141), button=1))
        self.app.save()
        loaded = MapSpec.load(self.path)
        self.assertEqual(loaded.agents[0], agent)
        self.assertAlmostEqual(agent["x"], (126 - PAD) / self.app.scale)

    def test_turn_forward_fine_controls_and_no_backward(self):
        self.model.add_agent(100.125, 100.375, facing=37.5)
        self.app.start_play()
        env = self.app.play["env"]
        agent = env.agents["A"]
        self.key(pygame.K_RIGHT, pygame.KMOD_SHIFT)
        self.assertEqual(agent.facing, 39.0)
        self.assertEqual((agent.x, agent.y), (100.125, 100.375))
        self.key(pygame.K_w, pygame.KMOD_SHIFT)
        self.assertAlmostEqual(agent.x, 100.125 + 0.25 * math.cos(math.radians(39)))
        self.assertAlmostEqual(agent.y, 100.375 + 0.25 * math.sin(math.radians(39)))
        self.assertEqual(agent.facing, 39.0)
        pose = (agent.x, agent.y, agent.facing, env.step_count)
        self.key(pygame.K_s)
        self.key(pygame.K_DOWN)
        self.assertEqual((agent.x, agent.y, agent.facing, env.step_count), pose)
        self.key(pygame.K_a)
        self.assertEqual(agent.facing, 24.0)
        self.key(pygame.K_UP)
        self.assertAlmostEqual(agent.last_move["distance"], 2.5)
        self.app.draw()

    def test_board_background_has_no_grid_lines(self):
        self.app.draw()
        # These were the horizontal and vertical grid intersections every 50 units.
        for x in range(50, 500, 50):
            for y in range(50, 500, 50):
                self.assertEqual(tuple(self.app.screen.get_at(self.app.to_screen(x, y)))[:3], COLORS["map"])

    def test_wheel_rotates_body_in_fractional_degrees_and_marks_dirty(self):
        agent = self.model.add_agent(100, 100, facing=0.25)
        self.app.hover = (100, 100)
        self.app.dirty = False
        pygame.key.set_mods(pygame.KMOD_SHIFT)
        self.app.handle(pygame.event.Event(pygame.MOUSEWHEEL, y=1))
        self.assertEqual(agent["facing"], 358.75)
        self.assertTrue(self.app.dirty)


if __name__ == "__main__":
    unittest.main()
