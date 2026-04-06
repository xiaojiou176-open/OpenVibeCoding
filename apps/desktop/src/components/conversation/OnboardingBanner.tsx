import { Button } from "../ui/Button";

type OnboardingBannerProps = {
  visible: boolean;
  phaseText: string;
  nextStepLabel: string;
  onNextStep: () => void;
  onDismiss: () => void;
};

export function OnboardingBanner({ visible, phaseText, nextStepLabel, onNextStep, onDismiss }: OnboardingBannerProps) {
  if (!visible) {
    return null;
  }
  return (
    <section className="alert-warning onboarding-banner" role="status" aria-live="polite">
      <p><strong>First run in 3 steps:</strong> 1. create a session 2. send your request and answer clarifying questions 3. type <code>/run</code> to start execution.</p>
      <p>Current stage: {phaseText}</p>
      <div className="quick-actions">
        <Button variant="primary" onClick={onNextStep}>{nextStepLabel}</Button>
        <Button variant="secondary" onClick={onDismiss}>Got it</Button>
      </div>
    </section>
  );
}
