/**
 * Dashboard Renderer - Renders the live game dashboard
 * Standalone class (does NOT extend UIRenderer).
 * Depends on globals from pixel-art.js: CHARACTER_IMAGES
 */
class DashboardRenderer {
  constructor() {
    this.players = [];          // player data from game_started event
    this.godMode = false;
    this.currentRound = 0;
    this.goodWins = 0;
    this.evilWins = 0;

    // Cross-game history persistence
    this.gameHistory = [];        // array of completed game snapshots
    this.currentGameId = 0;       // increments each game
    this._currentGameData = null; // tracks in-progress game data
    this._missionResults = [];    // mission results for current game
    this._speechTimer = null;      // auto-dismiss timer for speech bubbles
  }

  // ================================================================
  //  Game Initialization
  // ================================================================

  /**
   * Initialize a new game
   * @param {object} data - { players: [{player_id, player_name, role_id, role_name_cn, team}] }
   */
  initGame(data) {
    // Save snapshot of previous game before resetting (if one was in progress)
    this._saveCurrentGameSnapshot();

    this.players = data.players || [];
    this.currentRound = 0;
    this.goodWins = 0;
    this.evilWins = 0;

    // Start tracking new game
    this.currentGameId++;
    this._missionResults = [];
    this._currentGameData = {
      gameId: this.currentGameId,
      startTime: new Date().toISOString(),
      players: JSON.parse(JSON.stringify(this.players)),
      winner: null,
      reason: '',
      missions: [],
      endTime: null,
    };

    // Reset displays
    this._setTextContent('round-display', '-');
    this._setTextContent('phase-display', 'STARTING');
    this._setTextContent('good-score', '0');
    this._setTextContent('evil-score', '0');
    this._setTextContent('table-text', 'AVALON');

    // Clear game log (but NOT learning-content — preserve cross-game learning data)
    this._clearElement('game-log-content');

    // Add game divider to learning tab for games after the first
    if (this.currentGameId > 1) {
      this._addGameDivider('learning-content', this.currentGameId);
    }

    // Show history section if we have previous games
    if (this.gameHistory.length > 0) {
      const historySection = document.getElementById('game-history-section');
      if (historySection) historySection.style.display = '';
    }

    // Create player cards
    const playerArea = document.getElementById('player-area');
    // Remove old player cards
    playerArea.querySelectorAll('.player-card').forEach(el => el.remove());

    // Create 6 player cards in circular layout
    const positions = [
      { cls: 'pos-top', idx: 0 },
      { cls: 'pos-top-right', idx: 1 },
      { cls: 'pos-bottom-right', idx: 2 },
      { cls: 'pos-bottom', idx: 3 },
      { cls: 'pos-bottom-left', idx: 4 },
      { cls: 'pos-top-left', idx: 5 },
    ];

    this.players.forEach((player, i) => {
      if (i >= 6) return;
      const pos = positions[i];
      const card = this._createPlayerCard(player, pos);
      playerArea.appendChild(card);
    });

    this.appendGameLog('Game started with ' + this.players.length + ' players', 'system');
  }

  // ================================================================
  //  Phase Display
  // ================================================================

  /**
   * Update round-table center text and info bar
   * @param {object} data - { phase, round, description }
   */
  showPhase(data) {
    const phase = data.phase || '';
    const round = data.round || this.currentRound;
    if (data.round) this.currentRound = data.round;

    // Update info bar
    this._setTextContent('round-display', round > 0 ? round + '/5' : '-');
    this._setTextContent('phase-display', this._getPhaseLabel(phase));

    // Update table center
    const tableText = document.getElementById('table-text');
    if (tableText) {
      if (round > 0) {
        tableText.textContent = 'ROUND ' + round;
      } else {
        tableText.textContent = this._getPhaseLabel(phase);
      }
    }

    this.appendGameLog('[Phase] ' + (data.description || phase), 'system');
  }

  // ================================================================
  //  Agent Actions
  // ================================================================

  /**
   * Show thinking overlay on a player card
   * @param {object} data - { player_id, action }
   */
  showThinking(data) {
    const card = this._getPlayerCard(data.player_id);
    if (!card) return;

    // Remove any existing thinking overlay
    card.querySelectorAll('.thinking-overlay').forEach(el => el.remove());

    const overlay = document.createElement('div');
    overlay.className = 'thinking-overlay';
    overlay.innerHTML = '<span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span>';
    if (data.action) {
      overlay.innerHTML += '<span class="thinking-action">' + this._escapeHtml(data.action) + '</span>';
    }
    card.querySelector('.player-avatar-box').appendChild(overlay);
  }

