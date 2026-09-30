import React from 'react';

interface CompassProps {
  headingDeg?: number;
}

export const Compass: React.FC<CompassProps> = ({ headingDeg = 0 }) => {
  return (
    <div className="relative w-16 h-16 flex items-center justify-center pointer-events-none select-none">
      {/* Outer ring */}
      <div className="absolute inset-0 rounded-full border border-cyan-500/30 bg-slate-900/60 backdrop-blur-sm shadow-lg shadow-black/40" />
      
      {/* Rotating Dial */}
      <div
        className="absolute inset-1 rounded-full transition-transform duration-100 ease-out flex items-center justify-center"
        style={{ transform: `rotate(${-headingDeg}deg)` }}
      >
        {/* Needle North */}
        <div className="absolute top-1 w-0 h-0 border-x-4 border-x-transparent border-b-[18px] border-b-rose-500" />
        {/* Needle South */}
        <div className="absolute bottom-1 w-0 h-0 border-x-4 border-x-transparent border-t-[18px] border-t-cyan-400" />
        
        {/* Cardinal labels */}
        <span className="absolute top-1 text-[9px] font-mono font-bold text-rose-400">N</span>
        <span className="absolute bottom-1 text-[9px] font-mono font-bold text-cyan-300">S</span>
        <span className="absolute right-1.5 text-[8px] font-mono font-bold text-slate-400">E</span>
        <span className="absolute left-1.5 text-[8px] font-mono font-bold text-slate-400">W</span>
      </div>

      {/* Center Pivot */}
      <div className="w-2 h-2 rounded-full bg-cyan-400 border border-black z-10" />
    </div>
  );
};
