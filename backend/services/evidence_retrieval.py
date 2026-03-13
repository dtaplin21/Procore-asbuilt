from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from models.models import Drawing, EvidenceDrawingLink, EvidenceRecord


@dataclass
class EvidenceMatchResult:
    evidence: EvidenceRecord
    score: float
    reasons: List[Dict[str, Any]] = field(default_factory=list)
    direct_links: List[EvidenceDrawingLink] = field(default_factory=list)
    discipline_overlap: List[str] = field(default_factory=list)
    revision_proximity_days: Optional[int] = None


@dataclass
class EvidenceContextResult:
    drawing: Drawing
    matches: List[EvidenceMatchResult]


class EvidenceRetrievalService:
    """Rank evidence records for a drawing using the currently available signals."""

    DIRECT_LINK_WEIGHT = 1.0
    DISCIPLINE_WEIGHT = 0.35
    REVISION_WEIGHT = 0.25

    # Prefix → disciplines mapping for plan naming conventions.
    PREFIX_DISCIPLINE_MAP: Dict[str, Sequence[str]] = {
        "A": ("architectural",),
        "AR": ("architectural",),
        "S": ("structural",),
        "ST": ("structural",),
        "STR": ("structural",),
        "C": ("civil",),
        "CI": ("civil",),
        "CE": ("civil",),
        "E": ("electrical",),
        "EL": ("electrical",),
        "P": ("plumbing",),
        "PL": ("plumbing",),
        "M": ("mechanical",),
        "ME": ("mechanical",),
        "FP": ("fire_protection",),
        "FD": ("fire_protection",),
        "F": ("fire_protection",),
        "MEP": ("mechanical", "electrical", "plumbing"),
        "G": ("general",),
        "GN": ("general",),
        "LS": ("landscape",),
        "L": ("landscape",),
    }

    TRADE_DISCIPLINE_MAP: Dict[str, str] = {
        "hvac": "mechanical",
        "mechanical": "mechanical",
        "mep": "mechanical",
        "electrical": "electrical",
        "lighting": "electrical",
        "power": "electrical",
        "plumbing": "plumbing",
        "fire protection": "fire_protection",
        "fire": "fire_protection",
        "sprinkler": "fire_protection",
        "structural": "structural",
        "concrete": "structural",
        "steel": "structural",
        "civil": "civil",
        "sitework": "civil",
        "site": "civil",
        "architectural": "architectural",
        "finishes": "architectural",
        "landscape": "landscape",
        "general": "general",
    }

    DISCIPLINE_KEYWORDS: Dict[str, Sequence[str]] = {
        "structural": ("structural", "steel", "concrete", "rebar", "foundation"),
        "architectural": ("architectural", "interior", "finish", "partition", "door", "window"),
        "mechanical": ("mechanical", "hvac", "duct", "air", "equipment"),
        "electrical": ("electrical", "lighting", "switchgear", "power", "panel", "low voltage"),
        "plumbing": ("plumbing", "pipe", "piping", "sanitary", "storm", "water"),
        "fire_protection": ("fire", "sprinkler", "suppression"),
        "civil": ("civil", "site", "grading", "utility"),
        "landscape": ("landscape", "plant", "irrigation"),
        "general": ("general", "cover", "index"),
    }

    def __init__(self, db: Session):
        self.db = db

    def get_context_for_drawing(
        self,
        project_id: int,
        drawing_id: int,
        *,
        limit: int = 20,
    ) -> Optional[EvidenceContextResult]:
        drawing = (
            self.db.query(Drawing)
            .filter(Drawing.project_id == project_id, Drawing.id == drawing_id)
            .first()
        )
        if drawing is None:
            return None

        links = (
            self.db.query(EvidenceDrawingLink)
            .filter(
                EvidenceDrawingLink.project_id == project_id,
                EvidenceDrawingLink.drawing_id == drawing_id,
            )
            .order_by(EvidenceDrawingLink.id.asc())
            .all()
        )
        links_by_evidence: Dict[int, List[EvidenceDrawingLink]] = {}
        for link in links:
            links_by_evidence.setdefault(int(link.evidence_id), []).append(link)

        evidence_records = (
            self.db.query(EvidenceRecord)
            .filter(EvidenceRecord.project_id == project_id)
            .order_by(EvidenceRecord.created_at.desc(), EvidenceRecord.id.desc())
            .all()
        )

        drawing_disciplines = self._infer_drawing_disciplines(drawing)
        matches: List[EvidenceMatchResult] = []

        for record in evidence_records:
            direct_links = links_by_evidence.get(int(record.id), [])
            if not direct_links and not drawing_disciplines:
                continue

            evidence_disciplines = self._infer_evidence_disciplines(record)
            overlap = sorted(drawing_disciplines.intersection(evidence_disciplines))

            score = 0.0
            reasons: List[Dict[str, Any]] = []

            if direct_links:
                weight = self.DIRECT_LINK_WEIGHT + min(len(direct_links) - 1, 2) * 0.1
                score += weight
                reasons.append(
                    {
                        "reason": "direct_link",
                        "weight": round(weight, 3),
                        "details": {
                            "count": len(direct_links),
                            "link_types": sorted({link.link_type for link in direct_links}),
                        },
                    }
                )

            if overlap:
                overlap_weight = self.DISCIPLINE_WEIGHT + min(len(overlap) - 1, 3) * 0.05
                score += overlap_weight
                reasons.append(
                    {
                        "reason": "discipline_overlap",
                        "weight": round(overlap_weight, 3),
                        "details": {"overlap": overlap},
                    }
                )

            revision_days = self._revision_delta_days(drawing, record)
            revision_weight = self._revision_weight(revision_days)
            if revision_weight > 0:
                score += revision_weight
                reasons.append(
                    {
                        "reason": "revision_window",
                        "weight": round(revision_weight, 3),
                        "details": {"days_delta": revision_days},
                    }
                )

            if score <= 0:
                continue

            matches.append(
                EvidenceMatchResult(
                    evidence=record,
                    score=round(score, 4),
                    reasons=reasons,
                    direct_links=direct_links,
                    discipline_overlap=overlap,
                    revision_proximity_days=revision_days,
                )
            )

        matches.sort(key=lambda m: (-(m.score), getattr(m.evidence, "created_at", datetime.min)))
        return EvidenceContextResult(drawing=drawing, matches=matches[:limit])

    # ------------------------------------------------------------------
    # Signal helpers
    # ------------------------------------------------------------------

    def _infer_drawing_disciplines(self, drawing: Drawing) -> Set[str]:
        disciplines: Set[str] = set()
        fields = [drawing.name or "", getattr(drawing, "source", None) or ""]
        for field in fields:
            disciplines.update(self._disciplines_from_text(field))

        prefix = self._extract_sheet_prefix(drawing.name or "")
        if prefix:
            for mapped in self.PREFIX_DISCIPLINE_MAP.get(prefix, ()):
                disciplines.add(mapped)

        if not disciplines:
            disciplines.add("general")
        return disciplines

    def _infer_evidence_disciplines(self, evidence: EvidenceRecord) -> Set[str]:
        disciplines: Set[str] = set()
        potential_fields: List[Any] = [
            getattr(evidence, "trade", None),
            getattr(evidence, "spec_section", None),
            getattr(evidence, "title", None),
            getattr(evidence, "type", None),
        ]

        meta = getattr(evidence, "meta", None)
        if isinstance(meta, dict):
            for key in ("discipline", "trade", "category"):
                potential_fields.append(meta.get(key))

        cross_refs = getattr(evidence, "cross_refs_json", None)
        if isinstance(cross_refs, list):
            for entry in cross_refs:
                if isinstance(entry, dict):
                    potential_fields.extend(
                        entry.get(k) for k in ("value", "label", "discipline", "trade")
                    )
                elif isinstance(entry, str):
                    potential_fields.append(entry)

        for value in potential_fields:
            disciplines.update(self._disciplines_from_text(value))

        if not disciplines:
            disciplines.add("general")
        return disciplines

    def _disciplines_from_text(self, value: Any) -> Set[str]:
        results: Set[str] = set()
        if value is None:
            return results
        if isinstance(value, str):
            lowered = value.strip().lower()
            if not lowered:
                return results
            trade_hit = self.TRADE_DISCIPLINE_MAP.get(lowered)
            if trade_hit:
                results.add(trade_hit)

            tokens = re.split(r"[^a-z]+", lowered)
            tokens = [token for token in tokens if token]
            for token in tokens:
                trade_hit = self.TRADE_DISCIPLINE_MAP.get(token)
                if trade_hit:
                    results.add(trade_hit)
                    continue
                for discipline, keywords in self.DISCIPLINE_KEYWORDS.items():
                    if any(keyword in token for keyword in keywords):
                        results.add(discipline)
                        break
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                results.update(self._disciplines_from_text(item))
        elif isinstance(value, dict):
            for val in value.values():
                results.update(self._disciplines_from_text(val))
        return results

    PREFIX_REGEX = re.compile(r"^([A-Z]{1,4})(?=[\d\s\-_\.])|^([A-Z]{1,4})$")

    def _extract_sheet_prefix(self, name: str) -> Optional[str]:
        normalized = (name or "").strip().upper()
        match = self.PREFIX_REGEX.search(normalized)
        if match:
            group = match.group(1) or match.group(2)
            if group:
                return group
        # If no delimiter, remove trailing digits.
        letters = re.match(r"^([A-Z]{1,4})", normalized)
        if letters:
            return letters.group(1)
        return None

    def _revision_delta_days(self, drawing: Drawing, evidence: EvidenceRecord) -> Optional[int]:
        drawing_dt = self._normalize_datetime(getattr(drawing, "updated_at", None) or getattr(drawing, "created_at", None))
        if drawing_dt is None:
            return None

        evidence_dates = self._collect_evidence_dates(evidence)
        if not evidence_dates:
            return None

        deltas = [abs((drawing_dt - dt).total_seconds()) for dt in evidence_dates]
        if not deltas:
            return None
        best_delta_days = int(min(deltas) // 86400)
        return best_delta_days

    def _revision_weight(self, delta_days: Optional[int]) -> float:
        if delta_days is None:
            return 0.0
        if delta_days <= 14:
            return self.REVISION_WEIGHT
        if delta_days <= 30:
            return self.REVISION_WEIGHT * 0.7
        if delta_days <= 60:
            return self.REVISION_WEIGHT * 0.4
        if delta_days <= 90:
            return self.REVISION_WEIGHT * 0.2
        return 0.0

    def _collect_evidence_dates(self, evidence: EvidenceRecord) -> List[datetime]:
        dates: List[datetime] = []
        for attr in ("created_at", "updated_at"):
            dt = self._normalize_datetime(getattr(evidence, attr, None))
            if dt is not None:
                dates.append(dt)

        bucket = getattr(evidence, "dates", None)
        if isinstance(bucket, dict):
            values = bucket.values()
        elif isinstance(bucket, list):
            values = bucket
        else:
            values = []

        for value in values:
            if isinstance(value, dict):
                for candidate in value.values():
                    dt = self._parse_datetime(candidate)
                    if dt:
                        dates.append(dt)
            else:
                dt = self._parse_datetime(value)
                if dt:
                    dates.append(dt)

        return dates

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return self._normalize_datetime(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            iso_candidate = cleaned.replace("Z", "+00:00") if cleaned.endswith("Z") else cleaned
            try:
                parsed = datetime.fromisoformat(iso_candidate)
                return self._normalize_datetime(parsed)
            except ValueError:
                return None
        return None

    def _normalize_datetime(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