  /**
   * Remove thinking overlay from a player card
   * @param {object} data - { player_id }
   */
  hideThinking(data) {
    const card = this._getPlayerCard(data.player_id);
    if (!card) return;
    card.querySelectorAll('.thinking-overlay').forEach(el => el.remove());
  }

  /**
   * Show speech bubble on a player card
   * @param {object} data - { player_id, text }
   */
  showSpeech(data) {
    const card = this._getPlayerCard(data.player_id);
    if (!card) return;

    const bubble = card.querySelector('.db-speech-bubble');
    if (!bubble) return;

    // Clear all other speech bubbles and speaker highlights first
    this.clearSpeeches();

    const player = this._findPlayer(data.player_id);
    const name = player ? player.player_name : 'Player ' + data.player_id;

    // Truncate long text for bubble display (full text goes to game log)
    let displayText = data.text || '';
    if (displayText.length > 120) {
      displayText = displayText.substring(0, 120) + '...';
    }

    bubble.innerHTML =
      '<div class="bubble-speaker">' + this._escapeHtml(name) + ':</div>' +
      '<div class="bubble-text">' + this._escapeHtml(displayText) + '</div>';
    bubble.classList.remove('fading');
    bubble.classList.add('visible');

    // Highlight the speaking player
    card.classList.add('speaking');

    // Auto-dismiss after 8 seconds
    if (this._speechTimer) clearTimeout(this._speechTimer);
    this._speechTimer = setTimeout(() => {
      bubble.classList.add('fading');
      setTimeout(() => {
        bubble.classList.remove('visible', 'fading');
        bubble.innerHTML = '';
        card.classList.remove('speaking');
      }, 300);
    }, 8000);
  }

  /**
   * Remove all speech bubbles and speaker highlights
   */
  clearSpeeches() {
    if (this._speechTimer) {
      clearTimeout(this._speechTimer);
      this._speechTimer = null;
    }
    document.querySelectorAll('.db-speech-bubble.visible').forEach(el => {
      el.classList.remove('visible', 'fading');
      el.innerHTML = '';
    });
    document.querySelectorAll('.player-card.speaking').forEach(el => {
      el.classList.remove('speaking');
    });
  }

  /**
   * Show vote badge on a player card
   * @param {object} data - { player_id, approved }
   */
  showVote(data) {
    const card = this._getPlayerCard(data.player_id);
    if (!card) return;

    const badgesEl = card.querySelector('.player-badges');
    if (!badgesEl) return;

    // Remove old vote badges
    badgesEl.querySelectorAll('.badge-approve, .badge-reject').forEach(el => el.remove());

    const badge = this._createBadge(
      data.approved ? 'APPROVE' : 'REJECT',
      data.approved ? 'approve' : 'reject'
    );
    badgesEl.appendChild(badge);
  }

  /**
   * Show mission vote badge on a player card
   * @param {object} data - { player_id, success }
   */
  showMissionVote(data) {
    const card = this._getPlayerCard(data.player_id);
    if (!card) return;

    const badgesEl = card.querySelector('.player-badges');
    if (!badgesEl) return;

    // Remove old mission vote badges
    badgesEl.querySelectorAll('.badge-success, .badge-fail').forEach(el => el.remove());

    const badge = this._createBadge(
      data.success ? 'SUCCESS' : 'FAIL',
      data.success ? 'success' : 'fail'
    );
    badgesEl.appendChild(badge);
  }

  // ================================================================
  //  Results
  // ================================================================

  /**
   * Highlight team members when a team is proposed
   * @param {object} data - { leader_id, team, round }
   */
  showTeamProposed(data) {
    if (data.round) this.currentRound = data.round;

    // Clear all badges first
    this._clearAllBadges();

    // Add leader badge
    const leaderCard = this._getPlayerCard(data.leader_id);
    if (leaderCard) {
      leaderCard.querySelector('.player-badges').appendChild(
        this._createBadge('LEADER', 'leader')
      );
    }

    // Add team badges
    (data.team || []).forEach(pid => {
      const card = this._getPlayerCard(pid);
      if (card) {
        card.querySelector('.player-badges').appendChild(
          this._createBadge('TEAM', 'team')
        );
        card.classList.add('on-team');
      }
    });

    this.appendGameLog(
      'Round ' + (data.round || this.currentRound) + ': Team proposed by Player ' +
      data.leader_id + ' - Members: [' + (data.team || []).join(', ') + ']',
      'system'
    );
  }

