import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

describe("command tower reliability copy", () => {
  it("keeps the degraded live-overview callout wired through shared locale copy", () => {
    const pagePath = path.resolve(process.cwd(), "app/command-tower/page.tsx");
    const source = fs.readFileSync(pagePath, "utf8");

    expect(source).toContain("getUiCopy(locale).dashboard.commandTowerPage");
    expect(source).toContain("commandTowerCopy.unavailableTitle");
    expect(source).toContain("commandTowerCopy.partialTitle");
    expect(source).toContain("commandTowerCopy.unavailableBadge");
    expect(source).toContain("commandTowerCopy.partialBadge");
    expect(source).toContain("commandTowerCopy.actions.viewRuns");
  });

  it("keeps the live-home workspace chain wired through shared locale copy", () => {
    const homePath = path.resolve(process.cwd(), "components/command-tower/CommandTowerHomeLive.tsx");
    const layoutPath = path.resolve(process.cwd(), "components/command-tower/CommandTowerHomeLayout.tsx");
    const drawerPath = path.resolve(process.cwd(), "components/command-tower/CommandTowerHomeDrawer.tsx");
    const viewModelPath = path.resolve(process.cwd(), "components/command-tower/commandTowerHomeViewModel.ts");

    const homeSource = fs.readFileSync(homePath, "utf8");
    const layoutSource = fs.readFileSync(layoutPath, "utf8");
    const drawerSource = fs.readFileSync(drawerPath, "utf8");
    const viewModelSource = fs.readFileSync(viewModelPath, "utf8");

    expect(homeSource).toContain("const commandTowerCopy = uiCopy.desktop.commandTower");
    expect(homeSource).toContain("const liveHomeCopy = uiCopy.dashboard.commandTowerPage.liveHome");
    expect(homeSource).toContain("commandTowerCopy.sectionLabels.overview");
    expect(layoutSource).toContain("props.liveHomeCopy.layout.overviewTitle");
    expect(layoutSource).toContain("props.commandTowerCopy.sessionBoardTitle");
    expect(drawerSource).toContain("commandTowerCopy.drawer.quickActions");
    expect(drawerSource).toContain("liveHomeCopy.drawer.projectKeyPlaceholder");
    expect(viewModelSource).toContain("args.commandTowerCopy.focusLabels.highRisk");
    expect(viewModelSource).toContain("args.liveHomeCopy.viewModel.priorityLanes.liveTitle");
  });
});
