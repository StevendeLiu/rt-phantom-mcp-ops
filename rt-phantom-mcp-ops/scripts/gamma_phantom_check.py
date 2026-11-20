#!/usr/bin/env python3
"""Synthetic 3D water-phantom Monte Carlo QA verification (PDD, DVH, 3D Gamma-index).

Strictly uses synthetic analytical / water-phantom dose grids (zero PHI, offline only).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import numpy as np


def generate_synthetic_phantom_doses(
    shape: Tuple[int, int, int] = (24, 24, 30),
    voxel_mm: float = 2.0,
    prescription_gy: float = 78.0,
    noise_sigma: float = 0.008,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate reference analytical dose and simulated Monte Carlo dose in a water phantom."""
    rng = np.random.default_rng(seed)
    nx, ny, nz = shape
    x = (np.arange(nx) - nx / 2.0) * voxel_mm
    y = (np.arange(ny) - ny / 2.0) * voxel_mm
    z = np.arange(nz) * voxel_mm  # depth in mm

    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

    # 6 MV-like PDD buildup + exponential attenuation
    dmax_mm = 15.0
    pdd = (1.0 - np.exp(-Z / (dmax_mm / 2.5))) * np.exp(-0.0038 * np.maximum(Z - dmax_mm, 0.0))
    pdd = pdd / np.max(pdd)

    # Lateral Gaussian-flattened field profile (20 mm half-width)
    r2 = X**2 + Y**2
    lateral = np.exp(-((r2 / (20.0**2)) ** 2))

    ref_dose = prescription_gy * pdd * lateral
    # Simulated MC dose with slight statistical noise and minor penumbra shift
    mc_dose = np.clip(ref_dose * (1.0 + rng.normal(0.0, noise_sigma, size=shape)), 0.0, None)
    return ref_dose, mc_dose


def compute_3d_gamma(
    ref_dose: np.ndarray,
    eval_dose: np.ndarray,
    voxel_mm: float = 2.0,
    dose_diff_pct: float = 2.0,
    dta_mm: float = 2.0,
    dose_threshold_pct: float = 10.0,
    search_radius_vox: int = 2,
) -> Dict[str, float]:
    """Compute global 3D gamma-index pass rate over voxels above dose threshold."""
    max_ref = float(np.max(ref_dose))
    dose_tol = (dose_diff_pct / 100.0) * max_ref
    cutoff = (dose_threshold_pct / 100.0) * max_ref

    mask = ref_dose >= cutoff
    eval_voxels = int(np.sum(mask))
    if eval_voxels == 0:
        return {"gamma_pass_rate_pct": 0.0, "mean_gamma": 0.0, "max_gamma": 0.0, "evaluated_voxels": 0}

    gamma_min = np.full(ref_dose.shape, np.inf, dtype=np.float64)
    nx, ny, nz = ref_dose.shape

    for dx in range(-search_radius_vox, search_radius_vox + 1):
        for dy in range(-search_radius_vox, search_radius_vox + 1):
            for dz in range(-search_radius_vox, search_radius_vox + 1):
                dist_mm = np.sqrt((dx * voxel_mm) ** 2 + (dy * voxel_mm) ** 2 + (dz * voxel_mm) ** 2)
                dist_term = (dist_mm / dta_mm) ** 2

                # Slice overlap
                rx0, rx1 = max(0, -dx), min(nx, nx - dx)
                ry0, ry1 = max(0, -dy), min(ny, ny - dy)
                rz0, rz1 = max(0, -dz), min(nz, nz - dz)

                ex0, ex1 = max(0, dx), min(nx, nx + dx)
                ey0, ey1 = max(0, dy), min(ny, ny + dy)
                ez0, ez1 = max(0, dz), min(nz, nz + dz)

                diff = eval_dose[ex0:ex1, ey0:ey1, ez0:ez1] - ref_dose[rx0:rx1, ry0:ry1, rz0:rz1]
                g_val = np.sqrt((diff / dose_tol) ** 2 + dist_term)
                gamma_min[rx0:rx1, ry0:ry1, rz0:rz1] = np.minimum(
                    gamma_min[rx0:rx1, ry0:ry1, rz0:rz1], g_val
                )

    masked_gamma = gamma_min[mask]
    pass_rate = float(np.mean(masked_gamma <= 1.0) * 100.0)
    return {
        "gamma_pass_rate_pct": round(pass_rate, 3),
        "mean_gamma": round(float(np.mean(masked_gamma)), 4),
        "max_gamma": round(float(np.max(masked_gamma)), 4),
        "evaluated_voxels": eval_voxels,
    }


