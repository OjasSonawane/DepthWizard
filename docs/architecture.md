# DepthWizard: System Architecture & Technical Specification

DepthWizard is an AI-powered single-view remote-sensing 3D terrain reconstruction platform designed for the **ISRO Software Problem Statement** under the **Disaster Management** theme.

## 1. High-Level Architecture

```mermaid
graph TD
    User([User / Operator]) --> Frontend[React 19 + TypeScript + Three.js UI]
    Frontend -->|REST / JSON / Multipart| API[FastAPI Backend Service]

    subgraph Ingestion & Preprocessing
        API --> UploadEngine[Upload & Validation Engine]
        UploadEngine --> GeoTIFFParser[Rasterio / PyProj Geospatial Inspector]
        UploadEngine --> FileStorage[(Backend File Storage)]
    end

    subgraph Neural Monocular Depth Pipeline
        GeoTIFFParser --> DepthModel[DepthEstimator: Depth Anything V2]
        DepthModel -->|Apple Silicon MPS / CUDA / CPU| RelDepth[Relative Depth Surface Float32]
    end

    subgraph Scale Calibration Subsystem
        RelDepth --> CalibEngine[Scale Calibration Engine]
        DEMInput[Optional Reference DEM: SRTM/CartoDEM] --> CalibEngine
        GCPInput[Optional Ground Control Points: CSV] --> CalibEngine
        CalibEngine -->|Affine Mapping: Z = a*d + b| DSM[Calibrated Metric DSM / rDSM]
    end

    subgraph Derivative & 3D Synthesis
        DSM --> HornSlope[Horn 3x3 Finite-Difference Slope Operator]
        DSM --> Hillshade[Analytical Hillshade: 315° Azimuth, 45° Altitude]
        DSM --> MeshGen[Mesh Service: 192x192 Heightfield + Wavefront OBJ]
        GeoTIFFParser --> RGBTexture[RGB Optical Texture Map]
        MeshGen --> ThreeScene[Three.js Interactive 3D Scene]
        RGBTexture --> ThreeScene
    end

    subgraph Analytics & Validation
        DSM --> RiskAnalytics[Elevation Risk, Landslide Hazards, Flood Simulator]
        DSM --> TransectProfiler[Cross-Section Elevation Profiler]
        RefGroundTruth[Ground Truth DEM / LiDAR] --> ValidationEngine[Validation Engine]
        DSM --> ValidationEngine
        ValidationEngine --> Metrics[MAE, RMSE, Pearson r, Diverging Error Map]
    end

    ThreeScene --> Frontend
    RiskAnalytics --> Frontend
    Metrics --> Frontend
```

## 2. Component Directory Structure

```
DepthWizard/
├── backend/
│   ├── app/
│   │   ├── api/             # REST endpoint routers
│   │   │   ├── upload.py    # Multi-format upload & raster inspection
│   │   │   ├── processing.py# 12-stage reconstruction pipeline
│   │   │   ├── visualization.py # 2D & 3D asset delivery
│   │   │   ├── evaluation.py# Ground truth reference validation
│   │   │   ├── samples.py   # Pre-bundled demo dataset catalog
│   │   │   └── export.py    # ZIP & multi-format export packaging
│   │   ├── config.py        # Settings, hardware detection, directory paths
│   │   ├── main.py          # FastAPI application & static mounts
│   │   ├── models/
│   │   │   └── depth_model.py # Depth Anything V2 + PyTorch MPS acceleration
│   │   ├── schemas/
│   │   │   └── schemas.py   # Strict Pydantic v2 schemas
│   │   └── services/
│   │       ├── depth_service.py      # Master pipeline orchestration
│   │       ├── geospatial_service.py # Rasterio GeoTIFF & PyProj CRS engine
│   │       ├── calibration_service.py# Huber regression & affine scaling
│   │       ├── dsm_service.py        # Horn slope, hillshade & colormaps
│   │       ├── mesh_service.py       # Heightfield & OBJ generator
│   │       └── evaluation_service.py # MAE, RMSE, Pearson r, Error map
│   ├── storage/             # Clean structured file storage
│   ├── tests/               # Pytest automated test suite
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/      # Compass, HUD, MeasurementTool, FloodPlane, Mesh
│   │   ├── context/         # ProjectContext state provider
│   │   ├── layouts/         # AppLayout sidebar and telemetry bar
│   │   ├── pages/           # 8 core application pages
│   │   ├── services/        # API client
│   │   └── types/           # TypeScript domain definitions
│   └── package.json
└── data/
    └── samples/             # Bundled Himalayan, Coastal & Aerial datasets
```

## 3. Hardware Acceleration

The `DepthEstimator` subsystem dynamically probes available hardware at startup:
- **Apple Silicon**: Uses `mps` (Metal Performance Shaders) for sub-second inference on Mac laptops.
- **NVIDIA GPU**: Uses `cuda:0` when CUDA drivers and GPUs are present.
- **CPU**: Clean fallback with PyTorch multi-threaded CPU execution.
