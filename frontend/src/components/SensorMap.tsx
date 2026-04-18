import { useEffect, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, Popup, CircleMarker } from "react-leaflet";
import type { LatLngExpression } from "leaflet";
import type { Feature, FeatureCollection } from "geojson";
import { fetchJSON } from "@/api/client";
import { useSite } from "./SiteContext";
import { Link } from "react-router-dom";

interface SensorProps {
  sensor_id: string;
  sensor_type: string;
  display_name: string;
  structure_id: string;
  section_id: string;
}

export function SensorMap() {
  const { site } = useSite();
  const [sensors, setSensors] = useState<FeatureCollection | null>(null);
  const [structures, setStructures] = useState<FeatureCollection | null>(null);
  const [center, setCenter] = useState<LatLngExpression>([-19.92, -43.93]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchJSON<FeatureCollection>(`/gis/${site}/sensors.geojson`),
      fetchJSON<FeatureCollection>(`/gis/${site}/structures.geojson`),
    ])
      .then(([s, st]) => {
        if (cancelled) return;
        setSensors(s);
        setStructures(st);
        // center on first sensor if available
        const first = s?.features?.[0];
        if (first && first.geometry && first.geometry.type === "Point") {
          const [lon, lat] = (first.geometry as GeoJSON.Point).coordinates;
          setCenter([lat, lon]);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [site]);

  return (
    <div className="h-96 rounded-lg overflow-hidden border border-slate-200">
      <MapContainer center={center} zoom={16} style={{ height: "100%" }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap"
        />
        {structures && (
          <GeoJSON
            data={structures as any}
            style={{
              color: "#0f172a",
              weight: 2,
              fillColor: "#64748b",
              fillOpacity: 0.15,
            }}
          />
        )}
        {sensors?.features.map((f: Feature) => {
          if (!f.geometry || f.geometry.type !== "Point") return null;
          const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
          const props = f.properties as SensorProps;
          return (
            <CircleMarker
              key={props.sensor_id}
              center={[lat, lon]}
              radius={6}
              pathOptions={{
                color: sensorColor(props.sensor_type),
                fillColor: sensorColor(props.sensor_type),
                fillOpacity: 0.85,
              }}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-medium">{props.display_name}</div>
                  <div className="text-slate-500">{props.sensor_id}</div>
                  <div className="text-slate-500">{props.sensor_type}</div>
                  <Link
                    to={`/sensors/${props.sensor_id}`}
                    className="text-emerald-700 text-xs underline mt-1 inline-block"
                  >
                    abrir detalhes →
                  </Link>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}

function sensorColor(type: string): string {
  if (type.startsWith("piezometer")) return "#0ea5e9";
  if (type.startsWith("inclinometer")) return "#a855f7";
  if (type.startsWith("rain")) return "#22c55e";
  if (type.startsWith("gnss")) return "#f97316";
  return "#64748b";
}
