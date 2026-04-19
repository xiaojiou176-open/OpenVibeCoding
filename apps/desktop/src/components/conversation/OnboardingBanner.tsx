import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
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
  const isZh = detectPreferredUiLocale() === "zh-CN";
  return (
    <section className="alert-warning onboarding-banner" role="status" aria-live="polite">
      <p><strong>{isZh ? "首次运行 3 步走：" : "First run in 3 steps:"}</strong> {isZh ? <>1. 创建会话 2. 发送请求并回答澄清问题 3. 输入 <code>/run</code> 开始执行。</> : <>1. create a session 2. send your request and answer clarifying questions 3. type <code>/run</code> to start execution.</>}</p>
      <p>{isZh ? "当前阶段：" : "Current stage:"} {phaseText}</p>
      <div className="quick-actions">
        <Button variant="primary" onClick={onNextStep}>{nextStepLabel}</Button>
        <Button variant="secondary" onClick={onDismiss}>{isZh ? "知道了" : "Got it"}</Button>
      </div>
    </section>
  );
}
