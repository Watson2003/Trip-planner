"use client";

import { useMemo, useState } from "react";
import { Bike, CarFront, Fuel, Minus, Plus, Truck, Zap } from "lucide-react";

import type { VehicleDetails } from "@/types";

type VehicleFormProps = {
  onChange: (vehicle: VehicleDetails) => void;
  initialValues?: Partial<VehicleDetails>;
  routeDistanceKm?: number | null;
};

const VEHICLE_PRESETS: Record<VehicleDetails["vehicle_type"], { mileage: number[]; tank: number; label: string }> = {
  bike: { mileage: [35, 45, 55, 65], tank: 13, label: "Bike" },
  car: { mileage: [12, 15, 18, 22], tank: 40, label: "Car" },
  suv: { mileage: [8, 10, 12, 15], tank: 60, label: "SUV" },
  truck: { mileage: [6, 8, 10, 12], tank: 90, label: "Truck" },
};

const FUEL_PRESETS: Array<{ value: VehicleDetails["fuel_type"]; label: string; icon: string }> = [
  { value: "petrol", label: "Petrol", icon: "⛽" },
  { value: "diesel", label: "Diesel", icon: "🛢️" },
  { value: "electric", label: "Electric", icon: "⚡" },
  { value: "cng", label: "CNG", icon: "🌿" },
];

const FUEL_PRICE_PER_UNIT: Record<VehicleDetails["fuel_type"], number> = {
  petrol: 102.92,
  diesel: 89.62,
  electric: 8.5,
  cng: 75.5,
};

const DEFAULT_VALUES: VehicleDetails = {
  vehicle_type: "car",
  vehicle_name: "",
  fuel_type: "petrol",
  mileage_kmpl: 15,
  tank_capacity_litres: 40,
  number_of_people: 1,
};

function normalizeInitialValues(initialValues?: Partial<VehicleDetails>): VehicleDetails {
  return {
    ...DEFAULT_VALUES,
    ...initialValues,
    vehicle_type: initialValues?.vehicle_type ?? DEFAULT_VALUES.vehicle_type,
    vehicle_name: initialValues?.vehicle_name ?? DEFAULT_VALUES.vehicle_name,
    fuel_type: initialValues?.fuel_type ?? DEFAULT_VALUES.fuel_type,
    mileage_kmpl: initialValues?.mileage_kmpl ?? DEFAULT_VALUES.mileage_kmpl,
    tank_capacity_litres: initialValues?.tank_capacity_litres ?? DEFAULT_VALUES.tank_capacity_litres,
    number_of_people: initialValues?.number_of_people ?? DEFAULT_VALUES.number_of_people,
  };
}

function fuelLabel(fuelType: VehicleDetails["fuel_type"]) {
  return fuelType === "electric" ? "Range (km/kWh)" : "Mileage (km/litre)";
}

function tankLabel(fuelType: VehicleDetails["fuel_type"]) {
  return fuelType === "electric" ? "Battery Range (km)" : "Tank Capacity (litres)";
}

