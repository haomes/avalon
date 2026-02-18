/**
 * UI Renderer - Renders each phase into the DOM
 * Depends on globals from pixel-art.js: createPixelSVG, P, PIXEL_ART, CHARACTER_IMAGES
 */

const ROLE_VISUALS = {
  merlin: { label: '梅林', cssClass: 'role-merlin' },
  percival: { label: '派西维尔', cssClass: 'role-percival' },
  loyal_servant_1: { label: '忠臣', cssClass: 'role-servant' },
  loyal_servant_2: { label: '忠臣', cssClass: 'role-servant' },
  morgana: { label: '莫甘娜', cssClass: 'role-morgana' },
  assassin: { label: '刺客', cssClass: 'role-assassin' },
  unknown: { label: '???', cssClass: 'role-unknown' },
};

class UIRenderer {
  constructor(engine) {
    this.engine = engine;
    this.godMode = false;

    // Cache DOM elements
    this.els = {
      playerCircle: document.getElementById('player-circle'),
      roundTable: document.getElementById('round-table'),
      tablePhaseLabel: document.getElementById('table-phase-label'),
      phaseLabel: document.getElementById('phase-label'),
      detailContent: document.getElementById('detail-content'),
      roundInfo: document.getElementById('round-info'),
      scoreInfo: document.getElementById('score-info'),
      missionSizeInfo: document.getElementById('mission-size-info'),
      timelineRounds: document.getElementById('timeline-rounds'),
    };
  }

  setGodMode(enabled) {
    this.godMode = enabled;
    document.body.classList.toggle('god-mode', enabled);
    // Re-render current step to update visibility
    this.render(this.engine.getCurrentStep());
  }

  /**
   * Full render of the current step
   */
  render(step) {
    this._renderPlayerCards(step);
    this._renderPhaseLabel(step);
    this._renderInfoBar(step);
    this._renderDetailPanel(step);
    this._renderTimeline(step);
  }

  /**
   * Build initial player cards (called once on load)
   */
  initPlayerCards() {
    this.els.playerCircle.innerHTML = '';

    for (let i = 0; i < this.engine.data.players.length; i++) {
      const player = this.engine.data.players[i];
      const card = document.createElement('div');
      card.className = 'player-card';
      card.dataset.playerId = player.player_id;
      card.dataset.pos = i;
      card.dataset.team = player.team;

      const imgSrc = this.godMode
        ? (CHARACTER_IMAGES[player.role_id] || CHARACTER_IMAGES.unknown)
        : CHARACTER_IMAGES.unknown;

      card.innerHTML = `
        <div class="player-avatar-box">
          <img src="${imgSrc}" alt="avatar" class="player-avatar-img">
        </div>
        <div class="player-name">${player.player_name}</div>
        <div class="player-role">${this.godMode ? player.role_name_cn : '???'}</div>
        <div class="player-badges"></div>
        <div class="player-speech-bubble"></div>
      `;

      this.els.playerCircle.appendChild(card);
    }
  }

  _renderPlayerCards(step) {
    const cards = this.els.playerCircle.querySelectorAll('.player-card');

    cards.forEach(card => {
      const pid = parseInt(card.dataset.playerId);
      const player = this.engine.getPlayer(pid);
      const imgSrc = (this.godMode || step.phase === PHASE.GAME_END)
        ? (CHARACTER_IMAGES[player.role_id] || CHARACTER_IMAGES.unknown)
        : CHARACTER_IMAGES.unknown;

      // Update avatar image
      const avatarImg = card.querySelector('.player-avatar-img');
      if (avatarImg) {
        avatarImg.src = imgSrc;
      }

      // Update role text
      const roleEl = card.querySelector('.player-role');
      if (roleEl) {
        if (this.godMode || step.phase === PHASE.GAME_END) {
          roleEl.textContent = player.role_name_cn;
        } else {
          roleEl.textContent = '???';
        }
      }

      // Update badges
      const badgesEl = card.querySelector('.player-badges');
      badgesEl.innerHTML = '';

      const badges = this._getPlayerBadges(pid, step);
      badges.forEach(b => {
        const span = document.createElement('span');
        span.className = `badge ${b.cls}`;
        span.textContent = b.text;
        badgesEl.appendChild(span);
      });

      // Update inline speech bubble
      const bubbleEl = card.querySelector('.player-speech-bubble');
      if (bubbleEl) {
        if (step.phase === PHASE.SPEECH && pid === step.data.speaker_id) {
          const speakerName = player.player_name;
          const roleInfo = this.godMode ? ` (${player.role_name_cn})` : '';
          bubbleEl.innerHTML = `
            <div class="bubble-speaker">${speakerName}${roleInfo}:</div>
            ${this._escapeHtml(step.data.speech_text)}
          `;
          bubbleEl.classList.add('visible');
          bubbleEl.scrollTop = 0;
        } else {
          bubbleEl.classList.remove('visible');
          bubbleEl.innerHTML = '';
        }
      }
    });
  }

