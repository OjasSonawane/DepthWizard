import React, { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useLoader, ThreeEvent } from '@react-three/fiber';
import { HeightfieldData } from '../types';

interface TerrainMeshProps {
  heightfield: HeightfieldData;
  textureUrl: string;
  exaggeration: number;
  wireframe?: boolean;
  wireframeOnly?: boolean;
  onHoverPoint?: (info: {
    worldPos: [number, number, number];
    elevation: number;
    referenceHeight: number | null;
    elevationError: number | null;
    slopeDeg: number;
    xPct: number;
    yPct: number;
    gridCol: number;
    gridRow: number;
  } | null) => void;
  onClickPoint?: (info: {
    worldPos: [number, number, number];
    elevation: number;
    referenceHeight: number | null;
    elevationError: number | null;
    slopeDeg: number;
    xPct: number;
    yPct: number;
    gridCol: number;
    gridRow: number;
  }) => void;
}

export const TerrainMesh: React.FC<TerrainMeshProps> = ({
  heightfield,
  textureUrl,
  exaggeration,
  wireframe = false,
  wireframeOnly = false,
  onHoverPoint,
  onClickPoint
}) => {
  const meshRef = useRef<THREE.Mesh>(null);
  const texture = useLoader(THREE.TextureLoader, textureUrl);
  
  // Configure texture parameters
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;

  const { geometry, gridW, gridH, xSpan, zSpan } = useMemo(() => {
    const gridW = heightfield.grid_width;
    const gridH = heightfield.grid_height;
    const xSpan = heightfield.world_x_span;
    const zSpan = heightfield.world_z_span;

    const geom = new THREE.PlaneGeometry(xSpan, zSpan, gridW - 1, gridH - 1);
    geom.rotateX(-Math.PI / 2); // Rotate to make Y up

    const posAttr = geom.attributes.position;
    const heights = heightfield.heights;

    for (let i = 0; i < posAttr.count; i++) {
      const h = heights[i] !== undefined ? heights[i] * exaggeration : 0;
      posAttr.setY(i, h);
    }

    geom.computeVertexNormals();
    return { geometry: geom, gridW, gridH, xSpan, zSpan };
  }, [heightfield, exaggeration]);

  const extractTerrainInfo = (event: any) => {
    if (!event.point) return null;
    const { x, y, z } = event.point;

    // Convert from world X/Z [-xSpan/2, xSpan/2] to normalized [0, 1]
    const u = Math.min(Math.max((x / xSpan) + 0.5, 0.0), 1.0);
    const v = Math.min(Math.max((z / zSpan) + 0.5, 0.0), 1.0);

    const col = Math.min(Math.max(Math.round(u * (gridW - 1)), 0), gridW - 1);
    const row = Math.min(Math.max(Math.round(v * (gridH - 1)), 0), gridH - 1);
    const index = row * gridW + col;

    const elevation = heightfield.raw_elevations[index] ?? 0;
    const referenceHeight = heightfield.reference_elevations?.[index] ?? null;
    const elevationError = heightfield.elevation_errors?.[index] ?? null;

    // Estimate local slope from neighboring heights
    const idxRight = row * gridW + Math.min(col + 1, gridW - 1);
    const idxDown = Math.min(row + 1, gridH - 1) * gridW + col;
    const hCenter = heightfield.raw_elevations[index] ?? 0;
    const hRight = heightfield.raw_elevations[idxRight] ?? hCenter;
    const hDown = heightfield.raw_elevations[idxDown] ?? hCenter;

    const dx = Math.abs(hRight - hCenter);
    const dz = Math.abs(hDown - hCenter);
    const slopeDeg = Math.min(90, (Math.atan(Math.hypot(dx, dz) / 2.0) * 180) / Math.PI);

    return {
      worldPos: [x, y, z] as [number, number, number],
      elevation,
      referenceHeight,
      elevationError,
      slopeDeg,
      xPct: u,
      yPct: v,
      gridCol: col,
      gridRow: row
    };
  };

  const handlePointerMove = (e: any) => {
    e.stopPropagation();
    if (onHoverPoint) {
      const info = extractTerrainInfo(e);
      onHoverPoint(info);
    }
  };

  const handlePointerOut = () => {
    if (onHoverPoint) {
      onHoverPoint(null);
    }
  };

  const handleClick = (e: any) => {
    e.stopPropagation();
    if (onClickPoint) {
      const info = extractTerrainInfo(e);
      if (info) onClickPoint(info);
    }
  };

  return (
    <mesh
      ref={meshRef}
      geometry={geometry}
      onPointerMove={handlePointerMove}
      onPointerOut={handlePointerOut}
      onClick={handleClick}
      castShadow
      receiveShadow
    >
      <meshStandardMaterial
        map={wireframeOnly ? null : texture}
        color={wireframeOnly ? '#00f0ff' : '#ffffff'}
        roughness={0.8}
        metalness={0.1}
        wireframe={wireframe || wireframeOnly}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
};