  /**
   * Show vote result summary
   * @param {object} data - { approved, votes, round }
   */
  showVoteResult(data) {
    // Clear old vote badges
    document.querySelectorAll('.player-card .badge-approve, .player-card .badge-reject').forEach(el => el.remove());

    // Show individual votes
    if (data.votes) {
      Object.entries(data.votes).forEach(([pid, approved]) => {
        const card = this._getPlayerCard(parseInt(pid));
        if (!card) return;
        const badgesEl = card.querySelector('.player-badges');
        if (!badgesEl) return;
        badgesEl.appendChild(
          this._createBadge(approved ? 'APPROVE' : 'REJECT', approved ? 'approve' : 'reject')
        );
      });
    }

    const resultText = data.approved ? 'APPROVED' : 'REJECTED';
    this.appendGameLog('Vote result: ' + resultText, data.approved ? 'result' : 'system');
  }

  /**
   * Show mission result
   * @param {object} data - { success, fail_count, round }
   */
  showMissionResult(data) {
    const resultText = data.success ? 'SUCCESS' : 'FAILED';
    const failInfo = data.fail_count > 0 ? ' (' + data.fail_count + ' fail votes)' : '';

    this.appendGameLog(
      'Mission ' + (data.round || this.currentRound) + ': ' + resultText + failInfo,
      data.success ? 'result' : 'system'
    );

    // Track mission result for history
    const missionRecord = {
      round: data.round || this.currentRound,
      success: !!data.success,
      failCount: data.fail_count || 0,
    };
    this._missionResults.push(missionRecord);
    if (this._currentGameData) {
      this._currentGameData.missions = this._missionResults.slice();
    }

    // Update timeline marker
    this.updateTimeline(data.round || this.currentRound, data.success ? 'success' : 'fail');
  }

  /**
   * Update score display
   * @param {object} data - { good_wins, evil_wins }
   */
  updateScore(data) {
    this.goodWins = data.good_wins !== undefined ? data.good_wins : this.goodWins;
    this.evilWins = data.evil_wins !== undefined ? data.evil_wins : this.evilWins;

    this._setTextContent('good-score', String(this.goodWins));
    this._setTextContent('evil-score', String(this.evilWins));
  }

  /**
   * Show final game result
   * @param {object} data - { winner, reason, players }
   */
  showGameEnd(data) {
    // Record final result in current game data for history
    if (this._currentGameData) {
      this._currentGameData.winner = data.winner || null;
      this._currentGameData.reason = data.reason || '';
      this._currentGameData.endTime = new Date().toISOString();
      if (data.players) {
        this._currentGameData.finalPlayers = JSON.parse(JSON.stringify(data.players));
      }
    }

    this._setTextContent('phase-display', 'GAME OVER');
    const tableText = document.getElementById('table-text');
    if (tableText) {
      tableText.textContent = data.winner === 'good' ? 'GOOD\nWINS' : 'EVIL\nWINS';
      tableText.className = data.winner === 'good' ? 'winner-good' : 'winner-evil';
    }

    // Clear badges and show final roles
    this._clearAllBadges();
    if (data.players) {
      data.players.forEach(p => {
        const card = this._getPlayerCard(p.player_id);
        if (!card) return;

        // Show true role
        const roleEl = card.querySelector('.player-role');
        if (roleEl) {
          roleEl.textContent = p.role_name_cn || p.role_id;
          roleEl.style.color = p.team === 'good' ? 'var(--good-primary)' : 'var(--evil-primary)';
        }

        // Update avatar
        const avatarImg = card.querySelector('.player-avatar-img');
        if (avatarImg) {
          avatarImg.src = this._getRoleImage(p.role_id);
        }

        // Add team glow
        const avatarBox = card.querySelector('.player-avatar-box');
        if (avatarBox) {
          avatarBox.classList.add(p.team === 'good' ? 'glow-good' : 'glow-evil');
        }
      });
    }

    const reason = data.reason || '';
    this.appendGameLog('GAME OVER - ' + (data.winner === 'good' ? 'Good' : 'Evil') + ' wins! ' + reason, 'result');
  }

