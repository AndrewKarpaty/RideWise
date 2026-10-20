import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createBike,
  deleteBike,
  deletePhoto,
  getBikes,
  getProfile,
  putProfile,
  updateBike,
  uploadPhoto,
} from "../api";
import { Camera, Check, Plus, Trash, Warning } from "../components/Icons";
import type { Bike, BikeDraft, Profile, TireType, WindProtection } from "../types";

/** Screen 2: the motorcycle, its photo, and the two rider preferences that
 *  feed the weather scoring. */

interface Props {
  onReady: (bike: Bike) => void;
}

const TYRES: TireType[] = ["sport", "road", "touring", "dual-sport", "knobby"];
const SCREENS: WindProtection[] = ["none", "low", "full"];
const SCREEN_LABEL: Record<WindProtection, string> = {
  none: "None",
  low: "Low screen",
  full: "Full fairing",
};

function emptyDraft(): BikeDraft {
  return {
    nickname: "",
    make: "",
    model: "",
    year: new Date().getFullYear(),
    category: "naked",
    tank_liters: 16,
    consumption_l_per_100km: 4.5,
    reserve_liters: 2,
    wind_protection: "low",
    tire_type: "road",
    heated_grips: false,
    has_luggage: false,
    notes: "",
    is_default: true,
  };
}

function toDraft(bike: Bike): BikeDraft {
  const { id: _id, photo_url: _p, range_km: _r, label: _l, ...draft } = bike;
  return draft;
}

