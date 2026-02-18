/**
 * App - Entry point: file loading, event binding, keyboard shortcuts, auto-play
 */

(function () {
  let engine = null;
  let renderer = null;

  // Auto-play state
  let isPlaying = false;
  let playTimer = null;
  let playSpeed = 1; // multiplier
  const BASE_INTERVAL = 2000; // 1x speed = 2 seconds per step
  const SPEECH_MULTIPLIER = 1.5; // speech steps get extra time

  // DOM elements
  const loaderScreen = document.getElementById('loader-screen');
  const gameScreen = document.getElementById('game-screen');
  const replayFileInput = document.getElementById('replay-file');
  const replayFileNewInput = document.getElementById('replay-file-new');
  const loadNewBtn = document.getElementById('load-new-btn');
  const godModeBtn = document.getElementById('god-mode-btn');
  const godModeStatus = document.getElementById('god-mode-status');
  const btnFirst = document.getElementById('btn-first');
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  const btnLast = document.getElementById('btn-last');
  const btnPlay = document.getElementById('btn-play');
  const speedButtons = document.querySelectorAll('.pixel-btn-speed');

  // ==================== File Loading ====================

  function handleFileLoad(file) {
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (e) {
      try {
        const data = JSON.parse(e.target.result);
        initGame(data);
      } catch (err) {
        alert('Failed to parse replay file: ' + err.message);
        console.error(err);
      }
    };
    reader.onerror = function () {
      alert('Failed to read file');
    };
    reader.readAsText(file);
  }

  replayFileInput.addEventListener('change', function (e) {
    handleFileLoad(e.target.files[0]);
  });

  replayFileNewInput.addEventListener('change', function (e) {
    handleFileLoad(e.target.files[0]);
  });

  loadNewBtn.addEventListener('click', function () {
    replayFileNewInput.click();
  });

  // ==================== Game Initialization ====================

  function initGame(data) {
    // Validate data
    if (!data.players || !Array.isArray(data.players) || data.players.length === 0) {
      alert('Invalid replay file: missing or empty players array');
      return;
    }
    if (!data.mission_records || !Array.isArray(data.mission_records)) {
      alert('Invalid replay file: missing mission_records');
      return;
    }
    if (!data.game_config) {
      alert('Invalid replay file: missing game_config');
      return;
    }

    // Stop any existing auto-play
    stopPlay();

    engine = new ReplayEngine(data);
    renderer = new UIRenderer(engine);
    renderer.onNavigate = function () {
      stopPlay();
      renderCurrent();
    };

    // Switch to game screen
    loaderScreen.classList.add('hidden');
    gameScreen.classList.remove('hidden');

    // Reset god mode
    document.body.classList.remove('god-mode');
    godModeBtn.classList.remove('active');
    godModeStatus.textContent = 'OFF';

    // Initialize UI
    renderer.initPlayerCards();
    renderCurrent();
  }

  // ==================== Navigation ====================

  function renderCurrent() {
    if (!engine || !renderer) return;
    renderer.render(engine.getCurrentStep());
  }

  function goNext() {
    if (engine && engine.next()) {
      renderCurrent();
      return true;
    }
    return false;
  }

  function goPrev() {
    if (engine && engine.prev()) {
      renderCurrent();
      return true;
    }
    return false;
  }

  function goFirst() {
    if (engine) {
      engine.first();
      renderCurrent();
    }
  }

  function goLast() {
    if (engine) {
      engine.last();
      renderCurrent();
    }
  }

  btnNext.addEventListener('click', function () { stopPlay(); goNext(); });
  btnPrev.addEventListener('click', function () { stopPlay(); goPrev(); });
  btnFirst.addEventListener('click', function () { stopPlay(); goFirst(); });
  btnLast.addEventListener('click', function () { stopPlay(); goLast(); });

  // ==================== Auto-Play ====================

  function getInterval() {
    let interval = BASE_INTERVAL / playSpeed;
    // Give more time for speech steps
    if (engine) {
      const step = engine.getCurrentStep();
      if (step && step.phase === PHASE.SPEECH) {
        interval *= SPEECH_MULTIPLIER;
      }
    }
    return interval;
  }

  function startPlay() {
    if (!engine) return;
    isPlaying = true;
    btnPlay.textContent = '\u23F8'; // pause icon ⏸
    btnPlay.classList.add('playing');
    scheduleNextStep();
  }

  function stopPlay() {
    isPlaying = false;
    if (playTimer) {
      clearTimeout(playTimer);
      playTimer = null;
    }
    btnPlay.textContent = '\u25B6'; // play icon ▶
    btnPlay.classList.remove('playing');
  }

  function togglePlay() {
    if (isPlaying) {
      stopPlay();
    } else {
      startPlay();
    }
  }

  function scheduleNextStep() {
    if (!isPlaying || !engine) return;
    playTimer = setTimeout(function () {
      if (!isPlaying) return;
      const advanced = goNext();
      if (advanced) {
        scheduleNextStep();
      } else {
        // Reached the end
        stopPlay();
      }
    }, getInterval());
  }

  btnPlay.addEventListener('click', togglePlay);

  // Speed selector
  speedButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      playSpeed = parseFloat(this.dataset.speed);
      // Update active state
      speedButtons.forEach(function (b) { b.classList.remove('active'); });
      this.classList.add('active');
      // If playing, restart timer with new speed
      if (isPlaying) {
        clearTimeout(playTimer);
        scheduleNextStep();
      }
    });
  });

  // ==================== God Mode ====================

  function toggleGodMode() {
    if (!renderer) return;
    const newState = !renderer.godMode;
    renderer.setGodMode(newState);

    godModeBtn.classList.toggle('active', newState);
    godModeStatus.textContent = newState ? 'ON' : 'OFF';
  }

  godModeBtn.addEventListener('click', toggleGodMode);

  // ==================== Keyboard Shortcuts ====================

  document.addEventListener('keydown', function (e) {
    // Ignore when typing in input fields
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.key) {
      case 'ArrowRight':
        e.preventDefault();
        stopPlay();
        goNext();
        break;
      case ' ':
        e.preventDefault();
        // Space toggles play/pause instead of just next step
        togglePlay();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        stopPlay();
        goPrev();
        break;
      case 'Home':
        e.preventDefault();
        stopPlay();
        goFirst();
        break;
      case 'End':
        e.preventDefault();
        stopPlay();
        goLast();
        break;
      case 'g':
      case 'G':
        e.preventDefault();
        toggleGodMode();
        break;
      case 'p':
      case 'P':
        e.preventDefault();
        togglePlay();
        break;
    }
  });

  // ==================== Drag & Drop ====================

  document.addEventListener('dragover', function (e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });

  document.addEventListener('drop', function (e) {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].name.endsWith('.json')) {
      handleFileLoad(files[0]);
    }
  });
})();