  // ================================================================
  //  Info Panels
  // ================================================================

  /**
   * Render a single agent profile in the AGENTS tab
   * @param {object} data - { player_id, player_name, role_id, role_name_cn, team,
   *                          stats: {games, wins, roles}, strategy, social_relations, lessons }
   */
  renderAgentProfile(data) {
    const container = document.getElementById('agents-content');
    if (!container) return;

    // Check if profile card already exists
    let card = container.querySelector(`[data-agent-id="${data.player_id}"]`);
    if (card) {
      card.remove();
    }

    card = document.createElement('div');
    card.className = 'agent-profile-card';
    card.dataset.agentId = data.player_id;

    const team = data.team || 'unknown';
    const teamClass = team === 'good' ? 'team-good' : team === 'evil' ? 'team-evil' : '';

    let statsHtml = '';
    if (data.stats) {
      statsHtml = '<div class="agent-stats">';
      if (data.stats.games !== undefined) {
        statsHtml += '<div class="stat-row"><span class="stat-label">Games</span><span class="stat-value">' + data.stats.games + '</span></div>';
      }
      if (data.stats.wins !== undefined) {
        statsHtml += '<div class="stat-row"><span class="stat-label">Wins</span><span class="stat-value">' + data.stats.wins + '</span></div>';
      }
      if (data.stats.roles) {
        statsHtml += '<div class="stat-row"><span class="stat-label">Roles</span><span class="stat-value">' + this._escapeHtml(data.stats.roles) + '</span></div>';
      }
      statsHtml += '</div>';
    }

    let relationsHtml = '';
    if (data.social_relations && data.social_relations.length > 0) {
      relationsHtml = '<div class="agent-relations"><div class="section-title">Social Relations</div>' +
        '<div class="relation-legend">' +
          '<span class="legend-item"><span class="legend-dot trust-dot"></span>信任</span>' +
          '<span class="legend-item"><span class="legend-dot friend-dot"></span>友好</span>' +
        '</div>';
      data.social_relations.forEach(rel => {
        const trustPct = Math.max(0, Math.min(100, (rel.trust || 0) * 100));
        const friendPct = Math.max(0, Math.min(100, (rel.friendliness || 0) * 100));
        relationsHtml +=
          '<div class="relation-row">' +
            '<span class="relation-name">' + this._escapeHtml(rel.name || 'P' + rel.player_id) + '</span>' +
            '<div class="relation-bars">' +
              '<div class="trust-bar-container" title="信任 ' + trustPct.toFixed(0) + '%">' +
                '<div class="trust-bar" style="width: ' + trustPct + '%"></div>' +
              '</div>' +
              '<div class="friend-bar-container" title="友好 ' + friendPct.toFixed(0) + '%">' +
                '<div class="friend-bar" style="width: ' + friendPct + '%"></div>' +
              '</div>' +
            '</div>' +
          '</div>';
      });
      relationsHtml += '</div>';
    }

    let lessonsHtml = '';
    if (data.lessons && data.lessons.length > 0) {
      lessonsHtml = '<div class="agent-lessons"><div class="section-title">Recent Lessons</div>';
      data.lessons.slice(0, 3).forEach(lesson => {
        lessonsHtml += '<div class="lesson-item">' + this._escapeHtml(lesson) + '</div>';
      });
      lessonsHtml += '</div>';
    }

    card.innerHTML =
      '<div class="agent-header ' + teamClass + '">' +
        '<img src="' + this._getRoleImage(data.role_id) + '" alt="avatar" class="agent-avatar">' +
        '<div class="agent-info">' +
          '<div class="agent-name">' + this._escapeHtml(data.player_name || 'Player ' + data.player_id) + '</div>' +
          '<div class="agent-role">' + this._escapeHtml(data.role_name_cn || data.role_id || '???') + '</div>' +
        '</div>' +
      '</div>' +
      statsHtml +
      (data.strategy ? '<div class="agent-strategy"><div class="section-title">Strategy</div><div class="strategy-text">' + this._escapeHtml(data.strategy) + '</div></div>' : '') +
      relationsHtml +
      lessonsHtml;

    container.appendChild(card);
  }

