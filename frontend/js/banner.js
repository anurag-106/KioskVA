/**
 * Banner for alerts that have no tile in this kiosk's grid.
 *
 * The server's safety fallback routes alerts here when a NUC is unregistered,
 * has no room, or its unit has no connected kiosk. Those must still be seen.
 */
const Banner = (function () {

    const container = document.getElementById("fallback-alerts");
    const alerts = {};      // alert_id -> alert message
    const acked = new Set(); // alert_ids acknowledged at this kiosk

    const EVENT_LABELS = {
        gettingOutBed: "Getting Out of Bed",
        gotOutsideBed: "Got Out of Bed",
        gettingOutChair: "Getting Out of Chair",
        slidingOutChair: "Sliding Out of Chair",
        sittingInChair: "Sitting In Chair",
        fallen: "FALL DETECTED"
    };

    function setAll(list) {
        Object.keys(alerts).forEach(function (id) { delete alerts[id]; });
        (list || []).forEach(function (a) { alerts[a.alert_id] = a; });
        acked.forEach(function (id) { if (!alerts[id]) acked.delete(id); });
        render();
    }

    function add(alert) {
        alerts[alert.alert_id] = alert;
        render();
    }

    function remove(alertId) {
        delete alerts[alertId];
        acked.delete(alertId);
        render();
    }

    function locationText(a) {
        if (a.room_id != null && a.room_name && a.room_name !== "Unknown") {
            return a.room_name + (a.unit_name && a.unit_name !== "Unknown" ? " · " + a.unit_name : "");
        }
        return "Unassigned sensor " + (a.device_id || "?");
    }

    function render() {
        container.innerHTML = "";
        var ids = Object.keys(alerts);
        container.classList.toggle("hidden", ids.length === 0);

        ids.forEach(function (id) {
            var a = alerts[id];
            var item = document.createElement("div");
            item.className = "fallback-alert level-" + (a.alert_level || "highRisk");
            if (acked.has(id)) item.classList.add("acked");

            var label = document.createElement("strong");
            label.textContent = "ALERT";
            var where = document.createElement("span");
            where.className = "fallback-where";
            where.textContent = locationText(a);
            var what = document.createElement("span");
            what.className = "fallback-event";
            what.textContent = EVENT_LABELS[a.event_type] || a.event_type || "";

            item.appendChild(label);
            item.appendChild(where);
            item.appendChild(what);
            item.addEventListener("click", function () {
                if (acked.has(id)) return;
                acked.add(id);
                item.classList.add("acked");
                KioskWS.send({ type: "ack", alert_id: id, room_id: a.room_id });
            });
            container.appendChild(item);
        });
    }

    return { setAll: setAll, add: add, remove: remove };
})();
