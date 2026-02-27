/**
 * Combined hikes & runs map. Load this after Leaflet.
 * Expects: <div id="combined-map-container"></div>
 * Fetches _map-section.html into the container, then builds the map.
 */
(function () {
  var CONTAINER_ID = 'combined-map-container';
  var MAP_ID = 'combined-map';
  var HIKES_COLOR = '#c94f1e';
  var RUNS_COLOR = '#1e5fc9';
  var SNOW_COLOR = '#0d9488';

  function parseGpxToLatLngs(gpxText) {
    var parser = new DOMParser();
    var doc = parser.parseFromString(gpxText, 'application/xml');
    var ns = 'http://www.topografix.com/GPX/1/1';
    var pts = doc.getElementsByTagNameNS(ns, 'trkpt');
    if (!pts.length) pts = doc.querySelectorAll('trkpt');
    var latlngs = [];
    for (var i = 0; i < pts.length; i++) {
      var lat = parseFloat(pts[i].getAttribute('lat'));
      var lon = parseFloat(pts[i].getAttribute('lon'));
      if (!isNaN(lat) && !isNaN(lon)) latlngs.push([lat, lon]);
    }
    return latlngs;
  }

  function extendBounds(bounds, latlngs) {
    if (!latlngs.length) return bounds;
    if (!bounds) return L.latLngBounds(latlngs);
    for (var b = 0; b < latlngs.length; b++) bounds.extend(latlngs[b]);
    return bounds;
  }

  var container = document.getElementById(CONTAINER_ID);
  if (!container) return;

  fetch('./_map-section.html')
    .then(function (r) { return r.text(); })
    .then(function (html) {
      container.innerHTML = html;
      var mapEl = document.getElementById(MAP_ID);
      var root = document.getElementById('combined-map-root');
      if (!mapEl || !root) return;
      if (typeof L === 'undefined') {
        var loading = mapEl.querySelector('.heatmap-loading');
        if (loading) loading.textContent = 'Map unavailable (Leaflet required).';
        return;
      }

      Promise.all([
        fetch('./hikes/hikes.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }),
        fetch('./runs/runs.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }),
        fetch('./snow-sports/snow-sports.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; })
      ]).then(function (results) {
        var hikes = (results[0] && results[0].hikes) ? results[0].hikes : [];
        var runs = (results[1] && results[1].runs) ? results[1].runs : [];
        var snow = (results[2] && results[2].activities) ? results[2].activities : [];

        var allBounds = null;
        var hikesLayer = L.layerGroup();
        var runsLayer = L.layerGroup();
        var snowLayer = L.layerGroup();
        var combinedMap = L.map(MAP_ID, { zoomControl: false }).setView([40, -98], 4);
        combinedMap.addControl(L.control.zoom({ position: 'topright' }));
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        }).addTo(combinedMap);
        combinedMap.addLayer(hikesLayer);
        combinedMap.addLayer(runsLayer);
        combinedMap.addLayer(snowLayer);

        var filterHikes = root.querySelector('[data-map-filter="hikes"]');
        var filterRuns = root.querySelector('[data-map-filter="runs"]');
        var filterSnow = root.querySelector('[data-map-filter="snow"]');
        if (filterHikes) filterHikes.addEventListener('change', function () {
          if (this.checked) combinedMap.addLayer(hikesLayer); else combinedMap.removeLayer(hikesLayer);
        });
        if (filterRuns) filterRuns.addEventListener('change', function () {
          if (this.checked) combinedMap.addLayer(runsLayer); else combinedMap.removeLayer(runsLayer);
        });
        if (filterSnow) filterSnow.addEventListener('change', function () {
          if (this.checked) combinedMap.addLayer(snowLayer); else combinedMap.removeLayer(snowLayer);
        });

        var heatLoading = mapEl.querySelector('.heatmap-loading');
        var pending = hikes.length + snow.length;
        var mapReady = false;

        function oneRouteLoaded() {
          pending--;
          if (pending > 0) return;
          mapReady = true;
          if (heatLoading) heatLoading.remove();
          if (allBounds && allBounds.isValid()) combinedMap.fitBounds(allBounds, { padding: [30, 30], maxZoom: 14 });
        }

        for (var r = 0; r < runs.length; r++) {
          var run = runs[r];
          if (run.track && run.track.length) {
            allBounds = extendBounds(allBounds, run.track);
            L.polyline(run.track, { color: RUNS_COLOR, weight: 3, opacity: 0.9 }).addTo(runsLayer);
          }
        }

        for (var j = 0; j < hikes.length; j++) {
          (function (idx) {
            var gpxUrl = './' + encodeURIComponent(hikes[idx].gpxPath).replace(/%2F/g, '/');
            fetch(gpxUrl)
              .then(function (r) { return r.text(); })
              .then(function (gpxText) {
                var latlngs = parseGpxToLatLngs(gpxText);
                if (latlngs.length) {
                  allBounds = extendBounds(allBounds, latlngs);
                  L.polyline(latlngs, { color: HIKES_COLOR, weight: 3, opacity: 0.9 }).addTo(hikesLayer);
                }
                oneRouteLoaded();
              })
              .catch(function () { oneRouteLoaded(); });
          })(j);
        }

        for (var s = 0; s < snow.length; s++) {
          (function (idx) {
            var gpxUrl = './' + encodeURIComponent(snow[idx].gpxPath).replace(/%2F/g, '/');
            fetch(gpxUrl)
              .then(function (r) { return r.text(); })
              .then(function (gpxText) {
                var latlngs = parseGpxToLatLngs(gpxText);
                if (latlngs.length) {
                  allBounds = extendBounds(allBounds, latlngs);
                  L.polyline(latlngs, { color: SNOW_COLOR, weight: 3, opacity: 0.9 }).addTo(snowLayer);
                }
                oneRouteLoaded();
              })
              .catch(function () { oneRouteLoaded(); });
          })(s);
        }

        if (pending === 0) {
          if (heatLoading) heatLoading.remove();
          if (allBounds && allBounds.isValid()) combinedMap.fitBounds(allBounds, { padding: [30, 30], maxZoom: 14 });
        }
      }).catch(function () {
        var loading = mapEl.querySelector('.heatmap-loading');
        if (loading) loading.textContent = 'Could not load routes.';
      });
    })
    .catch(function () {
      container.innerHTML = '<p class="heatmap-loading">Could not load map section.</p>';
    });
})();