  /**
   * Render all 6 agent profile cards
   * @param {object} data - { agents: [agentData, ...] }
   */
  renderAllAgents(data) {
    const container = document.getElementById('agents-content');
    if (container) container.innerHTML = '';

    (data.agents || []).forEach(agent => {
      this.renderAgentProfile(agent);
    });
  }

  /**
   * Append a reflection result to the LEARNING tab
   * @param {object} data - { player_id, player_name, lesson, strategy_update }
   */
  renderReflection(data) {
    const container = document.getElementById('learning-content');
    if (!container) return;

    const entry = document.createElement('div');
    entry.className = 'reflection-entry';

    entry.innerHTML =
      '<div class="reflection-header">' +
        '<span class="reflection-name">' + this._escapeHtml(data.player_name || 'Player ' + data.player_id) + '</span>' +
        '<span class="game-badge">Game #' + this.currentGameId + '</span>' +
        '<span class="reflection-tag">REFLECTION</span>' +
      '</div>' +
      (data.lesson ? '<div class="reflection-lesson">' + this._escapeHtml(data.lesson) + '</div>' : '') +
      (data.strategy_update ? '<div class="reflection-strategy">Strategy: ' + this._escapeHtml(data.strategy_update) + '</div>' : '');

    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
  }

  /**
   * Append a private chat message to the LEARNING tab
   * @param {object} data - { from_id, from_name, to_id, to_name, message }
   */
  renderPrivateChat(data) {
    const container = document.getElementById('learning-content');
    if (!container) return;

    const entry = document.createElement('div');
    entry.className = 'chat-entry';

    entry.innerHTML =
      '<div class="chat-header">' +
        '<span class="chat-from">' + this._escapeHtml(data.from_name || 'P' + data.from_id) + '</span>' +
        '<span class="chat-arrow">&rarr;</span>' +
        '<span class="chat-to">' + this._escapeHtml(data.to_name || 'P' + data.to_id) + '</span>' +
        '<span class="game-badge">Game #' + this.currentGameId + '</span>' +
        '<span class="chat-tag">CHAT</span>' +
      '</div>' +
      '<div class="chat-message">' + this._escapeHtml(data.message || '') + '</div>';

    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
  }

  /**
   * Show chat analysis result
   * @param {object} data - { player_a_name, player_b_name, summary, analysis }
   */
  renderChatAnalysis(data) {
    const container = document.getElementById('learning-content');
    if (!container) return;

    const entry = document.createElement('div');
    entry.className = 'analysis-entry';

    const participants = (data.player_a_name && data.player_b_name)
      ? data.player_a_name + ' & ' + data.player_b_name
      : '';
    const analysisText = data.analysis || data.summary || '';

    entry.innerHTML =
      '<div class="analysis-header">' +
        (participants ? '<span class="analysis-participants">' + this._escapeHtml(participants) + '</span>' : '') +
        '<span class="game-badge">Game #' + this.currentGameId + '</span>' +
        '<span class="analysis-tag">CHAT SUMMARY</span>' +
      '</div>' +
      '<div class="analysis-text">' + this._escapeHtml(analysisText) + '</div>';

    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
  }

  /**
   * Render community statistics in the STATS tab
   * @param {object} data - { summary, player_rankings, recent_games }
   */
  renderStats(data) {
    // --- Session Overview ---
    const cumulative = document.getElementById('cumulative-stats-content');
    if (cumulative && data.summary) {
      const s = data.summary;
      cumulative.innerHTML =
        this._statsRow('总场次', s.total_games) +
        this._statsRow('正义胜率', s.good_win_rate) +
        this._statsRow('邪恶胜率', s.evil_win_rate) +
        this._statsRow('刺杀成功率', s.assassination_rate);
    }

    // --- Player Win Rates ---
    const winRate = document.getElementById('win-rate-content');
    if (winRate && data.player_rankings && data.player_rankings.length > 0) {
      let html = '';
      data.player_rankings.forEach(p => {
        const name = p.player || '';
        const displayName = name.replace(/^player_/, '玩家');
        html +=
          '<div class="ranking-row">' +
            '<span class="ranking-name">' + this._escapeHtml(displayName) + '</span>' +
            '<span class="ranking-detail">' +
              '<span class="ranking-games">' + (p.games || 0) + '局</span>' +
              '<span class="ranking-winrate">' + this._escapeHtml(p.win_rate || 'N/A') + '</span>' +
            '</span>' +
          '</div>';
      });
      winRate.innerHTML = html;
    }

    // --- Recent Games ---
    const statsContent = document.getElementById('stats-content');
    if (statsContent && data.recent_games && data.recent_games.length > 0) {
      let html = '<div class="section-title">Recent Games</div>';
      data.recent_games.forEach((g, i) => {
        const winnerClass = g.winner === 'good' ? 'winner-good' : 'winner-evil';
        const winnerText = g.winner === 'good' ? '正义胜' : '邪恶胜';
        html +=
          '<div class="recent-game-row">' +
            '<span class="recent-game-id">#' + (i + 1) + '</span>' +
            '<span class="recent-game-winner ' + winnerClass + '">' + winnerText + '</span>' +
            '<span class="recent-game-reason">' + this._escapeHtml(g.end_reason || '') + '</span>' +
          '</div>';
      });
      statsContent.innerHTML = html;
    }
  }

