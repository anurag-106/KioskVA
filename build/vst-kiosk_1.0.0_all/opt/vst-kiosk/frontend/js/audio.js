/**
 * Audio alert system using Web Audio API with bundled WAV fallbacks.
 *
 * Priority logic: if ANY room is highRisk -> loud alarm.
 *                 else if ANY room is lowRisk -> soft chime.
 *                 else -> silent.
 */
const AudioAlert = (function () {
    let audioCtx = null;
    let highBuffer = null;
    let lowBuffer = null;
    let currentSource = null;
    let currentTier = "silent"; // "high", "low", "silent"
    let initialized = false;

    function init() {
        try {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            loadBuffer("/audio/high_alert.wav", function (buf) { highBuffer = buf; });
            loadBuffer("/audio/low_alert.wav", function (buf) { lowBuffer = buf; });
            initialized = true;

            // Resume context on any user interaction (belt and suspenders)
            document.addEventListener("click", resumeContext, { once: true });
            document.addEventListener("touchstart", resumeContext, { once: true });
        } catch (e) {
            console.error("[Audio] Web Audio API not available:", e);
        }
    }

    function resumeContext() {
        if (audioCtx && audioCtx.state === "suspended") {
            audioCtx.resume();
        }
    }

    function loadBuffer(url, callback) {
        var xhr = new XMLHttpRequest();
        xhr.open("GET", url, true);
        xhr.responseType = "arraybuffer";
        xhr.onload = function () {
            if (xhr.status === 200) {
                audioCtx.decodeAudioData(xhr.response, function (buffer) {
                    callback(buffer);
                }, function (err) {
                    console.error("[Audio] Failed to decode", url, err);
                });
            }
        };
        xhr.onerror = function () {
            console.warn("[Audio] Failed to load", url);
        };
        xhr.send();
    }

    function play(tier) {
        if (!initialized || !audioCtx) return;
        if (tier === currentTier) return;

        stop();
        currentTier = tier;

        if (tier === "silent") return;

        var buffer = (tier === "high") ? highBuffer : lowBuffer;
        if (!buffer) {
            console.warn("[Audio] Buffer not loaded for tier:", tier);
            return;
        }

        // Resume if suspended (kiosk mode flag should prevent this, but just in case)
        if (audioCtx.state === "suspended") {
            audioCtx.resume();
        }

        currentSource = audioCtx.createBufferSource();
        currentSource.buffer = buffer;
        currentSource.loop = true;
        currentSource.connect(audioCtx.destination);
        currentSource.start(0);
    }

    function stop() {
        if (currentSource) {
            try { currentSource.stop(); } catch (e) { /* ignore */ }
            currentSource = null;
        }
        currentTier = "silent";
    }

    /**
     * Recalculate the audio state based on all room tiles.
     * Call this whenever alert states change.
     */
    function recalculate() {
        var tiles = document.querySelectorAll(".tile-icon-panel");
        var hasHigh = false;
        var hasLow = false;

        tiles.forEach(function (panel) {
            if (panel.classList.contains("state-highRisk")) hasHigh = true;
            if (panel.classList.contains("state-lowRisk")) hasLow = true;
        });

        if (hasHigh) {
            play("high");
        } else if (hasLow) {
            play("low");
        } else {
            play("silent");
        }
    }

    return {
        init: init,
        recalculate: recalculate,
        stop: stop
    };
})();
