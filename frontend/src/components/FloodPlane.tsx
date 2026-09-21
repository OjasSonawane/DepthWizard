import React, { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';

interface FloodPlaneProps {
  waterElevation: number;
  minElevation: number;
  maxElevation: number;
  worldXSpan: number;
  worldZSpan: number;
  exaggeration: number;
  visible: boolean;
}

export const FloodPlane: React.FC<FloodPlaneProps> = ({
  waterElevation,
  minElevation,
  maxElevation,
  worldXSpan,
  worldZSpan,
  exaggeration,
  visible
}) => {
  const meshRef = useRef<THREE.Mesh>(null);
  const relief = Math.max(1e-4, maxElevation - minElevation);
  const sceneVerticalScale = 20.0 * exaggeration;
  const worldY = ((waterElevation - minElevation) / relief) * sceneVerticalScale;

  useFrame(({ clock }) => {
    if (meshRef.current) {
      // Subtle organic water heave
      const t = clock.getElapsedTime();
      meshRef.current.position.y = worldY + Math.sin(t * 1.5) * 0.08;
    }
  });

  if (!visible) return null;

  return (
    <mesh
      ref={meshRef}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, worldY, 0]}
    >
      <planeGeometry args={[worldXSpan * 1.05, worldZSpan * 1.05, 32, 32]} />
      <meshStandardMaterial
        color="#0077be"
        roughness={0.1}
        metalness={0.2}
        transparent
        opacity={0.65}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
};
