export interface TripPlan {
  origin: string;
  destination: string;
  waypoints: string[];
  route: RouteInfo;
  weather: WeatherData[];
  budget: BudgetBreakdown;
  recommendations: Recommendation[];
  chat: ChatMessage[];
}

export interface RouteInfo {
  distanceKm: number;
  durationHours: number;
  polyline: Array<[number, number]>;
  stops: string[];
  origin?: string;
  destination?: string;
}

export interface WeatherData {
  location?: string;
  day?: string;
  severeAlert?: string | null;
  city?: string;
  temperatureC: number;
  condition: string;
  icon: string;
  highC: number;
  lowC: number;
  precipitationChance: number;
}

export interface BudgetBreakdown {
  fuel: number;
  tolls?: number;
  hotels?: number;
  food: number;
  miscellaneous?: number;
  total: number;
  fuelUsd?: number;
  tollsUsd?: number;
  hotelsUsd?: number;
  foodUsd?: number;
  miscellaneousUsd?: number;
  totalUsd?: number;
  lodging?: number;
  activities?: number;
  breakdown?: {
    fuel: { inr: number; usd: number };
    tolls: { inr: number; usd: number };
    hotels: { inr: number; usd: number };
    food: { inr: number; usd: number };
    miscellaneous: { inr: number; usd: number };
    total: { inr: number; usd: number };
  };
}

export interface Recommendation {
  title: string;
  description: string;
  category: string;
  priority: number;
  rating?: number;
  estimatedCostInr?: number;
  location?: string;
  lat?: number;
  lng?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface TripRoutePlan {
  route: {
    distance_km: number;
    duration_hours: number;
    polyline: Array<[number, number]>;
    toll_roads: boolean;
  };
  waypoints: string[];
}

export interface PlannedTripResponse {
  trip_id: number;
  report_id?: number | null;
  origin: string;
  destination: string;
  travel_dates: { start: string; end: string };
  budget: number;
  preferences: string[];
  waypoints: string[];
  route: {
    distance_km: number;
    duration_hours: number;
    polyline: Array<[number, number]>;
    toll_roads: boolean;
  };
  weather: Array<Record<string, unknown>>;
  recommendations: Record<string, Array<Record<string, unknown>>>;
  report_summary: string;
  pdf_path?: string | null;
  fuel_cost_inr?: number | null;
  toll_cost_inr?: number | null;
  hotel_cost_inr?: number | null;
  food_cost_inr?: number | null;
  total_inr?: number | null;
  total_usd?: number | null;
}

export interface TripMarker {
  lat: number;
  lng: number;
  label: string;
  type: "origin" | "destination" | "waypoint";
  eta?: string;
}
