"""Step 5 — outlier-robust similarity registration (never guesses)."""

from __future__ import annotations

import dataclasses
import itertools
import math
from typing import Optional, Sequence


@dataclasses.dataclass(frozen=True)
class Anchor:
    id: str
    src: tuple[float, float]  # paper inches, display frame, y DOWN
    dst: tuple[float, float]  # world feet or other paper inches (y UP in dst)
    weight_note: str = ""


@dataclasses.dataclass
class Registration:
    status: str
    reasons: list[str]
    scale: Optional[float] = None
    rotation_deg: Optional[float] = None
    a: Optional[complex] = None
    b: Optional[complex] = None
    inlier_ids: list[str] = dataclasses.field(default_factory=list)
    outlier_ids: list[str] = dataclasses.field(default_factory=list)
    rmse: Optional[float] = None
    max_residual: Optional[float] = None
    span_in: Optional[float] = None
    anisotropy: Optional[float] = None

    def apply(self, x_in: float, y_in: float) -> tuple[float, float]:
        if self.a is None or self.b is None:
            raise ValueError(f"registration not usable: {self.status} {self.reasons}")
        z = self.a * complex(x_in, -y_in) + self.b
        return z.real, z.imag

    def invert(self, e: float, n: float) -> tuple[float, float]:
        if self.a is None or self.b is None:
            raise ValueError(f"registration not usable: {self.status} {self.reasons}")
        w = (complex(e, n) - self.b) / self.a
        return w.real, -w.imag

    def to_record(self) -> dict:
        return {
            "status": self.status,
            "reasons": self.reasons,
            "scale_dst_per_paper_inch": self.scale,
            "rotation_deg": self.rotation_deg,
            "a_re": None if self.a is None else self.a.real,
            "a_im": None if self.a is None else self.a.imag,
            "b_re": None if self.b is None else self.b.real,
            "b_im": None if self.b is None else self.b.imag,
            "inlier_ids": self.inlier_ids,
            "outlier_ids": self.outlier_ids,
            "rmse": self.rmse,
            "max_residual": self.max_residual,
        }


def _to_z(an: Anchor) -> tuple[complex, complex]:
    return complex(an.src[0], -an.src[1]), complex(an.dst[0], an.dst[1])


def _fit(zs: Sequence[complex], ds: Sequence[complex]) -> tuple[complex, complex]:
    n = len(zs)
    zm = sum(zs) / n
    dm = sum(ds) / n
    num = sum((z - zm).conjugate() * (d - dm) for z, d in zip(zs, ds))
    den = sum(abs(z - zm) ** 2 for z in zs)
    a = num / den
    return a, dm - a * zm


def _residuals(anchors: Sequence[Anchor], a: complex, b: complex) -> list[float]:
    out: list[float] = []
    for an in anchors:
        z, d = _to_z(an)
        out.append(abs(a * z + b - d))
    return out


def _anisotropy(zs: Sequence[complex]) -> float:
    n = len(zs)
    zm = sum(zs) / n
    sxx = sum((z.real - zm.real) ** 2 for z in zs)
    syy = sum((z.imag - zm.imag) ** 2 for z in zs)
    sxy = sum((z.real - zm.real) * (z.imag - zm.imag) for z in zs)
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    disc = math.sqrt(max(tr * tr / 4 - det, 0.0))
    l1, l2 = tr / 2 + disc, tr / 2 - disc
    return math.sqrt(max(l2, 0.0) / l1) if l1 > 0 else 0.0


