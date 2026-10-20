import { WeatherIcon, weatherColour } from "./Icons";
import type { LegForecast } from "../types";

/** The forecast at each sampled point, at the hour the rider reaches it.
 *  This is the one view no competitor shows, so it earns its space. */
export function WeatherStrip({ legs }: { legs: LegForecast[] }) {
  if (!legs.length) return null;

  return (
    <div className="weather" style={{ ["--cols" as string]: String(legs.length) }}>
      {legs.map((leg) => {
        const w = leg.weather;
        const wet = w.precipitation_probability >= 50 || w.weather_code >= 51;
        return (
          <div
            key={`${leg.distance_along_km}-${leg.eta}`}
            className={`weather__cell${wet ? " weather__cell--wet" : ""}`}
          >
            <p className="weather__t">{formatTime(leg.eta)}</p>
            <div style={{ color: weatherColour(w.weather_code), margin: "5px 0" }}>
              <WeatherIcon code={w.weather_code} />
            </div>
            <p className="weather__deg">{Math.round(w.apparent_temperature_c)}&deg;</p>
            <p className="weather__km">
              km {Math.round(leg.distance_along_km)}
              {w.precipitation_probability >= 30
                ? ` · ${Math.round(w.precipitation_probability)}%`
                : ""}
            </p>
          </div>
        );
      })}
    </div>
  );
}

/** The API sends local naive timestamps, so trim rather than parse into a
 *  Date — constructing one would reinterpret it in the browser's zone. */
export function formatTime(iso: string): string {
  const t = iso.includes("T") ? iso.split("T")[1] : iso;
  return (t ?? iso).slice(0, 5);
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}
