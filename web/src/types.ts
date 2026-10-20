/** Mirrors of the Pydantic models the API returns. Keep in step with
 *  `src/ridewise/models.py` and `src/ridewise/api.py`. */

export type BikeCategory =
  | "sport"
  | "naked"
  | "adventure"
  | "touring"
  | "cruiser"
  | "supermoto"
  | "enduro"
  | "scooter";

export type WindProtection = "none" | "low" | "full";

export type TireType = "sport" | "road" | "touring" | "dual-sport" | "knobby";

export type Experience = "novice" | "intermediate" | "experienced";

export interface Bike {
  id: number;
  nickname: string;
  make: string;
  model: string;
  year: number | null;
  category: BikeCategory;
  tank_liters: number;
  consumption_l_per_100km: number;
  reserve_liters: number;
  wind_protection: WindProtection;
  tire_type: TireType;
  heated_grips: boolean;
  has_luggage: boolean;
  notes: string;
  is_default: boolean;
  photo_url: string | null;
  range_km: number;
  label: string;
}

export type BikeDraft = Omit<Bike, "id" | "photo_url" | "range_km" | "label">;

export interface Profile {
  id: number;
  name: string;
  home_label: string;
  experience: Experience;
  min_comfortable_temp_c: number;
  accepts_rain: boolean;
}

export interface GeoPlace {
  label: string;
  lat: number;
  lon: number;
}

export interface RideRequest {
  raw_text: string;
  start: GeoPlace;
  target_distance_km: number;
  ride_date: string;
  earliest_departure: string;
  latest_return: string;
  avoid_highways: boolean;
  prefer_twisty: boolean;
  notes: string;
}

/** `[latitude, longitude]`, matching the Python side. */
export type Point = [number, number];

export interface RouteCandidate {
  candidate_id: string;
  bearing_deg: number;
  distance_km: number;
  moving_duration_h: number;
  ascent_m: number;
  descent_m: number;
  twistiness: number;
  geometry: Point[];
  waypoints: Point[];
  road_score: number;
  direction: string;
}

export interface HourlyWeather {
  time: string;
  temperature_c: number;
  apparent_temperature_c: number;
  precipitation_mm: number;
  precipitation_probability: number;
  wind_speed_kmh: number;
  wind_gusts_kmh: number;
  cloud_cover: number;
  visibility_m: number | null;
  weather_code: number;
}

export interface LegForecast {
  distance_along_km: number;
  lat: number;
  lon: number;
  eta: string;
  weather: HourlyWeather;
}

export interface WeatherWindow {
  departure: string;
  arrival: string;
  score: number;
  rain_risk_pct: number;
  min_temp_c: number;
  max_temp_c: number;
  max_gust_kmh: number;
  total_precipitation_mm: number;
  verdict: string;
  legs: LegForecast[];
}

export interface FuelStop {
  name: string;
  brand: string;
  lat: number;
  lon: number;
  distance_along_km: number;
  detour_km: number;
  reason: string;
}

export interface GearItem {
  item: string;
  reason: string;
  essential: boolean;
}

export interface RidePlan {
  request: RideRequest;
  bike_label: string;
  route: RouteCandidate;
  alternatives: RouteCandidate[];
  weather: WeatherWindow | null;
  weather_options: WeatherWindow[];
  /** Each candidate's own best window, keyed by `candidate_id`. */
  best_window_by_candidate: Record<string, WeatherWindow>;
  fuel_stops: FuelStop[];
  gear: GearItem[];
  briefing: string;
  warnings: string[];
}

export interface PlanRequestBody {
  prompt: string;
  bike_id: number | null;
  start_place: string;
  distance_km: number;
  ride_date: string | null;
  earliest: string;
  latest: string;
  avoid_highways: boolean;
  prefer_twisty: boolean;
}

export interface Health {
  ok: boolean;
  routing_configured: boolean;
  model: string;
}

export interface ProgressEvent {
  node: string;
  label: string;
  lines: string[];
}
