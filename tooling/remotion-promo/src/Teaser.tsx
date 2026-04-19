import React from "react";
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import dashboardHome from "../../../docs/assets/storefront/dashboard-home-live-1440x900.png";
import desktopShell from "../../../docs/assets/storefront/desktop-shell-live-1440x900.png";
import showcaseCard from "../../../docs/assets/storefront/command-tower-showcase-card.svg";
import towerFlow from "../../../docs/assets/storefront/hero-command-tower.svg";

const palette = {
  bg: "#08111d",
  bgElevated: "#111d30",
  surface: "rgba(17, 29, 48, 0.86)",
  ink: "#f4efe7",
  muted: "#c0cfde",
  accent: "#28c28c",
  accentWarm: "#e18a4a",
  line: "rgba(192, 207, 222, 0.22)",
  glow: "rgba(40, 194, 140, 0.18)",
};

const appFont =
  'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
const displayFont =
  'ui-serif, Georgia, Cambria, "Times New Roman", serif';

const words = ["Plan", "Delegate", "Track", "Resume", "Prove"];

const FullscreenCard: React.FC<{
  src: string;
  title: string;
  caption: string;
  badge: string;
  frameStart: number;
}> = ({src, title, caption, badge, frameStart}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({
    frame: frame - frameStart,
    fps,
    config: {
      damping: 16,
      stiffness: 120,
      mass: 0.8,
    },
  });
  const translateY = interpolate(enter, [0, 1], [40, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        gridTemplateColumns: "1.1fr 0.9fr",
        gap: 28,
        padding: "104px 84px 88px",
        transform: `translateY(${translateY}px)`,
        opacity,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 22,
        }}
      >
        <div
          style={{
            width: "fit-content",
            padding: "9px 14px",
            borderRadius: 999,
            border: `1px solid ${palette.line}`,
            background: "rgba(255,255,255,0.04)",
            color: palette.accent,
            fontFamily: appFont,
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {badge}
        </div>
        <div
          style={{
            color: palette.ink,
            fontFamily: displayFont,
            fontSize: 74,
            lineHeight: 1.02,
            fontWeight: 700,
            letterSpacing: "-0.04em",
            maxWidth: 520,
          }}
        >
          {title}
        </div>
        <div
          style={{
            color: palette.muted,
            fontFamily: appFont,
            fontSize: 28,
            lineHeight: 1.5,
            maxWidth: 560,
          }}
        >
          {caption}
        </div>
      </div>
      <div
        style={{
          alignSelf: "center",
          justifySelf: "stretch",
          borderRadius: 28,
          overflow: "hidden",
          border: `1px solid ${palette.line}`,
          boxShadow: "0 36px 80px rgba(0,0,0,0.4)",
          background: palette.bgElevated,
        }}
      >
        <Img
          src={src}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
          }}
        />
      </div>
    </div>
  );
};

