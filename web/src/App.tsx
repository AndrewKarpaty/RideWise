import { useEffect, useState } from "react";
import { getBikes, getHealth } from "./api";
import { TopBar } from "./components/TopBar";
import { Warning } from "./components/Icons";
import { Ask } from "./screens/Ask";
import { Cabinet } from "./screens/Cabinet";
import { Login } from "./screens/Login";
import { Options } from "./screens/Options";
import type { Bike, RidePlan } from "./types";

export type View = "login" | "cabinet" | "ask" | "options";

const RIDER_KEY = "ridewise.rider";

/** Four screens in a line, so the whole app is one small state machine rather
 *  than a router. The hash is kept in step so reload and the back button land
 *  somewhere sensible. */
export default function App() {
  const [rider, setRider] = useState<string | null>(() => localStorage.getItem(RIDER_KEY));
  const [view, setView] = useState<View>(() => (localStorage.getItem(RIDER_KEY) ? "ask" : "login"));
  const [bike, setBike] = useState<Bike | null>(null);
  const [plan, setPlan] = useState<RidePlan | null>(null);
  const [routingConfigured, setRoutingConfigured] = useState(true);
  const [fatal, setFatal] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Which bike are we riding, and is routing even available?
  useEffect(() => {
    if (!rider) {
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const [health, bikes] = await Promise.all([getHealth(), getBikes()]);
        setRoutingConfigured(health.routing_configured);
        const first = bikes[0] ?? null;
        setBike(first);
        setView(first ? "ask" : "cabinet");
      } catch {
        setFatal(
          "The API is not responding. Start it with `make api` and make sure it is on port 8000.",
        );
      } finally {
        setLoading(false);
      }
    })();
  }, [rider]);

  // Keep the hash in step, and follow it when the user goes back.
  useEffect(() => {
    if (window.location.hash.slice(1) !== view) {
      window.history.replaceState(null, "", `#${view}`);
    }
  }, [view]);

  useEffect(() => {
    const onHash = () => {
      const target = window.location.hash.slice(1) as View;
      if (target === "options" && !plan) return;
      if (["login", "cabinet", "ask", "options"].includes(target)) setView(target);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [plan]);

  const signIn = (name: string) => {
    localStorage.setItem(RIDER_KEY, name);
    setRider(name);
    setLoading(true);
  };

  const signOut = () => {
    localStorage.removeItem(RIDER_KEY);
    setRider(null);
    setBike(null);
    setPlan(null);
    setView("login");
  };

  if (!rider) return <Login onContinue={signIn} />;

  return (
    <div className="shell">
      <TopBar view={view} onNavigate={setView} rider={rider} onSignOut={signOut} />

      {fatal && (
        <div className="page" style={{ paddingBottom: 0 }}>
          <p className="note note--error">
            <Warning size={17} />
            <span>{fatal}</span>
          </p>
        </div>
      )}

      {loading && !fatal && (
        <div className="page">
          <p className="muted">Loading your garage…</p>
        </div>
      )}

      {!loading && !fatal && (
        <>
          {view === "cabinet" && (
            <Cabinet
              onReady={(ready) => {
                setBike(ready);
                setView("ask");
              }}
            />
          )}

          {view === "ask" &&
            (bike ? (
              <Ask
                bike={bike}
                routingConfigured={routingConfigured}
                onEditBike={() => setView("cabinet")}
                onPlanned={(made) => {
                  setPlan(made);
                  setView("options");
                }}
              />
            ) : (
              <div className="page">
                <p className="note note--warn">
                  <Warning size={17} />
                  <span>
                    Add a motorcycle first — the fuel stops and the gear list both come from it.
                  </span>
                </p>
                <button type="button" className="btn" onClick={() => setView("cabinet")}>
                  Add a motorcycle
                </button>
              </div>
            ))}

          {view === "options" &&
            (plan ? (
              <Options plan={plan} onAskAgain={() => setView("ask")} />
            ) : (
              <div className="page">
                <p className="muted">No plan yet.</p>
              </div>
            ))}
        </>
      )}
    </div>
  );
}
