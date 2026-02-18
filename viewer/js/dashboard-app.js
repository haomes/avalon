/**
 * Dashboard App - Main application wiring WebSocket events to the renderer
 */
class DashboardApp {
  constructor() {
    this.client = new WebSocketClient(this._getWSUrl());
    this.renderer = new DashboardRenderer();
    this.state = 'disconnected';  // disconnected / idle / running / paused
    this.gameConfig = { num_games: 1, mode: 'community', step_mode: false };
    this._currentGame = 0;
    this._totalGames = 0;
  }

  /**
   * Called on DOMContentLoaded
   */
  init() {
    this._bindEventHandlers();
    this._bindUIControls();
    this._bindTabSwitching();

    // Set up connection state callback
    this.client.onStateChange = (connected) => {
      this._updateConnectionStatus(connected);
      if (connected) {
        this.state = 'idle';
        this._updateControlState({ state: 'idle' });
      } else {
        this.state = 'disconnected';
        this._updateControlState({ state: 'disconnected' });
      }
    };

    // Connect
    this.client.connect();
  }

  /**
   * Auto-detect WebSocket URL from window.location
   * @returns {string}
   */
  _getWSUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    const port = window.location.port || '8080';
    return protocol + '//' + host + ':' + port + '/ws';
  }

  /**
   * Register all WebSocket event handlers
   */
  _bindEventHandlers() {
    const c = this.client;
    const r = this.renderer;

    // Game lifecycle
    c.on('game_started', (d) => {
      this.state = 'running';
      this._updateControlState({ state: 'running' });
      r.initGame(d);
    });

    c.on('game_ended', (d) => {
      r.showGameEnd(d);
    });

    // Phase events
    c.on('phase_started', (d) => {
      r.showPhase(d);
    });

    // Agent actions
    c.on('agent_thinking', (d) => {
      r.showThinking(d);
    });

    c.on('agent_thinking_end', (d) => {
      r.hideThinking(d);
    });

    c.on('agent_speech', (d) => {
      r.showSpeech(d);
      r.hideThinking(d);
      const player = r._findPlayer(d.player_id);
      const name = player ? player.player_name : 'Player ' + d.player_id;
      r.appendGameLog(name + ': ' + (d.text || ''), 'speech');
    });

    c.on('agent_vote', (d) => {
      r.showVote(d);
      r.hideThinking(d);
    });

    c.on('agent_mission_vote', (d) => {
      r.showMissionVote(d);
      r.hideThinking(d);
    });

    // Results
    c.on('team_proposed', (d) => {
      r.showTeamProposed(d);
    });

    c.on('vote_result', (d) => {
      r.showVoteResult(d);
    });

    c.on('mission_result', (d) => {
      r.showMissionResult(d);
    });

    c.on('score_update', (d) => {
      r.updateScore(d);
    });

    // Learning & profile events
    c.on('agent_reflection', (d) => {
      r.renderReflection(d);
    });

    c.on('private_chat_start', (d) => {
      r.renderPrivateChat(d);
    });

    c.on('private_chat_message', (d) => {
      r.renderPrivateChat(d);
    });

    c.on('private_chat_end', (d) => {
      r.renderChatAnalysis(d);
    });

    c.on('agent_profile', (d) => {
      r.renderAgentProfile(d);
    });

    c.on('all_agents', (d) => {
      r.renderAllAgents(d);
    });

    c.on('stats_update', (d) => {
      r.renderStats(d);
    });

    // State management
    c.on('state_changed', (d) => {
      this.state = d.state || this.state;
      this._updateControlState(d);
    });

    c.on('runner_paused', (d) => {
      this.state = 'paused';
      this._updateControlState({ state: 'paused' });
    });

    c.on('session_ended', (d) => {
      this.state = 'idle';
      this._updateControlState({ state: 'idle' });
      r.appendGameLog('Session ended. Games: ' + (d.games_completed || 0), 'system');
    });

    c.on('game_stopped', (d) => {
      this.state = 'idle';
      this._updateControlState({ state: 'idle' });
      r.appendGameLog('Game stopped.', 'system');
    });

    // Community game counter
    c.on('community_game_start', (d) => {
      this._currentGame = d.game_num || d.current || 0;
      this._totalGames = d.total || 0;
      this._updateGameCounter();
    });

    // Error handling
    c.on('error', (d) => {
      const msg = d.message || d.error || 'Unknown error';
      r.appendGameLog('ERROR: ' + msg, 'system');
      console.error('[Dashboard] Server error:', msg);
    });
  }

  /**
   * Bind button clicks and keyboard shortcuts
   */
  _bindUIControls() {
    // Start button
    const btnStart = document.getElementById('btn-start');
    if (btnStart) {
      btnStart.addEventListener('click', () => this._startGame());
    }

    // Pause button
    const btnPause = document.getElementById('btn-pause');
    if (btnPause) {
      btnPause.addEventListener('click', () => this._togglePause());
    }

    // Step button
    const btnStep = document.getElementById('btn-step');
    if (btnStep) {
      btnStep.addEventListener('click', () => this._step());
    }

    // Stop button
    const btnStop = document.getElementById('btn-stop');
    if (btnStop) {
      btnStop.addEventListener('click', () => this._stopGame());
    }

    // God mode button
    const btnGod = document.getElementById('btn-god-mode');
    if (btnGod) {
      btnGod.addEventListener('click', () => {
        const isOn = this.renderer.toggleGodMode();
        btnGod.classList.toggle('active', isOn);
      });
    }

    // Config inputs
    const numGamesInput = document.getElementById('input-num-games');
    if (numGamesInput) {
      numGamesInput.addEventListener('change', (e) => {
        this.gameConfig.num_games = parseInt(e.target.value) || 1;
      });
    }

    const stepModeInput = document.getElementById('input-step-mode');
    if (stepModeInput) {
      stepModeInput.addEventListener('change', (e) => {
        this.gameConfig.step_mode = e.target.checked;
      });
    }

    // History toggle (collapsible previous games section)
    const historyToggle = document.getElementById('game-history-toggle');
    if (historyToggle) {
      historyToggle.addEventListener('click', () => {
        const section = document.getElementById('game-history-section');
        const icon = historyToggle.querySelector('.toggle-icon');
        if (section) {
          section.classList.toggle('collapsed');
          if (icon) {
            icon.textContent = section.classList.contains('collapsed') ? '\u25B6' : '\u25BC';
          }
        }
      });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      // Don't capture when typing in inputs
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

      switch (e.code) {
        case 'Space':
          e.preventDefault();
          this._togglePause();
          break;
        case 'KeyS':
          e.preventDefault();
          this._step();
          break;
        case 'KeyG':
          e.preventDefault();
          const btnGodMode = document.getElementById('btn-god-mode');
          if (btnGodMode) btnGodMode.click();
          break;
        case 'Enter':
          if (this.state === 'idle') {
            e.preventDefault();
            this._startGame();
          }
          break;
      }
    });
  }

  /**
   * Bind tab switching for info panels
   */
  _bindTabSwitching() {
    const tabs = document.querySelectorAll('#panel-tabs .tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const panelId = tab.dataset.panel;

        // Deactivate all tabs and panels
        tabs.forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.panel-content').forEach(p => p.classList.remove('active'));

        // Activate selected
        tab.classList.add('active');
        const panel = document.getElementById('panel-' + panelId);
        if (panel) panel.classList.add('active');
      });
    });
  }

  /**
   * Start a new game
   */
  _startGame() {
    if (!this.client.connected) return;
    this.client.send('start_game', this.gameConfig);
  }

  /**
   * Toggle pause/resume
   */
  _togglePause() {
    if (this.state === 'running') {
      this.client.send('pause');
      this.state = 'paused';
      this._updateControlState({ state: 'paused' });
    } else if (this.state === 'paused') {
      this.client.send('resume');
      this.state = 'running';
      this._updateControlState({ state: 'running' });
    }
  }

  /**
   * Step forward one action
   */
  _step() {
    if (!this.client.connected) return;
    this.client.send('step');
  }

  /**
   * Stop the current game
   */
  _stopGame() {
    if (!this.client.connected) return;
    this.client.send('stop');
    this.state = 'idle';
    this._updateControlState({ state: 'idle' });
  }

  /**
   * Enable/disable buttons based on current state
   * @param {object} data - { state }
   */
  _updateControlState(data) {
    const state = data.state || this.state;

    const btnStart = document.getElementById('btn-start');
    const btnPause = document.getElementById('btn-pause');
    const btnStep = document.getElementById('btn-step');
    const btnStop = document.getElementById('btn-stop');

    switch (state) {
      case 'disconnected':
        if (btnStart) btnStart.disabled = true;
        if (btnPause) btnPause.disabled = true;
        if (btnStep) btnStep.disabled = true;
        if (btnStop) btnStop.disabled = true;
        break;
      case 'idle':
        if (btnStart) btnStart.disabled = false;
        if (btnPause) btnPause.disabled = true;
        if (btnStep) btnStep.disabled = true;
        if (btnStop) btnStop.disabled = true;
        break;
      case 'running':
        if (btnStart) btnStart.disabled = true;
        if (btnPause) { btnPause.disabled = false; btnPause.textContent = '\u23F8 PAUSE'; }
        if (btnStep) btnStep.disabled = false;
        if (btnStop) btnStop.disabled = false;
        break;
      case 'paused':
        if (btnStart) btnStart.disabled = true;
        if (btnPause) { btnPause.disabled = false; btnPause.textContent = '\u25B6 RESUME'; }
        if (btnStep) btnStep.disabled = false;
        if (btnStop) btnStop.disabled = false;
        break;
    }
  }

  /**
   * Update connection status indicator
   * @param {boolean} connected
   */
  _updateConnectionStatus(connected) {
    const indicator = document.getElementById('connection-status');
    if (!indicator) return;

    if (connected) {
      indicator.textContent = '\u25CF ONLINE';
      indicator.className = 'status-indicator connected';
    } else {
      indicator.textContent = '\u25CF OFFLINE';
      indicator.className = 'status-indicator disconnected';
    }
  }

  /**
   * Update game counter display
   */
  _updateGameCounter() {
    const counter = document.getElementById('game-counter');
    if (counter) {
      if (this._totalGames > 0) {
        counter.textContent = 'Game ' + this._currentGame + '/' + this._totalGames;
      } else {
        counter.textContent = '-';
      }
    }
  }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  window.app = new DashboardApp();
  window.app.init();
});
