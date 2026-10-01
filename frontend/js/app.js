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
        Banner.setAll(config.other_alerts);
        AudioAlert.recalculate();
    });

    // New alert
    window.addEventListener("ws:alert", function (e) {
        var data = e.detail;
        if (Grid.hasRoom(data.room_id)) {
            Grid.updateRoom(data.room_id, {
                active_alert: data.alert_level,
                nuc_status: "online",
                alert_id: data.alert_id,
                event_type: data.event_type
            });
        } else {
            // Fallback-routed alert with no tile here — must still be seen
            Banner.add(data);
        }
        AudioAlert.recalculate();
    });

    // Alert cleared
    window.addEventListener("ws:alert_cleared", function (e) {
        var data = e.detail;
        Banner.remove(data.alert_id);
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
            nuc_status: "offline"
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

    // Keyboard event — nurse paused/resumed/switched mode on NUC
    window.addEventListener("ws:keyboard_event", function (e) {
        // Real NUC events: "off" = paused; "on" / "monitoring" / "smart_resume_*"
        // = monitoring in monitoring_type's mode ("fall" keeps the current mode).
        // Alerts are not cleared here — the server sends alert_cleared.
        var data = e.detail;
        var updates = {};
        if (data.event_status === "off") {
            updates.nuc_status = "paused";
        } else if (["on", "monitoring", "smart_resume_bed", "smart_resume_chair"].indexOf(data.event_status) !== -1) {
            updates.nuc_status = "online";
            if (data.monitoring_type === "bed" || data.monitoring_type === "chair") {
                updates.monitoring_type = data.monitoring_type;
            }
        }
        Grid.updateRoom(data.room_id, updates);
        AudioAlert.recalculate();
    });

    // Heartbeat-reported state change (pause / calibration / bed-chair mode)
    window.addEventListener("ws:device_state_change", function (e) {
        var data = e.detail;
        var changes = data.changes || {};
        var state = data.current_state || {};
        var updates = {};
        if (changes.pause_status || changes.type) {
            if (state.pause_status === "paused") updates.nuc_status = "paused";
            else if (state.type === "calibration") updates.nuc_status = "calibration";
            else updates.nuc_status = "online";
        }
        if (changes.mode && (state.mode === "bed" || state.mode === "chair")) {
            updates.monitoring_type = state.mode;
        }
        if (Object.keys(updates).length) {
            Grid.updateRoom(data.room_id, updates);
            AudioAlert.recalculate();
        }
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
