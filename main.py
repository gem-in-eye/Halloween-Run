"""
Halloween Run — Pixelated side-scroller with AI-friendly API (reset/step)

- Theme: Halloween, pixelated look via low-res internal surface scaled up
- Player: A black cat that moves up/down and avoids obstacles
- Obstacles: Simple shapes (pumpkin, ghost, bat) moving from right to left
- AI API: reset() -> state, step(action) -> (state, reward, done)
- Human play: run() loop maps keys to actions and renders frames

Controls (human):
- Up Arrow: move up (action=1)
- Down Arrow: move down (action=2)
- Space (or Right Arrow): accelerate/move right (action=3)
- R: restart when game over
"""

from __future__ import annotations

import os
import random
from typing import List, Tuple

import pygame


# Display constants
WIDTH, HEIGHT = 800, 600
INTERNAL_W, INTERNAL_H = 200, 150  # 4x scale -> pixelated style
FPS = 60

# Gameplay constants (all in internal pixel units)
CAT_W, CAT_H = 10, 10
CAT_SPEED_PER_STEP = 2

OBSTACLE_MIN_W, OBSTACLE_MAX_W = 8, 14
OBSTACLE_MIN_H, OBSTACLE_MAX_H = 8, 14
OBSTACLE_BASE_SPEED = 1.2  # per-frame base speed in internal px

PATH_MARGIN_TOP = 8
PATH_MARGIN_BOTTOM = 8

ACCELERATE_DELTA = 0.02
GAME_SPEED_MIN = 1.0
GAME_SPEED_MAX = 3.0

# Gradual world speed growth per frame (toward GAME_SPEED_MAX)
WORLD_SPEED_GROWTH = 0.001

# Horizontal movement for the cat
CAT_ACCEL_SPEED_X = 2  # when holding Right
CAT_DRIFT_SPEED_X = 1  # slow drift left when not holding Right

SURVIVE_REWARD = 0.1
CRASH_PENALTY = -100.0

# High score persistence
HIGHSCORE_FILE = "highscore.txt"


class Cat(pygame.sprite.Sprite):
    """Player sprite (a black cat)."""

    def __init__(self, x: int, y: int):
        super().__init__()
        self.image = pygame.Surface((CAT_W, CAT_H))
        self.image.fill((10, 10, 10))  # black cat
        self.rect = self.image.get_rect(topleft=(x, y))
        self._dy = 0
        self._dx = 0

    def move_up(self):
        self._dy = -CAT_SPEED_PER_STEP

    def move_down(self):
        self._dy = CAT_SPEED_PER_STEP

    def move_right(self):
        self._dx = CAT_ACCEL_SPEED_X

    def drift_left(self):
        self._dx = -CAT_DRIFT_SPEED_X

    def update(self):
        # Apply one-tick movement, then reset deltas.
        self.rect.y += self._dy
        self.rect.x += self._dx
        self._dy = 0
        self._dx = 0
        # Bounds check will be handled in game logic for collision.


class Obstacle(pygame.sprite.Sprite):
    """Halloween-themed obstacle: pumpkin/ghost/bat (simple colored rectangles)."""

    TYPES = (
        ("pumpkin", (239, 125, 14)),  # orange
        ("ghost", (200, 200, 255)),   # pale
        ("bat", (70, 0, 120)),        # purple-ish
    )

    def __init__(self, x: int, y: int):
        super().__init__()
        w = random.randint(OBSTACLE_MIN_W, OBSTACLE_MAX_W)
        h = random.randint(OBSTACLE_MIN_H, OBSTACLE_MAX_H)
        kind, color = random.choice(self.TYPES)
        self.kind = kind
        self.image = pygame.Surface((w, h))
        self.image.fill(color)
        self.rect = self.image.get_rect(topleft=(x, y))

    def update(self, game_speed: float):
        # Move left based on base speed and game speed multiplier
        dx = OBSTACLE_BASE_SPEED * game_speed
        self.rect.x -= int(round(dx))
        if self.rect.right < 0:
            self.kill()


