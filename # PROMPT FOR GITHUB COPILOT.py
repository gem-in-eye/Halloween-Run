# PROMPT FOR GITHUB COPILOT:
#
# Create the base code for a side-scrolling game in Python using the Pygame library.
# The game should be simple and have a pixelated, Halloween theme.
# The player is a "Cat" that runs along a path, avoiding "Obstacle" objects (e.g., pumpkins, ghosts).
# The game MUST be structured with a clear API for an AI agent (like PyTorch or TensorFlow) to play it.

# Key Requirements:
# 1.  **Main Game Class (`HalloweenCatGame`):**
#     -   Initialize Pygame, set up the main display screen (e.g., 800x600).
#     -   **Pixelated Style:** Create a smaller internal surface (e.g., 200x150) where the game logic and drawing happen. This surface will be scaled up to the main display (800x600) using `pygame.transform.scale()`, creating a retro, pixelated look.
#     -   Manage game state variables: `score`, `game_over`, `game_speed`.
#     -   Manage sprites: A `pygame.sprite.GroupSingle` for the `Player` and a `pygame.sprite.Group` for `Obstacle` sprites.
#     -   Implement a scrolling background (e.g., a path with Halloween decorations).
#
#     -   **AI Interface Methods:**
#         -   `reset()`: Resets the game to the starting state (score 0, player at start position, empty obstacles, default game speed). Returns the initial `game_state`.
#         -   `step(actions)`: This is the core AI interface.
#             -   It takes two `actions` as input (e.g., action1: [0: "dont_accelerate", 1:"accelerate"] and action2:[ 0:"dont_move", 1: "move_up", 2: "move_down"]).
#             -   It updates the game by one single frame based on these actions.
#             -   It applies the player's actions (move up/down, or increase `game_speed` if "accelerate").
#             -   It updates all obstacles (move them left based on `game_speed`).
#             -   It spawns new obstacles randomly from the right side of the screen.
#             -   It checks for collisions (player with obstacles or screen boundaries). If a collision occurs, set `game_over = True`.
#             -   It updates the `score`.
#             -   It calculates the `reward` for this step (e.g., +0.1 for surviving, -100 for crashing).
#             -   It gets the new `game_state` by calling `_get_game_state()`.
#             -   It returns a tuple: `(game_state, reward, done)`, where `done` is the `game_over` boolean.
#         -   `_get_game_state()`: A helper method that returns the current state of the game for the AI. This should be simple, e.g., `[player_y, distance_to_next_obstacle, next_obstacle_y, game_speed]`.
#
#     -   **Human-Play Method:**
#         -   `run()`: The main game loop for a human player.
#             -   Uses `pygame.time.Clock()` to control FPS.
#             -   Handles `pygame.event.get()` for human input (e.g., Arrow UP, Arrow DOWN, SPACE for accelerate) and quitting.
#             -   Translates the human input into the discrete `actions` format (two actions: accelerate and move).
#             -   Calls `step(actions)` with the human-derived actions.
#             -   Calls `_update_ui()` to render the game.
#             -   If `game_over` is True, it shows a "Game Over" message and waits for a restart input.
#
#     -   **Rendering Method:**
#         -   `_update_ui()`: Renders all game objects (background, player, obstacles, score) onto the small internal surface. Then, scales that surface up to the main display and calls `pygame.display.update()`.
#
# 2.  **Player Class (`Cat`):**
#     -   Inherits from `pygame.sprite.Sprite`.
#     -   Represents the cat. Use a simple `pygame.Surface` with a color (e.g., orange) as a placeholder.
#     -   Has a `rect` for position and collision.
#     -   Has methods `move_up()` and `move_down()` which change its `rect.y`. Ensure it stays within the screen boundaries.
#     -   The `update()` method will apply the vertical movement.
#
# 3.  **Obstacle Class (`Obstacle`):**
#     -   Inherits from `pygame.sprite.Sprite`.
#     -   Represents Halloween-themed obstacles (e.g., pumpkins, ghosts). Use simple colored `pygame.Surface` placeholders (e.g., black, purple).
#     -   Spawns off-screen to the right.
#     -   The `update(game_speed)` method moves the obstacle left based on the current `game_speed`. It should also call `self.kill()` if it moves off-screen to the left.
#
# 4.  **Main Execution Block:**
#     -   Include an `if __name__ == "__main__":` block.
#     -   Inside, create an instance of `HalloweenCatGame`.
#     -   Call the `run()` method to start the game for a human player.
#
# Please include comments explaining the key sections, especially the AI interface methods (`reset`, `step`).
