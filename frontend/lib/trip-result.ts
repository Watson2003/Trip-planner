import type {
  BudgetBreakdown as BudgetBreakdownType,
  FullItinerary,
  LocationRecommendation,
  RecommendationCatalog,
  RecommendationPayload,
  TripMarker,
  VehicleDetails,
} from "@/types";

export type TripResultStorage = {
  trip_id: number;
  origin: string;
  destination: string;
  destination_key?: string;
  distance_km: number;
  duration_hours: number;
  route: GeoJSON.FeatureCollection;
  weather: Array<{
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
  }>;
  weather_status: "success" | "unavailable" | "past_dates";
  weather_message: string | null;
  budget: BudgetBreakdownType;
  fuel_calculation: {
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
  } | null;
  recommendations: RecommendationPayload;
  itinerary: FullItinerary | null;
  vehicle: VehicleDetails;
  startDate: string;
  endDate: string;
  userBudget: number;
  markers: TripMarker[];
  report_summary: string;
};

const TRIP_RESULT_PREFIX = "tripResult:";
const TRIP_RESULT_ACTIVE_KEY = "tripResult:active";

export const EMPTY_RECOMMENDATION_CATALOG: RecommendationCatalog = {
  destination: "",
  hotels: [],
  restaurants: [],
  attractions: [],
  fallback_generated: false,
};

export const DEFAULT_VEHICLE: VehicleDetails = {
  vehicle_type: "car",
  vehicle_name: "Vehicle",
  fuel_type: "petrol",
  mileage_kmpl: 0,
  tank_capacity_litres: 0,
  number_of_people: 1,
};

export const DEFAULT_BUDGET: BudgetBreakdownType = {
  fuel: 0,
  tolls: 0,
  hotels: 0,
  food: 0,
  miscellaneous: 0,
  total: 0,
  fuelUsd: 0,
  tollsUsd: 0,
  hotelsUsd: 0,
  foodUsd: 0,
  miscellaneousUsd: 0,
  totalUsd: 0,
  lodging: 0,
  activities: 0,
  breakdown: {
    fuel: { inr: 0, usd: 0 },
    tolls: { inr: 0, usd: 0 },
    hotels: { inr: 0, usd: 0 },
    food: { inr: 0, usd: 0 },
    miscellaneous: { inr: 0, usd: 0 },
    total: { inr: 0, usd: 0 },
  },
};

function safeNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function safeString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function safeBudgetTotal(budget: unknown) {
  if (!budget || typeof budget !== "object") return undefined;
  const total = (budget as Record<string, unknown>).total;
  return typeof total === "number" && Number.isFinite(total) ? total : undefined;
}

function haversineDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const toRad = (value: number) => (value * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * earthRadiusKm * Math.asin(Math.sqrt(a));
}

function estimateRouteDistanceKm(route: unknown): number {
  if (!route || typeof route !== "object") return 0;
  const featureCollection = route as GeoJSON.FeatureCollection;
  let total = 0;

  for (const feature of featureCollection.features ?? []) {
    if (!feature || feature.type !== "Feature" || !feature.geometry || feature.geometry.type !== "LineString") continue;
    const coordinates = feature.geometry.coordinates;
    for (let index = 1; index < coordinates.length; index += 1) {
      const previous = coordinates[index - 1];
      const current = coordinates[index];
      if (!Array.isArray(previous) || !Array.isArray(current)) continue;
      const [prevLon, prevLat] = previous;
      const [currLon, currLat] = current;
      if (
        typeof prevLat !== "number" ||
        typeof prevLon !== "number" ||
        typeof currLat !== "number" ||
        typeof currLon !== "number" ||
        !Number.isFinite(prevLat) ||
        !Number.isFinite(prevLon) ||
        !Number.isFinite(currLat) ||
        !Number.isFinite(currLon)
      ) {
        continue;
      }
      total += haversineDistanceKm(prevLat, prevLon, currLat, currLon);
    }
  }

  return Math.round(total * 100) / 100;
}

function estimateRouteDurationHours(distanceKm: number): number {
  if (!Number.isFinite(distanceKm) || distanceKm <= 0) return 0;
  const averageSpeedKmh = 45;
  return Math.round((distanceKm / averageSpeedKmh) * 100) / 100;
}