  _getPlayerBadges(playerId, step) {
    const badges = [];
    const data = step.data;

    switch (step.phase) {
      case PHASE.TEAM_PROPOSAL:
        if (playerId === data.leader_id) badges.push({ text: 'LEADER', cls: 'badge-leader' });
        if (data.team_members.includes(playerId)) badges.push({ text: 'TEAM', cls: 'badge-team' });
        break;

      case PHASE.SPEECH:
        if (playerId === data.leader_id) badges.push({ text: 'LEADER', cls: 'badge-leader' });
        if (data.team_members.includes(playerId)) badges.push({ text: 'TEAM', cls: 'badge-team' });
        if (playerId === data.speaker_id) badges.push({ text: 'SPEAKING', cls: 'badge-speaking' });
        break;

      case PHASE.TEAM_VOTE:
        if (playerId === data.leader_id) badges.push({ text: 'LEADER', cls: 'badge-leader' });
        if (data.team_members.includes(playerId)) badges.push({ text: 'TEAM', cls: 'badge-team' });
        // Show individual votes in god mode, just totals otherwise
        if (this.godMode) {
          const vote = data.team_votes[String(playerId)];
          if (vote !== undefined) {
            badges.push(vote
              ? { text: 'APPROVE', cls: 'badge-approve' }
              : { text: 'REJECT', cls: 'badge-reject' }
            );
          }
        }
        break;

      case PHASE.MISSION:
        if (data.team_members.includes(playerId)) {
          badges.push({ text: 'TEAM', cls: 'badge-team' });
          if (this.godMode) {
            const mVote = data.mission_votes[String(playerId)];
            if (mVote !== undefined) {
              badges.push(mVote
                ? { text: 'SUCCESS', cls: 'badge-success' }
                : { text: 'FAIL', cls: 'badge-fail' }
              );
            }
          }
        }
        if (playerId === data.leader_id) badges.push({ text: 'LEADER', cls: 'badge-leader' });
        break;

      case PHASE.ASSASSIN:
        if (playerId === data.assassin_id) badges.push({ text: 'ASSASSIN', cls: 'badge-fail' });
        if (playerId === data.target_id) badges.push({ text: 'TARGET', cls: 'badge-target' });
        break;
    }

    return badges;
  }

  _renderPhaseLabel(step) {
    const info = this.engine.getStepInfo();
    this.els.phaseLabel.textContent = step.label;

    // Update table center label
    const phaseLabels = {
      [PHASE.NIGHT]: 'NIGHT\nPHASE',
      [PHASE.TEAM_PROPOSAL]: `ROUND ${step.roundNum}\nTEAM`,
      [PHASE.SPEECH]: `ROUND ${step.roundNum}\nDISCUSS`,
      [PHASE.TEAM_VOTE]: `ROUND ${step.roundNum}\nVOTE`,
      [PHASE.MISSION]: `ROUND ${step.roundNum}\nMISSION`,
      [PHASE.ASSASSIN]: 'ASSASSIN\nPHASE',
      [PHASE.GAME_END]: 'GAME\nOVER',
    };

    this.els.tablePhaseLabel.textContent = phaseLabels[step.phase] || 'ROUND TABLE';
  }

  _renderInfoBar(step) {
    const data = step.data;
    const goodWins = data.goodWins !== undefined ? data.goodWins :
      (data.good_wins_count !== undefined ? data.good_wins_count : 0);
    const evilWins = data.evilWins !== undefined ? data.evilWins :
      (data.evil_wins_count !== undefined ? data.evil_wins_count : 0);

    // Round info
    if (step.roundNum) {
      this.els.roundInfo.textContent = `Round: ${step.roundNum}/5`;
      const teamSize = this.engine.data.game_config.mission_team_sizes[step.roundNum - 1];
      this.els.missionSizeInfo.textContent = `Team Size: ${teamSize}`;
    } else if (step.phase === PHASE.NIGHT) {
      this.els.roundInfo.textContent = 'Round: -/5';
      this.els.missionSizeInfo.textContent = 'Team Size: -';
    } else {
      this.els.roundInfo.textContent = 'Round: -/5';
      this.els.missionSizeInfo.textContent = '';
    }

    // Score
    this.els.scoreInfo.innerHTML = `
      <span class="good-text">GOOD ${goodWins}</span>
      <span class="score-sep">:</span>
      <span class="evil-text">${evilWins} EVIL</span>
    `;
  }

