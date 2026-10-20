import { useState } from "react";
import { RouteMap } from "../components/RouteMap";
import { WeatherStrip, formatDate, formatTime } from "../components/WeatherStrip";
import { Check, Fuel, Warning } from "../components/Icons";
import type { RidePlan, RouteCandidate, WeatherWindow } from "../types";

/** Screen 4: the options, best first. */

interface Props {
  plan: RidePlan;
  onAskAgain: () => void;
}

function scoreClass(score: number): string {
  if (score >= 75) return "score--good";
  if (score >= 50) return "score--ok";
  return "score--poor";
}

export function Options({ plan, onAskAgain }: Props) {
  const { route, alternatives, weather, weather_options: windows } = plan;
  const [windowIndex, setWindowIndex] = useState(0);

  // Each option already carries its own legs, so switching departure is free.
  const shown: WeatherWindow | null = windows[windowIndex] ?? weather;

  return (
    <div className="page">
      <div className="row" style={{ alignItems: "baseline", gap: 14, marginBottom: 24 }}>
        <h1 style={{ fontWeight: 800, fontSize: 34 }}>
          {alternatives.length + 1} ride{alternatives.length ? "s" : ""} for{" "}
          {formatDate(plan.request.ride_date)}
        </h1>
        <p className="muted" style={{ flex: "1 1 220px", margin: 0, fontSize: 14.5 }}>
          {plan.request.raw_text ? `“${plan.request.raw_text}” · ` : ""}
          <button
            type="button"
            onClick={onAskAgain}
            style={{
              background: "none",
              border: 0,
              padding: 0,
              font: "inherit",
              color: "var(--brand-dark)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            ask differently
          </button>
        </p>
      </div>

      {plan.warnings.map((warning) => (
        <p key={warning} className="note note--warn" style={{ marginBottom: 14 }}>
          <Warning size={17} />
          <span>{warning}</span>
        </p>
      ))}

      {/* ---------------- the pick ---------------- */}
      <article className="card card--flush card--on" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", flexWrap: "wrap" }}>
          <div style={{ flex: "999 1 420px", minWidth: 0, position: "relative" }}>
            <RouteMap
              geometry={route.geometry}
              fuelStops={plan.fuel_stops}
              legs={shown?.legs ?? []}
            />
            <span
              className="tag tag--brand"
              style={{ position: "absolute", top: 14, left: 14 }}
            >
              Best match
            </span>
          </div>

          <div style={{ flex: "1 1 340px", minWidth: 0, padding: 24 }}>
            <div className="row" style={{ justifyContent: "space-between", gap: 16 }}>
              <div style={{ minWidth: 0 }}>
                <h2 style={{ fontWeight: 800, fontSize: 25 }}>
                  {Math.round(route.distance_km)} km {route.direction.toLowerCase()} loop
                </h2>
                {shown ? (
                  <p className="muted" style={{ margin: "5px 0 0", fontSize: 15 }}>
                    Leave <strong style={{ color: "var(--ink)" }}>{formatTime(shown.departure)}</strong> ·
                    back <strong style={{ color: "var(--ink)" }}>{formatTime(shown.arrival)}</strong>
                  </p>
                ) : (
                  <p className="muted" style={{ margin: "5px 0 0", fontSize: 15 }}>
                    No forecast for this date
                  </p>
                )}
              </div>
              {shown && (
                <div style={{ textAlign: "center", flex: "0 0 auto" }}>
                  <span className={`score ${scoreClass(shown.score)}`}>{Math.round(shown.score)}</span>
                  <p className="stat__k" style={{ marginTop: 5 }}>
                    Ride score
                  </p>
                </div>
              )}
            </div>

            {shown && (
              <>
                <p className="muted" style={{ margin: "14px 0 0", fontSize: 14 }}>
                  {shown.verdict}
                </p>
                <div style={{ margin: "18px 0" }}>
                  <WeatherStrip legs={shown.legs} />
                </div>
              </>
            )}

            {windows.length > 1 && (
              <div style={{ marginBottom: 18 }}>
                <p className="label" style={{ marginBottom: 8 }}>
                  Other departures
                </p>
                <div className="row" style={{ gap: 7 }}>
                  {windows.map((option, i) => (
                    <button
                      key={option.departure}
                      type="button"
                      className={`chip${i === windowIndex ? " chip--on" : ""}`}
                      onClick={() => setWindowIndex(i)}
                      style={{ padding: "7px 12px", fontSize: 13 }}
                    >
                      {formatTime(option.departure)}
                      <span className="muted" style={{ fontSize: 12.5 }}>
                        {Math.round(option.score)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <dl
              style={{
                margin: "0 0 18px",
                display: "grid",
                gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
                gap: 14,
              }}
            >
              <div>
                <dt className="stat__k">Corners</dt>
                <dd className="stat__v" style={{ color: "var(--brand)" }}>
                  {Math.round(route.twistiness)}&deg;/km
                </dd>
              </div>
              <div>
                <dt className="stat__k">Climb</dt>
                <dd className="stat__v">{Math.round(route.ascent_m)} m</dd>
              </div>
              <div>
                <dt className="stat__k">Moving</dt>
                <dd className="stat__v">{route.moving_duration_h.toFixed(1)} h</dd>
              </div>
            </dl>

            {plan.briefing && (
              <p className="note note--info" style={{ fontSize: 14.5, lineHeight: 1.6 }}>
                {plan.briefing}
              </p>
            )}
          </div>
        </div>

        {plan.fuel_stops.length > 0 && (
          <div style={{ borderTop: "1px solid var(--line)", padding: "18px 24px" }}>
            <p className="label" style={{ marginBottom: 12 }}>
              Fuel
            </p>
            {plan.fuel_stops.map((stop) => (
              <div
                key={`${stop.lat}-${stop.lon}`}
                style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 8 }}
              >
                <span
                  style={{
                    flex: "0 0 auto",
                    display: "grid",
                    placeItems: "center",
                    width: 34,
                    height: 34,
                    borderRadius: "var(--r-sm)",
                    background: "var(--go-soft)",
                    color: "var(--go-ink)",
                  }}
                >
                  <Fuel size={17} />
                </span>
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{stop.name}</p>
                  <p className="muted" style={{ margin: "2px 0 0", fontSize: 13 }}>
                    km {Math.round(stop.distance_along_km)}
                    {stop.detour_km > 0.02
                      ? ` · ${Math.round(stop.detour_km * 1000)} m off route`
                      : ""}
                    {stop.reason ? ` — ${stop.reason}` : ""}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </article>

      {/* ---------------- alternatives ---------------- */}
      {alternatives.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(alternatives.length, 2)}, minmax(0, 1fr))`,
            gap: 20,
          }}
        >
          {alternatives.map((alt) => (
            <Alternative
              key={alt.candidate_id}
              candidate={alt}
              window={plan.best_window_by_candidate[alt.candidate_id]}
            />
          ))}
        </div>
      )}

      {/* ---------------- gear ---------------- */}
      {plan.gear.length > 0 && <Gear plan={plan} />}

      <div className="row" style={{ justifyContent: "center", marginTop: 32 }}>
        <button type="button" className="btn btn--ghost" onClick={onAskAgain}>
          Plan another ride
        </button>
      </div>
    </div>
  );
}

function Alternative({
  candidate,
  window: option,
}: {
  candidate: RouteCandidate;
  window: WeatherWindow | undefined;
}) {
  return (
    <article className="card card--flush">
      <RouteMap geometry={candidate.geometry} height={210} detailed={false} />
      <div style={{ padding: 20 }}>
        <div className="row" style={{ justifyContent: "space-between", gap: 14 }}>
          <div style={{ minWidth: 0 }}>
            <h2 style={{ fontWeight: 800, fontSize: 20 }}>
              {Math.round(candidate.distance_km)} km {candidate.direction.toLowerCase()}
            </h2>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 14 }}>
              {option
                ? `Leave ${formatTime(option.departure)} · back ${formatTime(option.arrival)}`
                : "No forecast"}
            </p>
          </div>
          {option && (
            <span className={`score score--small ${scoreClass(option.score)}`}>
              {Math.round(option.score)}
            </span>
          )}
        </div>
        <div className="row" style={{ gap: 16, margin: "14px 0 0", fontSize: 13.5 }}>
          <span className="muted">
            <strong style={{ color: "var(--ink)" }}>{Math.round(candidate.twistiness)}&deg;/km</strong>{" "}
            corners
          </span>
          <span className="muted">
            <strong style={{ color: "var(--ink)" }}>{Math.round(candidate.ascent_m)} m</strong> climb
          </span>
        </div>
        {option && (
          <p className="muted" style={{ margin: "12px 0 0", fontSize: 14, lineHeight: 1.5 }}>
            {option.verdict}
          </p>
        )}
      </div>
    </article>
  );
}

function Gear({ plan }: { plan: RidePlan }) {
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const toggle = (item: string) =>
    setTicked((t) => {
      const next = new Set(t);
      if (next.has(item)) next.delete(item);
      else next.add(item);
      return next;
    });

  const essential = plan.gear.filter((g) => g.essential);
  const optional = plan.gear.filter((g) => !g.essential);

  return (
    <section className="card" style={{ marginTop: 20 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h2 style={{ fontWeight: 800, fontSize: 25 }}>Pack this</h2>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>
          {ticked.size} of {plan.gear.length} packed
        </p>
      </div>

      {[
        { title: "Essential", items: essential },
        { title: "Worth packing", items: optional },
      ]
        .filter((group) => group.items.length)
        .map((group) => (
          <div key={group.title} style={{ marginTop: 18 }}>
            <p
              className="stat__k"
              style={{ color: group.title === "Essential" ? "#b9500f" : "var(--muted)", marginBottom: 10 }}
            >
              {group.title}
            </p>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 10 }}>
              {group.items.map((g) => (
                <li key={g.item}>
                  <label style={{ display: "flex", gap: 11, alignItems: "flex-start", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={ticked.has(g.item)}
                      onChange={() => toggle(g.item)}
                      style={{ width: 17, height: 17, margin: "2px 0 0", accentColor: "var(--brand)" }}
                    />
                    <span>
                      <strong
                        style={{
                          fontWeight: 600,
                          fontSize: 15,
                          textDecoration: ticked.has(g.item) ? "line-through" : "none",
                          color: ticked.has(g.item) ? "var(--muted)" : "var(--ink)",
                        }}
                      >
                        {g.item}
                      </strong>
                      <br />
                      <span className="muted" style={{ fontSize: 13.5 }}>
                        {g.reason}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ))}

      {ticked.size === plan.gear.length && (
        <p className="note note--info" style={{ marginTop: 18, color: "var(--go-ink)" }}>
          <Check size={17} />
          <span>All packed. Have a good one.</span>
        </p>
      )}
    </section>
  );
}
