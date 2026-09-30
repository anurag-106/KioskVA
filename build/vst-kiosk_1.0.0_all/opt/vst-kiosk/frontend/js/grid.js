/**
 * Room grid renderer — builds and updates room tiles.
 *
 * Tile layout:
 * ┌────────────────┬──────────────┐
 * │  [ICON]        │              │
 * │  Bed/Chair     │    Room #    │
 * │  Monitoring    │    Status    │
 * └────────────────┴──────────────┘
 */
const Grid = (function () {

    const container = document.getElementById("room-grid");

    // Icon paths — SVG files in /icons/
    function getIconPath(state, monType) {
        switch (state) {
            case "highRisk":
            case "lowRisk":
                return "/icons/" + monType + "_exit.svg";
            case "paused":
                return "/icons/paused.svg";
            case "calibration":
                return "/icons/" + monType + "_calibration.svg";
            case "offline":
            case "no_device":
            case "unregistered":
                return "/icons/disconnected.svg";
            case "deactivated":
                return "/icons/deactivated.svg";
            default:
                return "/icons/" + monType + "_monitoring.svg";
        }
    }

    // Track acknowledged alerts
    const ackedAlerts = new Set();

    // Track alert timestamps for duration display
    var alertTimestamps = {};

    // Duration update interval
    var durationInterval = null;

    function renderFullGrid(config) {
        container.innerHTML = "";

        if (!config || !config.units || config.units.length === 0) {
            container.innerHTML = '<div class="placeholder-message">No rooms configured</div>';
            updateSummary(config);
            return;
        }

        // Update header
        if (config.facility) {
            document.getElementById("facility-name").textContent = config.facility;
        }

        var unitNames = config.units.map(function (u) { return u.unit_name; }).join(" / ");
        document.getElementById("unit-names").textContent = unitNames;

        config.units.forEach(function (unit) {
            var section = document.createElement("div");
            section.className = "unit-section";
            section.dataset.unitId = unit.unit_id;

            if (config.units.length > 1) {
                var title = document.createElement("h2");
                title.className = "unit-title";
                title.textContent = unit.unit_name + (unit.branch ? " — " + unit.branch : "");
                section.appendChild(title);
            }

            var grid = document.createElement("div");
            grid.className = "room-grid";

            // Sort rooms: alerts first (highRisk before lowRisk), then rest
            var sorted = sortRooms(unit.rooms);

            sorted.forEach(function (room) {
                // Track alert start time if not already tracked
                if (room.active_alert && !alertTimestamps[room.room_id]) {
                    alertTimestamps[room.room_id] = Date.now();
                } else if (!room.active_alert) {
                    delete alertTimestamps[room.room_id];
                }
                grid.appendChild(createTile(room));
            });

            section.appendChild(grid);
            container.appendChild(section);
        });

        updateSummary(config);
        startDurationUpdater();
    }

    function sortRooms(rooms) {
        var priority = { highRisk: 0, lowRisk: 1 };
        return rooms.slice().sort(function (a, b) {
            var pa = a.active_alert ? priority[a.active_alert] : 2;
            var pb = b.active_alert ? priority[b.active_alert] : 2;
            return pa - pb;
        });
    }

    function createTile(room) {
        var tile = document.createElement("div");
        tile.className = "room-tile";
        tile.dataset.roomId = room.room_id;

        var state = getTileState(room);
        var monType = room.monitoring_type || "bed";

        // Left icon panel
        var iconPanel = document.createElement("div");
        iconPanel.className = "tile-icon-panel state-" + state.panelState;

        var icon = document.createElement("img");
        icon.className = "tile-icon";
        icon.src = getIconPath(state.panelState, monType);
        icon.alt = state.label;
        iconPanel.appendChild(icon);

        var label = document.createElement("div");
        label.className = "tile-label";
        label.textContent = state.label;
        iconPanel.appendChild(label);

        // Right info panel
        var infoPanel = document.createElement("div");
        infoPanel.className = "tile-info-panel";

        var roomNum = document.createElement("div");
        roomNum.className = "tile-room-number";
        roomNum.textContent = room.name || "Room " + room.room_id;
        infoPanel.appendChild(roomNum);

        if (state.statusText) {
            var statusEl = document.createElement("div");
            statusEl.className = "tile-status-text " + state.statusClass;
            statusEl.textContent = state.statusText;
            infoPanel.appendChild(statusEl);
        }

        // Alert duration
        if (room.active_alert && alertTimestamps[room.room_id]) {
            var durationEl = document.createElement("div");
            durationEl.className = "tile-alert-duration";
            durationEl.dataset.alertStart = alertTimestamps[room.room_id];
            durationEl.textContent = formatDuration(Date.now() - alertTimestamps[room.room_id]);
            infoPanel.appendChild(durationEl);
        }

        tile.appendChild(iconPanel);
        tile.appendChild(infoPanel);

        // Add device state class
        tile.classList.add("device-" + (room.nuc_status || "no_device"));

        // Alert active class for box shadow
        if (room.active_alert) {
            tile.classList.add("alert-active");
        }

        // Ack indicator
        if (room.active_alert && ackedAlerts.has(room.room_id)) {
            tile.classList.add("tile-acked");
        }

        // Click handler for acknowledging alerts
        if (room.active_alert) {
            tile.style.cursor = "pointer";
            tile.addEventListener("click", function () {
                onAcknowledge(room);
            });
        }

        return tile;
    }

    function formatDuration(ms) {
        var seconds = Math.floor(ms / 1000);
        if (seconds < 60) return seconds + "s ago";
        var minutes = Math.floor(seconds / 60);
        if (minutes < 60) return minutes + "m ago";
        var hours = Math.floor(minutes / 60);
        return hours + "h " + (minutes % 60) + "m ago";
    }

    function startDurationUpdater() {
        if (durationInterval) clearInterval(durationInterval);
        durationInterval = setInterval(function () {
            var els = container.querySelectorAll(".tile-alert-duration");
            els.forEach(function (el) {
                var start = parseInt(el.dataset.alertStart, 10);
                if (start) {
                    el.textContent = formatDuration(Date.now() - start);
                }
            });
        }, 1000);
    }

    function updateSummary(config) {
        var alerts = 0, offline = 0, monitoring = 0, total = 0;

        if (config && config.units) {
            config.units.forEach(function (unit) {
                unit.rooms.forEach(function (room) {
                    total++;
                    if (room.active_alert) {
                        alerts++;
                    } else if (room.nuc_status === "offline") {
                        offline++;
                    } else if (room.nuc_status === "online") {
                        monitoring++;
                    }
                });
            });
        }

        document.getElementById("summary-alert-count").textContent = alerts;
        document.getElementById("summary-offline-count").textContent = offline;
        document.getElementById("summary-monitoring-count").textContent = monitoring;
        document.getElementById("summary-total-count").textContent = total;

        var alertItem = document.querySelector(".summary-alerts");
        if (alerts > 0) {
            alertItem.classList.add("has-alerts");
        } else {
            alertItem.classList.remove("has-alerts");
        }
    }

    function getTileState(room) {
        var monType = room.monitoring_type || "bed";
        var exitLabel = monType === "chair" ? "Chair\nExit" : "Bed\nExit";

        // Active alert takes priority
        if (room.active_alert === "highRisk") {
            return {
                panelState: "highRisk",
                label: exitLabel,
                statusText: "High",
                statusClass: "high"
            };
        }
        if (room.active_alert === "lowRisk") {
            return {
                panelState: "lowRisk",
                label: exitLabel,
                statusText: "Low",
                statusClass: "low"
            };
        }

        // NUC status states
        switch (room.nuc_status) {
            case "paused":
                return {
                    panelState: "paused",
                    label: "Paused",
                    statusText: "",
                    statusClass: ""
                };
            case "calibration":
                return {
                    panelState: "calibration",
                    label: "Calibration",
                    statusText: "",
                    statusClass: ""
                };
            case "deactivated":
                return {
                    panelState: "deactivated",
                    label: "Deactivated",
                    statusText: "",
                    statusClass: ""
                };
            case "offline":
                return {
                    panelState: "offline",
                    label: "System\nDisconnected",
                    statusText: "",
                    statusClass: ""
                };
            case "no_device":
            case "unregistered":
                return {
                    panelState: "no_device",
                    label: "No Sensor",
                    statusText: "",
                    statusClass: ""
                };
            default:
                // Normal / online — just "Monitoring"
                return {
                    panelState: "normal",
                    label: monType === "chair" ? "Chair\nMonitoring" : "Bed\nMonitoring",
                    statusText: "",
                    statusClass: ""
                };
        }
    }

    function updateRoom(roomId, updates) {
        // Track alert timestamps on updates
        if (updates.active_alert && !alertTimestamps[roomId]) {
            alertTimestamps[roomId] = Date.now();
        } else if (updates.active_alert === null) {
            delete alertTimestamps[roomId];
        }

        var tile = container.querySelector('[data-room-id="' + roomId + '"]');
        if (!tile) return;

        // Find the room data in the grid, rebuild the tile
        var parent = tile.parentElement;
        var newRoom = Object.assign({}, getRoomDataFromTile(tile), updates);
        var newTile = createTile(newRoom);
        parent.replaceChild(newTile, tile);

        // Re-sort: move alerting tiles to top within their grid
        resortGrid(parent);

        // Update summary from last config
        updateSummaryFromDOM();
    }

    function resortGrid(gridEl) {
        if (!gridEl || !gridEl.classList.contains("room-grid")) return;
        var tiles = Array.from(gridEl.children);
        var priority = { "state-highRisk": 0, "state-lowRisk": 1 };

        tiles.sort(function (a, b) {
            var pa = 2, pb = 2;
            var panelA = a.querySelector(".tile-icon-panel");
            var panelB = b.querySelector(".tile-icon-panel");
            if (panelA) {
                if (panelA.classList.contains("state-highRisk")) pa = 0;
                else if (panelA.classList.contains("state-lowRisk")) pa = 1;
            }
            if (panelB) {
                if (panelB.classList.contains("state-highRisk")) pb = 0;
                else if (panelB.classList.contains("state-lowRisk")) pb = 1;
            }
            return pa - pb;
        });

        tiles.forEach(function (t) { gridEl.appendChild(t); });
    }

    function updateSummaryFromDOM() {
        var alerts = 0, offline = 0, monitoring = 0, total = 0;
        var tiles = container.querySelectorAll(".room-tile");
        tiles.forEach(function (tile) {
            total++;
            if (tile.classList.contains("alert-active")) {
                alerts++;
            } else if (tile.classList.contains("device-offline")) {
                offline++;
            } else if (tile.classList.contains("device-online")) {
                monitoring++;
            }
        });

        document.getElementById("summary-alert-count").textContent = alerts;
        document.getElementById("summary-offline-count").textContent = offline;
        document.getElementById("summary-monitoring-count").textContent = monitoring;
        document.getElementById("summary-total-count").textContent = total;

        var alertItem = document.querySelector(".summary-alerts");
        if (alerts > 0) {
            alertItem.classList.add("has-alerts");
        } else {
            alertItem.classList.remove("has-alerts");
        }
    }

    function getRoomDataFromTile(tile) {
        var roomId = parseInt(tile.dataset.roomId, 10);
        var iconPanel = tile.querySelector(".tile-icon-panel");
        var roomNum = tile.querySelector(".tile-room-number");

        return {
            room_id: roomId,
            name: roomNum ? roomNum.textContent : "",
            nuc_status: extractNucStatus(tile),
            active_alert: extractAlertState(tile),
            monitoring_type: extractMonitoringType(iconPanel)
        };
    }

    function extractNucStatus(tile) {
        var classes = tile.className;
        if (classes.includes("device-offline")) return "offline";
        if (classes.includes("device-no_device")) return "no_device";
        if (classes.includes("device-paused")) return "paused";
        if (classes.includes("device-calibration")) return "calibration";
        if (classes.includes("device-deactivated")) return "deactivated";
        return "online";
    }

    function extractAlertState(tile) {
        if (tile.classList.contains("alert-active")) {
            var panel = tile.querySelector(".tile-icon-panel");
            if (panel.classList.contains("state-highRisk")) return "highRisk";
            if (panel.classList.contains("state-lowRisk")) return "lowRisk";
        }
        return null;
    }

    function extractMonitoringType(panel) {
        if (!panel) return "bed";
        var img = panel.querySelector(".tile-icon");
        if (img && img.src && img.src.includes("chair")) return "chair";
        return "bed";
    }

    function onAcknowledge(room) {
        if (ackedAlerts.has(room.room_id)) return;
        ackedAlerts.add(room.room_id);

        var tile = container.querySelector('[data-room-id="' + room.room_id + '"]');
        if (tile) tile.classList.add("tile-acked");

        KioskWS.send({
            type: "ack",
            alert_id: room._alert_id || ""
        });
    }

    function clearAck(roomId) {
        ackedAlerts.delete(roomId);
    }

    function removeRoom(roomId) {
        delete alertTimestamps[roomId];
        var tile = container.querySelector('[data-room-id="' + roomId + '"]');
        if (tile) tile.remove();
        updateSummaryFromDOM();
    }

    // Store last config for reference
    var lastConfig = null;

    function getLastConfig() {
        return lastConfig;
    }

    function setLastConfig(config) {
        lastConfig = config;
    }

    return {
        renderFullGrid: renderFullGrid,
        updateRoom: updateRoom,
        removeRoom: removeRoom,
        clearAck: clearAck,
        getLastConfig: getLastConfig,
        setLastConfig: setLastConfig
    };
})();