  _renderDetailPanel(step) {
    const el = this.els.detailContent;
    el.innerHTML = '';
    el.className = 'fade-in';

    switch (step.phase) {
      case PHASE.NIGHT:
        this._renderNightDetail(el, step);
        break;
      case PHASE.TEAM_PROPOSAL:
        this._renderTeamProposalDetail(el, step);
        break;
      case PHASE.SPEECH:
        this._renderSpeechDetail(el, step);
        break;
      case PHASE.TEAM_VOTE:
        this._renderTeamVoteDetail(el, step);
        break;
      case PHASE.MISSION:
        this._renderMissionDetail(el, step);
        break;
      case PHASE.ASSASSIN:
        this._renderAssassinDetail(el, step);
        break;
      case PHASE.GAME_END:
        this._renderGameEndDetail(el, step);
        break;
    }

    // Force re-trigger animation
    void el.offsetWidth;
  }

  _renderNightDetail(el, step) {
    const title = document.createElement('div');
    title.className = 'detail-title';
    title.textContent = '夜晚降临，各角色获得信息...';
    el.appendChild(title);

    if (this.godMode) {
      step.data.players.forEach(p => {
        const infoItems = [];
        if (p.known_evil && p.known_evil.length > 0) {
          const names = p.known_evil.map(id => this.engine.getPlayerName(id)).join(', ');
          infoItems.push(`看到邪恶阵营: ${names}`);
        }
        if (p.known_merlin_or_morgana && p.known_merlin_or_morgana.length > 0) {
          const names = p.known_merlin_or_morgana.map(id => this.engine.getPlayerName(id)).join(', ');
          infoItems.push(`看到梅林/莫甘娜: ${names}`);
        }
        if (p.known_allies && p.known_allies.length > 0) {
          const names = p.known_allies.map(id => this.engine.getPlayerName(id)).join(', ');
          infoItems.push(`邪恶同伴: ${names}`);
        }

        if (infoItems.length > 0) {
          const item = document.createElement('div');
          item.className = 'night-info-item';
          item.innerHTML = `
            <div class="info-player">${p.player_name} (${p.role_name_cn})</div>
            <div class="info-detail">${infoItems.join('<br>')}</div>
          `;
          el.appendChild(item);
        }
      });
    } else {
      const hint = document.createElement('div');
      hint.style.cssText = 'color: var(--text-dim); padding: 10px;';
      hint.textContent = '角色已分配，各玩家获得了夜晚信息。开启上帝视角可查看详情。';
      el.appendChild(hint);
    }
  }

  _renderTeamProposalDetail(el, step) {
    const data = step.data;
    const leaderName = this.engine.getPlayerName(data.leader_id);
    const teamNames = data.team_members.map(id => this.engine.getPlayerName(id)).join(', ');

    const title = document.createElement('div');
    title.className = 'detail-title';
    title.textContent = `队长 ${leaderName} 提议组队`;
    el.appendChild(title);

    const info = document.createElement('div');
    info.style.cssText = 'padding: 8px; line-height: 2;';
    info.innerHTML = `
      <div>本轮需要 <span style="color: var(--accent)">${data.team_size}</span> 人出任务</div>
      <div>队伍成员: <span style="color: var(--accent)">${teamNames}</span></div>
    `;
    el.appendChild(info);
  }

  _renderSpeechDetail(el, step) {
    const data = step.data;
    const speaker = this.engine.getPlayer(data.speaker_id);
    const speakerName = speaker.player_name;

    const title = document.createElement('div');
    title.className = 'detail-title';
    title.textContent = `讨论阶段 (${data.speech_index + 1}/${data.total_speeches})`;
    el.appendChild(title);

    // Summary in detail panel — full speech is shown in the inline bubble on the player card
    const summary = document.createElement('div');
    summary.style.cssText = 'color: var(--text-muted); padding: 8px;';
    const roleInfo = this.godMode ? ` (${speaker.role_name_cn})` : '';
    summary.innerHTML = `<span style="color: var(--accent)">${speakerName}${roleInfo}</span> 正在发言... 请查看玩家头像旁的对话气泡`;
    el.appendChild(summary);
  }

