const board = document.querySelector("#board");
const title = document.querySelector("#station-title");
const updated = document.querySelector("#updated");
const form = document.querySelector("#station-form");
const input = document.querySelector("#station-input");
const datalist = document.querySelector("#stations");

let currentStation = new URLSearchParams(window.location.search).get("station") || "Jamaica";
input.value = currentStation;

function fit(value, length) {
  const text = String(value || "").toUpperCase();
  return text.length > length ? text.slice(0, Math.max(0, length - 1)) + "." : text;
}

function flap(text, className = "") {
  const div = document.createElement("div");
  div.className = `flap ${className}`.trim();
  div.textContent = text;
  window.requestAnimationFrame(() => div.classList.add("flip"));
  return div;
}

function rowFor(item) {
  const row = document.createElement("article");
  row.className = "row";

  const route = document.createElement("div");
  route.className = "route";

  const swatch = document.createElement("div");
  swatch.className = "swatch";
  swatch.style.background = item.route_color;

  const routeFlap = flap(fit(item.route_name, 22));
  route.append(swatch, routeFlap);

  const destination = flap(fit(item.destination, 21), "destination");
  const time = flap(item.departure_time, "small");
  const minutes = flap(String(item.minutes), "small");
  const status = flap(fit(item.status, 10), "small status");

  row.append(route, destination, time, minutes, status);
  return row;
}

async function loadStations() {
  const response = await fetch("/api/stations");
  const data = await response.json();
  datalist.replaceChildren(
    ...data.stations.map((station) => {
      const option = document.createElement("option");
      option.value = station.stop_name;
      option.label = station.stop_code;
      return option;
    })
  );
}

async function refresh() {
  const response = await fetch(`/api/departures?station=${encodeURIComponent(currentStation)}&limit=12`);
  const data = await response.json();

  if (!response.ok) {
    board.innerHTML = `<div class="empty">${data.error || "Unable to load departures."}</div>`;
    return;
  }

  title.textContent = data.station.stop_name;
  board.replaceChildren(...data.departures.map(rowFor));

  if (!data.departures.length) {
    board.innerHTML = '<div class="empty">No more scheduled departures today.</div>';
  }

  const generated = new Date(data.generated_at);
  updated.textContent = `Updated ${generated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  currentStation = input.value.trim() || "Jamaica";
  const url = new URL(window.location);
  url.searchParams.set("station", currentStation);
  history.replaceState(null, "", url);
  refresh();
});

loadStations();
refresh();
setInterval(refresh, 30000);
