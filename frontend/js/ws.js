/**
 * WebSocket client for connecting to the local Python backend.
 * Auto-reconnects with exponential backoff.
 */
const KioskWS = (function () {
    let socket = null;
    let backoff = 1000; // start at 1s
    const MAX_BACKOFF = 5000; // local backend — come back quickly after it restarts
    const MIN_BACKOFF = 1000;
    let reconnectTimer = null;

    function getUrl() {
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        return proto + "//" + location.host + "/ws";
    }

    function connect() {
        if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
            return;
        }

        const url = getUrl();
        console.log("[WS] Connecting to", url);
        socket = new WebSocket(url);

        socket.onopen = function () {
            console.log("[WS] Connected");
            backoff = MIN_BACKOFF;
            window.dispatchEvent(new CustomEvent("ws:open"));
        };

        socket.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);
                const type = data.type || "unknown";
                window.dispatchEvent(new CustomEvent("ws:" + type, { detail: data }));
                window.dispatchEvent(new CustomEvent("ws:message", { detail: data }));
            } catch (e) {
                console.error("[WS] Failed to parse message:", e);
            }
        };

        socket.onclose = function (event) {
            console.log("[WS] Disconnected, code:", event.code);
            socket = null;
            window.dispatchEvent(new CustomEvent("ws:close"));
            scheduleReconnect();
        };

        socket.onerror = function (event) {
            console.error("[WS] Error");
            socket.close();
        };
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        console.log("[WS] Reconnecting in", backoff, "ms");
        reconnectTimer = setTimeout(function () {
            reconnectTimer = null;
            connect();
            backoff = Math.min(backoff * 2, MAX_BACKOFF);
        }, backoff);
    }

    function send(data) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(typeof data === "string" ? data : JSON.stringify(data));
        }
    }

    return { connect: connect, send: send };
})();
