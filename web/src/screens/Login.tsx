import { useState } from "react";
import { Wheel, Warning } from "../components/Icons";

/** Screen 1.
 *
 *  Accounts are not built yet (backlog #14), so this is deliberately a local
 *  gate: it remembers a name in this browser and nothing more. There is no
 *  password field, because one that goes nowhere is worse than none — it would
 *  teach people to type a real password into a form that does not protect it. */

interface Props {
  onContinue: (name: string) => void;
}

export function Login({ onContinue }: Props) {
  const [name, setName] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onContinue(name.trim() || "Rider");
  };

  return (
    <div style={{ minHeight: "100%", display: "flex", flexWrap: "wrap" }}>
      {/* brand side */}
      <div
        style={{
          flex: "1 1 420px",
          minWidth: 0,
          position: "relative",
          overflow: "hidden",
          background: "var(--ink)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "40px 44px",
          minHeight: 420,
        }}
      >
        <svg
          viewBox="0 0 560 420"
          preserveAspectRatio="xMidYMax slice"
          style={{ position: "absolute", left: 0, right: 0, bottom: 0, width: "100%", height: "62%" }}
          aria-hidden="true"
        >
          <path d="M0 300 L150 190 L260 260 L380 160 L560 290 L560 420 L0 420 Z" fill="#1b2b49" />
          <path d="M220 420 L360 240 L470 330 L560 270 L560 420 Z" fill="#223760" />
          <path
            d="M60 420 C 150 356 110 300 220 272 C 330 244 300 200 420 190"
            stroke="#3564e4"
            strokeWidth={7}
            fill="none"
            strokeLinecap="round"
          />
          <circle cx={455} cy={120} r={46} fill="#9accfa" opacity={0.16} />
          <circle cx={455} cy={120} r={24} fill="#9accfa" opacity={0.32} />
        </svg>

        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 10, color: "#fff" }}>
          <Wheel size={30} />
          <span
            style={{
              fontFamily: "var(--display)",
              fontWeight: 900,
              fontSize: 22,
              letterSpacing: "-0.3px",
              textTransform: "uppercase",
            }}
          >
            Ride<span style={{ color: "var(--sky)" }}>wise</span>
          </span>
        </div>

        <h1
          style={{
            position: "relative",
            maxWidth: "16ch",
            fontWeight: 900,
            fontSize: 48,
            lineHeight: 1,
            letterSpacing: "-1.4px",
            textTransform: "uppercase",
            color: "#fff",
          }}
        >
          Where
          <br />
          should I
          <br />
          <span style={{ color: "var(--sky)" }}>ride today?</span>
        </h1>
      </div>

      {/* form side */}
      <div
        style={{
          flex: "1 1 400px",
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 28px",
          background: "var(--base)",
        }}
      >
        <form onSubmit={submit} style={{ width: "100%", maxWidth: 380 }}>
          <h2 style={{ fontWeight: 800, fontSize: 30, marginBottom: 22 }}>Get started</h2>

          <p className="note note--warn" style={{ marginBottom: 22 }}>
            <Warning size={17} />
            <span>
              Accounts are not built yet. This just remembers your name in this browser — nothing
              is sent anywhere and there is no password to set.
            </span>
          </p>

          <label className="label" htmlFor="rider">
            What should we call you?
          </label>
          <input
            id="rider"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Andrii"
            autoComplete="name"
            autoFocus
          />

          <button type="submit" className="btn" style={{ width: "100%", marginTop: 22 }}>
            Continue
          </button>

          <p className="hint" style={{ marginTop: 18, textAlign: "center" }}>
            Next you will add your motorcycle, then ask for a ride.
          </p>
        </form>
      </div>
    </div>
  );
}