def compute_dvh_summary(dose: np.ndarray, prescription_gy: float = 78.0) -> Dict[str, float]:
    """Compute lightweight DVH summary metrics inside the high-dose target region."""
    target = dose[dose >= 0.5 * prescription_gy]
    if target.size == 0:
        return {"D98_Gy": 0.0, "D50_Gy": 0.0, "D2_Gy": 0.0, "V95_pct": 0.0}
    return {
        "D98_Gy": round(float(np.percentile(target, 2)), 3),
        "D50_Gy": round(float(np.percentile(target, 50)), 3),
        "D2_Gy": round(float(np.percentile(target, 98)), 3),
        "V95_pct": round(float(np.mean(target >= 0.95 * prescription_gy) * 100.0), 2),
    }


def run_qa_suite(
    dd_pct: float = 2.0,
    dta_mm: float = 2.0,
    prescription_gy: float = 78.0,
    noise_sigma: float = 0.008,
) -> Dict[str, object]:
    ref_dose, mc_dose = generate_synthetic_phantom_doses(
        prescription_gy=prescription_gy,
        noise_sigma=noise_sigma,
    )
    gamma = compute_3d_gamma(ref_dose, mc_dose, dose_diff_pct=dd_pct, dta_mm=dta_mm)
    dvh_ref = compute_dvh_summary(ref_dose, prescription_gy=prescription_gy)
    dvh_mc = compute_dvh_summary(mc_dose, prescription_gy=prescription_gy)

    # AAPM TG-218 action/tolerance inspired pass gate (>= 95% for 2%/2mm synthetic check)
    status = "PASS" if gamma["gamma_pass_rate_pct"] >= 95.0 else "NEEDS_REVIEW"
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "phantom": "synthetic_water_tank_6MV",
        "prescription_gy": prescription_gy,
        "criteria": f"{dd_pct}%/{dta_mm}mm (global, 10% cutoff)",
        "status": status,
        "gamma": gamma,
        "dvh_reference": dvh_ref,
        "dvh_monte_carlo": dvh_mc,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline synthetic water-phantom 3D Gamma QA check.")
    parser.add_argument("--dd", type=float, default=2.0, help="Dose difference tolerance (%)")
    parser.add_argument("--dta", type=float, default=2.0, help="Distance-to-agreement tolerance (mm)")
    parser.add_argument("--rx", type=float, default=78.0, help="Reference prescription dose (Gy)")
    parser.add_argument("--noise", type=float, default=0.008, help="Synthetic MC statistical noise sigma")
    parser.add_argument("--out", type=Path, default=Path("reports/latest_qa_report.json"), help="Output JSON path")
    args = parser.parse_args()

    report = run_qa_suite(dd_pct=args.dd, dta_mm=args.dta, prescription_gy=args.rx, noise_sigma=args.noise)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[QA {report['status']}] {report['phantom']} | Criteria: {report['criteria']}")
    print(f"  3D Gamma Pass Rate: {report['gamma']['gamma_pass_rate_pct']}% (mean={report['gamma']['mean_gamma']})")
    print(f"  MC DVH Summary:     {report['dvh_monte_carlo']}")
    print(f"  Saved report to:    {args.out}")


if __name__ == "__main__":
    main()
