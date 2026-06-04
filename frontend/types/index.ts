export interface TripPlan {
  origin: string;
  destination: string;
  waypoints: string[];
  route: RouteInfo;
  weather: DailyWeather[];
  budget: BudgetBreakdown;
  recommendations: LocationRecommendation[];
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

export interface DailyWeather {
  date: string;
  day_name: string;
  location: string;
  temp_min_celsius: number;
  temp_max_celsius: number;
  temp_feels_like: number;
  humidity_percent: number;
  condition: string;
  weather_icon: string;
  wind_speed_kmh: number;
  rain_chance_percent: number;
  alert: string | null;
}

export interface HotelRecommendation {
  name: string;
  description: string;
  estimated_cost_inr: number;
  rating: number;
  category: string;
}

export interface RestaurantRecommendation {
  name: string;
  description: string;
  estimated_cost_inr: number;
  rating: number;
  cuisine: string;
  category: string;
}

export interface AttractionRecommendation {
  name: string;
  description: string;
  entry_fee_inr: number;
  rating: number;
  type: string;
}

export interface LocationRecommendation {
  location: string;
  hotels: HotelRecommendation[];
  restaurants: RestaurantRecommendation[];
  attractions: AttractionRecommendation[];
}

export interface WeatherResponse {
  status: "success" | "unavailable" | "past_dates";
  message?: string;
  location: string;
  start_date: string;
  end_date: string;
  total_days: number;
  weather: DailyWeather[];
}

export interface WeatherData extends DailyWeather {
  day?: string;
  city?: string;
  temperatureC?: number;
  icon?: string;
  highC?: number;
  lowC?: number;
  precipitationChance?: number;
  severeAlert?: string | null;
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

export interface PlaceBase {
  place_id: string;
  name: string;
  description: string;
  address: string;
  rating: number;
  total_reviews: number;
  photo_url: string | null;
  lat: number;
  lng: number;
  maps_url: string;
  website: string | null;
  phone: string | null;
  open_now: boolean | null;
}

export interface HotelRecommendation extends PlaceBase {
  price_range: string;
  price_level: number;
  category: string;
}

export interface RestaurantRecommendation extends PlaceBase {
  price_range: string;
  price_level: number;
  cuisine: string;
}

export interface AttractionRecommendation extends PlaceBase {
  entry_fee: string;
  price_level: number;
  type: string;
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
  weather: DailyWeather[];
  weather_status?: "success" | "unavailable" | "past_dates";
  weather_message?: string | null;
  recommendations: LocationRecommendation[];
  recommendation_locations?: string[];
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