class HalloweenCatGame:
    """Main game class with an AI-friendly interface.

    AI actions (discrete):
    0: do nothing
    1: move_up
    2: move_down
    3: move_right (hold to move right)
    """

    def __init__(self):
        # Initialize pygame and create main display and internal low-res surface.
        pygame.init()
        pygame.display.set_caption("Halloween Run — Cat")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.internal = pygame.Surface((INTERNAL_W, INTERNAL_H))
        self.clock = pygame.time.Clock()

        # Sprite groups
        self.player = pygame.sprite.GroupSingle()
        self.obstacles = pygame.sprite.Group()

        # Game state
        self.score: int = 0
        self.game_over: bool = False
        self.game_speed: float = GAME_SPEED_MIN

        # Background scroll (for simple decorations)
        self.bg_scroll_x: float = 0.0

        # Obstacle spawn management
        self._spawn_cooldown: int = 0
        self._spawn_min = 45  # frames
        self._spawn_max = 110 # frames

        # Font for UI (scaled with pixel look after upscaling)
        self.font = pygame.font.SysFont("monospace", 10)

        # High score
        self.high_score: int = 0
        self._load_high_score()

        # Create initial state
        self.reset()

    # --------------------------- AI INTERFACE --------------------------- #
    def reset(self) -> List[float]:
        """Reset the game to the starting state and return initial game_state.

        Returns: game_state list [player_y, distance_to_next_obstacle, next_obstacle_y, game_speed]
        Values are normalized to 0..1 using internal surface dimensions where applicable.
        """
        self.score = 0
        self.game_over = False
        self.game_speed = GAME_SPEED_MIN
        self.bg_scroll_x = 0.0
        self._spawn_cooldown = random.randint(self._spawn_min, self._spawn_max)

        # Reset sprites
        self.player.empty()
        self.obstacles.empty()
        start_x = INTERNAL_W // 2 - CAT_W // 2
        start_y = INTERNAL_H // 2 - CAT_H // 2
        self.player.add(Cat(start_x, start_y))

        return self._get_game_state()

    def step(self, action: int) -> Tuple[List[float], float, bool]:
        """Advance the game by one frame based on a discrete action.

        Args:
            action: 0 nothing, 1 move_up, 2 move_down, 3 move_right (hold)

        Returns:
            (game_state, reward, done)

        Reward shaping:
            +0.1 per frame survived, -100 on crash.
        """
        if self.game_over:
            # If already done, keep returning terminal state with zero reward.
            return self._get_game_state(), 0.0, True

        # Increase world speed gradually over time
        self.game_speed = min(GAME_SPEED_MAX, self.game_speed + WORLD_SPEED_GROWTH)

        # Translate action
        cat = self.player.sprite
        if cat is not None:
            # Default: drift left when not accelerating
            cat.drift_left()
            if action == 1:
                cat.move_up()
            elif action == 2:
                cat.move_down()
            elif action == 3:
                # Move right while accelerating
                cat.move_right()

        # Update player (applies one-tick movement)
        self.player.update()

        # Keep within path bounds; leaving the vertical path counts as a crash
        path_top = PATH_MARGIN_TOP
        path_bottom = INTERNAL_H - PATH_MARGIN_BOTTOM
        if cat is not None:
            # Horizontal clamp (no crash on edges; just clamp inside screen)
            if cat.rect.left < 0:
                cat.rect.left = 0
            if cat.rect.right > INTERNAL_W:
                cat.rect.right = INTERNAL_W
            if cat.rect.top < path_top or cat.rect.bottom > path_bottom:
                self.game_over = True
                if self.score > self.high_score:
                    self.high_score = self.score
                self._save_high_score()
                return self._get_game_state(), CRASH_PENALTY, True

        # Spawn obstacles
        self._spawn_cooldown -= 1
        if self._spawn_cooldown <= 0:
            spawn_y = random.randint(path_top, path_bottom - OBSTACLE_MIN_H)
            spawn_x = INTERNAL_W + random.randint(0, 20)
            self.obstacles.add(Obstacle(spawn_x, spawn_y))
            # Cooldown scales with speed (faster game -> shorter cooldown)
            base = random.randint(self._spawn_min, self._spawn_max)
            scaled = max(20, int(base / self.game_speed))
            self._spawn_cooldown = scaled

        # Update obstacles
        for obs in list(self.obstacles):
            obs.update(self.game_speed)

        # Collision detection
        if cat is not None and pygame.sprite.spritecollideany(cat, self.obstacles):
            self.game_over = True
            # Persist current high score on crash
            if self.score > self.high_score:
                self.high_score = self.score
            self._save_high_score()
            return self._get_game_state(), CRASH_PENALTY, True

        # Scoring and background scroll
        self.score += 1
        if self.score > self.high_score:
            self.high_score = self.score
        self.bg_scroll_x += 0.2 * self.game_speed
        if self.bg_scroll_x >= INTERNAL_W:
            self.bg_scroll_x -= INTERNAL_W

        # Survival reward
        return self._get_game_state(), SURVIVE_REWARD, False

    def _get_game_state(self) -> List[float]:
        """Build a simple state vector for an AI agent.

        State format (normalized 0..1):
        [player_y, distance_to_next_obstacle, next_obstacle_y, game_speed]
        - player_y: top of the cat rect divided by INTERNAL_H
        - distance_to_next_obstacle: horizontal distance from cat.x to nearest obstacle ahead; clipped to INTERNAL_W
        - next_obstacle_y: top of that obstacle divided by INTERNAL_H (0 if none)
        - game_speed: normalized between GAME_SPEED_MIN..GAME_SPEED_MAX
        """
        cat = self.player.sprite
        player_y = (cat.rect.top / INTERNAL_H) if cat else 0.0

        # Find the nearest obstacle with x >= cat.x
        dist = float(INTERNAL_W)
        obs_y = 0.0
        if cat is not None:
            cat_x = cat.rect.centerx
            ahead = [o for o in self.obstacles if o.rect.centerx >= cat_x]
            if ahead:
                nearest = min(ahead, key=lambda o: o.rect.centerx)
                dist = max(0.0, float(nearest.rect.left - cat.rect.right))
                obs_y = nearest.rect.top / INTERNAL_H
        dist_norm = min(1.0, dist / INTERNAL_W)

        # Normalize speed
        speed_norm = (self.game_speed - GAME_SPEED_MIN) / (GAME_SPEED_MAX - GAME_SPEED_MIN)
        speed_norm = max(0.0, min(1.0, speed_norm))

        return [player_y, dist_norm, obs_y, speed_norm]

    # --------------------------- HUMAN LOOP ----------------------------- #
    def run(self):
        """Main game loop for human players."""
        running = True
        while running:
            self.clock.tick(FPS)

            # Handle inputs
            action = 0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if self.game_over and event.key == pygame.K_r:
                        self.reset()
            # Continuous key press handling (repeat while held)
            keys = pygame.key.get_pressed()
            if keys[pygame.K_SPACE] or keys[pygame.K_RIGHT]:
                action = 3
            elif keys[pygame.K_UP]:
                action = 1
            elif keys[pygame.K_DOWN]:
                action = 2

            # Advance game by one frame if not over
            if not self.game_over:
                self.step(action)

            # Draw frame
            self._update_ui()

        # Persist high score on exit
        self._save_high_score()
        pygame.quit()

    # --------------------------- RENDERING ------------------------------ #
    def _update_ui(self):
        """Render the frame onto the internal surface and scale up to screen."""
        # Clear background (night sky)
        self.internal.fill((10, 8, 18))

        # Draw a simple scrolling path/corridor
        path_color = (30, 30, 40)
        pygame.draw.rect(
            self.internal,
            path_color,
            pygame.Rect(0, PATH_MARGIN_TOP, INTERNAL_W, INTERNAL_H - PATH_MARGIN_TOP - PATH_MARGIN_BOTTOM),
        )

        # Decorations: repeating fence posts along the bottom using scroll
        deco_color = (50, 20, 10)
        spacing = 16
        offset = int(self.bg_scroll_x) % spacing
        y_bottom = INTERNAL_H - PATH_MARGIN_BOTTOM
        for x in range(-offset, INTERNAL_W, spacing):
            pygame.draw.rect(self.internal, deco_color, pygame.Rect(x, y_bottom - 4, 3, 4))

        # Sprites
        self.obstacles.draw(self.internal)
        self.player.draw(self.internal)

        # UI text (score and high score)
        score_surf = self.font.render(f"Score: {self.score}", True, (220, 220, 220))
        self.internal.blit(score_surf, (2, 2))
        high_surf = self.font.render(f"High: {self.high_score}", True, (250, 200, 80))
        self.internal.blit(high_surf, (INTERNAL_W - high_surf.get_width() - 2, 2))

        if self.game_over:
            msg = self.font.render("Game Over - Press R to Restart", True, (255, 100, 100))
            # Center the message roughly
            mx = (INTERNAL_W - msg.get_width()) // 2
            my = INTERNAL_H // 2 - 5
            self.internal.blit(msg, (mx, my))

        # Scale to screen
        scaled = pygame.transform.scale(self.internal, (WIDTH, HEIGHT))
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()

    # -------------------------- PERSISTENCE ---------------------------- #
    def _load_high_score(self):
        try:
            if os.path.exists(HIGHSCORE_FILE):
                with open(HIGHSCORE_FILE, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                    self.high_score = int(v) if v.isdigit() else 0
            else:
                self.high_score = 0
        except Exception:
            # Ignore file errors and default to 0
            self.high_score = 0

    def _save_high_score(self):
        try:
            # Only write if we have a non-negative integer
            hs = max(0, int(self.high_score))
            with open(HIGHSCORE_FILE, "w", encoding="utf-8") as f:
                f.write(str(hs))
        except Exception:
            # Ignore persistence errors silently
            pass


if __name__ == "__main__":
    # Optional: enable dummy video driver if running in certain headless environments
    if os.environ.get("PYGAME_HEADLESS", "0") == "1":
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    game = HalloweenCatGame()
    game.run()
