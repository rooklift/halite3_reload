# Halite 3 Reloader

This script takes a Halite 3 replay and feeds it (turn by turn) to a Halite 3 bot, comparing the bot's output to the output in the replay.

# Usage

`reload.py <filename> <player_id> <bot_path> <optional_2nd_bot_path>`

# Requirements

Out of the box, the script can only read JSON replays.

To read the .hlt replays, you will have to do `pip install zstandard`

# Output

Disagreements between the replay and the bot are shown, like so:

```
Turn 151
    (blank)           g
    m 7 o             m 7 s
    c 13              m 13 s
    m 19 s            m 19 e
    m 31 e            m 31 n
    m 37 o            m 37 s
    m 87 o            m 87 s
```
