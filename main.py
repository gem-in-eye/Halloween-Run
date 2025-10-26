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
import math
import random
import wave
import struct
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

# Make the sky larger by increasing the top margin (shrinks path area)
PATH_MARGIN_TOP = 40
PATH_MARGIN_BOTTOM = 10

ACCELERATE_DELTA = 0.02
GAME_SPEED_MIN = 1.0
GAME_SPEED_MAX = 3.0

# Gradual world speed growth per frame (toward GAME_SPEED_MAX)
WORLD_SPEED_GROWTH = 0.001

# Horizontal movement for the cat
CAT_ACCEL_SPEED_X = 2  # when holding Right
CAT_DRIFT_SPEED_X = 1  # slow drift left when not holding Right

# Starfield settings
STAR_COUNT = 50
STAR_TWINKLE_CHANCE = 0.02  # ~2% chance per frame to adjust brightness

SURVIVE_REWARD = 0.1
CRASH_PENALTY = -100.0

# High score persistence
HIGHSCORE_FILE = "highscore.txt"


class Cat(pygame.sprite.Sprite):
    """Player sprite (a black cat)."""

    def __init__(self, x: int, y: int):
        super().__init__()
        # Try to load animated frames cat1.png, cat2.png, cat3.png
        frame_names = ["cat1.png", "cat2.png", "cat3.png"]
        frames: list[pygame.Surface] = []
        for name in frame_names:
            path = name
            # Prefer assets/ directory if file exists there
            assets_path = os.path.join("assets", name)
            if os.path.exists(assets_path):
                path = assets_path
            if os.path.exists(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    if img.get_size() != (CAT_W, CAT_H):
                        img = pygame.transform.scale(img, (CAT_W, CAT_H))
                    frames.append(img)
                except Exception:
                    frames = []
                    break
            else:
                frames = []
                break

        if frames:
            self.frames = frames
        else:
            # Fallback: generate simple placeholder frames with tiny variations
            self.frames = []
            for i in range(3):
                surf = pygame.Surface((CAT_W, CAT_H), pygame.SRCALPHA)
                base = 10 + i * 8
                pygame.draw.rect(surf, (base, base, base), surf.get_rect())
                # tiny ear pixels
                pygame.draw.rect(surf, (0, 0, 0), pygame.Rect(2, 0, 2, 2))
                pygame.draw.rect(surf, (0, 0, 0), pygame.Rect(CAT_W - 4, 0, 2, 2))
                self.frames.append(surf)

        self.frame_idx: float = 0.0
        self.anim_speed: float = 0.2  # frames per update
        self.image = self.frames[0]
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
        # Advance animation
        if hasattr(self, "frames") and self.frames:
            self.frame_idx = (self.frame_idx + self.anim_speed) % len(self.frames)
            self.image = self.frames[int(self.frame_idx)]
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

        # Try to load animated frames per type; fallback to colored rectangle
        frames = self._load_frames_for_kind(kind, w, h)
        if frames:
            self.frames: list[pygame.Surface] = frames
            self.frame_idx: float = 0.0
            self.anim_speed: float = 0.18  # frames per update
            self.image = self.frames[0]
        else:
            self.frames = []
            self.frame_idx = 0.0
            self.anim_speed = 0.0
            surf = pygame.Surface((w, h))
            surf.fill(color)
            self.image = surf

        self.rect = self.image.get_rect(topleft=(x, y))

    def update(self, game_speed: float):
        # Move left based on base speed and game speed multiplier
        dx = OBSTACLE_BASE_SPEED * game_speed
        self.rect.x -= int(round(dx))
        if self.rect.right < 0:
            self.kill()

        # Advance animation if available
        if getattr(self, 'frames', None):
            self.frame_idx = (self.frame_idx + self.anim_speed) % len(self.frames)
            self.image = self.frames[int(self.frame_idx)]

    def _load_frames_for_kind(self, kind: str, w: int, h: int) -> list[pygame.Surface]:
        """Load and scale animation frames for the obstacle kind.

        Attempts to load from assets/ first, then project root. Returns [] on failure.
        """
        def load_frame(path: str) -> pygame.Surface | None:
            try:
                if os.path.exists(path):
                    img = pygame.image.load(path).convert_alpha()
                    if img.get_size() != (w, h):
                        img = pygame.transform.scale(img, (w, h))
                    return img
            except Exception:
                return None
            return None

        names: list[str] = []
        if kind == "pumpkin":
            # Support possible filename typo for frame 3
            names = ["pumpkin1.png", "pumpkin2.png", "pumpkin3.png"]
            alt3 = "pumping3.png"
        elif kind == "bat":
            names = ["bat1.png", "bat2.png", "bat3.png"]
            alt3 = None
        elif kind == "ghost":
            names = ["ghost1.png", "ghost2.png", "ghost3.png"]
            alt3 = None
        else:
            return []

        frames: list[pygame.Surface] = []
        for i, name in enumerate(names):
            candidates = []
            # Prefer assets/
            candidates.append(os.path.join("assets", name))
            candidates.append(name)
            # For pumpkin frame 3, also try the alt typo name if the main one is missing
            if i == 2 and kind == "pumpkin" and alt3:
                candidates.append(os.path.join("assets", alt3))
                candidates.append(alt3)
            loaded = None
            for p in candidates:
                loaded = load_frame(p)
                if loaded is not None:
                    break
            if loaded is None:
                return []
            frames.append(loaded)
        return frames


class HalloweenCatGame:
    """Main game class with an AI-friendly interface.

    AI actions (discrete):
    0: do nothing
    1: move_up
    2: move_down
    3: move_right (hold to move right)
    """

    def __init__(self):
        # Initialize audio first (mixer) for better latency, then pygame
        try:
            pygame.mixer.pre_init(22050, -16, 1, 512)
        except Exception:
            pass
        # Initialize pygame and create main display and internal low-res surface.
        pygame.init()
        pygame.display.set_caption("Halloween Run — Cat")
        # Fullscreen: use desktop resolution
        info = pygame.display.Info()
        desktop_size = (info.current_w, info.current_h)
        self.screen = pygame.display.set_mode(desktop_size, pygame.FULLSCREEN)
        self.internal = pygame.Surface((INTERNAL_W, INTERNAL_H))
        self.clock = pygame.time.Clock()
        # Start background spooky music (best-effort)
        self._init_audio_and_music()

        # Gamepad support
        self._init_gamepads()

        # Sprite groups
        self.player = pygame.sprite.GroupSingle()
        self.obstacles = pygame.sprite.Group()

        # Game state
        self.score: int = 0
        self.game_over: bool = False
        self.game_speed: float = GAME_SPEED_MIN

        # Background scroll (for simple decorations)
        self.bg_scroll_x: float = 0.0
        # Parallax sky elements
        self.sky_scroll1: float = 0.0  # near clouds (faster)
        self.sky_scroll2: float = 0.0  # far clouds (slower)
        self.sky_scroll3: float = 0.0  # stars layer (very slow)
        self.moon_x: float = float(INTERNAL_W - 30)
        self.moon_y: float = 18.0

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

        # Reset parallax sky
        self.sky_scroll1 = 0.0
        self.sky_scroll2 = 0.0
        self.sky_scroll3 = 0.0
        self.moon_x = float(random.randint(int(INTERNAL_W*0.6), INTERNAL_W - 10))
        self.moon_y = float(random.randint(10, 25))

        # Stars (spawn in sky area above the path)
        sky_height = max(8, PATH_MARGIN_TOP - 6)
        self.stars = []
        for _ in range(STAR_COUNT):
            sx = random.randint(0, INTERNAL_W - 1)
            sy = random.randint(2, sky_height)
            size = random.choice([1, 1, 1, 2])  # mostly small
            bright = random.randint(170, 240)
            self.stars.append({"x": sx, "y": sy, "size": size, "b": bright})

        # Left-edge decorations: pumpkins, bats, ghosts along corridor
        self.left_decos = []
        corridor_top = PATH_MARGIN_TOP
        corridor_bottom = INTERNAL_H - PATH_MARGIN_BOTTOM
        corridor_h = max(0, corridor_bottom - corridor_top)
        kinds = ["pumpkin", "bat", "ghost"]
        n = len(kinds)
        if corridor_h >= 12 and n > 0:
            spacing = corridor_h // (n + 1)
            size_w = 10
            size_h = 10
            for i, kind in enumerate(kinds, start=1):
                y = corridor_top + i * spacing - size_h // 2
                # Try to reuse obstacle frame loader via a small helper
                frames = self._load_deco_frames(kind, size_w, size_h)
                anim_speed = 0.15
                color_map = {
                    "pumpkin": (239, 125, 14),
                    "bat": (70, 0, 120),
                    "ghost": (200, 200, 255),
                }
                # Bobbing motion params
                bob_amp = 3
                # Small variation per kind
                bob_speed = {
                    "pumpkin": 0.035,
                    "bat": 0.055,
                    "ghost": 0.045,
                }.get(kind, 0.04)
                bob_phase = random.random() * 2 * math.pi
                self.left_decos.append({
                    "kind": kind,
                    "x": 1,
                    "y": int(y),
                    "base_y": int(y),
                    "w": size_w,
                    "h": size_h,
                    "frames": frames,
                    "frame_idx": 0.0,
                    "anim_speed": anim_speed,
                    "color": color_map.get(kind, (180, 180, 180)),
                    "bob_amp": bob_amp,
                    "bob_speed": bob_speed,
                    "bob_phase": bob_phase,
                })
        # Restart music if it was stopped on previous game over
        self._init_audio_and_music()

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

        # Update parallax sky motion (subtly respond to game speed)
        speed_norm = (self.game_speed - GAME_SPEED_MIN) / (GAME_SPEED_MAX - GAME_SPEED_MIN)
        speed_norm = max(0.0, min(1.0, speed_norm))
        speed_factor = 1.0 + 0.4 * speed_norm
        self.sky_scroll1 += 0.1 * speed_factor  # near layer
        self.sky_scroll2 += 0.025 * speed_factor # far layer
        self.sky_scroll3 += 0.010 * speed_factor # stars layer (very slow)
        self.moon_x -= 0.02 * speed_factor
        if self.moon_x < -10:
            self.moon_x = INTERNAL_W + 10

        # Twinkling stars: small random brightness variation
        if hasattr(self, 'stars'):
            for s in self.stars:
                if random.random() < STAR_TWINKLE_CHANCE:
                    delta = random.choice([-20, -10, 10, 20])
                    s['b'] = max(140, min(255, s['b'] + delta))

        # Advance left-edge decorations animation
        if hasattr(self, 'left_decos'):
            for d in self.left_decos:
                frames = d.get("frames")
                if frames:
                    d["frame_idx"] = (d["frame_idx"] + d["anim_speed"]) % len(frames)
                # Vertical bobbing motion
                by = d.get("base_y", d.get("y", PATH_MARGIN_TOP))
                amp = d.get("bob_amp", 3)
                spd = d.get("bob_speed", 0.04)
                ph = d.get("bob_phase", 0.0) + spd
                d["bob_phase"] = ph
                y = int(round(by + amp * math.sin(ph)))
                # Clamp inside corridor
                corridor_top = PATH_MARGIN_TOP
                corridor_bottom = INTERNAL_H - PATH_MARGIN_BOTTOM
                y = max(corridor_top, min(y, corridor_bottom - d.get("h", 10)))
                d["y"] = y

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

        # Bounds handling: keep cat within the path corridor vertically
        # (no moving into sky or fence), and end the game if touching the left edge.
        if cat is not None:
            # Horizontal clamp
            if cat.rect.left < 0:
                cat.rect.left = 0
            if cat.rect.right > INTERNAL_W:
                cat.rect.right = INTERNAL_W

            # Vertical clamp to path corridor (avoid sky and fence areas)
            corridor_top = PATH_MARGIN_TOP
            corridor_bottom = INTERNAL_H - PATH_MARGIN_BOTTOM
            if cat.rect.top < corridor_top:
                cat.rect.top = corridor_top
            if cat.rect.bottom > corridor_bottom:
                cat.rect.bottom = corridor_bottom

            # Game over if touching left edge
            if cat.rect.left <= 0:
                self.game_over = True
                if self.score > self.high_score:
                    self.high_score = self.score
                self._save_high_score()
                # Stop music on game over
                self._stop_music()
                # Play ouch SFX
                self._play_ouch_sfx()
                return self._get_game_state(), CRASH_PENALTY, True

        # Spawn obstacles
        self._spawn_cooldown -= 1
        if self._spawn_cooldown <= 0:
            # Spawn within the path corridor vertically
            path_top = PATH_MARGIN_TOP
            path_bottom = INTERNAL_H - PATH_MARGIN_BOTTOM
            spawn_y = random.randint(path_top, max(path_top, path_bottom - OBSTACLE_MIN_H))
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
            # Stop music on game over
            self._stop_music()
            # Play ouch SFX
            self._play_ouch_sfx()
            return self._get_game_state(), CRASH_PENALTY, True

        # Scoring and background scroll
        self.score += 1
        if self.score > self.high_score:
            self.high_score = self.score
        # Make fence move faster as the game gets faster (amplify with speed_norm)
        self.bg_scroll_x += 0.2 * self.game_speed * (1.0 + 1.0 * speed_norm)
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
                elif event.type == pygame.JOYDEVICEADDED or event.type == pygame.JOYDEVICEREMOVED:
                    # Refresh gamepads on hotplug
                    self._init_gamepads()
            # Continuous key press handling (repeat while held)
            gp_action = self._get_gamepad_action()
            if gp_action is not None:
                action = gp_action
            else:
                keys = pygame.key.get_pressed()
                if keys[pygame.K_SPACE] or keys[pygame.K_RIGHT]:
                    action = 3
                elif keys[pygame.K_UP]:
                    action = 1
                elif keys[pygame.K_DOWN]:
                    action = 2

            # Advance or restart on accelerate while game over
            if self.game_over:
                if action == 3:
                    self.reset()
            else:
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

        # Stars (very small dots, parallaxed by sky_scroll3)
        if hasattr(self, 'stars') and self.stars:
            offset_star = int(self.sky_scroll3) % INTERNAL_W
            for s in self.stars:
                x = (s['x'] - offset_star) % INTERNAL_W
                y = s['y']
                b = s['b']
                color = (b, b, min(255, b + 20))
                size = s['size']
                pygame.draw.rect(self.internal, color, pygame.Rect(x, y, size, size))

        # Parallax sky: moon
        moon_color = (250, 240, 190)
        pygame.draw.circle(self.internal, moon_color, (int(self.moon_x), int(self.moon_y)), 7)
        # simple crescent effect
        pygame.draw.circle(self.internal, (10, 8, 18), (int(self.moon_x) + 3, int(self.moon_y) - 1), 6)

        # Parallax sky: clouds (two layers)
        def draw_cloud(x: int, y: int, w: int, h: int, color):
            pygame.draw.ellipse(self.internal, color, pygame.Rect(x, y, w, h))
            pygame.draw.ellipse(self.internal, color, pygame.Rect(x - w//3, y + 1, w, h))
            pygame.draw.ellipse(self.internal, color, pygame.Rect(x + w//3, y + 2, w, h))

        # Far layer (slower, dimmer)
        color_far = (200, 200, 220)
        spacing_far = 60
        offset_far = int(self.sky_scroll2) % spacing_far
        for cx in range(-offset_far, INTERNAL_W, spacing_far):
            draw_cloud(cx, 20, 16, 4, color_far)

        # Near layer (a bit faster, brighter)
        color_near = (230, 230, 245)
        spacing_near = 80
        offset_near = int(self.sky_scroll1) % spacing_near
        for cx in range(-offset_near, INTERNAL_W, spacing_near):
            draw_cloud(cx + 10, 24, 20, 8, color_near)

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

        # Left-edge animated decorations (pumpkin, bat, ghost)
        if hasattr(self, 'left_decos'):
            for d in self.left_decos:
                frames = d.get("frames")
                x = d.get("x", 1)
                y = d.get("y", PATH_MARGIN_TOP)
                w = d.get("w", 10)
                h = d.get("h", 10)
                if frames:
                    idx = int(d.get("frame_idx", 0.0)) % len(frames)
                    self.internal.blit(frames[idx], (x, y))
                else:
                    # Fallback simple rect
                    pygame.draw.rect(self.internal, d.get("color", (180, 180, 180)), pygame.Rect(x, y, w, h))

        # Sprites
        self.obstacles.draw(self.internal)
        self.player.draw(self.internal)

        # UI text (score and high score)
        score_surf = self.font.render(f"Score: {self.score}", True, (220, 220, 220))
        self.internal.blit(score_surf, (2, 2))
        high_surf = self.font.render(f"High: {self.high_score}", True, (250, 200, 80))
        self.internal.blit(high_surf, (INTERNAL_W - high_surf.get_width() - 2, 2))

        if self.game_over:
            msg = self.font.render("Game Over - Press R", True, (255, 100, 100))
            msg2 = self.font.render("or A on Controller", True, (255, 100, 100))
            msg3 = self.font.render(f"to Restart", True, (255, 100, 100))
            # Center the message roughly
            mx = (INTERNAL_W - msg.get_width()) // 2
            my = INTERNAL_H // 2 - 5
            self.internal.blit(msg, (mx, my))
            self.internal.blit(msg2, (mx, my + msg.get_height() + 2))
            self.internal.blit(msg3, (mx, my + msg.get_height() + 2 + msg2.get_height() + 2))
        # Scale to screen with letterboxing: keep aspect ratio and pixel scale
        sw, sh = self.screen.get_size()
        # Choose an integer scale to preserve crisp pixels
        scale = max(1, min(sw // INTERNAL_W, sh // INTERNAL_H))
        render_w, render_h = INTERNAL_W * scale, INTERNAL_H * scale
        scaled = pygame.transform.scale(self.internal, (render_w, render_h))
        # Center the scaled image and fill bars
        x = (sw - render_w) // 2
        y = (sh - render_h) // 2
        self.screen.fill((0, 0, 0))
        self.screen.blit(scaled, (x, y))
        pygame.display.flip()

    # ------------------------- GAMEPAD INPUT -------------------------- #
    def _init_gamepads(self):
        try:
            pygame.joystick.init()
        except Exception:
            self.gamepads = []
            return
        count = 0
        try:
            count = pygame.joystick.get_count()
        except Exception:
            count = 0
        self.gamepads = []
        for i in range(count):
            try:
                js = pygame.joystick.Joystick(i)
                js.init()
                self.gamepads.append(js)
            except Exception:
                continue

    def _get_gamepad_action(self):
        """Return an action from the first connected gamepad, or None if no input.

        Mapping (Xbox-style typical):
        - Accelerate: A (button 0) or RB (button 5) or right trigger axis (>0.5) or D-pad right
        - Up: Left stick up (axis 1 < -0.3) or D-pad up
        - Down: Left stick down (axis 1 > 0.3) or D-pad down
        """
        if not hasattr(self, 'gamepads') or not self.gamepads:
            return None
        gp = self.gamepads[0]
        try:
            # Buttons
            btns = gp.get_numbuttons()
            def btn(i):
                return gp.get_button(i) if i < btns else 0
            # Hats (D-pad)
            hat = (0, 0)
            if gp.get_numhats() > 0:
                hat = gp.get_hat(0)  # (x,y) with -1,0,1
            # Axes
            axes = [0.0] * gp.get_numaxes()
            for i in range(len(axes)):
                try:
                    axes[i] = gp.get_axis(i)
                except Exception:
                    axes[i] = 0.0

            # Accelerate checks
            accel = False
            # A button (0) or RB (5) commonly; tolerate variants
            if btn(0) or btn(5) or btn(7):
                accel = True
            # D-pad right
            if hat[0] > 0:
                accel = True
            # Right trigger axis on some mappings (index varies: 5, 4, or 2); treat >0.5 as pressed
            for idx in (5, 4, 2):
                if idx < len(axes) and axes[idx] > 0.5:
                    accel = True
                    break
            if accel:
                return 3

            # Up/down via D-pad and left stick Y (axis 1)
            if hat[1] > 0:
                return 1
            if hat[1] < 0:
                return 2
            if len(axes) > 1:
                y = axes[1]
                if y < -0.3:
                    return 1
                if y > 0.3:
                    return 2
        except Exception:
            return None
        return None

    # ---------------------------- AUDIO ------------------------------- #
    def _init_audio_and_music(self):
        """Initialize mixer and start looping spooky music. Best-effort, no crash if unavailable."""
        try:
            if not pygame.mixer.get_init():
                # If not already initialized by pre_init
                pygame.mixer.init(22050, -16, 1, 512)
        except Exception:
            return  # No audio available

        try:
            music_path = os.path.join("assets", "spooky_loop.wav")
            self._ensure_spooky_music(music_path)
            pygame.mixer.music.load(music_path)
            pygame.mixer.music.set_volume(10)
            pygame.mixer.music.play(-1)
        except Exception:
            # Silently ignore audio errors
            pass

    def _stop_music(self):
        """Fade out or stop music safely."""
        try:
            if pygame.mixer.get_init():
                try:
                    pygame.mixer.music.fadeout(700)
                except Exception:
                    pygame.mixer.music.stop()
        except Exception:
            pass

    def _play_ouch_sfx(self):
        """Play a short 'ouch' sound effect once, best-effort."""
        try:
            if not pygame.mixer.get_init():
                return
            if not hasattr(self, "_ouch_sfx") or self._ouch_sfx is None:
                path = os.path.join("assets", "ouch.wav")
                self._ensure_ouch_sfx(path)
                try:
                    self._ouch_sfx = pygame.mixer.Sound(path)
                    self._ouch_sfx.set_volume(0.6)
                except Exception:
                    self._ouch_sfx = None
            if getattr(self, "_ouch_sfx", None) is not None:
                self._ouch_sfx.play()
        except Exception:
            pass

    def _ensure_ouch_sfx(self, path: str, overwrite: bool = False):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            return
        if not overwrite and os.path.exists(path):
            return
        try:
            self._generate_ouch_wav(path)
        except Exception:
            pass

    def _generate_ouch_wav(self, path: str):
        """Generate a short descending-pitch square chirp as an 'ouch' SFX."""
        sr = 22050
        dur = 0.35
        n = int(sr * dur)
        start_f = 900.0
        end_f = 220.0
        attack = max(1, int(0.01 * sr))
        decay = max(1, int(0.12 * sr))
        amp = 6000

        frames = bytearray()
        phase = 0.0
        for i in range(n):
            t = i / (n - 1) if n > 1 else 0
            # Linear pitch slide from start_f to end_f
            f = start_f + (end_f - start_f) * t
            phase += (2 * math.pi * f) / sr
            s = amp if math.sin(phase) >= 0 else -amp
            # Tiny noise sprinkle for crunch
            s += int((random.random() - 0.5) * 1200)
            # Envelope
            if i < attack:
                s *= i / attack
            elif n - i < decay:
                s *= (n - i) / decay
            # Clip
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            frames.extend(struct.pack('<h', int(s)))

        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(frames)

    def _ensure_spooky_music(self, path: str, overwrite: bool = False):
        """Create a small chiptune-like spooky loop if not present."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            return
        if not overwrite and os.path.exists(path):
            return
        try:
            self._generate_spooky_wav(path)
        except Exception:
            # Ignore failures; music will just not play
            pass

    def _generate_spooky_wav(self, path: str):
        """Generate a short, looping 8-bit-style spooky tune as a WAV file.

        - Mono, 22050 Hz, 16-bit
        - Two square-wave voices: lead and bass
        - In-key of A minor, simple motif, ~9.6s loop
        """
        sr = 22050
        tempo = 100.0  # BPM
        beat_sec = 60.0 / tempo

        # Frequencies (approx) for A minor scale notes
        A4 = 440.00
        C5 = 523.25
        D5 = 587.33
        E5 = 659.25
        G5 = 783.99
        A5 = 880.00
        F5 = 698.46
        # Bass
        A2 = 110.00
        E2 = 82.41
        G2 = 98.00
        F2 = 87.31

        # Simple motif (lead) over 8 beats, repeated twice
        lead_seq = [
            (A4, 1), (C5, 1), (E5, 1), (C5, 1),
            (G5, 1), (E5, 1), (D5, 1), (C5, 1),
        ] * 2
        # Bass pattern aligned to 16 beats total
        bass_seq = [
            (A2, 2), (E2, 2), (G2, 2), (F2, 2),
        ] * 2

        def render_voice(seq, amp):
            samples = []
            for (freq, beats) in seq:
                dur = beats * beat_sec
                n_samp = int(dur * sr)
                # Simple A/D envelope to reduce clicks
                attack = max(1, int(0.01 * sr))
                decay = max(1, int(0.02 * sr))
                for n in range(n_samp):
                    t = n / sr
                    # Square wave
                    s = amp if math.sin(2 * math.pi * freq * t) >= 0 else -amp
                    # Envelope
                    if n < attack:
                        s *= n / attack
                    elif n_samp - n < decay:
                        s *= (n_samp - n) / decay
                    samples.append(int(s))
            return samples

        lead = render_voice(lead_seq, 3000)
        bass = render_voice(bass_seq, 4000)
        total = max(len(lead), len(bass))
        # Pad shorter voice
        if len(lead) < total:
            lead.extend([0] * (total - len(lead)))
        if len(bass) < total:
            bass.extend([0] * (total - len(bass)))

        # Mix and clip
        frames = bytearray()
        for i in range(total):
            v = lead[i] + bass[i]
            if v > 32767:
                v = 32767
            elif v < -32768:
                v = -32768
            frames.extend(struct.pack('<h', int(v)))

        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(frames)

    def _load_deco_frames(self, kind: str, w: int, h: int) -> list[pygame.Surface]:
        """Load frames for a decoration using the same naming as obstacles."""
        def load_frame(path: str) -> pygame.Surface | None:
            try:
                if os.path.exists(path):
                    img = pygame.image.load(path).convert_alpha()
                    if img.get_size() != (w, h):
                        img = pygame.transform.scale(img, (w, h))
                    return img
            except Exception:
                return None
            return None

        if kind == "pumpkin":
            names = ["pumpkin1.png", "pumpkin2.png", "pumpkin3.png", "pumping3.png"]
        elif kind == "bat":
            names = ["bat1.png", "bat2.png", "bat3.png"]
        elif kind == "ghost":
            names = ["ghost1.png", "ghost2.png", "ghost3.png"]
        else:
            return []

        frames: list[pygame.Surface] = []
        # We expect exactly 3 frames; try to collect 3 in order
        target = []
        if kind == "pumpkin":
            target = [["pumpkin1.png"], ["pumpkin2.png"], ["pumpkin3.png", "pumping3.png"]]
        elif kind == "bat":
            target = [["bat1.png"], ["bat2.png"], ["bat3.png"]]
        elif kind == "ghost":
            target = [["ghost1.png"], ["ghost2.png"], ["ghost3.png"]]

        for group in target:
            loaded = None
            for name in group:
                candidates = [os.path.join("assets", name), name]
                for p in candidates:
                    loaded = load_frame(p)
                    if loaded is not None:
                        break
                if loaded is not None:
                    break
            if loaded is None:
                return []
            frames.append(loaded)
        return frames

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
