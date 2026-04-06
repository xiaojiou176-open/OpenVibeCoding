"use client";

import { fetchWorkflowCopilotBrief } from "../../lib/api";
import OperatorCopilotPanel from "./OperatorCopilotPanel";

type Props = {
  workflowId: string;
};

const WORKFLOW_QUESTION_SET = [
  "What is the most important workflow case risk right now?",
  "What is the queue and SLA posture for this workflow case?",
  "What is the biggest gap between the latest run and the current workflow state?",
  "What should the operator do first to move this workflow case forward?",
];

export default function WorkflowOperatorCopilotPanel({ workflowId }: Props) {
  return (
    <OperatorCopilotPanel
      title="Workflow Case copilot"
      intro="Generate one bounded workflow brief grounded in workflow status, queue posture, the latest linked run, proof, incident, diff gate, and approval truth."
      buttonLabel="Explain this workflow case"
      questionSet={WORKFLOW_QUESTION_SET}
      takeawaysHeading="Latest run, proof, and missing truth"
      postureHeading="Queue and approval posture"
      onGenerate={() => fetchWorkflowCopilotBrief(workflowId)}
    />
  );
}