  /**
   * Helper: build a single stats row HTML string
   */
  _statsRow(label, value) {
    return '<div class="stats-row">' +
      '<span class="stats-label">' + this._escapeHtml(String(label)) + '</span>' +
      '<span class="stats-value">' + this._escapeHtml(String(value != null ? value : '—')) + '</span>' +
    '</div>';
  }

  // ================================================================
  //  Game Detail Panel (GAME tab)
  // ================================================================

  /**
   * Append a line to the GAME tab log
   * @param {string} text - Log text
   * @param {string} type - 'system' | 'speech' | 'vote' | 'result'
   */
  appendGameLog(text, type) {
    const container = document.getElementById('game-log-content');
    if (!container) return;

    const line = document.createElement('div');
    line.className = 'log-line log-' + (type || 'system');

    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    line.innerHTML =
      '<span class="log-time">' + time + '</span>' +
      '<span class="log-text">' + this._escapeHtml(text) + '</span>';

    container.appendChild(line);

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;
  }

  // ================================================================
  //  Timeline
  // ================================================================

  /**
   * Update timeline markers
   * @param {number} roundNum - Round number
   * @param {string} result - 'success' | 'fail' | 'rejected'
   */
  updateTimeline(roundNum, result) {
    // Find or create timeline marker for this round
    const timeline = document.getElementById('info-bar');
    if (!timeline) return;

    // Update round display
    this._setTextContent('round-display', roundNum + '/5');
  }

  // ================================================================
  //  God Mode
  // ================================================================

  /**
   * Toggle god mode - show/hide secret info
   */
  toggleGodMode() {
    this.godMode = !this.godMode;
    document.body.classList.toggle('god-mode', this.godMode);

    // Update all player cards
    this.players.forEach(player => {
      const card = this._getPlayerCard(player.player_id);
      if (!card) return;

      const roleEl = card.querySelector('.player-role');
      const avatarImg = card.querySelector('.player-avatar-img');
      const avatarBox = card.querySelector('.player-avatar-box');

      if (this.godMode) {
        // Show role info
        if (roleEl) {
          roleEl.textContent = player.role_name_cn || player.role_id;
          roleEl.style.color = player.team === 'good' ? 'var(--good-primary)' : 'var(--evil-primary)';
        }
        if (avatarImg) {
          avatarImg.src = this._getRoleImage(player.role_id);
        }
        if (avatarBox) {
          avatarBox.classList.add(player.team === 'good' ? 'glow-good' : 'glow-evil');
        }
        card.dataset.team = player.team;
      } else {
        // Hide role info
        if (roleEl) {
          roleEl.textContent = '???';
          roleEl.style.color = '';
        }
        if (avatarImg) {
          avatarImg.src = CHARACTER_IMAGES.unknown;
        }
        if (avatarBox) {
          avatarBox.classList.remove('glow-good', 'glow-evil');
        }
        card.dataset.team = '';
      }
    });

    return this.godMode;
  }

  // ================================================================
  //  Utility / Private Methods
  // ================================================================

  /**
   * Get DOM element for a player card
   * @param {number} pid - Player ID
   * @returns {HTMLElement|null}
   */
  _getPlayerCard(pid) {
    return document.querySelector('.player-card[data-player-id="' + pid + '"]');
  }

