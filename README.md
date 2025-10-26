# Halloween Run (Pygame)

A tiny Halloween-themed, pixelated side-scrolling game written in Python using Pygame.

- Player: a black cat that moves up/down
- Obstacles: simple pumpkins/ghosts/bats
- Retro look: game renders to a 200x150 surface and scales to 800x600
- AI API: reset() and step(action) for integration with RL or scripting

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you’re on Windows PowerShell, use:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

Controls:
- Up Arrow: move up
- Down Arrow: move down
- Space (or Right Arrow): accelerate/move right (hold to move)
- R: restart when game over
- Esc or window close: quit

## AI Interface

Use the class `HalloweenCatGame` from `main.py`:

```python
from main import HalloweenCatGame

env = HalloweenCatGame()
state = env.reset()

# Example random policy for 300 steps
import random
for _ in range(300):
    action = random.choice([0,1,2,3])
    state, reward, done = env.step(action)
    if done:
        state = env.reset()
```

State vector (normalized floats):
`[player_y, distance_to_next_obstacle, next_obstacle_y, game_speed]`

- `player_y`: player top position / INTERNAL_H
- `distance_to_next_obstacle`: horizontal distance to the nearest upcoming obstacle (clipped to INTERNAL_W)
- `next_obstacle_y`: that obstacle’s top / INTERNAL_H (0 if none)
- `game_speed`: normalized between the min and max game speed

Rewards:
- +0.1 for each frame survived
- -100 on collision (episode terminates)

## High score

The game saves your best score to `highscore.txt` in the project folder. It updates when you crash or exit the game.

## Headless note

If you need to run without a display (e.g., CI), set:

```bash
export PYGAME_HEADLESS=1
```

This enables SDL’s dummy video driver before starting the game loop.

## License

MIT License. See `LICENSE`.
