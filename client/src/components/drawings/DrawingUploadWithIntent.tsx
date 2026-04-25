import { useEffect, useId, useState } from "react";
import type { DrawingResponse } from "@shared/schema";
import { AlertTriangle } from "lucide-react";

import DrawingUploadField from "@/components/drawings/DrawingUploadField";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

export type DrawingUploadWithIntentProps = {
  projectId: number;
  /** When false, clears pending/error state on the inner field (e.g. modal closed). */
  isActive: boolean;
  onUploaded: (drawing: DrawingResponse) => void | Promise<void>;
  onUploadingChange?: (uploading: boolean) => void;
  disabled?: boolean;
  fileInputTestId?: string;
  /** Initial and reset value when `projectId` or this prop changes. */
  defaultIntent?: "master" | "sub";
  /** Optional helper under the intent radios. */
  intentHelpText?: string;
  /** Passed to {@link DrawingUploadField} under the file button. */
  description?: string;
};

/**
 * Upload control with master vs sub intent (multipart `upload_intent`).
 * Wraps {@link DrawingUploadField} so intent-specific UX stays out of the generic field.
 */
export default function DrawingUploadWithIntent({
  projectId,
  isActive,
  onUploaded,
  onUploadingChange,
  disabled = false,
  fileInputTestId,
  defaultIntent = "sub",
  intentHelpText,
  description,
}: DrawingUploadWithIntentProps) {
  const baseId = useId();
  const [intent, setIntent] = useState<"master" | "sub">(defaultIntent);

  useEffect(() => {
    setIntent(defaultIntent);
  }, [projectId, defaultIntent]);

  return (
    <div className="space-y-4" data-testid="drawing-upload-with-intent">
      <div className="space-y-2">
        <div className="text-sm font-medium">This file is a</div>
        <RadioGroup
          value={intent}
          onValueChange={(v) => setIntent(v as "master" | "sub")}
          className="gap-3"
          disabled={disabled}
        >
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="sub" id={`${baseId}-intent-sub`} />
            <Label
              htmlFor={`${baseId}-intent-sub`}
              className="font-normal cursor-pointer"
            >
              Sub drawing (compare to the current master)
            </Label>
          </div>
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="master" id={`${baseId}-intent-master`} />
            <Label
              htmlFor={`${baseId}-intent-master`}
              className="font-normal cursor-pointer"
            >
              Master drawing (open as the workspace sheet)
            </Label>
          </div>
        </RadioGroup>
        {intentHelpText ? (
          <p className="text-xs text-muted-foreground">{intentHelpText}</p>
        ) : null}
      </div>

      {intent === "master" ? (
        <Alert className="border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100">
          <AlertTriangle className="h-4 w-4 text-amber-700 dark:text-amber-400" />
          <AlertDescription>
            This upload is tagged as a <strong>master</strong> sheet. After it succeeds, move
            the workspace to this drawing if you want it to be the active master. Previous
            drawings stay in the project.
          </AlertDescription>
        </Alert>
      ) : null}

      <DrawingUploadField
        projectId={projectId}
        isActive={isActive}
        onUploaded={onUploaded}
        onUploadingChange={onUploadingChange}
        disabled={disabled}
        fileInputTestId={fileInputTestId}
        description={description}
        uploadIntent={intent}
      />
    </div>
  );
}
