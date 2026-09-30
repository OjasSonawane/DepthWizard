import os
import csv
from pathlib import Path
import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin
import cv2

def create_samples():
    base_dir = Path(__file__).resolve().parent.parent / "data" / "samples"
    
    # ----------------------------------------------------
    # 1. Himalayan Valley Sample
    # ----------------------------------------------------
    him_dir = base_dir / "himalayan_valley"
    him_dir.mkdir(parents=True, exist_ok=True)
    
    w, h = 512, 512
    # Spatial grid for UTM 43N: Easting ~300000, Northing ~3400000, pixel size 10m
    west, north = 300000.0, 3400000.0
    pixel_size = 10.0
    transform = from_origin(west, north, pixel_size, pixel_size)
    crs = "EPSG:32643"

    # Synthetic realistic topography: ridges + valley + noise
    y, x = np.mgrid[0:h, 0:w]
    ridge1 = np.sin(x / 60.0 + y / 100.0) * 400.0
    ridge2 = np.cos(x / 40.0 - y / 50.0) * 250.0
    valley = -np.exp(-((x - 220)**2 + (y - 256)**2) / (2 * 120**2)) * 600.0
    base_elev = 3200.0
    noise = cv2.GaussianBlur(np.random.normal(0, 15, (h, w)).astype(np.float32), (15, 15), 3.0)
    dem_data = (base_elev + ridge1 + ridge2 + valley + noise).astype(np.float32)

    # Save reference DEM GeoTIFF
    ref_dem_path = him_dir / "himalayan_ref_dem.tif"
    with rasterio.open(
        ref_dem_path, "w", driver="GTiff",
        height=h, width=w, count=1, dtype=rasterio.float32,
        crs=crs, transform=transform, nodata=-9999.0
    ) as dst:
        dst.write(dem_data, 1)

    # Generate synthetic RGB satellite scene based on elevation & slope
    dy, dx = np.gradient(dem_data, pixel_size)
    slope = np.hypot(dx, dy)

    # Base landcover colors
    # High elev (>3600m): snow/rock (light gray/white)
    # Mid elev (3100-3600m): alpine vegetation/forest (deep green)
    # Valley bottom: river channel (blue-grey) and silty banks
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    norm_dem = (dem_data - 2600.0) / 1200.0
    norm_dem = np.clip(norm_dem, 0.0, 1.0)

    # Forest green base
    rgb[:, :, 0] = np.clip(40 + norm_dem * 150 - slope * 1.5, 20, 240).astype(np.uint8)
    rgb[:, :, 1] = np.clip(70 + norm_dem * 160 - slope * 1.2, 40, 245).astype(np.uint8)
    rgb[:, :, 2] = np.clip(35 + norm_dem * 180 + (norm_dem > 0.75) * 60, 20, 255).astype(np.uint8)

    # River in valley bottom
    river_mask = (dem_data < 2850.0) & (abs(x - 220) < 25)
    rgb[river_mask] = [45, 95, 140]

    # Save satellite scene GeoTIFF
    scene_tif_path = him_dir / "himalayan_scene.tif"
    with rasterio.open(
        scene_tif_path, "w", driver="GTiff",
        height=h, width=w, count=3, dtype=rasterio.uint8,
        crs=crs, transform=transform
    ) as dst:
        dst.write(rgb[:, :, 0], 1)
        dst.write(rgb[:, :, 1], 2)
        dst.write(rgb[:, :, 2], 3)

    # GCPs CSV
    gcp_path = him_dir / "himalayan_gcps.csv"
    with open(gcp_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "easting", "northing", "elevation"])
        gcp_pixels = [(80, 80), (420, 90), (250, 256), (90, 420), (430, 440), (220, 150)]
        for i, (pr, pc) in enumerate(gcp_pixels, 1):
            easting = west + pc * pixel_size
            northing = north - pr * pixel_size
            elev = round(float(dem_data[pr, pc]), 2)
            writer.writerow([f"GCP_{i:02d}", easting, northing, elev])

    print("Himalayan Valley dataset generated.")

    # ----------------------------------------------------
    # 2. Coastal Estuary Sample
    # ----------------------------------------------------
    coast_dir = base_dir / "coastal_estuary"
    coast_dir.mkdir(parents=True, exist_ok=True)

    c_w, c_h = 512, 512
    c_west, c_north = 400000.0, 2100000.0
    c_res = 5.0
    c_transform = from_origin(c_west, c_north, c_res, c_res)

    cy, cx = np.mgrid[0:c_h, 0:c_w]
    # Coastline from west (ocean) to east (land), max elev 35m
    coastal_slope = (cx / c_w) * 25.0
    dunes = np.sin(cy / 30.0) * 3.0
    estuary = -np.exp(-((cy - 256)**2) / (2 * 40**2)) * 12.0
    c_dem = np.clip(coastal_slope + dunes + estuary, 0.0, 45.0).astype(np.float32)

    # Save coastal DEM
    c_dem_path = coast_dir / "coastal_ref_dem.tif"
    with rasterio.open(
        c_dem_path, "w", driver="GTiff",
        height=c_h, width=c_w, count=1, dtype=rasterio.float32,
        crs=crs, transform=c_transform, nodata=-9999.0
    ) as dst:
        dst.write(c_dem, 1)

    # Coastal RGB
    c_rgb = np.zeros((c_h, c_w, 3), dtype=np.uint8)
    water_mask = c_dem < 1.0
    sand_mask = (c_dem >= 1.0) & (c_dem < 5.0)
    urban_mask = c_dem >= 5.0

    c_rgb[water_mask] = [20, 75, 130]  # Deep coastal ocean
    c_rgb[sand_mask] = [210, 195, 140]  # Coastal beach sand
    c_rgb[urban_mask] = [120, 140, 110] # Vegetated/urban land

    c_scene_path = coast_dir / "coastal_scene.tif"
    with rasterio.open(
        c_scene_path, "w", driver="GTiff",
        height=c_h, width=c_w, count=3, dtype=rasterio.uint8,
        crs=crs, transform=c_transform
    ) as dst:
        dst.write(c_rgb[:, :, 0], 1)
        dst.write(c_rgb[:, :, 1], 2)
        dst.write(c_rgb[:, :, 2], 3)

    print("Coastal Estuary dataset generated.")

    # ----------------------------------------------------
    # 3. Aerial Urban Survey (Non-Georeferenced)
    # ----------------------------------------------------
    aerial_dir = base_dir / "aerial_urban_flood"
    aerial_dir.mkdir(parents=True, exist_ok=True)

    a_w, a_h = 512, 512
    aerial_img = np.zeros((a_h, a_w, 3), dtype=np.uint8)
    # Green terrain background
    aerial_img[:] = [80, 120, 60]
    # Roads (cross)
    aerial_img[:, 230:280] = [60, 60, 65]
    aerial_img[230:280, :] = [60, 60, 65]
    # Buildings (rectangular clusters)
    for bx in [50, 130, 320, 410]:
        for by in [50, 130, 320, 410]:
            aerial_img[by:by+50, bx:bx+60] = [180, 150, 130]
            # Rooftop shadow
            aerial_img[by:by+5, bx:bx+60] = [120, 90, 80]

    Image.fromarray(aerial_img).save(aerial_dir / "aerial_survey.jpg", quality=95)
    print("Aerial Urban survey generated.")

if __name__ == "__main__":
    create_samples()