function normalizeRoutePoint(point: unknown): [number, number] | null {
  if (!Array.isArray(point) || point.length < 2) return null;
  const [lat, lng] = point;
  if (typeof lat !== "number" || typeof lng !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return [lat, lng];
}

function normalizeMarkersFromRoute(
  markers: unknown,
  routeSource: Record<string, unknown> | undefined,
  origin: string,
  destination: string,
): TripMarker[] {
  const parsedMarkers = Array.isArray(markers) ? (markers as TripMarker[]) : [];
  const routePolyline = Array.isArray(routeSource?.polyline) ? (routeSource?.polyline as Array<[number, number]>) : [];
  const fallbackOrigin = normalizeRoutePoint(routeSource?.origin_coords) ?? routePolyline[0] ?? null;
  const fallbackDestination = normalizeRoutePoint(routeSource?.destination_coords) ?? routePolyline[routePolyline.length - 1] ?? null;

  if (!fallbackOrigin && !fallbackDestination) {
    return parsedMarkers;
  }

  const nextMarkers = [...parsedMarkers];
  if (nextMarkers.length === 0) {
    if (fallbackOrigin) {
      nextMarkers.push({ lat: fallbackOrigin[0], lng: fallbackOrigin[1], label: origin, type: "origin" });
    }
    if (fallbackDestination) {
      nextMarkers.push({ lat: fallbackDestination[0], lng: fallbackDestination[1], label: destination, type: "destination" });
    }
    return nextMarkers;
  }

  if (fallbackOrigin) {
    const originIndex = nextMarkers.findIndex((marker) => marker.type === "origin");
    const originMarker = { lat: fallbackOrigin[0], lng: fallbackOrigin[1], label: origin, type: "origin" as const };
    if (originIndex >= 0) {
      nextMarkers[originIndex] = originMarker;
    } else {
      nextMarkers.unshift(originMarker);
    }
  }

  if (fallbackDestination) {
    const destinationIndex = [...nextMarkers].reverse().findIndex((marker) => marker.type === "destination");
    const destinationMarker = {
      lat: fallbackDestination[0],
      lng: fallbackDestination[1],
      label: destination,
      type: "destination" as const,
    };
    if (destinationIndex >= 0) {
      nextMarkers[nextMarkers.length - 1 - destinationIndex] = destinationMarker;
    } else {
      nextMarkers.push(destinationMarker);
    }
  }

  return nextMarkers;
}

export function normalizeDestinationKey(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\u2018\u2019`']/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function getTripResultStorageKey(destination: string) {
  const key = normalizeDestinationKey(destination) || "destination";
  return `${TRIP_RESULT_PREFIX}${key}`;
}

function getStorageKeys(): string[] {
  if (typeof window === "undefined") return [];
  const keys: string[] = [];
  for (let index = 0; index < window.sessionStorage.length; index += 1) {
    const key = window.sessionStorage.key(index);
    if (key) {
      keys.push(key);
    }
  }
  return keys;
}

export function storeTripResult(tripResult: TripResultStorage) {
  if (typeof window === "undefined") return;

  const destinationKey = normalizeDestinationKey(tripResult.destination);
  const storageKey = getTripResultStorageKey(tripResult.destination);
  const payload: TripResultStorage = {
    ...tripResult,
    destination_key: tripResult.destination_key ?? destinationKey,
  };

  for (const key of getStorageKeys()) {
    if (key.startsWith(TRIP_RESULT_PREFIX) || key === TRIP_RESULT_ACTIVE_KEY) {
      window.sessionStorage.removeItem(key);
    }
  }

  window.sessionStorage.setItem(storageKey, JSON.stringify(payload));
  window.sessionStorage.setItem(TRIP_RESULT_ACTIVE_KEY, storageKey);
}

export function loadStoredTripResult(): TripResultStorage | null {
  if (typeof window === "undefined") return null;

  const activeKey = window.sessionStorage.getItem(TRIP_RESULT_ACTIVE_KEY);
  const candidates = [
    activeKey,
    ...getStorageKeys().filter((key) => key.startsWith(TRIP_RESULT_PREFIX) || key === "tripResult"),
  ].filter((value, index, items) => Boolean(value) && items.indexOf(value) === index) as string[];

  for (const key of candidates) {
    const stored = window.sessionStorage.getItem(key);
    if (!stored) continue;

    try {
      const parsed = JSON.parse(stored) as Record<string, unknown>;
      const trip = normalizeTripData(parsed);
      if (!trip) continue;

      const payloadDestinationKey = typeof parsed.destination_key === "string" ? normalizeDestinationKey(parsed.destination_key) : "";
      const normalizedDestinationKeyValue = normalizeDestinationKey(trip.destination);
      const keyDestination = key.startsWith(TRIP_RESULT_PREFIX) ? key.slice(TRIP_RESULT_PREFIX.length) : "";

      if (keyDestination && normalizedDestinationKeyValue && keyDestination !== normalizedDestinationKeyValue) {
        continue;
      }
      if (payloadDestinationKey && keyDestination && payloadDestinationKey !== keyDestination) {
        continue;
      }

      window.sessionStorage.setItem(TRIP_RESULT_ACTIVE_KEY, key);
      return {
        ...trip,
        destination_key: payloadDestinationKey || normalizedDestinationKeyValue || keyDestination || undefined,
      };
    } catch {
      continue;
    }
  }

  return null;
}

function normalizeRecommendationItems(items: unknown): LocationRecommendation[] {
  if (!Array.isArray(items)) return [];
  return items.filter((item): item is LocationRecommendation => Boolean(item) && typeof item === "object") as LocationRecommendation[];
}

export function normalizeRecommendations(value: unknown, destination = ""): RecommendationCatalog {
  if (!value || typeof value !== "object") return { ...EMPTY_RECOMMENDATION_CATALOG, destination };

  if (Array.isArray(value)) {
    const blocks = normalizeRecommendationItems(value);
    const destinationBlock =
      blocks.find((block) => block.location.trim().toLowerCase() === destination.trim().toLowerCase()) ?? blocks[0];
    const hotels = blocks.flatMap((block) => block.hotels ?? []);
    const restaurants = blocks.flatMap((block) => block.restaurants ?? []);
    const attractions = blocks.flatMap((block) => block.attractions ?? []);
    return {
      destination: destinationBlock?.location ?? destination,
      hotels,
      restaurants,
      attractions,
      fallback_generated: Boolean(blocks.some((block) => block.fallback_generated)),
    };
  }

  const raw = value as Record<string, unknown>;
  const hot = Array.isArray(raw.hotels) ? (raw.hotels as RecommendationCatalog["hotels"]) : [];
  const restaurants = Array.isArray(raw.restaurants) ? (raw.restaurants as RecommendationCatalog["restaurants"]) : [];
  const attractions = Array.isArray(raw.attractions) ? (raw.attractions as RecommendationCatalog["attractions"]) : [];

  return {
    destination: typeof raw.destination === "string" ? raw.destination : destination,
    hotels: hot,
    restaurants,
    attractions,
    fallback_generated: Boolean(raw.fallback_generated),
  };
}

export function formatDuration(hours: number) {
  const totalMinutes = Math.max(0, Math.round(hours * 60));
  const wholeHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (wholeHours === 0) return `${minutes} min`;
  if (minutes === 0) return `${wholeHours} hr`;
  return `${wholeHours} hr ${minutes} min`;
}

export function normalizeTripData(raw: unknown): TripResultStorage | null {
  if (!raw || typeof raw !== "object") return null;

  const value = raw as Record<string, unknown>;
  const routeSource = value.route as Record<string, unknown> | undefined;
  const travelDates = (value.travel_dates as Record<string, unknown> | undefined) ?? {};

  return {
    trip_id: safeNumber(value.trip_id ?? value.tripId, 0),
    origin: safeString(value.origin),
    destination: safeString(value.destination),
    destination_key: safeString(value.destination_key),
    distance_km: (() => {
      const directDistance = safeNumber(value.distance_km ?? routeSource?.distance_km ?? value.distanceKm, 0);
      if (directDistance > 0) return directDistance;
      const routeDistance = estimateRouteDistanceKm(value.route);
      return routeDistance > 0 ? routeDistance : 0;
    })(),
    duration_hours: (() => {
      const directDuration = safeNumber(value.duration_hours ?? routeSource?.duration_hours ?? value.durationHours, 0);
      if (directDuration > 0) return directDuration;
      const routeDistance = safeNumber(value.distance_km, 0) || estimateRouteDistanceKm(value.route);
      return estimateRouteDurationHours(routeDistance);
    })(),
    route:
      value.route && typeof value.route === "object"
        ? (value.route as GeoJSON.FeatureCollection)
        : { type: "FeatureCollection", features: [] },
    weather: Array.isArray(value.weather) ? (value.weather as TripResultStorage["weather"]) : [],
    weather_status: (value.weather_status as TripResultStorage["weather_status"]) ?? "success",
    weather_message: (value.weather_message as string | null | undefined) ?? null,
    budget: (value.budget as BudgetBreakdownType) ?? DEFAULT_BUDGET,
    fuel_calculation: (value.fuel_calculation as TripResultStorage["fuel_calculation"]) ?? null,
    recommendations: normalizeRecommendations(value.recommendations, safeString(value.destination)),
    itinerary: (value.itinerary as FullItinerary | null | undefined) ?? null,
    vehicle: (value.vehicle as VehicleDetails) ?? DEFAULT_VEHICLE,
    startDate: safeString(value.startDate ?? travelDates.start),
    endDate: safeString(value.endDate ?? travelDates.end),
    userBudget: safeNumber(value.userBudget ?? safeBudgetTotal(value.budget) ?? value.total_inr, 0),
    markers: normalizeMarkersFromRoute(value.markers, routeSource, safeString(value.origin), safeString(value.destination)),
    report_summary: safeString(value.report_summary),
  };
}
