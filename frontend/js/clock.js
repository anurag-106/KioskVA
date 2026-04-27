/**
 * Header clock and connection status indicator.
 */
const Clock = (function () {
    const clockEl = document.getElementById("clock");
    const statusEl = document.getElementById("connection-status");

    function start() {
        update();
        setInterval(update, 1000);
    }

    function update() {
        const now = new Date();
        const h = String(now.getHours()).padStart(2, "0");
        const m = String(now.getMinutes()).padStart(2, "0");
        const s = String(now.getSeconds()).padStart(2, "0");
        clockEl.textContent = h + ":" + m + ":" + s;
    }

    function setConnected(connected) {
        statusEl.className = "status-dot " + (connected ? "connected" : "disconnected");
        statusEl.title = connected ? "Connected" : "Disconnected";
    }

    function setReconnecting() {
        statusEl.className = "status-dot reconnecting";
        statusEl.title = "Reconnecting...";
    }

    return {
        start: start,
        setConnected: setConnected,
        setReconnecting: setReconnecting
    };
})();
