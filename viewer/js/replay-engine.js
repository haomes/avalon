/**
 * Replay Engine - Flattens game JSON data into linear steps for playback
 */

const PHASE = {
  NIGHT: 'night',
  TEAM_PROPOSAL: 'team_proposal',
  SPEECH: 'speech',
  TEAM_VOTE: 'team_vote',
  MISSION: 'mission',
  ASSASSIN: 'assassin',
  GAME_END: 'game_end',
};

class ReplayEngine {
  constructor(gameData) {
    this.data = gameData;
    this.steps = [];
    this.currentIndex = 0;
    this._generateSteps();
  }

  _generateSteps() {
    this.steps = [];

    // Night phase
    this.steps.push({
      phase: PHASE.NIGHT,
      label: '夜晚阶段 - 角色分配',
      data: {
        players: this.data.players,
      },
    });

    // Process each mission record
    let currentRound = 0;
    let goodWins = 0;
    let evilWins = 0;
    let missionIndex = 0;  // index into mission_results

    for (let i = 0; i < this.data.mission_records.length; i++) {
      const record = this.data.mission_records[i];
      const isNewRound = record.round_num !== currentRound;

      if (isNewRound) {
        currentRound = record.round_num;
      }

      const teamSize = this.data.game_config?.mission_team_sizes?.[record.round_num - 1] ?? '?';

      // Team proposal step
      this.steps.push({
        phase: PHASE.TEAM_PROPOSAL,
        label: `第${record.round_num}轮 - 队长组队`,
        roundNum: record.round_num,
        recordIndex: i,
        data: {
          leader_id: record.team_leader_id,
          team_members: record.team_members,
          team_size: teamSize,
          goodWins,
          evilWins,
        },
      });

      // Speech steps (one per speaker)
      const speechEntries = Object.entries(record.speeches);
      for (let si = 0; si < speechEntries.length; si++) {
        const [playerId, text] = speechEntries[si];
        this.steps.push({
          phase: PHASE.SPEECH,
          label: `第${record.round_num}轮 - 讨论 (${si + 1}/${speechEntries.length})`,
          roundNum: record.round_num,
          recordIndex: i,
          data: {
            speaker_id: parseInt(playerId),
            speech_text: text,
            speech_index: si,
            total_speeches: speechEntries.length,
            leader_id: record.team_leader_id,
            team_members: record.team_members,
            goodWins,
            evilWins,
          },
        });
      }

      // Team vote step
      const approveCount = Object.values(record.team_votes).filter(v => v).length;
      const rejectCount = Object.values(record.team_votes).filter(v => !v).length;
      // Use backend-exported approved field if available, otherwise derive
      const teamApproved = record.team_approved !== undefined
        ? record.team_approved
        : approveCount > rejectCount;

      this.steps.push({
        phase: PHASE.TEAM_VOTE,
        label: `第${record.round_num}轮 - 组队投票`,
        roundNum: record.round_num,
        recordIndex: i,
        data: {
          team_votes: record.team_votes,
          approve_count: approveCount,
          reject_count: rejectCount,
          approved: teamApproved,
          leader_id: record.team_leader_id,
          team_members: record.team_members,
          goodWins,
          evilWins,
        },
      });

      // Mission step (only if team was approved)
      if (record.success !== null) {
        const failCount = Object.values(record.mission_votes).filter(v => !v).length;
        const successCount = Object.values(record.mission_votes).filter(v => v).length;

        // Update scores
        if (record.success) {
          goodWins++;
        } else {
          evilWins++;
        }

        this.steps.push({
          phase: PHASE.MISSION,
          label: `第${record.round_num}轮 - 任务${record.success ? '成功' : '失败'}`,
          roundNum: record.round_num,
          recordIndex: i,
          data: {
            mission_votes: record.mission_votes,
            success: record.success,
            success_count: successCount,
            fail_count: failCount,
            team_members: record.team_members,
            leader_id: record.team_leader_id,
            goodWins,
            evilWins,
          },
        });

        missionIndex++;
      }
    }

    // Assassin phase (if exists)
    if (this.data.assassin_phase) {
      const ap = this.data.assassin_phase;
      this.steps.push({
        phase: PHASE.ASSASSIN,
        label: '刺杀阶段',
        data: {
          assassin_id: ap.assassin_id,
          target_id: ap.target_id,
          morgana_advice: ap.morgana_advice,
          merlin_killed: ap.merlin_killed,
          goodWins,
          evilWins,
        },
      });
    }

    // Game end
    this.steps.push({
      phase: PHASE.GAME_END,
      label: '游戏结束',
      data: {
        winner: this.data.winner,
        end_reason: this.data.end_reason,
        players: this.data.players,
        good_wins_count: this.data.good_wins_count,
        evil_wins_count: this.data.evil_wins_count,
      },
    });
  }

  getCurrentStep() {
    return this.steps[this.currentIndex];
  }

  getStepInfo() {
    return {
      current: this.currentIndex + 1,
      total: this.steps.length,
    };
  }

  next() {
    if (this.currentIndex < this.steps.length - 1) {
      this.currentIndex++;
      return true;
    }
    return false;
  }

  prev() {
    if (this.currentIndex > 0) {
      this.currentIndex--;
      return true;
    }
    return false;
  }

  first() {
    this.currentIndex = 0;
  }

  last() {
    this.currentIndex = this.steps.length - 1;
  }

  jumpToRound(roundNum) {
    const idx = this.steps.findIndex(s => s.roundNum === roundNum);
    if (idx >= 0) {
      this.currentIndex = idx;
      return true;
    }
    return false;
  }

  jumpToPhase(phase) {
    const idx = this.steps.findIndex(s => s.phase === phase);
    if (idx >= 0) {
      this.currentIndex = idx;
      return true;
    }
    return false;
  }

  getPlayer(playerId) {
    return this.data.players.find(p => p.player_id === playerId);
  }

  getPlayerName(playerId) {
    const p = this.getPlayer(playerId);
    return p ? p.player_name : `Player ${playerId}`;
  }

  /**
   * Get all unique round numbers present in mission_records.
   * Returns [{roundNum, records: [{recordIndex, approved, success}]}]
   */
  getRoundSummary() {
    const rounds = [];
    let currentRound = 0;
    let roundObj = null;

    for (let i = 0; i < this.data.mission_records.length; i++) {
      const rec = this.data.mission_records[i];
      if (rec.round_num !== currentRound) {
        currentRound = rec.round_num;
        roundObj = { roundNum: currentRound, records: [] };
        rounds.push(roundObj);
      }
      const approveCount = Object.values(rec.team_votes).filter(v => v).length;
      const rejectCount = Object.values(rec.team_votes).filter(v => !v).length;
      roundObj.records.push({
        recordIndex: i,
        approved: approveCount > rejectCount,
        success: rec.success,
      });
    }

    return rounds;
  }
}
