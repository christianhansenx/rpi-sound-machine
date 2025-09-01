const playTimer = document.getElementById('play-timer');
const pauseResumeBtn = document.getElementById('pause-resume-btn');
const stopBtn = document.getElementById('stop-btn');
const fileLinks = document.querySelectorAll('.file-name-link');
const volumeSlider = document.getElementById('volume-slider');

let lastPlayTime = initialState.lastPlayTime;
let elapsedAtPause = initialState.elapsedAtPause;
let timerInterval = null;

// Function to update the active sound class based on server state
function updateActiveSounds(activeSounds) {
    fileLinks.forEach(link => {
        const fileName = link.dataset.fileName;
        if (activeSounds.includes(fileName)) {
            link.classList.add('active-sound');
        } else {
            link.classList.remove('active-sound');
        }
    });
}

// Initial setup from server-side rendered data
updateActiveSounds(initialState.activeSounds);

function updateTimer() {
    let totalElapsedSeconds = elapsedAtPause;
    if (lastPlayTime) {
        const now = Date.now() / 1000;
        totalElapsedSeconds = Math.floor(now - lastPlayTime + elapsedAtPause);
    }

    if (totalElapsedSeconds >= 0) {
        const hours = Math.floor(totalElapsedSeconds / 3600);
        const minutes = Math.floor((totalElapsedSeconds % 3600) / 60);
        const seconds = totalElapsedSeconds % 60;

        const formattedHours = String(hours).padStart(2, '0');
        const formattedMinutes = String(minutes).padStart(2, '0');
        const formattedSeconds = String(seconds).padStart(2, '0');

        playTimer.textContent = formattedHours + ':' + formattedMinutes + ':' + formattedSeconds;
    } else {
        playTimer.textContent = '00:00:00';
    }
}

function startTimer() {
    if (!timerInterval) {
        timerInterval = setInterval(updateTimer, 1000);
    }
}

function pauseTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
}

function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    playTimer.textContent = '00:00:00';
}

// Initial timer setup
if (lastPlayTime) {
    startTimer();
} else {
    stopTimer();
}

// Asynchronous handling of sound playback

// Sound file links
fileLinks.forEach(link => {
    link.addEventListener('click', async (e) => {
        e.preventDefault();
        const fileName = e.target.dataset.fileName;
        const response = await fetch(`/toggle_play/${fileName}`);
        const data = await response.json();

        // Update UI based on response
        lastPlayTime = data.last_play_time;
        elapsedAtPause = data.elapsed_time_at_pause;

        // Update timer
        if (lastPlayTime) {
            startTimer();
        } else {
            stopTimer();
        }

        // Update active sound class for all links
        updateActiveSounds(data.active_sounds);
    });
});

// Pause/Resume button
pauseResumeBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    const response = await fetch('/pause_resume');
    const data = await response.json();

    // Update UI based on response
    lastPlayTime = data.last_play_time;
    elapsedAtPause = data.elapsed_time_at_pause;

    if (data.paused) {
        pauseResumeBtn.innerHTML = '▶️';
        pauseTimer(); // Only pauses the countdown
    } else {
        pauseResumeBtn.innerHTML = '⏸️';
        startTimer();
    }
    updateActiveSounds(data.active_sounds);
});

// Stop button
stopBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    const response = await fetch('/stop');
    const data = await response.json();

    // Update UI based on response
    lastPlayTime = data.last_play_time;
    elapsedAtPause = data.elapsed_time_at_pause;

    pauseResumeBtn.innerHTML = '⏸️';
    stopTimer(); // Resets the timer to 00:00:00
    updateActiveSounds(data.active_sounds);
});

// Volume slider
volumeSlider.addEventListener('input', async (e) => {
    const newVolume = e.target.value;
    await fetch(`/set_volume/${newVolume}`);
});