  _renderTeamVoteDetail(el, step) {
    const data = step.data;

    const title = document.createElement('div');
    title.className = 'detail-title';
    title.textContent = '组队投票结果';
    el.appendChild(title);

    // Summary
    const summary = document.createElement('div');
    summary.style.cssText = 'padding: 8px; margin-bottom: 8px;';
    const resultText = data.approved
      ? '<span class="vote-approve">通过</span>'
      : '<span class="vote-reject">否决</span>';
    summary.innerHTML = `
      投票结果: ${resultText}
      (<span class="vote-approve">${data.approve_count} 同意</span>,
       <span class="vote-reject">${data.reject_count} 反对</span>)
    `;
    el.appendChild(summary);

    // Individual votes (god mode)
    if (this.godMode) {
      const voteList = document.createElement('div');
      voteList.className = 'detail-section secret';
      voteList.style.display = 'block';

      Object.entries(data.team_votes).forEach(([pid, vote]) => {
        const player = this.engine.getPlayer(parseInt(pid));
        const row = document.createElement('div');
        row.className = 'vote-row';
        row.innerHTML = `
          <span>${player.player_name}</span>
          <span class="${vote ? 'vote-approve' : 'vote-reject'}">${vote ? 'APPROVE' : 'REJECT'}</span>
        `;
        voteList.appendChild(row);
      });

      el.appendChild(voteList);
    }
  }

  _renderMissionDetail(el, step) {
    const data = step.data;

    // Mission result banner
    const banner = document.createElement('div');
    banner.className = `mission-result-banner ${data.success ? 'success' : 'fail'}`;
    banner.innerHTML = data.success
      ? '&#x2605; MISSION SUCCESS &#x2605;'
      : '&#x2716; MISSION FAILED &#x2716;';
    el.appendChild(banner);

    // Vote counts
    const info = document.createElement('div');
    info.style.cssText = 'padding: 8px; text-align: center;';
    info.innerHTML = `
      <span class="vote-success">${data.success_count} 成功票</span>,
      <span class="vote-fail">${data.fail_count} 失败票</span>
    `;
    el.appendChild(info);

    // Individual mission votes (god mode)
    if (this.godMode) {
      const voteList = document.createElement('div');
      voteList.className = 'detail-section';
      voteList.style.marginTop = '8px';

      const vTitle = document.createElement('div');
      vTitle.className = 'detail-title';
      vTitle.textContent = '详细投票 (上帝视角)';
      voteList.appendChild(vTitle);

      Object.entries(data.mission_votes).forEach(([pid, vote]) => {
        const player = this.engine.getPlayer(parseInt(pid));
        const row = document.createElement('div');
        row.className = 'vote-row';
        row.innerHTML = `
          <span>${player.player_name}${player.role_name_cn ? ` (${player.role_name_cn})` : ''}</span>
          <span class="${vote ? 'vote-success' : 'vote-fail'}">${vote ? 'SUCCESS' : 'FAIL'}</span>
        `;
        voteList.appendChild(row);
      });

      el.appendChild(voteList);
    }
  }

  _renderAssassinDetail(el, step) {
    const data = step.data;
    const assassinName = this.engine.getPlayerName(data.assassin_id);
    const targetName = this.engine.getPlayerName(data.target_id);
    const targetPlayer = this.engine.getPlayer(data.target_id);

    const title = document.createElement('div');
    title.className = 'detail-title';
    title.textContent = '刺杀阶段 - 刺客的最后一搏';
    el.appendChild(title);

    // Morgana advice (god mode only or always shown since it's the assassin phase)
    if (data.morgana_advice) {
      const advice = document.createElement('div');
      advice.className = 'assassin-info';
      advice.style.marginBottom = '8px';
      advice.innerHTML = `
        <div style="color: var(--evil-light); margin-bottom: 4px;">莫甘娜的建议:</div>
        <div style="color: var(--text-muted); font-family: monospace; font-size: 0.7rem;">${this._escapeHtml(data.morgana_advice)}</div>
      `;
      el.appendChild(advice);
    }

    // Assassin choice
    const choice = document.createElement('div');
    choice.className = 'assassin-info';
    choice.innerHTML = `
      <div style="color: var(--evil-light); margin-bottom: 4px;">
        ${assassinName} 选择刺杀 → <span style="color: var(--warn)">${targetName}</span>
      </div>
      <div style="margin-top: 8px; font-size: 0.7rem; ${data.merlin_killed ? 'color: var(--evil-light)' : 'color: var(--success)'};">
        ${data.merlin_killed
          ? `${targetName} 就是梅林！刺杀成功！邪恶阵营逆转获胜！`
          : `${targetName} 不是梅林（${this.godMode ? targetPlayer.role_name_cn : '???'}）！刺杀失败！`
        }
      </div>
    `;
    el.appendChild(choice);
  }