  /**
   * Create a player card HTML element
   * @param {object} player - Player data
   * @param {object} pos - { cls, idx }
   * @returns {HTMLElement}
   */
  _createPlayerCard(player, pos) {
    const card = document.createElement('div');
    card.className = 'player-card ' + pos.cls;
    card.dataset.playerId = player.player_id;
    card.dataset.pos = pos.idx;
    card.dataset.team = this.godMode ? (player.team || '') : '';

    const imgSrc = this.godMode
      ? this._getRoleImage(player.role_id)
      : CHARACTER_IMAGES.unknown;

    const roleText = this.godMode
      ? (player.role_name_cn || player.role_id || '???')
      : '???';

    card.innerHTML =
      '<div class="player-avatar-box' + (this.godMode ? (player.team === 'good' ? ' glow-good' : player.team === 'evil' ? ' glow-evil' : '') : '') + '">' +
        '<img src="' + imgSrc + '" alt="avatar" class="player-avatar-img">' +
      '</div>' +
      '<div class="player-name">' + this._escapeHtml(player.player_name) + '</div>' +
      '<div class="player-role"' + (this.godMode ? ' style="color: ' + (player.team === 'good' ? 'var(--good-primary)' : 'var(--evil-primary)') + '"' : '') + '>' + this._escapeHtml(roleText) + '</div>' +
      '<div class="player-badges"></div>' +
      '<div class="db-speech-bubble"></div>';

    return card;
  }

  /**
   * Map position index to CSS class
   * @param {number} idx - 0-5
   * @returns {string}
   */
  _getPositionClass(idx) {
    const classes = ['pos-top', 'pos-top-right', 'pos-bottom-right', 'pos-bottom', 'pos-bottom-left', 'pos-top-left'];
    return classes[idx] || 'pos-top';
  }

  /**
   * Get pixel art SVG data URI for a role
   * @param {string} roleId
   * @returns {string}
   */
  _getRoleImage(roleId) {
    return CHARACTER_IMAGES[roleId] || CHARACTER_IMAGES.unknown;
  }

  /**
   * Create a badge element
   * @param {string} text - Badge text
   * @param {string} type - Badge type (leader/team/approve/reject/success/fail/speaking/target)
   * @returns {HTMLElement}
   */
  _createBadge(text, type) {
    const span = document.createElement('span');
    span.className = 'badge badge-' + type;
    span.textContent = text;
    return span;
  }

  /**
   * Find player data by ID
   * @param {number} pid
   * @returns {object|null}
   */
  _findPlayer(pid) {
    return this.players.find(p => p.player_id === pid) || null;
  }

  /**
   * Clear all badges from all player cards
   */
  _clearAllBadges() {
    document.querySelectorAll('.player-card .player-badges').forEach(el => {
      el.innerHTML = '';
    });
    document.querySelectorAll('.player-card.on-team').forEach(el => {
      el.classList.remove('on-team');
    });
  }

  /**
   * Get a human-readable phase label
   * @param {string} phase
   * @returns {string}
   */
  _getPhaseLabel(phase) {
    const labels = {
      'night': 'NIGHT',
      'team_proposal': 'TEAM',
      'discussion': 'DISCUSS',
      'speech': 'DISCUSS',
      'vote': 'VOTE',
      'team_vote': 'VOTE',
      'mission': 'MISSION',
      'assassin': 'ASSASSIN',
      'reflection': 'REFLECT',
      'private_chat': 'CHAT',
      'game_end': 'GAME OVER',
    };
    return labels[phase] || phase.toUpperCase();
  }

  /**
   * Set text content of an element by ID
   * @param {string} id
   * @param {string} text
   */
  _setTextContent(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  /**
   * Clear an element's content by ID
   * @param {string} id
   */
  _clearElement(id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  }

  /**
   * Escape HTML special characters
   * @param {string} text
   * @returns {string}
   */
  _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // ================================================================
  //  Game Dividers (Learning Tab)
  // ================================================================

  /**
   * Add a visual divider to a container to separate content from different games
   * @param {string} containerId - DOM element ID
   * @param {number} gameNum - Game number to display
   */
  _addGameDivider(containerId, gameNum) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const divider = document.createElement('div');
    divider.className = 'game-divider';
    divider.innerHTML =
      '<div class="game-divider-line"></div>' +
      '<span class="game-divider-label">Game #' + gameNum + '</span>' +
      '<div class="game-divider-line"></div>';
    container.appendChild(divider);
  }

  // ================================================================
  //  Cross-Game History Persistence
  // ================================================================

