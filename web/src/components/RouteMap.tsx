import type { FuelStop, LegForecast, Point } from "../types";

/** Draws the real routed geometry as an SVG polyline.
 *
 *  There is no tile basemap here on purpose: the geometry the planner returns
 *  is the thing worth looking at, and an SVG needs no map library, no API key
 *  and no attribution. Swapping in MapLibre or Leaflet later only means
 *  replacing this component — nothing else reads the geometry. */

interface Props {
  geometry: Point[];
  fuelStops?: FuelStop[];
  legs?: LegForecast[];
  height?: number;
  /** Shows km marks and fuel labels. Off for small previews. */
  detailed?: boolean;
}

const PAD = 26;
const W = 640;

export function RouteMap({
  geometry,
  fuelStops = [],
  legs = [],
  height = 400,
  detailed = true,
}: Props) {
  if (geometry.length < 2) {
    return (
      <div
        style={{
          height,
          display: "grid",
          placeItems: "center",
          background: "var(--mist)",
          color: "var(--muted)",
          fontSize: 14,
        }}
      >
        No route geometry
      </div>
    );
  }

  const lats = geometry.map((p) => p[0]);
  const lons = geometry.map((p) => p[1]);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  // Longitude degrees shrink towards the poles, so scale them by cos(lat) or
  // the loop comes out stretched sideways.
  const kx = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  const spanX = Math.max((maxLon - minLon) * kx, 1e-6);
  const spanY = Math.max(maxLat - minLat, 1e-6);

  // The viewBox follows the loop's own aspect ratio, clamped so a very flat
  // route still gets a usable height.
  const viewH = Math.min(
    Math.max(Math.round((W - PAD * 2) * (spanY / spanX)) + PAD * 2, 220),
    Math.round(W * 1.1),
  );
  const scale = Math.min((W - PAD * 2) / spanX, (viewH - PAD * 2) / spanY);
  const offX = (W - spanX * scale) / 2;
  const offY = (viewH - spanY * scale) / 2;

  const project = (lat: number, lon: number): [number, number] => [
    offX + (lon - minLon) * kx * scale,
    offY + (maxLat - lat) * scale,
  ];

  const d =
    geometry
      .map(([lat, lon], i) => {
        const [x, y] = project(lat, lon);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ") + " Z";

  const [sx, sy] = project(geometry[0]![0], geometry[0]![1]);

  return (
    <svg
      viewBox={`0 0 ${W} ${viewH}`}
      style={{ display: "block", width: "100%", height: "auto", background: "#edf1f7" }}
      role="img"
      aria-label={`Route loop of ${geometry.length} points with ${fuelStops.length} fuel stop${
        fuelStops.length === 1 ? "" : "s"
      }.`}
    >
      {/* casing under the line, so the route reads against the background */}
      <path d={d} stroke="#1d3a94" strokeWidth={9} fill="none" strokeLinejoin="round" />
      <path d={d} stroke="#3564e4" strokeWidth={5} fill="none" strokeLinejoin="round" />

      {legs.slice(1, -1).map((leg) => {
        const [x, y] = project(leg.lat, leg.lon);
        return (
          <g key={`leg-${leg.distance_along_km}`}>
            <circle cx={x} cy={y} r={11} fill="#fff" stroke="#0e1420" strokeWidth={2.4} />
            {detailed && (
              <text
                x={x}
                y={y + 4}
                textAnchor="middle"
                fontFamily="Inter, sans-serif"
                fontSize={10}
                fontWeight={700}
                fill="#0e1420"
              >
                {Math.round(leg.distance_along_km)}
              </text>
            )}
          </g>
        );
      })}

      {fuelStops.map((stop) => {
        const [x, y] = project(stop.lat, stop.lon);
        return (
          <g key={`fuel-${stop.lat}-${stop.lon}`}>
            <circle cx={x} cy={y} r={14} fill="#0e9f6e" stroke="#fff" strokeWidth={3} />
            <path
              d={`M${x - 5} ${y - 7}v13M${x - 5} ${y - 7}h7v6h-7M${x + 4} ${y - 4}h2.6v7.5a1.4 1.4 0 0 0 2.6 0v-5l-1.7-2.5`}
              stroke="#fff"
              strokeWidth={1.7}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </g>
        );
      })}

      <g>
        <circle cx={sx} cy={sy} r={16} fill="#0e1420" stroke="#fff" strokeWidth={3.4} />
        <path
          d={`M${sx - 7} ${sy + 4}h5l3-5h-3M${sx + 2} ${sy - 1}l2.4 5M${sx + 2.5} ${sy - 5}h2.4l1 3`}
          stroke="#fff"
          strokeWidth={1.6}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}
