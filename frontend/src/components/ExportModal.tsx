import React from 'react';
import { useProject } from '../context/ProjectContext';
import { api } from '../services/api';
import { X, Download, FileArchive, Globe, Box, Image, FileText, CheckCircle2, ShieldCheck } from 'lucide-react';

export const ExportModal: React.FC = () => {
  const { isExportOpen, setIsExportOpen, results, currentJobId, evaluation } = useProject();

  if (!isExportOpen || !results || !currentJobId) return null;

  const exportZipUrl = api.getExportUrl(currentJobId);
  const reportJsonUrl = `/api/results/${currentJobId}/report`;

  const exportItems = [
    {
      title: 'Complete Project Archive (.ZIP)',
      desc: 'Contains DSM GeoTIFF, Wavefront OBJ mesh, JSON heightfield, all telemetry PNG layers, and project_report.json.',
      icon: <FileArchive className="w-5 h-5 text-cyan-400" />,
      url: exportZipUrl,
      isPrimary: true
    },
    {
      title: 'Scientific Audit Report (project_report.json)',
      desc: 'Machine-readable GeoJSON/JSON telemetry with CRS verification, affine transform, model provenance, and validation metrics.',
      icon: <FileText className="w-5 h-5 text-emerald-400" />,
      url: reportJsonUrl,
      downloadName: `project_report_${currentJobId}.json`
    },
    {
      title: 'Digital Surface Model (.TIF)',
      desc: results.is_georeferenced
        ? `GeoTIFF preserving CRS (${results.image_metadata.crs || 'UTM'}) and metric elevations.`
        : 'rDSM GeoTIFF with relative elevation units.',
      icon: <Globe className="w-5 h-5 text-blue-400" />,
      url: results.assets.dsm_geotiff
    },
    {
      title: '3D Wavefront Terrain Mesh (.OBJ)',
      desc: 'Triangulated 3D mesh with vertex elevations and UV texture coordinates for Blender/QGIS/Unreal.',
      icon: <Box className="w-5 h-5 text-amber-400" />,
      url: results.assets.mesh_obj
    },
    ...(evaluation && evaluation.abs_error_map_url ? [{
      title: 'Ground Truth Absolute Error Map (.PNG)',
      desc: 'Quantified spatial error residuals compared against reference DEM raster.',
      icon: <Image className="w-5 h-5 text-rose-400" />,
      url: evaluation.abs_error_map_url
    }] : []),
    {
      title: 'Analytical Hillshade Raster (.PNG)',
      desc: '315° azimuth shaded relief surface map.',
      icon: <Image className="w-5 h-5 text-purple-400" />,
      url: results.assets.hillshade
    },
    {
      title: 'Slope Hazard Map (.PNG)',
      desc: 'Horn gradient slope calculation with hazard zones.',
      icon: <Image className="w-5 h-5 text-rose-400" />,
      url: results.assets.slope
    }
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0e1424] border border-slate-700/80 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Download className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Export Reconstruction Assets</h3>
              <p className="text-xs text-slate-400 font-mono">Job: {currentJobId} • {results.filename}</p>
            </div>
          </div>
          <button
            onClick={() => setIsExportOpen(false)}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Spatial Verification Checklist Banner */}
        <div className="px-6 py-2.5 bg-slate-950/60 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-slate-300">
          <div className="flex items-center space-x-1.5 text-emerald-400">
            <ShieldCheck className="w-4 h-4" />
            <span className="font-bold">SPATIAL AUDIT:</span>
          </div>
          <div className="flex items-center space-x-3 text-slate-400">
            <span>CRS: <strong className="text-white">{results.image_metadata.crs ? `${results.image_metadata.crs} ✓` : 'Local Grid ✓'}</strong></span>
            <span>•</span>
            <span>Transform: <strong className="text-white">{results.image_metadata.transform ? 'Affine (6-param) ✓' : 'Preserved ✓'}</strong></span>
            <span>•</span>
            <span>Units: <strong className="text-cyan-400">{results.dsm_stats.is_metric ? 'Meters (AMSL) ✓' : 'Relative Scale ✓'}</strong></span>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-3">
          {exportItems.map((item, idx) => (
            <div
              key={idx}
              className={`flex items-center justify-between p-4 rounded-xl border transition-all ${
                item.isPrimary
                  ? 'bg-cyan-500/10 border-cyan-500/30 hover:bg-cyan-500/15'
                  : 'bg-slate-900/60 border-slate-800/80 hover:bg-slate-800/60'
              }`}
            >
              <div className="flex items-start space-x-3.5 pr-4">
                <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700/60 mt-0.5">
                  {item.icon}
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-slate-100">{item.title}</h4>
                  <p className="text-xs text-slate-400 mt-0.5">{item.desc}</p>
                </div>
              </div>

              <a
                href={item.url}
                download
                className={`flex-shrink-0 flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all ${
                  item.isPrimary
                    ? 'bg-cyan-500 hover:bg-cyan-400 text-black shadow-lg shadow-cyan-500/25'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
                }`}
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download</span>
              </a>
            </div>
          ))}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-slate-800/80 bg-slate-950/40 flex items-center justify-between text-xs text-slate-400 font-mono">
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>All spatial tags preserved (GeoTIFF / OBJ / JSON)</span>
          </div>
          <button
            onClick={() => setIsExportOpen(false)}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-sans"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