  /**
   * Save a snapshot of the current game to history (called before initGame resets state).
   * Only saves if a game was actually in progress with recorded data.
   */
  _saveCurrentGameSnapshot() {
    if (!this._currentGameData) return;
    // Only save if the game actually started (has players)
    if (!this._currentGameData.players || this._currentGameData.players.length === 0) return;

    // If game ended normally, endTime is already set; otherwise mark it now
    if (!this._currentGameData.endTime) {
      this._currentGameData.endTime = new Date().toISOString();
    }

    // Freeze mission results
    this._currentGameData.missions = this._missionResults.slice();

    // Push to history
    this.gameHistory.push(Object.freeze(this._currentGameData));

    // Render updated history panel
    this.renderGameHistory();

    // Clear current tracking
    this._currentGameData = null;
    this._missionResults = [];
  }

  /**
   * Render the full game history list in the history section.
   * Creates collapsible cards for each completed game.
   */
  renderGameHistory() {
    const container = document.getElementById('game-history-list');
    if (!container) return;

    container.innerHTML = '';

    if (this.gameHistory.length === 0) {
      container.innerHTML = '<div class="empty-state">No previous games yet</div>';
      return;
    }

    // Render in reverse chronological order (most recent first)
    for (let i = this.gameHistory.length - 1; i >= 0; i--) {
      const entry = this._renderHistoryEntry(this.gameHistory[i], i + 1);
      container.appendChild(entry);
    }

    // Update the toggle badge count
    const badge = document.getElementById('history-count');
    if (badge) {
      badge.textContent = String(this.gameHistory.length);
      badge.style.display = this.gameHistory.length > 0 ? 'inline-block' : 'none';
    }
  }

  /**
   * Render a single history entry card.
   * @param {object} game - Frozen game snapshot
   * @param {number} displayNum - Display number (1-indexed)
   * @returns {HTMLElement}
   */
  _renderHistoryEntry(game, displayNum) {
    const card = document.createElement('div');
    card.className = 'history-card';
    if (game.winner) {
      card.classList.add('history-' + game.winner);
    }

    // Compute mission summary icons
    const missionIcons = (game.missions || []).map(m =>
      '<span class="history-mission ' + (m.success ? 'mission-success' : 'mission-fail') + '">' +
        (m.success ? '\u2714' : '\u2718') +
      '</span>'
    ).join('');

    // Compute duration string
    let durationStr = '';
    if (game.startTime && game.endTime) {
      const ms = new Date(game.endTime) - new Date(game.startTime);
      const secs = Math.floor(ms / 1000);
      const mins = Math.floor(secs / 60);
      const remSecs = secs % 60;
      durationStr = mins + ':' + String(remSecs).padStart(2, '0');
    }

    // Winner label
    const winnerLabel = game.winner === 'good' ? 'Good Wins' : game.winner === 'evil' ? 'Evil Wins' : 'Incomplete';
    const winnerClass = game.winner === 'good' ? 'winner-good-text' : game.winner === 'evil' ? 'winner-evil-text' : 'winner-unknown-text';

    card.innerHTML =
      '<div class="history-card-header">' +
        '<span class="history-game-num">Game #' + displayNum + '</span>' +
        '<span class="history-winner ' + winnerClass + '">' + winnerLabel + '</span>' +
        (durationStr ? '<span class="history-duration">' + durationStr + '</span>' : '') +
      '</div>' +
      '<div class="history-card-body">' +
        '<div class="history-missions">' + (missionIcons || '<span class="empty-state">No missions</span>') + '</div>' +
        (game.reason ? '<div class="history-reason">' + this._escapeHtml(game.reason) + '</div>' : '') +
      '</div>';

    return card;
  }

  /**
   * Get the full game history array (read-only access).
   * @returns {Array} Array of frozen game snapshot objects
   */
  getGameHistory() {
    return this.gameHistory.slice();
  }

  /**
   * Clear all game history. Used when starting a fresh session.
   */
  clearHistory() {
    this.gameHistory = [];
    this.currentGameId = 0;
    this._currentGameData = null;
    this._missionResults = [];

    // Clear the history display
    const container = document.getElementById('game-history-list');
    if (container) {
      container.innerHTML = '<div class="empty-state">No previous games yet</div>';
    }

    // Reset badge
    const badge = document.getElementById('history-count');
    if (badge) {
      badge.textContent = '0';
      badge.style.display = 'none';
    }
  }
}
