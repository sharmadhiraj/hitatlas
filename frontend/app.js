const REF_WIDTH = 960;
const PADDING = 20;
const ANTARCTICA_MAX_LAT = -60;
const ANTIMERIDIAN_SLIVER_MAX_POINTS = 50;

const svg = d3.select("#map-svg").attr("preserveAspectRatio", "xMidYMid meet");
const landPath = svg.append("path").attr("class", "land");
const pingsGroup = svg.append("g").attr("class", "pings");

const scale = (REF_WIDTH - 2 * PADDING) / (2 * Math.PI);
const projection = d3.geoEquirectangular().scale(scale);
const pathGenerator = d3.geoPath(projection);

function polygonMaxLat(polygon) {
  let maxLat = -Infinity;
  polygon.forEach((ring) => ring.forEach(([, lat]) => {
    if (lat > maxLat) maxLat = lat;
  }));
  return maxLat;
}

function touchesAntimeridian(polygon) {
  return polygon.some((ring) => ring.some(([lng]) => lng <= -179.9 || lng >= 179.9));
}

function polygonPointCount(polygon) {
  let count = 0;
  polygon.forEach((ring) => { count += ring.length; });
  return count;
}

d3.json("https://cdn.jsdelivr.net/npm/world-atlas@2/land-110m.json").then((topology) => {
  const landFeature = topojson.feature(topology, topology.objects.land).features[0];
  landFeature.geometry.coordinates = landFeature.geometry.coordinates.filter((polygon) => {
    if (polygonMaxLat(polygon) < ANTARCTICA_MAX_LAT) return false;
    if (touchesAntimeridian(polygon) && polygonPointCount(polygon) < ANTIMERIDIAN_SLIVER_MAX_POINTS) {
      return false;
    }
    return true;
  });

  const [[, minLat], [, maxLat]] = d3.geoBounds(landFeature);
  const toRad = (deg) => (deg * Math.PI) / 180;
  const topYRaw = -toRad(maxLat);
  const bottomYRaw = -toRad(minLat);
  const translateY = PADDING - topYRaw * scale;
  const refHeight = (bottomYRaw - topYRaw) * scale + 2 * PADDING;

  projection.translate([REF_WIDTH / 2, translateY]);
  svg.attr("viewBox", `0 0 ${REF_WIDTH} ${refHeight}`);
  landPath.attr("d", pathGenerator(landFeature));
});

const statusDot = document.getElementById("status-dot");
const statsSummaryEl = document.getElementById("stats-summary");
const statsTimeEl = document.getElementById("stats-time");
const feedPanel = document.querySelector(".feed");
const feedHeader = document.querySelector(".feed h2");
const feedList = document.getElementById("feed-list");

let hitCount = 0;
const uniqueIps = new Set();
const uniqueCountries = new Set();
const startTime = performance.now();

function formatPlace(hit) {
  const parts = [hit.city, hit.country].filter(Boolean);
  return parts.length ? parts.join(", ") : "Unknown location";
}

function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function updateStats() {
  const hits = `${hitCount} hit${hitCount === 1 ? "" : "s"}`;
  const users = `${uniqueIps.size} user${uniqueIps.size === 1 ? "" : "s"}`;
  const countries =
    uniqueCountries.size === 1 ? "1 country" : `${uniqueCountries.size} countries`;
  statsSummaryEl.textContent = `${hits} · ${users} · ${countries}`;
  statsTimeEl.textContent = `Live for ${formatDuration(performance.now() - startTime)}`;
}

function addFeedItem(hit) {
  const item = document.createElement("div");
  item.className = "feed-item";

  const place = document.createElement("span");
  place.className = "place";
  place.textContent = formatPlace(hit);

  const ip = document.createElement("span");
  ip.className = "ip";
  ip.textContent = hit.ip;

  item.appendChild(place);
  item.appendChild(ip);
  feedList.insertBefore(item, feedList.firstChild);

  const itemHeight = item.getBoundingClientRect().height;
  const availableHeight = feedPanel.clientHeight - feedHeader.offsetHeight;
  const maxItems =
    itemHeight > 0 ? Math.max(1, Math.floor(availableHeight / itemHeight)) : 10;

  while (feedList.children.length > maxItems) {
    feedList.removeChild(feedList.lastChild);
  }
}

function pingMap(hit) {
  const coords = projection([hit.lng, hit.lat]);
  if (!coords) return;
  const [x, y] = coords;

  const circle = pingsGroup
    .append("circle")
    .attr("cx", x)
    .attr("cy", y)
    .attr("r", 0)
    .attr("fill", "#f5f7fa");

  circle.append("title").text(`${formatPlace(hit)}\n${hit.ip}`);

  const start = performance.now();
  const popDuration = 120;
  const fadeDuration = 1400;
  const maxRadius = 4;

  function animate(now) {
    const elapsed = now - start;
    if (elapsed < popDuration) {
      circle.attr("r", maxRadius * (elapsed / popDuration)).attr("fill-opacity", 1);
    } else {
      const t = Math.min((elapsed - popDuration) / fadeDuration, 1);
      circle.attr("r", maxRadius).attr("fill-opacity", 1 - t);
    }
    if (elapsed < popDuration + fadeDuration) {
      requestAnimationFrame(animate);
    } else {
      circle.remove();
    }
  }
  requestAnimationFrame(animate);
}

let eventSource = null;

function connect() {
  if (eventSource) eventSource.close();

  eventSource = new EventSource("/events");

  eventSource.onopen = () => statusDot.classList.add("live");
  eventSource.onerror = () => statusDot.classList.remove("live");

  eventSource.onmessage = (event) => {
    const hit = JSON.parse(event.data);
    hitCount += 1;
    uniqueIps.add(hit.ip);
    if (hit.country) uniqueCountries.add(hit.country);
    updateStats();
    pingMap(hit);
    addFeedItem(hit);
  };
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && eventSource?.readyState !== EventSource.OPEN) {
    connect();
  }
});

connect();
updateStats();
setInterval(updateStats, 1000);
