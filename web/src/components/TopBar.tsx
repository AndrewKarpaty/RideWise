import { Wheel } from "./Icons";
import type { View } from "../App";

interface Props {
  view: View;
  onNavigate: (view: View) => void;
  rider?: string;
  onSignOut?: () => void;
}

const TABS: { view: View; label: string }[] = [
  { view: "cabinet", label: "My moto" },
  { view: "ask", label: "Ask" },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "R";
  return parts
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export function TopBar({ view, onNavigate, rider, onSignOut }: Props) {
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <button
          type="button"
          className="brand"
          onClick={() => onNavigate("ask")}
          style={{ background: "none", border: 0, cursor: "pointer", padding: 0 }}
        >
          <Wheel size={25} />
          Ride<span>wise</span>
        </button>

        <nav aria-label="Main" style={{ display: "flex", gap: 4 }}>
          {TABS.map((tab) => (
            <button
              key={tab.view}
              type="button"
              className={`navlink${view === tab.view || (tab.view === "ask" && view === "options") ? " navlink--on" : ""}`}
              aria-current={view === tab.view ? "page" : undefined}
              onClick={() => onNavigate(tab.view)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="spacer" />

        {rider && (
          <>
            <button
              type="button"
              className="navlink"
              onClick={onSignOut}
              style={{ fontSize: 13 }}
            >
              Sign out
            </button>
            <span className="avatar" title={rider}>
              {initials(rider)}
            </span>
          </>
        )}
      </div>
    </header>
  );
}
