/**
 * TypeScript mirror of backend/services/inspection_vocabulary.py.
 *
 * This mirrors category names and CANONICAL terms only — not aliases or
 * extraction regex patterns, since those are backend extraction
 * implementation detail the frontend doesn't need. The frontend's job is
 * to render already-normalized tags (from DrawingOverlay / inspection_runs
 * records) using consistent labels, category colors, and grouping — not
 * to re-run extraction itself.
 *
 * Contract-sync rule: if backend/services/inspection_vocabulary.py changes
 * a category name or a canonical term, update this file in the same PR —
 * the same convention used for shared/schema.ts <-> backend/models/schemas.py
 * elsewhere in this refactor.
 */

export enum VocabCategory {
  ProjectIdentifier = "project_identifier",
  InspectionType = "inspection_type",
  InspectionStatus = "inspection_status",
  LocationTerm = "location_term",
  TradeTerm = "trade_term",
  DrawingTerm = "drawing_term",
  SheetIdentifier = "sheet_identifier",
  DocumentReference = "document_reference",
  MarkupTerm = "markup_term",
  FieldConditionTerm = "field_condition_term",
  InspectionActionTerm = "inspection_action_term",
  ConfidenceLabel = "confidence_label",
}

export enum ConfidenceLabel {
  High = "High Confidence",
  Medium = "Medium Confidence",
  Low = "Low Confidence",
}

/** Canonical terms per category. Keep in the same order as the Python
 * source for easy diffing. SheetIdentifier has no fixed list (pattern-
 * matched on the backend) so it's intentionally empty here. */
export const VOCABULARY: Record<VocabCategory, readonly string[]> = {
  [VocabCategory.ProjectIdentifier]: [
    "Project",
    "Project Number",
    "Permit",
    "Phase",
    "Area",
    "Building",
    "Facility",
    "Campus",
    "Site",
    "Utility",
    "NPC",
    "UCSF",
    "Benioff",
  ],
  [VocabCategory.InspectionType]: [
    "Underground Fire Water Rough In",
    "Rough In",
    "Final",
    "Partial Final",
    "Above Ground",
    "Underground",
    "Hydrostatic Test",
    "Flush",
    "Acceptance Test",
    "Fire Water",
    "Fire Protection",
    "Sprinkler",
    "Underground Piping",
    "Underground Utilities",
  ],
  [VocabCategory.InspectionStatus]: [
    "Open",
    "Closed",
    "Approved",
    "Approved As Noted",
    "Rejected",
    "Pending",
    "In Progress",
    "Scheduled",
    "Completed",
    "Passed",
    "Failed",
    "Deferred",
  ],
  [VocabCategory.LocationTerm]: [
    "Utility MR",
    "Mechanical Room",
    "Equipment Room",
    "Site",
    "Yard",
    "Corridor",
    "Level",
    "Floor",
    "Roof",
    "Exterior",
    "Interior",
    "Building Area",
    "Grid Line",
    "Coordinate",
    "Utility Corridor",
  ],
  [VocabCategory.TradeTerm]: [
    "Fire Protection",
    "Mechanical",
    "Plumbing",
    "Electrical",
    "Structural",
    "Civil",
    "Architectural",
    "Underground Utilities",
  ],
  [VocabCategory.DrawingTerm]: [
    "Drawing",
    "Sheet",
    "Sheet Number",
    "Plan",
    "Detail",
    "Section",
    "Elevation",
    "Revision",
    "Attachment",
    "Reference Drawing",
    "Master Drawing",
    "Construction Drawing",
  ],
  [VocabCategory.SheetIdentifier]: [],
  [VocabCategory.DocumentReference]: [
    "Attachment",
    "Linked Drawing",
    "Referenced Drawing",
    "Supporting Document",
    "Inspection Package",
    "Record Drawing",
  ],
  [VocabCategory.MarkupTerm]: [
    "Cloud",
    "Revision Cloud",
    "Arrow",
    "Leader",
    "Callout",
    "Note",
    "Comment",
    "Markup",
    "Highlight",
    "Stamp",
    "Inspection Tag",
    "Deficiency Marker",
  ],
  [VocabCategory.FieldConditionTerm]: [
    "Installed",
    "Existing",
    "New",
    "Verify",
    "Confirm",
    "Relocate",
    "Remove",
    "Modify",
    "Correct",
    "Repair",
    "Replace",
  ],
  [VocabCategory.InspectionActionTerm]: [
    "Inspect",
    "Verify",
    "Observe",
    "Witness",
    "Review",
    "Test",
    "Approve",
    "Reject",
    "Close",
    "Document",
  ],
  [VocabCategory.ConfidenceLabel]: [
    ConfidenceLabel.High,
    ConfidenceLabel.Medium,
    ConfidenceLabel.Low,
  ],
};

/** The shape of a single extracted/normalized term, as produced by
 * backend.ai.pipelines.term_extractor.ExtractedTerm.to_dict() and
 * returned over the wire. Field names are camelCase to match the
 * to_dict() serialization. */
export interface ExtractedTerm {
  category: VocabCategory;
  canonical: string;
  matchedText: string;
  start: number;
  end: number;
  confidenceScore: number;
  confidenceLabel: ConfidenceLabel;
}

/** Mirrors NormalizedEvidenceTags.to_dict() from inspection_mapping.py —
 * the normalized-tag bundle attached to a DrawingOverlay / inspection
 * finding once evidence text has been run through extraction. */
export interface NormalizedEvidenceTags {
  inspectionTypes: string[];
  inspectionStatuses: string[];
  locations: string[];
  trades: string[];
  fieldConditions: string[];
  actions: string[];
  markupTerms: string[];
  confidenceLabel: ConfidenceLabel;
}

/** Convenience lookup for UI components that need every canonical term
 * for a category, e.g. populating a filter dropdown on the inspection
 * runs sidebar. */
export function canonicalTermsFor(category: VocabCategory): readonly string[] {
  return VOCABULARY[category];
}

/** Display color tokens per category, for consistent overlay/tag styling
 * across the inspection runs sidebar, overlay layer, and findings list.
 * Adjust to the app's actual design tokens — these are placeholders. */
export const VOCAB_CATEGORY_COLOR: Record<VocabCategory, string> = {
  [VocabCategory.ProjectIdentifier]: "#64748B",
  [VocabCategory.InspectionType]: "#2E5395",
  [VocabCategory.InspectionStatus]: "#1F8A4C",
  [VocabCategory.LocationTerm]: "#B97034",
  [VocabCategory.TradeTerm]: "#7B5EA7",
  [VocabCategory.DrawingTerm]: "#44546A",
  [VocabCategory.SheetIdentifier]: "#0E7C86",
  [VocabCategory.DocumentReference]: "#8A6D3B",
  [VocabCategory.MarkupTerm]: "#C0392B",
  [VocabCategory.FieldConditionTerm]: "#D68910",
  [VocabCategory.InspectionActionTerm]: "#117864",
  [VocabCategory.ConfidenceLabel]: "#566573",
};

/** Maps a confidence label to a severity-style indicator, for surfacing
 * "this extraction needs a human glance" in the sidebar/overlay UI. */
export function confidenceIndicator(
  label: ConfidenceLabel
): "success" | "warning" | "danger" {
  switch (label) {
    case ConfidenceLabel.High:
      return "success";
    case ConfidenceLabel.Medium:
      return "warning";
    case ConfidenceLabel.Low:
      return "danger";
  }
}
