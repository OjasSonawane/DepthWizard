import React, { useState, useEffect, useRef, Suspense } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Sky } from '@react-three/drei';
import * as THREE from 'three';
import { useProject } from '../context/ProjectContext';
import { api } from '../services/api';
import { HeightfieldData } from '../types';
import { TerrainMesh } from '../components/TerrainMesh';
import { FloodPlane } from '../components/FloodPlane';
import { HUD } from '../components/HUD';
import { Measurement3DLayer, MeasurementHUDCard, MeasurePoint } from '../components/MeasurementTool';
import {
  Box,
  Eye,
  Sliders,
  Maximize2,
  Minimize2,
  RefreshCw,
  Ruler,
  Waves,
  Layers,
  Sparkles,
  Compass,
  AlertCircle
} from 'lucide-react';

// Flythrough keyboard and mouse drag controller
const FlyController: React.FC<{ active: boolean; speed?: number }> = ({ active, speed = 35.0 }) => {
  const { camera, gl } = useThree();
  const keys = useRef<{ [key: string]: boolean }>({});
  const isMouseDown = useRef<boolean>(false);
  const lastMousePos = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const euler = useRef<THREE.Euler>(new THREE.Euler(0, 0, 0, 'YXZ'));

  useEffect(() => {
    if (!active) return;
    euler.current.setFromQuaternion(camera.quaternion);

    const onKeyDown = (e: KeyboardEvent) => { keys.current[e.code] = true; };
    const onKeyUp = (e: KeyboardEvent) => { keys.current[e.code] = false; };
    const onMouseDown = (e: MouseEvent) => {
      if (e.button === 0) {
        isMouseDown.current = true;
        lastMousePos.current = { x: e.clientX, y: e.clientY };
      }
    };
    const onMouseUp = () => { isMouseDown.current = false; };
    const onMouseMove = (e: MouseEvent) => {
      if (!isMouseDown.current) return;
      const dx = e.clientX - lastMousePos.current.x;
      const dy = e.clientY - lastMousePos.current.y;
      lastMousePos.current = { x: e.clientX, y: e.clientY };

      euler.current.y -= dx * 0.003;
      euler.current.x = Math.max(-Math.PI / 2.2, Math.min(Math.PI / 2.2, euler.current.x - dy * 0.003));
      camera.quaternion.setFromEuler(euler.current);
    };

    const dom = gl.domElement;
    dom.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      dom.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [active, camera, gl]);

  useFrame((_, delta) => {
    if (!active) return;
    const moveDist = speed * delta;
    const dir = new THREE.Vector3();
    camera.getWorldDirection(dir);
    const right = new THREE.Vector3().crossVectors(dir, camera.up).normalize();

    if (keys.current['KeyW'] || keys.current['ArrowUp']) camera.position.addScaledVector(dir, moveDist);
    if (keys.current['KeyS'] || keys.current['ArrowDown']) camera.position.addScaledVector(dir, -moveDist);
    if (keys.current['KeyD'] || keys.current['ArrowRight']) camera.position.addScaledVector(right, moveDist);
    if (keys.current['KeyA'] || keys.current['ArrowLeft']) camera.position.addScaledVector(right, -moveDist);
    if (keys.current['KeyE'] || keys.current['Space']) camera.position.y += moveDist * 0.8;
    if (keys.current['KeyQ'] || keys.current['ShiftLeft']) camera.position.y -= moveDist * 0.8;
  });

  return null;
};

// Scene camera watcher to extract telemetry
const CameraWatcher: React.FC<{
  onUpdate: (alt: number, heading: number) => void;
}> = ({ onUpdate }) => {
  const { camera } = useThree();

  useFrame(() => {
    const alt = camera.position.y;
    const dir = new THREE.Vector3();
    camera.getWorldDirection(dir);
    const headingRad = Math.atan2(dir.x, dir.z);
    const headingDeg = (headingRad * 180) / Math.PI;
    onUpdate(alt, headingDeg);
  });

  return null;
};

export const ExplorerPage: React.FC = () => {
  const { results, setActiveTab } = useProject();
  const [heightfield, setHeightfield] = useState<HeightfieldData | null>(null);
  const [loadingMesh, setLoadingMesh] = useState<boolean>(true);

  // Explorer controls
  const [cameraMode, setCameraMode] = useState<'orbit' | 'fly' | 'top'>('orbit');
  const [exaggeration, setExaggeration] = useState<number>(1.2);
  const [wireframe, setWireframe] = useState<boolean>(false);
  const [activeTextureMode, setActiveTextureMode] = useState<'rgb' | 'elevation' | 'slope' | 'hillshade' | 'wireframe'>('rgb');
  const [lodQuality, setLodQuality] = useState<'low' | 'medium' | 'high'>('high');

  // Telemetry HUD state
  const [cameraAlt, setCameraAlt] = useState<number>(100);
  const [headingDeg, setHeadingDeg] = useState<number>(0);
  const [hoveredPoint, setHoveredPoint] = useState<any>(null);
  const [clickedPoint, setClickedPoint] = useState<any>(null);

  // Height measurement state
  const [isMeasureActive, setIsMeasureActive] = useState<boolean>(false);
  const [measurePointA, setMeasurePointA] = useState<MeasurePoint | null>(null);
  const [measurePointB, setMeasurePointB] = useState<MeasurePoint | null>(null);

  // Flood simulation state
  const [isFloodActive, setIsFloodActive] = useState<boolean>(false);
  const [floodElevation, setFloodElevation] = useState<number>(100);

  // Fullscreen state
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const orbitRef = useRef<any>(null);

  const changeLodQuality = async (quality: 'low' | 'medium' | 'high') => {
    if (!results) return;
    setLodQuality(quality);
    setLoadingMesh(true);
    try {
      const meshAsset = await api.getMeshAssets(results.job_id, quality);
      const hf = await api.getHeightfield(meshAsset.heightfield_url);
      setHeightfield(hf);
    } catch (err) {
      console.error('Failed to change mesh LOD:', err);
    } finally {
      setLoadingMesh(false);
    }
  };

  useEffect(() => {
    if (results?.assets?.mesh_heightfield) {
      setLoadingMesh(true);
      api.getHeightfield(results.assets.mesh_heightfield)
        .then((hf) => {
          setHeightfield(hf);
          setFloodElevation(hf.min_elevation + hf.relief * 0.2);
          setLoadingMesh(false);
        })
        .catch((err) => {
          console.error(err);
          setLoadingMesh(false);
        });
    }
  }, [results]);

  if (!results) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] text-center space-y-4">
        <Box className="w-12 h-12 text-slate-600" />
        <h3 className="text-lg font-bold text-white">No 3D Model Available</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Run an elevation reconstruction to explore the 3D surface model.
        </p>
        <button
          onClick={() => setActiveTab('upload')}
          className="px-4 py-2 rounded-lg bg-cyan-500 text-black font-semibold text-xs font-mono"
        >
          Start Reconstruction
        </button>
      </div>
    );
  }

  const enrichPoint = (info: any) => {
    if (!info || !results) return info;
    const { xPct, yPct } = info;
    const meta = results.image_metadata;
    if (meta.bounds) {
      const [west, south, east, north] = meta.bounds;
      const easting = west + xPct * (east - west);
      const northing = north - yPct * (north - south);
      return {
        ...info,
        geoCoords: { x: easting, y: northing }
      };
    } else {
      const px = Math.round(xPct * (meta.width - 1));
      const py = Math.round(yPct * (meta.height - 1));
      return {
        ...info,
        pixelCoords: { x: px, y: py }
      };
    }
  };

  const handleTerrainHover = (info: any) => {
    setHoveredPoint(enrichPoint(info));
  };

  const handleTerrainClick = (info: any) => {
    const enriched = enrichPoint(info);
    setClickedPoint(enriched);

    if (isMeasureActive) {
      if (!measurePointA) {
        setMeasurePointA({
          worldPos: info.worldPos,
          elevation: info.elevation,
          label: 'Point A'
        });
      } else if (!measurePointB) {
        setMeasurePointB({
          worldPos: info.worldPos,
          elevation: info.elevation,
          label: 'Point B'
        });
      } else {
        // Reset and set point A
        setMeasurePointA({
          worldPos: info.worldPos,
          elevation: info.elevation,
          label: 'Point A'
        });
        setMeasurePointB(null);
      }
    }
  };

  const resetCamera = () => {
    if (orbitRef.current) {
      orbitRef.current.reset();
    }
    setCameraMode('orbit');
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const getActiveTextureUrl = () => {
    switch (activeTextureMode) {
      case 'elevation':
        return results.assets.dsm_color;
      case 'slope':
        return results.assets.slope;
      case 'hillshade':
        return results.assets.hillshade;
      case 'wireframe':
      case 'rgb':
      default:
        return results.assets.rgb_texture;
    }
  };
  const activeTextureUrl = getActiveTextureUrl();

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-[calc(100vh-3.5rem)] bg-[#04070e] select-none overflow-hidden ${
        isFullscreen ? 'h-screen' : ''
      }`}
    >
      {/* 3D WebGL Canvas */}
      {heightfield && (
        <Canvas shadows className="w-full h-full">
          <PerspectiveCamera
            makeDefault
            position={cameraMode === 'top' ? [0, 140, 0.1] : [0, 50, 80]}
            fov={50}
            near={0.5}
            far={2000}
          />

          {/* Environmental Illumination */}
          <ambientLight intensity={0.4} />
          <directionalLight
            position={[80, 120, 60]}
            intensity={1.2}
            castShadow
            shadow-mapSize={[2048, 2048]}
          />
          <Sky distance={450000} sunPosition={[80, 120, 60]} inclination={0.4} azimuth={0.25} />

          {/* 3D Camera Controls */}
          {cameraMode === 'orbit' && (
            <OrbitControls
              ref={orbitRef}
              enableDamping
              dampingFactor={0.05}
              maxPolarAngle={Math.PI / 2.05}
              minDistance={10}
              maxDistance={350}
            />
          )}

          {cameraMode === 'top' && (
            <OrbitControls
              enableRotate={false}
              enableDamping
              minDistance={20}
              maxDistance={400}
            />
          )}

          <FlyController active={cameraMode === 'fly'} speed={35} />

          <CameraWatcher
            onUpdate={(alt, hdg) => {
              setCameraAlt(alt);
              setHeadingDeg(hdg);
            }}
          />

          {/* Terrain Heightfield Mesh */}
          <Suspense fallback={null}>
            <TerrainMesh
              heightfield={heightfield}
              textureUrl={activeTextureUrl}
              exaggeration={exaggeration}
              wireframe={wireframe || activeTextureMode === 'wireframe'}
              wireframeOnly={activeTextureMode === 'wireframe'}
              onHoverPoint={handleTerrainHover}
              onClickPoint={handleTerrainClick}
            />

            {/* Dynamic Flood Plane Layer */}
            <FloodPlane
              waterElevation={floodElevation}
              minElevation={heightfield.min_elevation}
              maxElevation={heightfield.max_elevation}
              worldXSpan={heightfield.world_x_span}
              worldZSpan={heightfield.world_z_span}
              exaggeration={exaggeration}
              visible={isFloodActive}
            />

            {/* 3D Measurement Tool Markers & Line */}
            {isMeasureActive && (
              <Measurement3DLayer
                pointA={measurePointA}
                pointB={measurePointB}
                isMetric={results.dsm_stats.is_metric}
                onClear={() => {
                  setMeasurePointA(null);
                  setMeasurePointB(null);
                }}
              />
            )}
          </Suspense>
        </Canvas>
      )}

      {/* Floating HUD Telemetry Overlay */}
      <HUD
        headingDeg={headingDeg}
        cameraAltitude={cameraAlt}
        hoveredData={hoveredPoint}
        clickedPoint={clickedPoint}
        cameraMode={cameraMode}
        isMetric={results.dsm_stats.is_metric}
        crs={results.image_metadata.crs}
      />

      {/* Height Measurement Tool HUD Card */}
      {isMeasureActive && (
        <MeasurementHUDCard
          pointA={measurePointA}
          pointB={measurePointB}
          isMetric={results.dsm_stats.is_metric}
          pixelResolution={results.image_metadata.resolution}
          worldXSpan={heightfield?.world_x_span}
          dataWidth={heightfield?.data_width || heightfield?.grid_width}
          onClear={() => {
            setMeasurePointA(null);
            setMeasurePointB(null);
          }}
        />
      )}

      {/* Top Controls Toolbar */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 pointer-events-auto flex items-center space-x-2 bg-slate-900/85 border border-slate-700/80 backdrop-blur-md px-3 py-1.5 rounded-2xl shadow-2xl text-xs font-mono">
        {/* Camera Modes */}
        <div className="flex items-center space-x-1 border-r border-slate-800 pr-2">
          <button
            onClick={() => setCameraMode('orbit')}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              cameraMode === 'orbit' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Orbit
          </button>
          <button
            onClick={() => setCameraMode('fly')}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              cameraMode === 'fly' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Fly (WASD)
          </button>
          <button
            onClick={() => setCameraMode('top')}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              cameraMode === 'top' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Top-Down
          </button>
        </div>

        {/* 5-way Display Mode Switcher */}
        <div className="flex items-center space-x-1 border-r border-slate-800 pr-2">
          <button
            onClick={() => { setActiveTextureMode('rgb'); setWireframe(false); }}
            className={`px-2 py-1 rounded-md text-[11px] font-bold transition-all ${
              activeTextureMode === 'rgb' && !wireframe ? 'bg-cyan-500 text-black' : 'text-slate-400 hover:text-white'
            }`}
            title="Original Aerial / Satellite RGB Texture"
          >
            RGB
          </button>
          <button
            onClick={() => { setActiveTextureMode('elevation'); setWireframe(false); }}
            className={`px-2 py-1 rounded-md text-[11px] font-bold transition-all ${
              activeTextureMode === 'elevation' && !wireframe ? 'bg-emerald-500 text-black' : 'text-slate-400 hover:text-white'
            }`}
            title="Elevation Surface Relief (Hypsometric Color)"
          >
            ELEV
          </button>
          <button
            onClick={() => { setActiveTextureMode('slope'); setWireframe(false); }}
            className={`px-2 py-1 rounded-md text-[11px] font-bold transition-all ${
              activeTextureMode === 'slope' && !wireframe ? 'bg-amber-500 text-black' : 'text-slate-400 hover:text-white'
            }`}
            title="3x3 Finite Difference Slope Map"
          >
            SLOPE
          </button>
          <button
            onClick={() => { setActiveTextureMode('hillshade'); setWireframe(false); }}
            className={`px-2 py-1 rounded-md text-[11px] font-bold transition-all ${
              activeTextureMode === 'hillshade' && !wireframe ? 'bg-indigo-500 text-white' : 'text-slate-400 hover:text-white'
            }`}
            title="Analytical Shaded Relief (315° Illumination)"
          >
            SHADE
          </button>
          <button
            onClick={() => {
              if (activeTextureMode === 'wireframe') {
                setActiveTextureMode('rgb');
                setWireframe(false);
              } else {
                setActiveTextureMode('wireframe');
              }
            }}
            className={`px-2 py-1 rounded-md text-[11px] font-bold transition-all ${
              activeTextureMode === 'wireframe' || wireframe ? 'bg-cyan-400 text-black' : 'text-slate-400 hover:text-white'
            }`}
            title="Wireframe Terrain Geometry Mode"
          >
            WIRE
          </button>
        </div>

        {/* LOD Quality Selector */}
        <div className="flex items-center space-x-1 border-r border-slate-800 pr-2">
          <span className="text-[10px] text-slate-500 font-bold mr-0.5">LOD:</span>
          {(['low', 'medium', 'high'] as const).map((q) => (
            <button
              key={q}
              onClick={() => changeLodQuality(q)}
              disabled={loadingMesh}
              className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold transition-all ${
                lodQuality === q
                  ? 'bg-slate-700 text-cyan-300 border border-cyan-500/30'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {q === 'low' ? '64²' : q === 'medium' ? '128²' : '192²'}
            </button>
          ))}
        </div>

        {/* Disaster / Measurement Tools */}
        <div className="flex items-center space-x-1 border-r border-slate-800 pr-2">
          <button
            onClick={() => {
              setIsMeasureActive(!isMeasureActive);
              if (isMeasureActive) {
                setMeasurePointA(null);
                setMeasurePointB(null);
              }
            }}
            className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg transition-all ${
              isMeasureActive
                ? 'bg-amber-500 text-black font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Ruler className="w-3.5 h-3.5" />
            <span>Measure ΔZ</span>
          </button>

          <button
            onClick={() => setIsFloodActive(!isFloodActive)}
            className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg transition-all ${
              isFloodActive
                ? 'bg-blue-500 text-white font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Waves className="w-3.5 h-3.5" />
            <span>Flood Sim</span>
          </button>
        </div>

        {/* Low-res preview indicator */}
        {results.dimensions?.is_low_resolution && (
          <div className="flex items-center px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 text-amber-300 text-[10px] font-bold" title={results.dimensions.resolution_warning || 'Low resolution input'}>
            <span>PREVIEW ({results.dimensions.input_width}×{results.dimensions.input_height})</span>
          </div>
        )}

        {/* Reset & Fullscreen */}
        <div className="flex items-center space-x-1 pl-1">
          <button
            onClick={resetCamera}
            className="p-1 rounded text-slate-400 hover:text-white transition-colors"
            title="Reset Camera"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={toggleFullscreen}
            className="p-1 rounded text-slate-400 hover:text-white transition-colors"
            title="Fullscreen"
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Floating Flood Simulation Level Bar */}
      {isFloodActive && heightfield && (
        <div className="absolute top-20 left-4 z-20 pointer-events-auto bg-slate-900/90 border border-blue-500/40 backdrop-blur-md rounded-xl p-4 shadow-2xl font-mono text-xs w-72 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center space-x-2 text-blue-400 font-bold">
              <Waves className="w-4 h-4" />
              <span>FLOOD THRESHOLD SIM</span>
            </div>
            <button
              onClick={() => setIsFloodActive(false)}
              className="text-[10px] text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-400">Water Elevation:</span>
              <span className="text-blue-300 font-bold">
                {floodElevation.toFixed(1)} {results.dsm_stats.is_metric ? 'm' : 'rel'}
              </span>
            </div>
            <input
              type="range"
              min={heightfield.min_elevation}
              max={heightfield.max_elevation}
              step={0.5}
              value={floodElevation}
              onChange={(e) => setFloodElevation(Number(e.target.value))}
              className="w-full accent-blue-400 cursor-pointer"
            />
          </div>

          <div className="p-2 rounded bg-blue-500/10 border border-blue-500/20 text-[10px] text-blue-300 flex items-start space-x-1.5">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-blue-400" />
            <span className="leading-tight">
              Illustrative elevation-based visualization — not a hydrological forecast.
            </span>
          </div>
        </div>
      )}

      {/* Vertical Exaggeration Slider Pill (Bottom Center) */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 pointer-events-auto flex items-center space-x-3 bg-slate-900/80 border border-slate-800 backdrop-blur-md px-4 py-2 rounded-xl text-xs font-mono shadow-xl">
        <span className="text-slate-400">RELIEF EXAGGERATION:</span>
        <input
          type="range"
          min="0.5"
          max="3.0"
          step="0.1"
          value={exaggeration}
          onChange={(e) => setExaggeration(Number(e.target.value))}
          className="w-28 accent-cyan-400 cursor-pointer"
        />
        <span className="text-cyan-300 font-bold w-10 text-right">{exaggeration.toFixed(1)}×</span>
      </div>
    </div>
  );
};