export default function VehicleForm({ onChange, initialValues, routeDistanceKm }: VehicleFormProps) {
  const [vehicle, setVehicle] = useState<VehicleDetails>(() => normalizeInitialValues(initialValues));

  const presetValues = useMemo(() => VEHICLE_PRESETS[vehicle.vehicle_type].mileage, [vehicle.vehicle_type]);
  const estimatedFuelCost = useMemo(() => {
    if (!vehicle.mileage_kmpl || vehicle.mileage_kmpl <= 0 || !routeDistanceKm || routeDistanceKm <= 0) return null;
    const distanceKm = routeDistanceKm;
    const fuelRequired = distanceKm / vehicle.mileage_kmpl;
    const fuelPrice = FUEL_PRICE_PER_UNIT[vehicle.fuel_type];
    const total = fuelRequired * fuelPrice;
    const perPerson = total / Math.max(1, vehicle.number_of_people);
    return {
      distanceKm,
      fuelRequired,
      total,
      perPerson,
    };
  }, [routeDistanceKm, vehicle.fuel_type, vehicle.mileage_kmpl, vehicle.number_of_people]);

  function updateVehicle(next: Partial<VehicleDetails>) {
    const merged = { ...vehicle, ...next };
    setVehicle(merged);
    onChange(merged);
  }

  function selectVehicleType(vehicleType: VehicleDetails["vehicle_type"]) {
    const preset = VEHICLE_PRESETS[vehicleType];
    updateVehicle({
      vehicle_type: vehicleType,
      mileage_kmpl: preset.mileage[1] ?? preset.mileage[0],
      tank_capacity_litres: preset.tank,
    });
  }

  function selectFuelType(fuelType: VehicleDetails["fuel_type"]) {
    updateVehicle({ fuel_type: fuelType });
  }

  function adjustPeople(delta: number) {
    updateVehicle({
      number_of_people: Math.min(10, Math.max(1, vehicle.number_of_people + delta)),
    });
  }

  return (
    <section className="rounded-3xl border border-[#1a1a1a] bg-[#0a0a0a] p-4 shadow-inner shadow-black/10">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-white">Vehicle details</p>
          <h3 className="text-lg font-bold text-white">Tell us about your ride</h3>
        </div>
        <div className="rounded-full border border-[#2a2a2a] bg-[#111111] px-3 py-1 text-xs font-semibold text-white">
          Accurate fuel estimate
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <div className="mb-2 text-sm font-medium text-[#a0a0a0]">Vehicle Type</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { type: "bike", icon: <Bike className="h-5 w-5" /> },
              { type: "car", icon: <CarFront className="h-5 w-5" /> },
              { type: "suv", icon: <CarFront className="h-5 w-5" /> },
              { type: "truck", icon: <Truck className="h-5 w-5" /> },
            ].map(({ type, icon }) => {
              const selected = vehicle.vehicle_type === type;
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => selectVehicleType(type as VehicleDetails["vehicle_type"])}
                  className={`flex min-h-[84px] flex-col items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-sm font-semibold transition ${
                    selected
                      ? "border-white bg-white text-black shadow-lg shadow-black/10"
                      : "border-[#2a2a2a] bg-[#111111] text-[#a0a0a0] hover:border-white hover:bg-[#1a1a1a] hover:text-white"
                  }`}
                >
                  <span className="text-2xl">{icon}</span>
                  <span>{VEHICLE_PRESETS[type as VehicleDetails["vehicle_type"]].label}</span>
                </button>
              );
            })}
          </div>
        </div>

        <label className="grid gap-2">
          <span className="text-sm font-medium text-[#a0a0a0]">Vehicle Name</span>
          <input
            value={vehicle.vehicle_name}
            onChange={(event) => updateVehicle({ vehicle_name: event.target.value })}
            placeholder={
              vehicle.vehicle_type === "bike"
                ? "e.g. Royal Enfield Classic 350"
                : vehicle.vehicle_type === "car"
                  ? "e.g. Maruti Swift, Honda City"
                  : vehicle.vehicle_type === "suv"
                    ? "e.g. Mahindra Thar, Toyota Fortuner"
                    : "e.g. Tata Ace, Mahindra Bolero"
            }
            className="rounded-2xl border border-[#2a2a2a] bg-[#111111] px-4 py-3 text-white outline-none placeholder:text-[#444444] focus:border-white"
          />
        </label>

        <div>
          <div className="mb-2 text-sm font-medium text-[#a0a0a0]">Fuel Type</div>
          <div className="flex flex-wrap gap-2">
            {FUEL_PRESETS.map((item) => {
              const active = vehicle.fuel_type === item.value;
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => selectFuelType(item.value)}
                  className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition ${
                    active
                      ? "border-white bg-white text-black shadow-lg shadow-black/10"
                      : "border-[#2a2a2a] bg-transparent text-[#a0a0a0] hover:border-white hover:text-white"
                  }`}
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="mb-2 text-sm font-medium text-[#a0a0a0]">{fuelLabel(vehicle.fuel_type)}</div>
          <div className="grid gap-3">
            <input
              type="number"
              min={1}
              max={200}
              step={0.1}
              value={vehicle.mileage_kmpl}
              onChange={(event) => updateVehicle({ mileage_kmpl: Number(event.target.value) })}
              className="rounded-2xl border border-[#2a2a2a] bg-[#111111] px-4 py-3 text-white outline-none placeholder:text-[#444444] focus:border-white"
            />
            <p className="text-xs leading-6 text-[#888888]">
              Check your vehicle&apos;s official mileage or use your real-world experience.
            </p>
            <div className="flex flex-wrap gap-2">
              {presetValues.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => updateVehicle({ mileage_kmpl: preset })}
                  className="rounded-full border border-[#2a2a2a] bg-[#111111] px-3 py-1.5 text-xs font-semibold text-[#a0a0a0] transition hover:border-white hover:text-white"
                >
                  {preset} km/l
                </button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div className="mb-2 text-sm font-medium text-[#a0a0a0]">{tankLabel(vehicle.fuel_type)}</div>
          <input
            type="number"
            min={1}
            max={200}
            step={1}
            value={vehicle.tank_capacity_litres}
            onChange={(event) => updateVehicle({ tank_capacity_litres: Number(event.target.value) })}
            className="w-full rounded-2xl border border-[#2a2a2a] bg-[#111111] px-4 py-3 text-white outline-none placeholder:text-[#444444] focus:border-white"
          />
        </div>

        <div>
          <div className="mb-2 text-sm font-medium text-[#a0a0a0]">Number of Travellers</div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => adjustPeople(-1)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-[#111111] text-white transition hover:border-white hover:bg-[#1a1a1a]"
              aria-label="Decrease travellers"
            >
              <Minus className="h-4 w-4" />
            </button>
            <div className="min-w-16 rounded-2xl border border-[#2a2a2a] bg-[#111111] px-5 py-3 text-center text-base font-bold text-white">
              {vehicle.number_of_people}
            </div>
            <button
              type="button"
              onClick={() => adjustPeople(1)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-[#111111] text-white transition hover:border-white hover:bg-[#1a1a1a]"
              aria-label="Increase travellers"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-2 text-xs text-[#888888]">Fuel cost will be split per person.</p>
        </div>

        <div className="rounded-3xl border border-[#1a1a1a] bg-[#0a0a0a] p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <Fuel className="h-4 w-4" />
            Estimated Fuel Cost Preview
          </div>
          <div className="grid gap-2 text-sm text-[#a0a0a0]">
            <div className="flex items-center justify-between gap-4">
              <span className="text-[#888888]">Based on your vehicle data</span>
              <span className="font-semibold text-white">
                Final cost calculated after route planning
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>Distance</span>
              <span>{estimatedFuelCost ? `${estimatedFuelCost.distanceKm} km` : "--- km"}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>Fuel needed</span>
              <span>{estimatedFuelCost ? `${estimatedFuelCost.fuelRequired.toFixed(2)} units` : "---"}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>Estimated cost</span>
              <span>{estimatedFuelCost ? `₹${estimatedFuelCost.total.toFixed(0)}` : "₹---"}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>Per person</span>
              <span>{estimatedFuelCost ? `₹${estimatedFuelCost.perPerson.toFixed(0)}` : "₹---"}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
