import type { TripPlan } from "@/types";

export const sampleTripPlan: TripPlan = {
  origin: "San Francisco, CA",
  destination: "Los Angeles, CA",
  waypoints: ["Monterey", "Big Sur", "Santa Barbara"],
  route: {
    distanceKm: 615,
    durationHours: 9.5,
    polyline: [
      [37.7749, -122.4194],
      [36.6002, -121.8947],
      [36.2456, -121.7835],
      [35.3677, -120.8499],
      [34.4208, -119.6982],
      [34.0522, -118.2437],
    ],
    stops: ["Monterey", "Big Sur", "Santa Barbara"],
  },
  weather: [
    {
      city: "Monterey",
      temperatureC: 18,
      condition: "Cloudy with light coastal breeze",
      icon: "cloud",
      highC: 20,
      lowC: 14,
      precipitationChance: 10,
    },
    {
      city: "Santa Barbara",
      temperatureC: 24,
      condition: "Bright and warm",
      icon: "sun",
      highC: 27,
      lowC: 18,
      precipitationChance: 0,
    },
  ],
  budget: {
    fuel: 145,
    lodging: 420,
    food: 180,
    activities: 120,
    total: 865,
  },
  recommendations: [
    {
      title: "Big Sur scenic stop",
      description: "Plan a sunset pause here to avoid driving the coastal curves after dark.",
      category: "Scenic",
      priority: 1,
    },
    {
      title: "Refuel near Paso Robles",
      description: "Prices tend to be friendlier inland, so top off before the final stretch.",
      category: "Budget",
      priority: 2,
    },
    {
      title: "Reserve lodging in advance",
      description: "Coastal stays fill up early on weekends, especially in Santa Barbara.",
      category: "Logistics",
      priority: 3,
    },
  ],
  chat: [
    {
      id: "1",
      role: "assistant",
      content: "I’ve mapped a scenic coastal route with three recommended stops and one overnight break.",
      timestamp: new Date().toISOString(),
    },
    {
      id: "2",
      role: "user",
      content: "Can we keep fuel costs under $150?",
      timestamp: new Date().toISOString(),
    },
    {
      id: "3",
      role: "assistant",
      content: "Yes. Keep the tank topped up near inland towns and avoid premium stations near tourist spots.",
      timestamp: new Date().toISOString(),
    },
  ],
};