  _renderGameEndDetail(el, step) {
    const data = step.data;

    const banner = document.createElement('div');
    banner.className = `game-end-banner ${data.winner === 'good' ? 'good-wins' : 'evil-wins'}`;
    banner.innerHTML = `
      <div class="winner-text">${data.winner === 'good' ? 'GOOD WINS' : 'EVIL WINS'}</div>
      <div class="reason-text">${this._escapeHtml(data.end_reason)}</div>
    `;
    el.appendChild(banner);

    // Final score
    const score = document.createElement('div');
    score.style.cssText = 'text-align: center; padding: 8px; margin-bottom: 12px;';
    score.innerHTML = `
      最终比分:
      <span class="good-text">GOOD ${data.good_wins_count}</span>
      :
      <span class="evil-text">${data.evil_wins_count} EVIL</span>
    `;
    el.appendChild(score);

    // Player identities (always shown at game end)
    const identTitle = document.createElement('div');
    identTitle.className = 'detail-title';
    identTitle.textContent = '身份揭晓';
    el.appendChild(identTitle);

    data.players.forEach(p => {
      const item = document.createElement('div');
      item.className = 'vote-row';
      item.innerHTML = `
        <span>${p.player_name}</span>
        <span style="color: ${p.team === 'good' ? 'var(--good-light)' : 'var(--evil-light)'}">
          ${p.role_name_cn} (${p.team === 'good' ? '正义' : '邪恶'})
        </span>
      `;
      el.appendChild(item);
    });
  }

  _renderTimeline(step) {
    const el = this.els.timelineRounds;
    el.innerHTML = '';

    const roundSummary = this.engine.getRoundSummary();

    // Night marker
    const nightItem = document.createElement('span');
    nightItem.className = 'timeline-item' + (step.phase === PHASE.NIGHT ? ' active' : '');
    nightItem.textContent = 'NIGHT';
    nightItem.onclick = () => { this.engine.jumpToPhase(PHASE.NIGHT); this._onTimelineClick(); };
    el.appendChild(nightItem);

    // Round markers
    roundSummary.forEach(round => {
      const sep = document.createElement('span');
      sep.className = 'timeline-sep';
      sep.textContent = '>';
      el.appendChild(sep);

      const lastRecord = round.records[round.records.length - 1];
      let cls = '';
      if (lastRecord.success === true) cls = 'success';
      else if (lastRecord.success === false) cls = 'fail';
      else cls = 'rejected';

      const isActive = step.roundNum === round.roundNum;

      const item = document.createElement('span');
      item.className = `timeline-item ${cls}${isActive ? ' active' : ''}`;
      item.textContent = `R${round.roundNum}`;
      item.onclick = () => { this.engine.jumpToRound(round.roundNum); this._onTimelineClick(); };
      el.appendChild(item);
    });

    // Assassin marker (if present)
    if (this.engine.data.assassin_phase) {
      const sep = document.createElement('span');
      sep.className = 'timeline-sep';
      sep.textContent = '>';
      el.appendChild(sep);

      const item = document.createElement('span');
      item.className = 'timeline-item' + (step.phase === PHASE.ASSASSIN ? ' active' : '');
      item.textContent = 'ASSASSIN';
      item.onclick = () => { this.engine.jumpToPhase(PHASE.ASSASSIN); this._onTimelineClick(); };
      el.appendChild(item);
    }

    // End marker
    const sepEnd = document.createElement('span');
    sepEnd.className = 'timeline-sep';
    sepEnd.textContent = '>';
    el.appendChild(sepEnd);

    const endItem = document.createElement('span');
    endItem.className = 'timeline-item' + (step.phase === PHASE.GAME_END ? ' active' : '');
    endItem.textContent = 'END';
    endItem.onclick = () => { this.engine.jumpToPhase(PHASE.GAME_END); this._onTimelineClick(); };
    el.appendChild(endItem);

    // Step counter
    const counter = document.createElement('div');
    counter.className = 'step-counter';
    const info = this.engine.getStepInfo();
    counter.textContent = `Step ${info.current} / ${info.total}`;
    el.appendChild(counter);
  }

  _onTimelineClick() {
    // Callback for timeline navigation - will be set by app.js
    if (this.onNavigate) this.onNavigate();
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
