import React from 'react';
import * as THREE from 'three';
import { Line } from '@react-three/drei';

export interface MeasurePoint {
  worldPos: [number, number, number];
  elevation: number;
  label: string;
}

interface MeasurementToolProps {
  pointA: MeasurePoint | null;
  pointB: MeasurePoint | null;
  isMetric: boolean;
  onClear: () => void;
  pixelResolution?: number | [number, number] | null;
  worldXSpan?: number;
  dataWidth?: number;
}

export const Measurement3DLayer: React.FC<MeasurementToolProps> = ({
  pointA,
  pointB,
  isMetric
}) => {
  if (!pointA) return null;

  return (
    <group>
      {/* Marker A */}
      <mesh position={pointA.worldPos}>
        <sphereGeometry args={[0.8, 16, 16]} />
        <meshStandardMaterial color="#00f0ff" emissive="#00f0ff" emissiveIntensity={0.8} />
      </mesh>

      {/* Marker B */}
      {pointB && (
        <>
          <mesh position={pointB.worldPos}>
            <sphereGeometry args={[0.8, 16, 16]} />
            <meshStandardMaterial color="#f59e0b" emissive="#f59e0b" emissiveIntensity={0.8} />
          </mesh>

          {/* Line connecting Point A and B */}
          <Line
            points={[pointA.worldPos, pointB.worldPos]}
            color="#ffffff"
            lineWidth={2.5}
            dashed
            dashScale={50}
            dashSize={1}
            gapSize={0.5}
          />
        </>
      )}
    </group>
  );
};

export const MeasurementHUDCard: React.FC<MeasurementToolProps> = ({
  pointA,
  pointB,
  isMetric,
  onClear,
  pixelResolution,
  worldXSpan = 100.0,
  dataWidth
}) => {
  if (!pointA) return null;

  let deltaZ = 0;
  let distHoriz = 0;
  let dist3D = 0;
  let slopeDeg = 0;

  const unit = isMetric ? 'm' : 'rel';

  if (pointA && pointB) {
    deltaZ = Math.abs(pointB.elevation - pointA.elevation);
    const dxWorld = pointB.worldPos[0] - pointA.worldPos[0];
    const dzWorld = pointB.worldPos[2] - pointA.worldPos[2];
    const distHorizWorld = Math.sqrt(dxWorld * dxWorld + dzWorld * dzWorld);

    // If georeferenced metric scale is known: convert world units to true ground meters
    const resM = typeof pixelResolution === 'number'
      ? pixelResolution
      : Array.isArray(pixelResolution)
      ? Math.abs(pixelResolution[0])
      : null;

    if (isMetric && resM && dataWidth && worldXSpan > 0) {
      const metersPerWorldUnit = (dataWidth * resM) / worldXSpan;
      distHoriz = distHorizWorld * metersPerWorldUnit;
      dist3D = Math.sqrt(distHoriz * distHoriz + deltaZ * deltaZ);
    } else {
      distHoriz = distHorizWorld;
      dist3D = Math.sqrt(distHoriz * distHoriz + deltaZ * deltaZ);
    }

    slopeDeg = distHoriz > 0 ? (Math.atan(deltaZ / distHoriz) * 180) / Math.PI : 0;
  }

  return (
    <div className="absolute top-20 right-4 z-20 pointer-events-auto bg-slate-900/90 border border-amber-500/40 backdrop-blur-md rounded-xl p-4 shadow-2xl font-mono text-xs w-72 space-y-3">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2 text-amber-400 font-bold">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span>DISTANCE & ΔZ TOOL</span>
        </div>
        <button
          onClick={onClear}
          className="text-[10px] text-slate-400 hover:text-white px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 transition-colors"
        >
          Clear
        </button>
      </div>

      <div className="space-y-1.5 text-[11px]">
        <div className="flex items-center justify-between text-slate-300">
          <span className="text-cyan-400 font-bold">Point A (Base):</span>
          <span className="text-white font-bold">{pointA.elevation.toFixed(2)} {unit}</span>
        </div>
        <div className="flex items-center justify-between text-slate-300">
          <span className="text-amber-400 font-bold">Point B (Target):</span>
          <span className="text-white font-bold">
            {pointB ? `${pointB.elevation.toFixed(2)} ${unit}` : 'Click terrain...'}
          </span>
        </div>
      </div>

      {pointB && (
        <div className="pt-2 border-t border-slate-800 space-y-1.5 font-mono text-[11px]">
          <div className="flex items-center justify-between text-white font-bold text-xs">
            <span className="text-emerald-400">Elevation Diff (ΔZ):</span>
            <span className="text-emerald-300">{deltaZ.toFixed(2)} {unit}</span>
          </div>
          <div className="flex items-center justify-between text-slate-300">
            <span className="text-slate-400">Horizontal Ground Dist:</span>
            <span className="text-cyan-300 font-bold">{distHoriz.toFixed(2)} {unit}</span>
          </div>
          <div className="flex items-center justify-between text-slate-300">
            <span className="text-slate-400">3D Euclidean Distance:</span>
            <span className="text-slate-200">{dist3D.toFixed(2)} {unit}</span>
          </div>
          <div className="flex items-center justify-between text-slate-400 text-[10px]">
            <span>Gradient / Slope:</span>
            <span className="text-amber-300 font-bold">{slopeDeg.toFixed(1)}°</span>
          </div>
        </div>
      )}
    </div>
  );
};
