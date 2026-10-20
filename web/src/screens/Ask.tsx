import { useState } from "react";
import { ApiError, planRide } from "../api";
import { ArrowRight, Camera, Warning } from "../components/Icons";
import type { Bike, ProgressEvent, RidePlan } from "../types";

/** Screen 3: one box, one button. */

interface Props {
  bike: Bike;
  routingConfigured: boolean;
  onPlanned: (plan: RidePlan) => void;
  onEditBike: () => void;
}

const EXAMPLES = [
  "Twisty backroads this Saturday, about 250 km, home before dark",
  "Short evening blast, an hour or so",
  "All day Sunday, mountains, I do not mind the cold",
  "Somewhere with a view for lunch, 150 km",
];

/** The eight planner nodes, in the order the graph runs them. */
const STEPS = ["intake", "routes", "weather", "choose", "fuel", "gear", "briefing", "assemble"];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function Ask({ bike, routingConfigured, onPlanned, onEditBike }: Props) {
  const [prompt, setPrompt] = useState("");
  const [rideDate, setRideDate] = useState(today);
  const [distance, setDistance] = useState(250);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setProgress([]);
    try {
      const plan = await planRide(
        {
          prompt,
          bike_id: bike.id,
          start_place: "",
          distance_km: distance,
          ride_date: rideDate,
          earliest: "08:00",
          latest: "19:00",
          avoid_highways: true,
          prefer_twisty: true,
        },
        { onProgress: (event) => setProgress((p) => [...p, event]) },
      );
      onPlanned(plan);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The planner could not be reached.");
    } finally {
      setBusy(false);
    }
  };

  const doneNodes = new Set(progress.map((p) => p.node));
  const nextNode = STEPS.find((s) => !doneNodes.has(s));

  return (
    <div className="page" style={{ maxWidth: 740 }}>
      {!routingConfigured && (
        <p className="note note--warn" style={{ marginBottom: 24 }}>
          <Warning size={17} />
          <span>
            No OpenRouteService key is set, so routes cannot be built. Add{" "}
            <code>RIDEWISE_ORS_API_KEY</code> to <code>.env</code> and restart the API — a free key
            comes from openrouteservice.org.
          </span>
        </p>
      )}

      <button
        type="button"
        className="chip"
        onClick={onEditBike}
        style={{ marginBottom: 24, padding: "7px 15px 7px 7px" }}
      >
        {bike.photo_url ? (
          <img
            src={bike.photo_url}
            alt=""
            style={{ width: 38, height: 38, borderRadius: "var(--r-pill)", objectFit: "cover" }}
          />
        ) : (
          <span
            style={{
              display: "grid",
              placeItems: "center",
              width: 38,
              height: 38,
              borderRadius: "var(--r-pill)",
              background: "var(--mist)",
              color: "var(--muted-2)",
            }}
          >
            <Camera size={18} />
          </span>
        )}
        <span style={{ fontWeight: 600 }}>{bike.label}</span>
        <span className="muted">{Math.round(bike.range_km)} km range</span>
        <span style={{ color: "var(--brand-dark)", fontWeight: 600 }}>Change</span>
      </button>

      <h1 style={{ fontWeight: 800, fontSize: 38, lineHeight: 1.08, marginBottom: 22 }}>
        What do you feel like riding?
      </h1>

      <form onSubmit={run}>
        <label className="sr-only" htmlFor="ask">
          Describe the ride you want
        </label>
        <textarea
          id="ask"
          className="textarea"
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Twisty backroads this Saturday, about 250 km, home before dark."
          style={{ fontSize: 17, padding: "16px 18px", borderRadius: "var(--r-lg)" }}
          disabled={busy}
        />

        <p className="label" style={{ margin: "18px 0 10px" }}>
          Or start from one of these
        </p>
        <div className="row" style={{ gap: 9 }}>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className={`chip${prompt === example ? " chip--on" : ""}`}
              onClick={() => setPrompt(example)}
              disabled={busy}
            >
              {example}
            </button>
          ))}
        </div>

        <div className="row" style={{ gap: 16, marginTop: 24, alignItems: "flex-end" }}>
          <div style={{ flex: "0 1 180px", minWidth: 0 }}>
            <label className="label" htmlFor="when">
              Date
            </label>
            <input
              id="when"
              className="input"
              type="date"
              value={rideDate}
              min={today()}
              onChange={(e) => setRideDate(e.target.value)}
              disabled={busy}
            />
          </div>
          <div style={{ flex: "0 1 150px", minWidth: 0 }}>
            <label className="label" htmlFor="far">
              Distance, km
            </label>
            <input
              id="far"
              className="input"
              type="number"
              min={20}
              max={1200}
              step={10}
              value={distance}
              onChange={(e) => setDistance(Number(e.target.value))}
              disabled={busy}
            />
          </div>
          <p className="hint" style={{ flex: "1 1 160px", margin: 0 }}>
            Anything you type above overrides these.
          </p>
        </div>

        <div className="row" style={{ gap: 16, alignItems: "center", marginTop: 28 }}>
          <button type="submit" className="btn" disabled={busy || !routingConfigured}>
            {busy ? "Planning…" : "Find rides"}
            {!busy && <ArrowRight size={18} />}
          </button>
          {!busy && <p className="hint" style={{ margin: 0 }}>About ten seconds.</p>}
        </div>
      </form>

      {error && (
        <p className="note note--error" style={{ marginTop: 24 }}>
          <Warning size={17} />
          <span>{error}</span>
        </p>
      )}

      {busy && (
        <div className="card" style={{ marginTop: 28 }}>
          <div className="loading" aria-live="polite">
            {STEPS.map((node) => {
              const event = progress.find((p) => p.node === node);
              const state = event ? "done" : node === nextNode ? "now" : "";
              return (
                <div key={node} className={`step${state ? ` step--${state}` : ""}`}>
                  <span className="step__dot" />
                  <span style={{ color: state ? "var(--ink)" : "var(--muted-2)" }}>
                    {event?.lines[0] ?? event?.label ?? labelFor(node)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function labelFor(node: string): string {
  const labels: Record<string, string> = {
    intake: "Reading the request",
    routes: "Building candidate loops",
    weather: "Checking the weather window",
    choose: "Choosing the best ride",
    fuel: "Planning fuel stops",
    gear: "Writing the gear checklist",
    briefing: "Writing your briefing",
    assemble: "Finishing up",
  };
  return labels[node] ?? node;
}
