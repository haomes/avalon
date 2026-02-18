<p align="center">
  <img src="assets/banner.png" alt="Avalon Multi-Agent Simulation" width="800"/>
</p>

<p align="center">
  <strong>6 LLM Agents sit at a round table, battling through deduction and deception</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="#features">Features</a> · <a href="#architecture">Architecture</a> · <a href="#visualization">Visualization</a> · <a href="README_CN.md">中文文档</a>
</p>

---

## Introduction

A **multi-agent sandbox simulator** based on the board game *The Resistance: Avalon*. All 6 players are powered by independent LLM Agents that discuss, reason, vote, and deceive through natural language to play a complete game of Avalon autonomously.

Each Agent has its own memory system and decision logic, with access limited strictly to the information its role should know — Merlin knows who the evil players are but must hide his identity, the Assassin hunts for clues in the discussion, and Morgana impersonates Merlin to sow confusion.

The project supports **single-game mode**, **community mode** (with post-game reflection and inter-game private chats), and two visualization options: a **real-time WebSocket dashboard** and an **offline replay viewer**.

## Features

### Full Avalon Game Engine

- **6-player standard game** — Good team (4): Merlin, Percival, Loyal Servant ×2 vs Evil team (2): Morgana, Assassin
- **5-round quest system** — Team sizes: 2, 3, 4, 3, 4
- **Complete game flow** — Night phase → Team proposal → Discussion → Vote → Mission → Assassination
- **Information asymmetry** — Strict adherence to board game rules; each role only receives the intel it should have

### Intelligent Agent System

- **Independent memory** — Each Agent maintains its own memory stream with LLM-powered summarization to prevent context overflow
- **Role-playing** — System prompts inject role identity and strategic guidance; Agents make autonomous decisions based on character traits
- **3-layer fault tolerance** — LLM response parsing: JSON extraction → keyword fallback → random fallback, ensuring the game never stalls
- **Flexible models** — Compatible with any OpenAI-compatible API; Good/Evil teams can use different models

### Community Mode — Multi-Game Evolution

- **Reflection learning** — After each game, Agents review their performance and iteratively revise their strategies
- **Private chat system** — Between games, players chat in pairs; LLM analyzes conversations to update trust and friendliness scores
- **Social network** — Persistent trust/friendliness relationship graph that influences future in-game decisions
- **Player profiling** — Records each opponent's play style and behavioral patterns across games

### Visualization

- **Live dashboard** — WebSocket-driven, watch Agent discussions, votes, and missions unfold in real time
- **Control panel** — Pause, step-through, and resume to observe each decision closely
- **God mode** — Toggle to reveal all players' true identities and secret vote details
- **4-tab panel** — GAME log / AGENTS profiles / LEARNING reflections & chats / STATS statistics
- **Timeline navigation** — Jump to any round/phase, with adjustable auto-play speed

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Visualization Layer                    │
│  server/         WebSocket service + async game runner   │
│  viewer/         Live dashboard + offline replay UI      │
├─────────────────────────────────────────────────────────┤
│                   Community Layer                        │
│  community/      Multi-game loop + reflection + chat     │
│                  + persistent agent data                 │
├─────────────────────────────────────────────────────────┤
│                    Engine Layer                          │
│  engine/         Game flow (team/vote/mission/assassin)  │
│  agents/         Agent decisions + memory management     │
│  models/         Role / Player / GameState data models   │
├─────────────────────────────────────────────────────────┤
│                    Infrastructure                        │
│  config.py       Global configuration                    │
│  llm_client.py   LLM API wrapper (OpenAI-compatible)    │
│  utils/logger    Colored terminal + file + event logger  │
└─────────────────────────────────────────────────────────┘
```

### Information Asymmetry Matrix

|  | Merlin | Percival | Loyal Servant | Morgana | Assassin |
|--|--------|----------|---------------|---------|----------|
| Evil identities | Knows all | - | - | - | - |
| Merlin/Morgana | - | Sees both, can't tell apart | - | - | - |
| Evil allies | - | - | - | Knows Assassin | Knows Morgana |
| Vote counts | Totals only | Totals only | Totals only | Totals only | Totals only |
| Fail votes | Count only | Count only | Count only | Count only | Count only |

## Quick Start

### Prerequisites

```bash
# Clone the repo
git clone https://github.com/haomes/avalon.git
cd avalon

