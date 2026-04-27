/**
 * Main application bootstrap — wires together WS, Grid, Audio, and Clock.
 */
(function () {
    "use strict";

    var overlay = document.getElementById("disconnect-overlay");
    var serverConnected = false;
    var localConnected = false;

    function updateOverlay() {
        // Show overlay only when local WS to backend is down
        // (server disconnect shows via header dot + summary bar, not a blocking overlay)
        if (!localConnected) {
            overlay.classList.remove("hidden");
        } else {
            overlay.classList.add("hidden");
        }
    }

    // Start the clock
    Clock.start();

    // Initialize audio
    AudioAlert.init();

    // --- WebSocket event handlers ---

    // Full config received — render entire grid
    window.addEventListener("ws:config", function (e) {
        var config = e.detail;
        Grid.setLastConfig(config);
        Grid.renderFullGrid(config);
        AudioAlert.recalculate();
    });

    // New alert
    window.addEventListener("ws:alert", function (e) {
        var data = e.detail;
        Grid.updateRoom(data.room_id, {
            active_alert: data.alert_level,
            nuc_status: "online",
            _alert_id: data.alert_id
        });
        AudioAlert.recalculate();
    });

    // Alert cleared
    window.addEventListener("ws:alert_cleared", function (e) {
        var data = e.detail;
        Grid.clearAck(data.room_id);
        Grid.updateRoom(data.room_id, {
            active_alert: null
        });
        AudioAlert.recalculate();
    });

    // Device offline
    window.addEventListener("ws:device_offline", function (e) {
        var data = e.detail;
        Grid.updateRoom(data.room_id, {
            nuc_status: "offline",
            active_alert: null
        });
        AudioAlert.recalculate();
    });

    // Device online
    window.addEventListener("ws:device_online", function (e) {
        var data = e.detail;
        Grid.updateRoom(data.room_id, {
            nuc_status: "online"
        });
    });

    // Room added — request fresh config
    window.addEventListener("ws:room_added", function () {
        KioskWS.send({ type: "sync_request" });
    });

    // Room removed
    window.addEventListener("ws:room_removed", function (e) {
        var data = e.detail;
        Grid.removeRoom(data.room_id);
        AudioAlert.recalculate();
    });

    // Connection status from backend (server connection state)
    window.addEventListener("ws:connection_status", function (e) {
        var data = e.detail;
        serverConnected = data.connected;
        Clock.setConnected(data.connected);
        updateOverlay();
    });

    // Local WS connection events
    window.addEventListener("ws:open", function () {
        localConnected = true;
        // Don't hide overlay yet — wait for server connection status
    });

    window.addEventListener("ws:close", function () {
        localConnected = false;
        serverConnected = false;
        Clock.setReconnecting();
        updateOverlay();
    });

    // Connect to local backend
    KioskWS.connect();
})();
