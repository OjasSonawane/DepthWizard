import React, { useState, useEffect } from 'react';
import { Compass } from './Compass';
import { Crosshair, Eye, Mountain, Navigation, Compass as CompassIcon } from 'lucide-react';

export interface InspectionPointInfo {
  elevation?: number;
  predictedHeight?: number;
  referenceHeight?: number | null;
  elevationError?: number | null;
  slopeDeg?: number;
  xPct?: number;
  yPct?: number;
  gridCol?: number;
  gridRow?: number;
  geoCoords?: { x: number; y: number; lat?: number; lon?: number };
  pixelCoords?: { x: number; y: number };
}

interface HUDProps {
  headingDeg: number;
  cameraAltitude: number;
  hoveredData?: InspectionPointInfo | null;
  clickedPoint?: InspectionPointInfo | null;
  cameraMode: 'orbit' | 'fly' | 'top';
  isMetric: boolean;
  crs?: string | null;
}

export const HUD: React.FC<HUDProps> = ({
  headingDeg,
  cameraAltitude,
  hoveredData,
  clickedPoint,
  cameraMode,
  isMetric,
  crs
}) => {
  const [fps, setFps] = useState<number>(60);

  useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();
    let animId: number;

    const loop = () => {
      frameCount++;
      const now = performance.now();
      if (now - lastTime >= 1000) {
        setFps(Math.round((frameCount * 1000) / (now - lastTime)));
        frameCount = 0;
        lastTime = now;
      }
      animId = requestAnimationFrame(loop);
    };

    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, []);

  const activeInspection = clickedPoint || hoveredData;

  return (
    <div className="absolute inset-0 pointer-events-none p-4 flex flex-col justify-between select-none z-10 font-mono">
      {/* Top Bar Telemetry */}
      <div className="flex items-start justify-between">
        {/* Top-Left: Camera & Flight Telemetry */}
        <div className="flex items-center space-x-3 pointer-events-auto">
          <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur-md text-[11px] space-y-1 shadow-lg">
            <div className="flex items-center space-x-2 text-slate-400">
              <Eye className="w-3.5 h-3.5 text-cyan-400" />
              <span className="uppercase text-[10px] tracking-wider text-slate-400">CAMERA MODE</span>
            </div>
            <div className="text-cyan-300 font-bold uppercase text-xs">
              {cameraMode === 'fly' ? 'FLYTHROUGH (WASD)' : cameraMode === 'top' ? 'ORTHO TOP-DOWN' : 'ORBIT CONTROLS'}
            </div>
            <div className="flex items-center space-x-4 text-slate-300 pt-1 border-t border-slate-800 text-[10px]">
              <div>
                ALT: <span className="text-slate-100 font-bold">{Math.round(cameraAltitude)}m</span>
              </div>
              <div>
                HDG: <span className="text-slate-100 font-bold">{Math.round((headingDeg + 360) % 360)}°</span>
              </div>
              <div>
                FPS: <span className="text-emerald-400 font-bold">{fps}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Top-Right: 3D Compass Rose */}
        <div className="pointer-events-auto flex items-center space-x-3">
          <Compass headingDeg={headingDeg} />
        </div>
      </div>

      {/* Bottom Bar: Terrain Surface Inspector */}
      <div className="flex items-end justify-between">
        {/* Bottom-Left: Live Surface Telemetry */}
        <div className="pointer-events-auto">
          {activeInspection ? (
            <div className="p-4 rounded-xl bg-slate-900/85 border border-cyan-500/40 backdrop-blur-md text-xs space-y-2 shadow-xl shadow-black/60 max-w-sm">
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                <div className="flex items-center space-x-2 text-cyan-400 font-bold text-[11px]">
                  <Crosshair className="w-3.5 h-3.5" />
                  <span>{clickedPoint ? 'PINNED POINT INSPECTION' : 'TERRAIN HOVER'}</span>
                </div>
                <span className="text-[10px] text-slate-400">
                  {crs || 'Unavailable'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2 rounded bg-slate-950/60 border border-slate-800">
                  <div className="text-[9px] text-slate-400 font-bold uppercase">PREDICTED HEIGHT</div>
                  <div className="text-sm font-bold text-white mt-0.5">
                    {activeInspection.elevation !== undefined
                      ? `${activeInspection.elevation.toFixed(2)} ${isMetric ? 'm' : 'rel'}`
                      : 'Unavailable'}
                  </div>
                </div>

                <div className="p-2 rounded bg-slate-950/60 border border-slate-800">
                  <div className="text-[9px] text-slate-400 font-bold uppercase">REFERENCE HEIGHT</div>
                  <div className={`text-sm font-bold mt-0.5 ${activeInspection.referenceHeight !== null && activeInspection.referenceHeight !== undefined ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {activeInspection.referenceHeight !== null && activeInspection.referenceHeight !== undefined
                      ? `${activeInspection.referenceHeight.toFixed(2)} ${isMetric ? 'm' : 'rel'}`
                      : 'Unavailable'}
                  </div>
                </div>

                <div className="p-2 rounded bg-slate-950/60 border border-slate-800">
                  <div className="text-[9px] text-slate-400 font-bold uppercase">ELEVATION ERROR</div>
                  <div className={`text-sm font-bold mt-0.5 ${activeInspection.elevationError !== null && activeInspection.elevationError !== undefined ? 'text-amber-400' : 'text-slate-500'}`}>
                    {activeInspection.elevationError !== null && activeInspection.elevationError !== undefined
                      ? `${activeInspection.elevationError > 0 ? '+' : ''}${activeInspection.elevationError.toFixed(2)} ${isMetric ? 'm' : 'rel'}`
                      : 'Unavailable'}
                  </div>
                </div>

                <div className="p-2 rounded bg-slate-950/60 border border-slate-800">
                  <div className="text-[9px] text-slate-400 font-bold uppercase">SURFACE SLOPE</div>
                  <div className="text-sm font-bold text-cyan-400 mt-0.5">
                    {activeInspection.slopeDeg !== undefined
                      ? `${activeInspection.slopeDeg.toFixed(1)}°`
                      : 'Unavailable'}
                  </div>
                </div>
              </div>

              {activeInspection.pixelCoords && (
                <div className="pt-1.5 border-t border-slate-800 text-[10px] text-slate-300 flex items-center justify-between">
                  <span className="text-slate-400">RASTER PIXEL:</span>
                  <span className="text-cyan-300 font-bold font-mono">X: {activeInspection.pixelCoords.x}, Y: {activeInspection.pixelCoords.y}</span>
                </div>
              )}

              {activeInspection.geoCoords ? (
                <div className="pt-1 text-[10px] text-slate-300 space-y-0.5">
                  {activeInspection.geoCoords.lat !== undefined ? (
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">WGS84 LAT/LON:</span>
                      <span className="text-slate-100 font-bold">{activeInspection.geoCoords.lat.toFixed(5)}°, {activeInspection.geoCoords.lon?.toFixed(5)}°</span>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">PROJECTED (E, N):</span>
                      <span className="text-slate-100 font-bold">{activeInspection.geoCoords.x.toFixed(1)}m, {activeInspection.geoCoords.y.toFixed(1)}m</span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="pt-1 text-[10px] text-slate-500 flex items-center justify-between">
                  <span>GEOREFERENCING:</span>
                  <span className="font-bold">Unavailable (Relative)</span>
                </div>
              )}
            </div>
          ) : (
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 backdrop-blur-sm text-[11px] text-slate-400 flex items-center space-x-2">
              <Crosshair className="w-3.5 h-3.5 text-slate-500" />
              <span>Click or hover terrain for elevation & slope inspection</span>
            </div>
          )}
        </div>

        {/* Bottom-Right: Scale Indicator */}
        <div className="p-2.5 rounded-xl bg-slate-900/70 border border-slate-800 backdrop-blur-sm text-[10px] text-slate-400 flex flex-col items-end space-y-1">
          <div className="flex items-center space-x-2">
            <span>GRID LOD:</span>
            <span className="text-cyan-400 font-bold">192×192 VTX</span>
          </div>
          <div className="w-24 h-1 bg-cyan-500/30 rounded-full overflow-hidden">
            <div className="w-1/2 h-full bg-cyan-400" />
          </div>
        </div>
      </div>
    </div>
  );
};