def register(
    anchors: Sequence[Anchor],
    *,
    tol: float,
    min_sep_in: float = 0.5,
    min_inliers: int = 3,
    expected_scale: Optional[float] = None,
    scale_rel_tol: float = 0.10,
    min_anisotropy: float = 0.15,
) -> Registration:
    reasons: list[str] = []
    if len({a.id for a in anchors}) != len(anchors):
        return Registration("insufficient", ["duplicate_anchor_ids"])
    if len(anchors) < 2:
        return Registration("insufficient", [f"need>=2_anchors_got_{len(anchors)}"])

    zd = [_to_z(a) for a in anchors]
    best: list[tuple[frozenset[int], float]] = []
    for i, j in itertools.combinations(range(len(anchors)), 2):
        (z1, d1), (z2, d2) = zd[i], zd[j]
        if abs(z2 - z1) < min_sep_in or abs(d2 - d1) < 1e-9:
            continue
        a = (d2 - d1) / (z2 - z1)
        if expected_scale and abs(abs(a) / expected_scale - 1) > scale_rel_tol:
            continue
        b = d1 - a * z1
        res = _residuals(anchors, a, b)
        inl = frozenset(k for k, r in enumerate(res) if r <= tol)
        if len(inl) >= 2:
            best.append((inl, 0.0))
    if not best:
        why = ["no_pair_hypothesis_survived"]
        if expected_scale:
            why.append("scale_veto_or_pair_too_close")
        return Registration("insufficient", why)

    cands: dict[frozenset[int], tuple[complex, complex, float, float]] = {}
    for inl, _ in best:
        if inl in cands:
            continue
        idx = sorted(inl)
        a, b = _fit([zd[k][0] for k in idx], [zd[k][1] for k in idx])
        full = _residuals(anchors, a, b)
        inl2 = frozenset(k for k, r in enumerate(full) if r <= tol)
        idx2 = sorted(inl2)
        a, b = _fit([zd[k][0] for k in idx2], [zd[k][1] for k in idx2])
        res2 = _residuals([anchors[k] for k in idx2], a, b)
        rmse = math.sqrt(sum(r * r for r in res2) / len(res2))
        cands[inl2] = (a, b, rmse, max(res2))
    ranked = sorted(cands.items(), key=lambda kv: (-len(kv[0]), kv[1][2]))
    inl, (a, b, rmse, mx) = ranked[0]
    ids_in = [anchors[k].id for k in sorted(inl)]
    ids_out = [anchors[k].id for k in range(len(anchors)) if k not in inl]
    scale = abs(a)
    rot = math.degrees(math.atan2(a.imag, a.real))
    zs_in = [zd[k][0] for k in sorted(inl)]
    span = max(abs(p - q) for p, q in itertools.combinations(zs_in, 2))
    aniso = _anisotropy(zs_in) if len(zs_in) >= 3 else 0.0

    status = "registered"
    for other, (a2, b2, _rmse2, _) in ranked[1:]:
        if len(other) == len(inl) and other != inl:
            if abs(a2 / a - 1) > 0.02 or abs(b2 - b) > 3 * tol:
                status = "ambiguous"
                reasons.append(f"competing_consensus_same_size({len(other)})")
                break

    if len(inl) < 2:
        return Registration("insufficient", ["no_consensus"])
    if len(inl) < min_inliers and status == "registered":
        status = "needs_review"
        reasons.append(f"inliers={len(inl)}<{min_inliers}_no_redundancy")
    if len(inl) >= 3 and aniso < min_anisotropy and status == "registered":
        status = "needs_review"
        reasons.append(f"collinear_anchors(aniso={aniso:.2f})_extrapolation_off_axis_unreliable")
    if expected_scale and abs(scale / expected_scale - 1) > scale_rel_tol:
        if status == "registered":
            status = "needs_review"
        reasons.append(f"fit_scale_{scale:.2f}_vs_expected_{expected_scale:.2f}")
    if ids_out:
        reasons.append(f"outliers:{','.join(ids_out)}")

    return Registration(status, reasons, scale, rot, a, b, ids_in, ids_out, rmse, mx, span, aniso)


def screen_survey_rows(
    rows: Sequence[dict],
    max_pair_dist_ft: float = 1.0,
) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for r in rows:
        d = (r.get("meta_json") or {}).get("pairing_distance_ft")
        if d is not None and d > max_pair_dist_ft:
            dropped.append({**r, "_drop": f"pairing_distance_ft={d:.2f}>{max_pair_dist_ft}"})
        else:
            kept.append(r)
    out: list[dict] = []
    for r in kept:
        clash = [
            o
            for o in kept
            if o is not r and (o["northing"] == r["northing"] or o["easting"] == r["easting"])
        ]
        if clash:
            dr = (r.get("meta_json") or {}).get("pairing_distance_ft", 0)
            if any(((o.get("meta_json") or {}).get("pairing_distance_ft", 0)) <= dr for o in clash):
                dropped.append({**r, "_drop": "reuses_N_or_E_of_better_paired_row"})
                continue
        out.append(r)
    return out, dropped
