export interface TripPlan {
  origin: string;
  destination: string;
  waypoints: string[];
  route: RouteInfo;
  weather: DailyWeather[];
  budget: BudgetBreakdown;
  recommendations: LocationRecommendation[];
  chat: ChatMessage[];
  vehicle: VehicleDetails;
  fuel_calculation: FuelCalculation;
}

export interface VehicleDetails {
  vehicle_type: "bike" | "car" | "suv" | "bus";
  vehicle_name: string;
  fuel_type: "petrol" | "diesel" | "electric" | "cng";
  mileage_kmpl: number;
  tank_capacity_litres: number;
  number_of_people: number;
}

export interface FuelCalculation {
  distance_km: number;
  mileage_kmpl: number;
  fuel_required_litres: number;
  fuel_type: string;
  fuel_price_per_litre: number;
  total_fuel_cost_inr: number;
  total_fuel_cost_usd: number;
  refueling_stops: number;
  cost_per_person_inr: number;
  vehicle_name: string;
  vehicle_type: string;
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
  hotel_price_per_night?: number;
  hotel_category?: string;
  hotel_nights?: number;
  hotel_daily_breakdown?: Array<{
    night: number;
    date: string;
    checkout_date: string;
    label: string;
    cost: number;
  }>;
  hotel_explanation?: string;
  food_price_per_day_per_person?: number;
  food_type?: string;
  food_days?: number;
  food_is_vegetarian?: boolean;
  food_daily_breakdown?: Array<{
    day: number;
    date: string;
    label: string;
    cost_per_person: number;
    total_cost: number;
    people: number;
  }>;
  food_explanation?: string;
  trip_days?: number;
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
  vehicle?: VehicleDetails | null;
  fuel_calculation?: FuelCalculation | null;
  fuel_cost_inr?: number | null;
  toll_cost_inr?: number | null;
  hotel_cost_inr?: number | null;
  hotel_price_per_night?: number | null;
  hotel_category?: string | null;
  hotel_nights?: number | null;
  hotel_daily_breakdown?: Array<{
    night: number;
    date: string;
    checkout_date: string;
    label: string;
    cost: number;
  }> | null;
  hotel_explanation?: string | null;
  food_cost_inr?: number | null;
  food_price_per_day_per_person?: number | null;
  food_type?: string | null;
  food_days?: number | null;
  food_is_vegetarian?: boolean | null;
  food_daily_breakdown?: Array<{
    day: number;
    date: string;
    label: string;
    cost_per_person: number;
    total_cost: number;
    people: number;
  }> | null;
  food_explanation?: string | null;
  misc_cost_inr?: number | null;
  number_of_people?: number | null;
  trip_days?: number | null;
  cost_per_person_inr?: number | null;
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
