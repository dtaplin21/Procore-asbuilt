/**
 * Canonical inspection vocabulary — frontend mirror of
 * backend/services/inspection_vocabulary.py.
 *
 * Exposes category names and canonical terms only (not aliases or regex
 * patterns). Keep in sync when the Python source changes.
 */

export const VocabCategory = {
  PROJECT_IDENTIFIER: "project_identifier",
  INSPECTION_TYPE: "inspection_type",
  INSPECTION_STATUS: "inspection_status",
  LOCATION_TERM: "location_term",
  TRADE_TERM: "trade_term",
  DRAWING_TERM: "drawing_term",
  SHEET_IDENTIFIER: "sheet_identifier",
  DOCUMENT_REFERENCE: "document_reference",
  MARKUP_TERM: "markup_term",
  FIELD_CONDITION_TERM: "field_condition_term",
  INSPECTION_ACTION_TERM: "inspection_action_term",
  CONFIDENCE_LABEL: "confidence_label",
} as const;

export type VocabCategory = (typeof VocabCategory)[keyof typeof VocabCategory];

/** Canonical terms per category (PHRASE categories only; sheet_identifier is pattern-based). */
export const INSPECTION_VOCABULARY: Record<VocabCategory, readonly string[]> = {
  [VocabCategory.PROJECT_IDENTIFIER]: [
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
  [VocabCategory.INSPECTION_TYPE]: [
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
  [VocabCategory.INSPECTION_STATUS]: [
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
  [VocabCategory.LOCATION_TERM]: [
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
  [VocabCategory.TRADE_TERM]: [
    "Fire Protection",
    "Mechanical",
    "Plumbing",
    "Electrical",
    "Structural",
    "Civil",
    "Architectural",
    "Underground Utilities",
  ],
  [VocabCategory.DRAWING_TERM]: [
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
  /** Pattern-matched in Python; no finite canonical term list on the frontend. */
  [VocabCategory.SHEET_IDENTIFIER]: [],
  [VocabCategory.DOCUMENT_REFERENCE]: [
    "Attachment",
    "Linked Drawing",
    "Referenced Drawing",
    "Supporting Document",
    "Inspection Package",
    "Record Drawing",
  ],
  [VocabCategory.MARKUP_TERM]: [
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
  [VocabCategory.FIELD_CONDITION_TERM]: [
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
  [VocabCategory.INSPECTION_ACTION_TERM]: [
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
  [VocabCategory.CONFIDENCE_LABEL]: [
    "High Confidence",
    "Medium Confidence",
    "Low Confidence",
  ],
};

export function allVocabCategories(): VocabCategory[] {
  return Object.values(VocabCategory);
}

export function canonicalTermsForCategory(category: VocabCategory): readonly string[] {
  return INSPECTION_VOCABULARY[category];
}