export const OpenVibeCodingTeaser: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const introEnter = spring({
    frame,
    fps,
    config: {
      damping: 18,
      stiffness: 110,
    },
  });
  const introOpacity = interpolate(introEnter, [0, 1], [0, 1]);
  const introY = interpolate(introEnter, [0, 1], [36, 0]);
  const outroProgress = spring({
    frame: frame - 420,
    fps,
    config: {
      damping: 15,
      stiffness: 110,
    },
  });
  const backgroundShift = interpolate(frame, [0, durationInFrames], [0, 1]);

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${palette.bg} 0%, #102036 58%, #081520 100%)`,
        color: palette.ink,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(circle at ${18 + backgroundShift * 14}% 16%, ${palette.glow}, transparent 22%),
            radial-gradient(circle at ${86 - backgroundShift * 8}% 18%, rgba(225, 138, 74, 0.14), transparent 18%)`,
        }}
      />

      <Sequence from={0} durationInFrames={120}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            padding: "88px 84px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            opacity: introOpacity,
            transform: `translateY(${introY}px)`,
          }}
        >
          <div style={{display: "flex", flexDirection: "column", gap: 18}}>
            <div
              style={{
                width: "fit-content",
                padding: "8px 14px",
                borderRadius: 999,
                border: `1px solid ${palette.line}`,
                background: "rgba(255,255,255,0.04)",
                color: palette.accent,
                fontFamily: appFont,
                fontSize: 17,
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              OpenVibeCoding / command tower
            </div>
            <div
              style={{
                fontFamily: displayFont,
                fontSize: 92,
                lineHeight: 0.95,
                letterSpacing: "-0.05em",
                maxWidth: 880,
                fontWeight: 700,
              }}
            >
              Stop babysitting AI coding work.
            </div>
            <div
              style={{
                maxWidth: 860,
                color: palette.muted,
                fontFamily: appFont,
                fontSize: 30,
                lineHeight: 1.5,
              }}
            >
              AI coding does not lack models. It lacks a command tower.
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
              gap: 14,
            }}
          >
            {words.map((word, index) => {
              const active = interpolate(frame, [index * 12, index * 12 + 18], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              return (
                <div
                  key={word}
                  style={{
                    padding: "18px 20px",
                    borderRadius: 20,
                    border: `1px solid ${palette.line}`,
                    background: active > 0.92 ? "rgba(40,194,140,0.16)" : "rgba(255,255,255,0.04)",
                    color: palette.ink,
                    fontFamily: appFont,
                    fontSize: 22,
                    fontWeight: 700,
                    textAlign: "center",
                  }}
                >
                  {word}
                </div>
              );
            })}
          </div>
        </div>
      </Sequence>

      <Sequence from={120} durationInFrames={120}>
        <FullscreenCard
          src={dashboardHome}
          title="One operator loop, not five scattered tools."
          caption="OpenVibeCoding turns PM intake, Command Tower, Workflow Cases, and Proof & Replay into one governed operating path."
          badge="Front door"
          frameStart={120}
        />
      </Sequence>

      <Sequence from={240} durationInFrames={90}>
        <FullscreenCard
          src={showcaseCard}
          title="Read the board before you trust the result."
          caption="Track live work, queue posture, blocker risk, and proof readiness before promotion or replay."
          badge="Command tower"
          frameStart={240}
        />
      </Sequence>

      <Sequence from={330} durationInFrames={90}>
        <FullscreenCard
          src={desktopShell}
          title="The same command tower lives on desktop, too."
          caption="The desktop shell keeps the PM loop, hotkeys, drawers, and proof surfaces aligned with the web operator surface."
          badge="Desktop shell"
          frameStart={330}
        />
      </Sequence>

      <Sequence from={420} durationInFrames={120}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            padding: "84px",
            display: "grid",
            gridTemplateColumns: "0.92fr 1.08fr",
            gap: 28,
            opacity: interpolate(outroProgress, [0, 1], [0, 1]),
            transform: `translateY(${interpolate(outroProgress, [0, 1], [30, 0])}px)`,
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              gap: 20,
            }}
          >
            <div
              style={{
                width: "fit-content",
                padding: "8px 14px",
                borderRadius: 999,
                border: `1px solid ${palette.line}`,
                background: "rgba(255,255,255,0.04)",
                color: palette.accentWarm,
                fontFamily: appFont,
                fontSize: 17,
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              Public boundary
            </div>
            <div
              style={{
                fontFamily: displayFont,
                fontSize: 76,
                lineHeight: 1.02,
                letterSpacing: "-0.05em",
                fontWeight: 700,
                maxWidth: 520,
              }}
            >
              Repo-backed. Proof-first. Read-only MCP.
            </div>
            <div
              style={{
                color: palette.muted,
                fontFamily: appFont,
                fontSize: 26,
                lineHeight: 1.5,
                maxWidth: 540,
              }}
            >
              Start with one proven workflow. Then choose the adoption path that
              matches the real job.
            </div>
            <div style={{display: "flex", gap: 12, flexWrap: "wrap"}}>
              {[
                "Command Tower",
                "Workflow Cases",
                "Proof & Replay",
                "Read-only MCP",
              ].map((item) => (
                <div
                  key={item}
                  style={{
                    padding: "11px 14px",
                    borderRadius: 999,
                    border: `1px solid ${palette.line}`,
                    background: "rgba(255,255,255,0.04)",
                    color: palette.ink,
                    fontFamily: appFont,
                    fontSize: 18,
                    fontWeight: 700,
                  }}
                >
                  {item}
                </div>
              ))}
            </div>
            <div
              style={{
                color: palette.ink,
                fontFamily: appFont,
                fontSize: 22,
                fontWeight: 700,
              }}
            >
              xiaojiou176-open.github.io/OpenVibeCoding
            </div>
          </div>

          <div
            style={{
              display: "grid",
              alignItems: "center",
            }}
          >
            <div
              style={{
                borderRadius: 28,
                overflow: "hidden",
                border: `1px solid ${palette.line}`,
                background: palette.bgElevated,
                boxShadow: "0 36px 80px rgba(0,0,0,0.4)",
              }}
            >
              <Img
                src={towerFlow}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  display: "block",
                }}
              />
            </div>
          </div>
        </div>
      </Sequence>
    </AbsoluteFill>
  );
};