# Install dependencies
pip install openai aiohttp

# Set up environment variables
cp .env.example .env
# Edit .env with your API configuration
```

`.env` configuration:

```bash
# Required: API endpoint (any OpenAI-compatible API)
API_BASE_URL=https://api.openai.com/v1/
API_KEY=your-api-key-here

```

### Running the Game

**Single game** — Run one complete Avalon game:

```bash
source .env
python main.py
```

**Community mode** — Multi-game loop with inter-game learning:

```python
from community.community_runner import CommunityRunner

runner = CommunityRunner()
runner.run_n_games(10)  # Run 10 games
```

**Live dashboard** — Watch games in your browser:

```bash
source .env
python -m server.websocket_server
# Open http://localhost:8080 in your browser
```

**Offline replay** — Open `viewer/index.html` and load a `replay_*.json` file from the `logs/` directory.

### Configuration

Key settings in `config.py`:

| Setting | Description | Default |
|---------|-------------|---------|
| `MODEL_CONFIG` | Models for Good/Evil teams | `dsv32` |
| `LLM_TEMPERATURE` | LLM temperature parameter | `0.8` |
| `MEMORY_COMPRESS_THRESHOLD` | Memory compression trigger | `30` |
| `REFLECTION_ENABLED` | Enable post-game reflection | `True` |
| `PRIVATE_CHAT_ENABLED` | Enable inter-game private chats | `True` |
| `PRIVATE_CHAT_MAX_PAIRS` | Max chat pairs per game | `3` |

## Project Structure

```
avalon/
├── main.py                       # Entry point
├── config.py                     # Global configuration
├── llm_client.py                 # LLM API wrapper
├── models/                       # Data models
│   ├── role.py                   #   Role definitions
│   ├── player.py                 #   Player state
│   └── game_state.py             #   Game state + serialization
├── agents/                       # Agent system
│   ├── memory.py                 #   Memory management (LLM summarization)
│   └── agent.py                  #   Agent decision wrapper
├── engine/                       # Game engine
│   ├── game_engine.py            #   Main engine (flow control)
│   ├── night_phase.py            #   Night phase
│   ├── team_phase.py             #   Team building phase
│   ├── vote_phase.py             #   Discussion + voting
│   ├── mission_phase.py          #   Mission execution
│   └── assassin_phase.py         #   Assassination phase
├── community/                    # Community mode
│   ├── community_runner.py       #   Multi-game runner
│   ├── reflection.py             #   Reflection system
│   ├── private_chat.py           #   Private chat system
│   ├── persistent_agent.py       #   Agent data persistence
│   └── statistics.py             #   Statistics & reporting
├── server/                       # WebSocket server
│   ├── websocket_server.py       #   aiohttp server
│   ├── async_game_runner.py      #   Async game runner
│   ├── event_emitter.py          #   Event broadcaster
│   └── commands.py               #   Frontend command handler
├── viewer/                       # Frontend visualization
│   ├── dashboard.html            #   Live dashboard
│   ├── index.html                #   Offline replay
│   ├── css/                      #   Stylesheets
│   └── js/                       #   JavaScript modules
├── assets/                       # Image assets
├── logs/                         # Game logs (gitignored)
└── data/agents/                  # Agent persistent data (gitignored)
```

## Technical Highlights

- **Layered memory compression** — Recent memories preserved in full; older memories compressed into structured summaries via LLM, with hard-truncation fallback on failure
- **3-layer LLM response parsing** — JSON extraction → keyword fallback → random fallback, guaranteeing uninterrupted gameplay
- **Async state machine** — WebSocket runner supports pause/step/stop with checkpoints at every critical step
- **60+ event types** — Pushed from backend to frontend, driving real-time rendering
- **Incremental strategy revision** — Reflection system performs iterative revisions based on current game behavior + historical strategy, rather than full rewrites
- **Cross-game history persistence** — Dashboard auto-saves game snapshots for cross-game comparison and analysis

## License

MIT