export function Cabinet({ onReady }: Props) {
  const [bikes, setBikes] = useState<Bike[]>([]);
  const [selected, setSelected] = useState<number | "new">("new");
  const [draft, setDraft] = useState<BikeDraft>(emptyDraft);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const current = typeof selected === "number" ? bikes.find((b) => b.id === selected) : undefined;

  useEffect(() => {
    void (async () => {
      try {
        const [loaded, prof] = await Promise.all([getBikes(), getProfile()]);
        setBikes(loaded);
        setProfile(prof);
        const first = loaded[0];
        if (first) {
          setSelected(first.id);
          setDraft(toDraft(first));
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not reach the API.");
      }
    })();
  }, []);

  const patch = (fields: Partial<BikeDraft>) => {
    setDraft((d) => ({ ...d, ...fields }));
    setSaved(false);
  };

  const pick = (id: number | "new") => {
    setSelected(id);
    setSaved(false);
    setError(null);
    if (id === "new") setDraft(emptyDraft());
    else {
      const bike = bikes.find((b) => b.id === id);
      if (bike) setDraft(toDraft(bike));
    }
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result =
        typeof selected === "number" ? await updateBike(selected, draft) : await createBike(draft);
      const refreshed = await getBikes();
      setBikes(refreshed);
      setSelected(result.id);
      setDraft(toDraft(result));
      setSaved(true);
      if (profile) await putProfile({ ...profile });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Saving failed.");
    } finally {
      setBusy(false);
    }
  };

  const onPhoto = async (file: File | undefined) => {
    if (!file || typeof selected !== "number") return;
    setBusy(true);
    setError(null);
    try {
      const updated = await uploadPhoto(selected, file);
      setBikes((bs) => bs.map((b) => (b.id === updated.id ? updated : b)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The upload failed.");
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const removePhoto = async () => {
    if (typeof selected !== "number") return;
    const updated = await deletePhoto(selected);
    setBikes((bs) => bs.map((b) => (b.id === updated.id ? updated : b)));
  };

  const remove = async () => {
    if (typeof selected !== "number") return;
    setBusy(true);
    try {
      await deleteBike(selected);
      const refreshed = await getBikes();
      setBikes(refreshed);
      pick(refreshed[0]?.id ?? "new");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed.");
    } finally {
      setBusy(false);
    }
  };

  const usable = Math.max(draft.tank_liters - draft.reserve_liters, 0);
  const range =
    draft.consumption_l_per_100km > 0 ? Math.round((usable / draft.consumption_l_per_100km) * 100) : 0;
  const complete = draft.nickname.trim() && draft.make.trim() && draft.model.trim();

  return (
    <div className="page page--narrow">
      <h1 style={{ fontWeight: 800, fontSize: 34, marginBottom: 20 }}>Your motorcycle</h1>

      {bikes.length > 0 && (
        <div className="row" style={{ gap: 9, marginBottom: 22 }}>
          {bikes.map((bike) => (
            <button
              key={bike.id}
              type="button"
              className={`chip${selected === bike.id ? " chip--on" : ""}`}
              onClick={() => pick(bike.id)}
            >
              {bike.nickname}
              <span className="muted" style={{ fontSize: 13 }}>
                {Math.round(bike.range_km)} km
              </span>
            </button>
          ))}
          <button
            type="button"
            className={`chip${selected === "new" ? " chip--on" : ""}`}
            onClick={() => pick("new")}
          >
            <Plus size={15} /> Add a bike
          </button>
        </div>
      )}

      {error && (
        <p className="note note--error" style={{ marginBottom: 20 }}>
          <Warning size={17} />
          <span>{error}</span>
        </p>
      )}

      <form onSubmit={save} className="card" style={{ display: "flex", flexWrap: "wrap", gap: 28 }}>
        {/* photo + range */}
        <div style={{ flex: "1 1 280px", minWidth: 0 }}>
          <p className="label">Photo</p>

          {current?.photo_url ? (
            <div>
              <img
                src={current.photo_url}
                alt={`${current.label}`}
                style={{
                  width: "100%",
                  aspectRatio: "4 / 3",
                  objectFit: "cover",
                  borderRadius: "var(--r)",
                  border: "1px solid var(--line)",
                  display: "block",
                }}
              />
              <div className="row" style={{ gap: 8, marginTop: 10 }}>
                <button
                  type="button"
                  className="btn--ghost btn"
                  onClick={() => fileInput.current?.click()}
                >
                  Replace
                </button>
                <button type="button" className="btn btn--danger" onClick={() => void removePhoto()}>
                  Remove
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={typeof selected !== "number"}
              style={{
                width: "100%",
                aspectRatio: "4 / 3",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 10,
                border: "2px dashed var(--line)",
                borderRadius: "var(--r)",
                background: "var(--field)",
                cursor: typeof selected === "number" ? "pointer" : "not-allowed",
                padding: 20,
                textAlign: "center",
                fontFamily: "var(--body)",
                color: "var(--ink)",
              }}
            >
              <span
                style={{
                  display: "grid",
                  placeItems: "center",
                  width: 50,
                  height: 50,
                  borderRadius: "var(--r-pill)",
                  background: "var(--brand-soft)",
                  color: "var(--brand)",
                }}
              >
                <Camera size={23} />
              </span>
              <span style={{ fontSize: 15, fontWeight: 600 }}>Add a photo of your bike</span>
              <span className="hint" style={{ margin: 0 }}>
                {typeof selected === "number"
                  ? "JPEG, PNG or WebP, up to 8 MB."
                  : "Save the bike first, then add a photo."}
              </span>
            </button>
          )}

          <input
            ref={fileInput}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(e) => void onPhoto(e.target.files?.[0])}
          />

          <div className="card card--dark" style={{ marginTop: 18, padding: "18px 20px" }}>
            <p className="stat__k" style={{ color: "var(--muted-2)" }}>
              Range on one tank
            </p>
            <p
              style={{
                margin: "5px 0 0",
                fontFamily: "var(--display)",
                fontWeight: 900,
                fontSize: 38,
                letterSpacing: "-1.2px",
                lineHeight: 1.05,
              }}
            >
              {range} km
            </p>
            <p style={{ margin: "5px 0 0", fontSize: 13, color: "var(--on-dark)" }}>
              {usable.toFixed(1)} usable litres of {draft.tank_liters}, keeping{" "}
              {draft.reserve_liters} in reserve
            </p>
          </div>
        </div>

        {/* fields */}
        <div style={{ flex: "999 1 380px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label className="label" htmlFor="nick">
              Name it
            </label>
            <input
              id="nick"
              className="input"
              value={draft.nickname}
              onChange={(e) => patch({ nickname: e.target.value })}
              placeholder="Tenere"
              required
            />
          </div>

          <div className="row" style={{ gap: 14 }}>
            <div style={{ flex: "1 1 120px", minWidth: 0 }}>
              <label className="label" htmlFor="make">
                Make
              </label>
              <input
                id="make"
                className="input"
                value={draft.make}
                onChange={(e) => patch({ make: e.target.value })}
                placeholder="Yamaha"
                required
              />
            </div>
            <div style={{ flex: "999 1 150px", minWidth: 0 }}>
              <label className="label" htmlFor="model">
                Model
              </label>
              <input
                id="model"
                className="input"
                value={draft.model}
                onChange={(e) => patch({ model: e.target.value })}
                placeholder="Ténéré 700"
                required
              />
            </div>
            <div style={{ flex: "0 1 100px", minWidth: 0 }}>
              <label className="label" htmlFor="year">
                Year
              </label>
              <input
                id="year"
                className="input"
                type="number"
                min={1900}
                max={2100}
                value={draft.year ?? ""}
                onChange={(e) => patch({ year: e.target.value ? Number(e.target.value) : null })}
              />
            </div>
          </div>

          <div className="row" style={{ gap: 14 }}>
            <div style={{ flex: "1 1 130px", minWidth: 0 }}>
              <label className="label" htmlFor="tank">
                Tank, litres
              </label>
              <input
                id="tank"
                className="input"
                type="number"
                step={0.5}
                min={1}
                max={80}
                value={draft.tank_liters}
                onChange={(e) => patch({ tank_liters: Number(e.target.value) })}
                required
              />
            </div>
            <div style={{ flex: "1 1 170px", minWidth: 0 }}>
              <label className="label" htmlFor="cons">
                Litres per 100 km
              </label>
              <input
                id="cons"
                className="input"
                type="number"
                step={0.1}
                min={1}
                max={30}
                value={draft.consumption_l_per_100km}
                onChange={(e) => patch({ consumption_l_per_100km: Number(e.target.value) })}
                required
              />
            </div>
          </div>

          <div className="row" style={{ gap: 14 }}>
            <div style={{ flex: "1 1 150px", minWidth: 0 }}>
              <label className="label" htmlFor="tyres">
                Tyres
              </label>
              <select
                id="tyres"
                className="select"
                value={draft.tire_type}
                onChange={(e) => patch({ tire_type: e.target.value as TireType })}
              >
                {TYRES.map((t) => (
                  <option key={t} value={t}>
                    {t[0]!.toUpperCase() + t.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ flex: "1 1 150px", minWidth: 0 }}>
              <label className="label" htmlFor="wind">
                Wind protection
              </label>
              <select
                id="wind"
                className="select"
                value={draft.wind_protection}
                onChange={(e) => patch({ wind_protection: e.target.value as WindProtection })}
              >
                {SCREENS.map((w) => (
                  <option key={w} value={w}>
                    {SCREEN_LABEL[w]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="row" style={{ gap: 9 }}>
            <label className={`check${draft.heated_grips ? " check--on" : ""}`}>
              <input
                type="checkbox"
                checked={draft.heated_grips}
                onChange={(e) => patch({ heated_grips: e.target.checked })}
              />
              Heated grips
            </label>
            <label className={`check${draft.has_luggage ? " check--on" : ""}`}>
              <input
                type="checkbox"
                checked={draft.has_luggage}
                onChange={(e) => patch({ has_luggage: e.target.checked })}
              />
              Luggage fitted
            </label>
          </div>

          <details>
            <summary style={{ cursor: "pointer", fontSize: 14, fontWeight: 600, color: "var(--muted)" }}>
              Notes and reserve
            </summary>
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ maxWidth: 200 }}>
                <label className="label" htmlFor="reserve">
                  Reserve held back, litres
                </label>
                <input
                  id="reserve"
                  className="input"
                  type="number"
                  step={0.5}
                  min={0}
                  max={20}
                  value={draft.reserve_liters}
                  onChange={(e) => patch({ reserve_liters: Number(e.target.value) })}
                />
                <p className="hint">Range is worked out without it, so stops never assume reserve.</p>
              </div>
              <div>
                <label className="label" htmlFor="notes">
                  Anything the planner should know
                </label>
                <textarea
                  id="notes"
                  className="textarea"
                  rows={2}
                  value={draft.notes}
                  onChange={(e) => patch({ notes: e.target.value })}
                  placeholder="Short screen — windblast above 110 km/h."
                />
              </div>
            </div>
          </details>

          {profile && (
            <>
              <hr className="divider" style={{ margin: "6px 0" }} />
              <p className="label" style={{ marginBottom: 2 }}>
                How you ride — this scores the weather
              </p>
              <div className="row" style={{ gap: 18, alignItems: "flex-end" }}>
                <div style={{ flex: "999 1 240px", minWidth: 0 }}>
                  <label className="label" htmlFor="mintemp" style={{ fontWeight: 500 }}>
                    Coldest you will ride: <strong>{profile.min_comfortable_temp_c} °C</strong>
                  </label>
                  <input
                    id="mintemp"
                    type="range"
                    min={-5}
                    max={20}
                    step={1}
                    value={profile.min_comfortable_temp_c}
                    onChange={(e) =>
                      setProfile({ ...profile, min_comfortable_temp_c: Number(e.target.value) })
                    }
                    style={{ width: "100%", accentColor: "var(--brand)" }}
                  />
                </div>
                <label className={`check${profile.accepts_rain ? " check--on" : ""}`}>
                  <input
                    type="checkbox"
                    checked={profile.accepts_rain}
                    onChange={(e) => setProfile({ ...profile, accepts_rain: e.target.checked })}
                  />
                  Rain is fine
                </label>
              </div>
              <div>
                <label className="label" htmlFor="home">
                  Home base — where loops start
                </label>
                <input
                  id="home"
                  className="input"
                  value={profile.home_label}
                  onChange={(e) => setProfile({ ...profile, home_label: e.target.value })}
                  placeholder="Lviv, Ukraine"
                />
              </div>
            </>
          )}

          <div className="row" style={{ gap: 12, alignItems: "center", paddingTop: 4 }}>
            <button type="submit" className="btn" disabled={busy || !complete}>
              {busy ? "Saving…" : "Save"}
            </button>
            {current && (
              <button
                type="button"
                className="btn"
                onClick={() => onReady(current)}
                style={{ background: "var(--ink)" }}
              >
                Continue <span aria-hidden="true">→</span>
              </button>
            )}
            {saved && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 7, color: "var(--go-ink)", fontSize: 14, fontWeight: 600 }}>
                <Check size={16} /> Saved
              </span>
            )}
            <div className="spacer" />
            {typeof selected === "number" && (
              <button type="button" className="btn btn--danger" onClick={() => void remove()}>
                <Trash size={15} /> Delete
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
