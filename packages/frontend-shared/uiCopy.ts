export type UiLocale = "en" | "zh-CN";

export const DEFAULT_UI_LOCALE: UiLocale = "en";

type DashboardNavLabels = {
  overview: string;
  pmIntake: string;
  commandTower: string;
  runs: string;
  quickApproval: string;
  search: string;
  agents: string;
  workflowCases: string;
  events: string;
  reviews: string;
  diffGate: string;
  tests: string;
  contracts: string;
  policies: string;
  locks: string;
  worktrees: string;
};

type DesktopLabels = {
  overview: string;
  pmIntake: string;
  commandTower: string;
  runs: string;
  runDetail: string;
  runCompare: string;
  workflowCases: string;
  workflowCaseDetail: string;
  quickApproval: string;
  search: string;
  events: string;
  contracts: string;
  reviews: string;
  tests: string;
  policies: string;
  agents: string;
  locks: string;
  worktrees: string;
  diffGate: string;
  sessionView: string;
};

type HomeCardCopy = {
  badge?: string;
  title: string;
  desc: string;
  href: string;
  prefetch?: boolean;
};

type HomeSpineCardCopy = {
  href: string;
  title: string;
  desc: string;
};

type HomeTemplateCardCopy = {
  href: string;
  badge: string;
  title: string;
  desc: string;
  bestFor: string;
  example: string;
  proof: string;
  fields: string[];
};

type HomeStepCopy = {
  href: string;
  prefetch: boolean;
  step: string;
  title: string;
  desc: string;
};

export type UiCopy = {
  brandTitle: string;
  brandSubtitle: string;
  dashboard: {
    homePhase2: {
      heroTitle: string;
      heroSubtitle: string;
      startFirstTaskLabel: string;
      startNewTaskLabel: string;
      viewLatestRunsLabel: string;
      investigateHighRiskFailuresLabel: string;
      handleLatestFailureLabel: string;
      productSpineTitle: string;
      productSpineDescription: string;
      productSpineCards: HomeSpineCardCopy[];
      publicTemplatesTitle: string;
      publicTemplatesDescription: string;
      publicTemplatesActionLabel: string;
      publicTemplatesActionHref: string;
      publicTemplateCards: HomeTemplateCardCopy[];
      publicAdvantagesTitle: string;
      publicAdvantagesDescription: string;
      publicAdvantageCards: HomeSpineCardCopy[];
      ecosystemTitle: string;
      ecosystemDescription: string;
      ecosystemAction: string;
      ecosystemActionHref: string;
      ecosystemCards: HomeCardCopy[];
      integrationTitle: string;
      integrationDescription: string;
      proofFirstActionLabel: string;
      proofFirstActionHref: string;
      integrationCards: HomeCardCopy[];
      aiSurfacesTitle: string;
      aiSurfacesDescription: string;
      aiSurfacesActionLabel: string;
      aiSurfacesActionHref: string;
      aiSurfaceCards: HomeCardCopy[];
      builderTitle: string;
      builderDescription: string;
      builderQuickstartCtaLabel: string;
      builderQuickstartCtaHref: string;
      builderCards: HomeCardCopy[];
      liveCaseGalleryTitle: string;
      liveCaseGalleryDescription: string;
      liveCaseGalleryActionLabel: string;
      liveCaseGalleryActionHref: string;
      firstTaskGuideTitle: string;
      firstTaskGuideDescription: string;
      firstTaskGuideSummary: string;
      firstTaskGuideSteps: HomeStepCopy[];
      optionalApprovalStep: HomeStepCopy;
    };
    skipToMainContent: string;
    navigationAriaLabel: string;
    topbarTitle: string;
    platformStatusAriaLabel: string;
    lowFrequencyToolsLabel: string;
    localeToggleAriaLabel: string;
    localeToggleButtonLabel: string;
    badges: {
      governanceView: string;
      liveVerificationRequired: string;
      pageLevelStatus: string;
    };
    approval: {
      pageTitle: string;
      pageSubtitle: string;
      panelTitle: string;
      panelIntro: string;
      roleConfigurationAriaLabel: string;
      operatorRoleLabel: string;
      operatorRoleUnconfigured: string;
      refreshPending: string;
      refreshingPending: string;
      lastSuccessfulRefreshPrefix: string;
      actionsDisabledTitle: string;
      queueLoadingBadge: string;
      queueLoadFailedBadge: string;
      queueIdleBadge: string;
      queuePendingBadge: (count: number) => string;
      pendingTruthUnavailable: (error: string) => string;
      recoveryTip: string;
      lastAttemptPrefix: string;
      retryFetch: string;
      retryingFetch: string;
      inspectConnection: string;
      verifyAuthState: string;
      loadingPending: string;
      pendingQueueAriaLabel: string;
      reasonLabel: string;
      requiredActionLabel: string;
      resumeAtLabel: string;
      continueButton: string;
      continuingButton: string;
      manualHint: string;
      runIdLabel: string;
      runIdPlaceholder: string;
      approveButton: string;
      approvingButton: string;
      confirmTitle: string;
      confirmDescription: (runId: string) => string;
      cancel: string;
      confirmApproval: string;
      statusRefreshingQueue: string;
      statusRetryingQueue: string;
      statusQueueRefreshed: (count: number) => string;
      statusRefreshFailed: (message: string, authError: boolean) => string;
      statusRetryFailed: (message: string, authError: boolean) => string;
      statusEnterRunId: string;
      statusSubmittingApproval: string;
      statusApproved: string;
      statusFailed: (message: string) => string;
    };
    commandTowerPage: {
      unavailableTitle: string;
      unavailableNextAction: string;
      unavailableBadge: string;
      partialTitle: string;
      partialNextAction: string;
      partialBadge: string;
      actions: {
        reload: string;
        viewRuns: string;
        startFromPm: string;
        openRuns: string;
        openWorkflowCases: string;
      };
      fallbackLoading: string;
      srTitle: string;
      srSubtitle: string;
      liveHome: {
        loadingContextPanelAriaLabel: string;
        loadingContextPanelTitle: string;
        loadingContextPanelBody: string;
        loadingSessionBoard: string;
        focusModeLabels: {
          all: string;
          highRisk: string;
          blocked: string;
          running: string;
        };
        liveStatus: {
          paused: string;
          backoff: string;
          degraded: string;
          running: string;
        };
        refreshHealth: {
          fullHealthy: string;
          refreshFailed: string;
          partialDegradation: (okCount: number) => string;
        };
        snapshot: {
          refreshFailed: string;
          partialDegradation: string;
          paused: string;
        };
        freshness: {
          noSuccessfulRefresh: string;
          sourceFallback: (source: string) => string;
          lastSuccessfulSeconds: (seconds: number) => string;
          lastSuccessfulMinutes: (minutes: number) => string;
          lastSuccessfulHours: (hours: number) => string;
        };
        actionFeedback: {
          collapsedDrawer: string;
          expandedDrawer: string;
          pinnedDrawer: string;
          unpinnedDrawer: string;
          retryRefreshStart: string;
          retryRefreshPartial: string;
          retryRefreshSuccess: string;
          retryRefreshFailure: string;
          focusSwitchStart: string;
          focusSwitchPartial: string;
          focusSwitchSuccess: (modeLabel: string) => string;
          focusSwitchFailure: string;
          copiedCurrentView: string;
          copyUnavailable: string;
          copyFailedManual: string;
          resumedLiveRefresh: string;
          pausedLiveRefresh: string;
          exportedFailedSessions: string;
          focusedProjectKeyInput: string;
          appliedDraftFilters: (count: number) => string;
          draftFiltersAlreadyMatch: string;
        };
        layout: {
          overviewAriaLabel: string;
          overviewTitle: string;
          overviewDescription: string;
          sloDegraded: string;
          sloWarning: string;
          focusButtonActive: string;
          focusButtonInactive: string;
          focusButtonActiveAriaLabel: string;
          focusButtonInactiveAriaLabel: string;
          focusButtonActiveTitle: string;
          focusButtonInactiveTitle: string;
          focusButtonActiveHint: string;
          primaryActionOpenRisk: string;
          primaryActionGoToPm: string;
          failureEvents: string;
          filterDrawerHint: string;
          degradedRefreshFailed: string;
          degradedPartial: string;
          snapshotTimestampOnly: (label: string) => string;
          degradedActionsAriaLabel: string;
          reviewFailureEvents: string;
          reviewRuns: string;
          reload: string;
          riskSampleSummary: (total: number, failed: number, blocked: number, running: number) => string;
          noLiveData: string;
          dataUnavailable: string;
          dataUnavailableActionsAriaLabel: string;
          sessionBoardAriaLabel: string;
          sessionBoardMeta: (visible: number, total: number) => string;
          cachedSnapshotBadge: string;
          sessionBoardListAriaLabel: string;
          laneQuickActionsAriaLabel: (laneTitle: string) => string;
          liveLaneSwitchToLive: string;
          liveLaneSwitchToPaused: string;
          riskLaneRestoreFullView: string;
          riskLaneSwitchToHighRisk: string;
          actionsLaneOpenFirstRisk: string;
          laneNote: string;
        };
        drawer: {
          projectKeyPlaceholder: string;
          focusViewSwitcherAriaLabel: string;
        };
        viewModel: {
          quickActions: {
            refreshDescription: string;
            liveDescription: string;
            exportDescription: string;
            copyDescription: string;
            focusDescription: string;
            toggleDrawerDescription: string;
            togglePinDescription: string;
            applyDescription: string;
            pauseAction: string;
            resumeAction: string;
            exportAction: string;
            focusAction: string;
            expandAction: string;
            collapseAction: string;
            pinAction: string;
            unpinAction: string;
          };
          contextHealth: {
            liveEngine: string;
            runningValue: (intervalMs: number) => string;
            pausedValue: string;
            sloHealth: string;
            focusHit: string;
            filterState: string;
            filtersApplied: (count: number) => string;
            filtersOff: string;
          };
          drawerPrompts: {
            criticalAlerts: (count: number) => string;
            currentIssue: (label: string) => string;
            unappliedDraftFilters: (count: number) => string;
            riskCounts: (failed: number, blocked: number) => string;
            paused: string;
            stable: string;
          };
          priorityLanes: {
            liveTitle: string;
            liveSummary: (status: string, intervalMs: number) => string;
            riskTitle: string;
            riskSummary: (failed: number, blocked: number, critical: number) => string;
            actionsTitle: string;
            draftFiltersWaiting: (count: number) => string;
            refreshFirst: string;
            primaryActionsReady: string;
            liveBadge: string;
            pausedBadge: string;
            pendingBadge: string;
            convergingBadge: string;
            readyBadge: string;
          };
        };
      };
    };
    runDetailPage: {
      title: string;
      subtitle: string;
      openCompareSurface: string;
      degradedTitle: string;
      degradedNextAction: string;
      degradedBadge: string;
      reloadAction: string;
      backToRunsAction: string;
      compareDecisionTitle: string;
      compareMissing: string;
      compareAligned: string;
      compareNeedsReview: string;
      compareNextStepMissing: string;
      compareNextStepAligned: string;
      compareNextStepNeedsReview: string;
      incidentActionTitle: string;
      incidentMissing: string;
      incidentNextStepFallback: string;
      proofActionTitle: string;
      proofMissing: string;
      proofNextStepFallback: string;
    };
    workflowDetailPage: {
      title: string;
      subtitle: string;
      riskSummaryAriaLabel: string;
      highRiskLabel: string;
      normalRiskLabel: string;
      shareAssetCta: string;
      degradedTitle: string;
      degradedNextAction: string;
      degradedBadge: string;
      degradedIdentityTitle: string;
      degradedRunMappingTitle: string;
      degradedRunMappingEmpty: string;
      degradedRunMappingReadonlyNote: string;
      degradedEventTimelineTitle: string;
      degradedEventTimelineReadonlyNote: string;
      retryLoadAction: string;
      backToWorkflowListAction: string;
      governanceEntryDisabled: string;
      summaryStatus: string;
      summaryRunMappings: string;
      summaryEvents: string;
      summaryRunMappingsHint: string;
      summaryEventsHint: string;
      queuePostureNote: string;
      caseFieldLabels: {
        workflowId: string;
        name: string;
        updatedAt: string;
        namespace: string;
        taskQueue: string;
        owner: string;
        project: string;
        verdict: string;
        runs: string;
      };
    };
    workflowListPage: {
      title: string;
      subtitle: string;
      summaryAriaLabel: string;
      countsBadge: (workflowCount: number, queueCount: number) => string;
      metricLabels: {
        workflowCases: string;
        queueSla: string;
        nextRecommendedAction: string;
      };
      casesWithQueuedWork: (count: number) => string;
      eligibleNow: (eligibleCount: number, atRiskCount: number) => string;
      recommendedActions: {
        runNext: string;
        reviewTiming: string;
        openWorkflow: string;
        createFirstWorkflow: string;
      };
      emptyTitle: string;
      emptyHint: string;
      tableCaption: string;
      tableHeaders: {
        workflowId: string;
        status: string;
        namespace: string;
        taskQueue: string;
        runs: string;
      };
      verdictPrefix: string;
      queueSummary: (count: number, slaState: string) => string;
    };
    runsPage: {
      title: string;
      subtitle: string;
      countsBadge: (runCount: number) => string;
      warningTitle: string;
      warningNextStep: string;
      metricLabels: {
        runInventory: string;
        replayPosture: string;
        operatorPriority: string;
      };
      inventorySubline: string;
      failureHeadline: (failed: number) => string;
      successHeadline: (success: number) => string;
      failureSubline: (success: number, running: number) => string;
      successSubline: (running: number, failed: number) => string;
      operatorPriorityHeadline: (failed: number) => string;
      operatorPriorityClearHeadline: string;
      operatorPrioritySubline: string;
      operatorPriorityClearSubline: string;
      operatorPrimaryActionFailed: string;
      operatorPrimaryActionClear: string;
      operatorSecondaryAction: string;
      filterAriaLabel: string;
      filters: {
        all: string;
        failed: string;
        running: string;
        success: string;
      };
      firstScreenLimit: (visibleCount: number) => string;
    };
    contractsPage: {
      title: string;
      subtitle: string;
      countsBadge: (contractCount: number) => string;
      searchLabel: string;
      searchPlaceholder: string;
      applyFilter: string;
      filterSummary: (visible: number, total: number, defaultLimit: number) => string;
      warningTitle: string;
      warningNextStep: string;
      emptyTitle: string;
      emptyHint: string;
      fieldLabels: {
        taskId: string;
        runId: string;
        assignedRole: string;
        executionAuthority: string;
        skillsBundle: string;
        mcpBundle: string;
        runtimeBinding: string;
        runtimeCapability: string;
        toolExecution: string;
        allowedPaths: string;
        acceptanceTests: string;
        toolPermissions: string;
      };
      fallbackValues: {
        unknownSource: string;
        unknownContract: string;
        notAssigned: string;
        notPublished: string;
        notDerived: string;
        unrestricted: string;
        noAcceptanceTests: string;
        defaultPermissions: string;
      };
      fullJsonSummary: string;
      moreHidden: (count: number) => string;
      showAll: string;
    };
    agentsPage: {
      title: string;
      subtitle: string;
      openCommandTower: string;
      warningTitle: string;
      warningNextStep: string;
      summaryAriaLabel: string;
      metricLabels: {
        riskDesk: string;
        executionSeats: string;
        schedulerPosture: string;
      };
      metricBadges: {
        riskActive: string;
        riskClear: string;
        schedulerNeedsAction: string;
        schedulerStable: string;
      };
      metricSublines: {
        risk: (statuses: number, healthy: number) => string;
        riskHint: string;
        execution: (activeAgents: number, capacityRatio: number) => string;
        executionHint: string;
        scheduler: (unassignedStatuses: number, unassignedFailedStatuses: number) => string;
        schedulerHint: (lockedAgentCount: number) => string;
      };
      actions: {
        inspectRiskDesk: string;
        inspectRoleDesk: string;
        openFailedEvents: string;
      };
      roleCatalog: {
        title: string;
        subtitle: string;
        fullList: string;
        registryUnavailable: string;
        noMatches: string;
        headers: {
          role: string;
          skillsBundle: string;
          mcpBundle: string;
          runtimeBinding: string;
          executionAuthority: string;
          registeredSeats: string;
        };
        noRolePurpose: string;
        readOnlyMirror: string;
        lockedSuffix: string;
      };
      filters: {
        title: string;
        subtitle: string;
        searchPlaceholder: string;
        allRoles: string;
        applyFilter: string;
        hint: string;
        clearFilter: string;
      };
      stateMachine: {
        title: string;
        subtitle: string;
        summaryBadge: (statuses: number, sample: number) => string;
        failedBadge: (failed: number, currentPageFailed: number) => string;
        unassignedFailuresBadge: (count: number) => string;
        viewFailedRuns: string;
        emptyTitle: string;
        sampleHint: (visible: number) => string;
        headers: {
          runId: string;
          taskId: string;
          role: string;
          agentId: string;
          flowStage: string;
          executionContext: string;
          governanceAction: string;
        };
        pendingScheduling: string;
        pendingSchedulingHint: string;
        schedulingFailed: string;
        executionContextAriaLabel: string;
        governanceActionsAriaLabel: string;
        detail: string;
        detailFailedTitle: string;
        detailDefaultTitle: string;
        missingRunId: string;
      };
      registeredInventory: {
        title: (count: number) => string;
        registryUnavailable: string;
        emptyTitle: string;
        tableAriaLabel: string;
        headers: {
          agentId: string;
          role: string;
          lockCount: string;
          lockedPaths: string;
        };
      };
      locks: {
        title: (total: number, pageCount: number) => string;
        emptyTitle: string;
        tableAriaLabel: string;
        headers: {
          lockId: string;
          runId: string;
          agentId: string;
          role: string;
          path: string;
          timestamp: string;
        };
      };
      pagination: {
        status: (page: number, totalPages: number, pageSize: number) => string;
        previous: string;
        next: string;
      };
    };
    sectionPrimary: string;
    sectionAdvanced: string;
    labels: DashboardNavLabels;
  };
  desktop: {
    sectionPrimary: string;
    sectionAdvanced: string;
    sectionGovernance: string;
    shellAriaLabel: string;
    skipToMainContent: string;
    workspacePickerLabel: string;
    selectWorkspace: string;
    loadingPageStyles: string;
    loadingPage: string;
    localeToggleAriaLabel: string;
    localeToggleButtonLabel: string;
    commandTower: {
      title: string;
      subtitle: string;
      currentModePrefix: string;
      badges: {
        liveRefresh: string;
        paused: string;
        backoff: string;
        sloPrefix: string;
      };
      actions: {
        refreshProgress: string;
        refreshing: string;
        pauseAutoRefresh: string;
        resumeAutoRefresh: string;
        resumeWork: string;
        openWebDeepAnalysis: string;
        showAdvancedDetail: string;
        hideAdvancedDetail: string;
      };
      collapsedHint: string;
      webHandoffIntro: string;
      webAnalysisView: string;
      metrics: {
        totalSessions: string;
        active: string;
        failed: string;
        blocked: string;
      };
      filterTitle: string;
      filterHint: string;
      statusLegend: string;
      projectKey: string;
      sort: string;
      apply: string;
      reset: string;
      draftNotApplied: string;
      focusLabels: {
        all: string;
        highRisk: string;
        blocked: string;
        running: string;
      };
      refreshHealth: {
        fullSuccess: string;
        fullFailure: string;
        partialSuccess: (okCount: number) => string;
      };
      sectionLabels: {
        overview: string;
        sessions: string;
        alerts: string;
        healthy: string;
        issue: string;
      };
      errorIssueBadge: string;
      errorRecommendedAction: string;
      retryRefresh: string;
      retrying: string;
      pauseLiveTriage: string;
      noSessionsForFilters: string;
      noSessionsForFocus: string;
      viewAll: string;
      sessionBoardTitle: string;
      sessionBoardCount: (visible: number, total: number) => string;
      noSessionsYet: string;
      refreshNow: string;
      viewAllSessions: string;
      blockingHotspots: string;
      drawer: {
        ariaLabel: string;
        title: string;
        close: string;
        quickActions: string;
        health: string;
        inspectionPrompts: string;
        alerts: string;
        export: string;
        copy: string;
        running: string;
        paused: string;
        focusHits: string;
        filterState: string;
        allFilters: string;
        noAlerts: string;
        reviewAlertState: string;
        records: (count: number) => string;
        criticalCount: (count: number) => string;
      };
    };
    runDetail: {
      backToList: string;
      taskLabelPrefix: string;
      liveModeActive: string;
      liveModePaused: string;
      liveTogglePauseTitle: string;
      liveToggleResumeTitle: string;
      loadErrorPrefix: string;
      loadErrorNextStep: string;
      retryLoad: string;
      noDetailPayload: string;
      noDetailNextStep: string;
      pendingApprovalWithCount: (count: number) => string;
      pendingApprovalWithoutCount: string;
      operatorCopilotTitle: string;
      operatorCopilotIntro: string;
      operatorCopilotButton: string;
      tabs: {
        events: (count: number) => string;
        diff: string;
        reports: (count: number) => string;
        tools: (count: number) => string;
        chain: string;
        contract: string;
        replay: string;
      };
      summaryCards: {
        overviewTitle: string;
        executionRolesTitle: string;
        evidenceTitle: string;
      };
      bindingReadModel: {
        title: string;
        authority: string;
        source: string;
        executionAuthority: string;
        skillsBundle: string;
        mcpBundle: string;
        runtimeBinding: string;
        runtimeCapability: string;
        toolExecution: string;
        readOnlyNote: string;
      };
      completionGovernance: {
        title: string;
        workerPromptContracts: string;
        unblockTasks: string;
        onIncomplete: string;
        onBlocked: string;
        doneChecks: string;
        unblockOwner: string;
        unblockMode: string;
        unblockTrigger: string;
        advisoryNote: string;
      };
      fieldLabels: {
        runId: string;
        taskId: string;
        status: string;
        executionSemantic: string;
        failureCode: string;
        failureSummary: string;
        nextAction: string;
        currentOwner: string;
        assignedExecution: string;
        createdAt: string;
        traceId: string;
        workflow: string;
        failureReason: string;
        allowedPaths: string;
      };
      tableHeaders: {
        time: string;
        event: string;
        level: string;
        taskId: string;
        tool: string;
        status: string;
        duration: string;
        error: string;
      };
      actionBar: {
        promoteEvidence: string;
        rollback: string;
        reject: string;
        refresh: string;
      };
      emptyStates: {
        noExecutionRoleStatus: string;
        executionRolesNextStep: string;
        retryFetch: string;
        noEvidenceSummary: string;
        evidenceNextStep: string;
        refreshData: string;
        noEvents: string;
        eventsNextStep: string;
        refreshEvents: string;
        noDiff: string;
        diffNextStep: string;
        backToEventTimeline: string;
        noReports: string;
        reportsNextStep: string;
        refreshReports: string;
        noToolCalls: string;
        toolCallsNextStep: string;
        refreshToolCalls: string;
        noChainFlow: string;
        chainNextStep: string;
        refreshChain: string;
        chainSpecTitle: string;
        chainReportTitle: string;
        noContractSnapshot: string;
        contractNextStep: string;
        refreshContract: string;
        replayTitle: string;
        replayDescription: string;
        selectBaselineRun: string;
        runReplay: string;
        replayResult: string;
        compareDecisionTitle: string;
        compareAligned: string;
        compareNeedsReview: string;
        compareNextStep: string;
        actionContextTitle: string;
        proofPrefix: string;
        incidentPrefix: string;
        noProofIncident: string;
        compareSummaryTitle: string;
        openCompareSurface: string;
        proofPackTitle: string;
        relatedReportsTitle: string;
        testReportTitle: string;
        reviewReportTitle: string;
        evidenceReportTitle: string;
      };
    };
    workflowDetail: {
      backToList: string;
      queuePriority: string;
      queueScheduledAt: string;
      queueDeadlineAt: string;
      operatorRoleLabel: string;
      roleGateReason: string;
      queueSummary: (queueCount: number, eligibleCount: number) => string;
      queueLatestRun: string;
      runNextQueuedTask: string;
      queueingTask: string;
      runningTask: string;
      noRunAvailable: string;
      queuedNotice: (taskId: string) => string;
      startedNotice: (runId: string) => string;
      invalidScheduledAt: string;
      invalidDeadlineAt: string;
      queueEmptyReason: string;
      workflowCopilotTitle: string;
      workflowCopilotIntro: string;
      workflowCopilotButton: string;
      workflowCopilotTakeaways: string;
      workflowCopilotPosture: string;
      workflowCopilotQuestions: string[];
      nextOperatorActionTitle: string;
      nextOperatorActionHint: string;
      recommendedActionQueued: string;
      recommendedActionNoQueue: string;
      recommendedActionNoRun: string;
      summaryTitle: string;
      readModelTitle: string;
      noReadModel: string;
      relatedRunsTitle: (count: number) => string;
      noRelatedRuns: string;
      eventsTitle: (count: number) => string;
      noEvents: string;
      queueSlaTitle: (count: number) => string;
      noQueuedWork: string;
      queueMeta: (priority: string, sla: string) => string;
      summaryLabels: {
        status: string;
        objective: string;
        owner: string;
        project: string;
        verdict: string;
        pmSessions: string;
        summary: string;
      };
      readModelLabels: {
        authority: string;
        executionAuthority: string;
        source: string;
        sourceRunId: string;
        skillsBundle: string;
        mcpBundle: string;
        runtimeBinding: string;
        readOnlyNote: string;
      };
    };
    overview: {
      title: string;
      subtitle: string;
      refreshData: string;
      metricsAriaLabel: string;
      metricLabels: {
        totalSessions: string;
        activeNow: string;
        failureRatio: string;
        blockedQueue: string;
      };
      primaryActionsTitle: string;
      optionalStepLabel: string;
      approvalCheckpoint: string;
      approvalCheckpointDesc: string;
      currentProgressTitle: string;
      progressCards: {
        runningNow: string;
        runningNowHint: string;
        runningNowEmpty: string;
        needsAttention: string;
        needsAttentionHint: string;
        needsAttentionEmpty: string;
        riskEvents: string;
        riskEventsHint: string;
        riskEventsEmpty: string;
      };
      recentRunsTitle: string;
      recentRunsHint: string;
      noRunsYet: string;
      viewAllRuns: string;
      recentEventsTitle: string;
      viewAllExceptions: string;
      noExceptionsYet: string;
      openEventStream: string;
      viewRun: string;
      runningNowTitle: string;
      recentExceptionTaskRequiresAttention: (taskId: string) => string;
      recentExceptionOperatorEventFallback: string;
      recentExceptionLevelPrefix: string;
      recentExceptionRunPrefix: string;
      tableHeaders: {
        runId: string;
        taskId: string;
        status: string;
        createdAt: string;
        time: string;
        exception: string;
        details: string;
        action: string;
      };
      quickActions: {
        step1Label: string;
        step1Desc: string;
        step2Label: string;
        step2Desc: string;
        step3Label: string;
        step3Desc: string;
        step4Label: string;
        step4Desc: string;
      };
    };
    approval: {
      pageTitle: string;
      pageSubtitle: string;
      refresh: string;
      warningBanner: string;
      queueTitle: string;
      pendingBadge: (count: number) => string;
      criticalBadge: string;
      noPendingText: string;
      summaryLabel: string;
      taskIdLabel: string;
      failureReasonLabel: string;
      approveExecution: string;
      manualInputTitle: string;
      manualInputHint: string;
      runIdLabel: string;
      runIdPlaceholder: string;
      approve: string;
      confirmDialogAriaLabel: string;
      closeConfirmDialogAriaLabel: string;
      confirmTitle: string;
      confirmDescription: (runId: string) => string;
      cancel: string;
      confirmApproval: string;
      approvedToast: (runId: string) => string;
    };
    labels: DesktopLabels;
  };
};

const UI_COPY: Record<UiLocale, UiCopy> = {
  en: {
    brandTitle: "CortexPilot",
    brandSubtitle: "Plan · Delegate · Track · Resume · Prove",
    dashboard: {
      homePhase2: {
        heroTitle: "The command tower for AI engineering",
        heroSubtitle:
          "Stop babysitting AI coding work. CortexPilot plans, delegates, tracks, resumes, and proves long-running engineering work across Codex and Claude Code while keeping one governed operator path, one case record, and one proof trail.",
        startFirstTaskLabel: "Start first task",
        startNewTaskLabel: "Start new task",
        viewLatestRunsLabel: "View latest runs",
        investigateHighRiskFailuresLabel: "Investigate high-risk failures",
        handleLatestFailureLabel: "Handle latest failure",
        productSpineTitle: "Plan, delegate, track, resume, and prove",
        productSpineDescription:
          "The first screen should explain the operator loop, then anchor it on the three truth surfaces that keep the loop honest: Command Tower, Workflow Cases, and Proof & Replay.",
        productSpineCards: [
          {
            href: "/command-tower",
            title: "Command Tower",
            desc: "Track live work, queue posture, and high-risk drift from one command tower instead of babysitting scattered sessions.",
          },
          {
            href: "/workflows",
            title: "Workflow Cases",
            desc: "Delegate and resume through one durable case record that ties request, queue, verdict, proof, and linked runs together.",
          },
          {
            href: "/runs",
            title: "Proof & Replay",
            desc: "Prove what happened with evidence bundles, rerun comparison, and replay before you trust the result.",
          },
        ],
        publicTemplatesTitle: "One proven workflow, two showcase expansions",
        publicTemplatesDescription:
          "Start with `news_digest` first. It is the official public baseline. `topic_brief` and `page_brief` stay useful, but they are still showcase paths until they earn their own healthy proof bundles.",
        publicTemplatesActionLabel: "Open proof pack",
        publicTemplatesActionHref: "/use-cases/",
        publicTemplateCards: [
          {
            href: "/pm?template=news_digest",
            badge: "Release-proven first run",
            title: "news_digest",
            desc: "Generate a news summary around one topic from public sources while keeping the evidence auditable.",
            bestFor: "Use when you want the fastest proof-oriented public path.",
            example: "Seattle tech and AI + 3 source domains + 24h",
            proof: "Proof state: official public baseline",
            fields: ["topic", "sources[]", "time_range", "max_results"],
          },
          {
            href: "/pm?template=topic_brief",
            badge: "Public showcase",
            title: "topic_brief",
            desc: "Open a bounded topic brief as a read-only workflow case with search-backed proof.",
            bestFor: "Use when you want a narrow brief around one topic and a recent time window.",
            example: "Seattle tech and AI + 7d + 5 results",
            proof: "Proof state: public, but not yet release-proven",
            fields: ["topic", "time_range", "max_results"],
          },
          {
            href: "/pm?template=page_brief",
            badge: "Public showcase",
            title: "page_brief",
            desc: "Capture one URL as a read-only workflow case with browser-backed evidence.",
            bestFor: "Use when one page matters more than a whole search topic.",
            example: "https://example.com + focused summary request",
            proof: "Proof state: browser-backed showcase path",
            fields: ["url", "focus"],
          },
        ],
        publicAdvantagesTitle: "Three engineering layers behind the command tower",
        publicAdvantagesDescription:
          "CortexPilot is not just one more prompt wrapper. It turns prompt, context, and harness decisions into explicit product surfaces so long-running work keeps moving when humans step away.",
        publicAdvantageCards: [
          {
            href: "/pm",
            title: "Prompt Engineering",
            desc: "Write the right worker brief, scope, guardrails, and deliverables instead of throwing one more giant prompt at a model.",
          },
          {
            href: "/workflows",
            title: "Context Engineering",
            desc: "Keep the right material in the right head: case truth, role bindings, queue posture, and handoff context stay structured instead of rotting inside one window.",
          },
          {
            href: "/contracts",
            title: "Harness Engineering",
            desc: "Move work through contracts, approvals, runtime bindings, and proof surfaces so the system can continue safely instead of hoping the model behaves.",
          },
        ],
        ecosystemTitle: "Works with today's coding-agent ecosystem",
        ecosystemDescription:
          "Keep the front door anchored on Codex, Claude Code, and read-only MCP. Mention OpenHands and comparison-only tools in the ecosystem layer, not in the hero.",
        ecosystemAction: "Open ecosystem map",
        ecosystemActionHref: "/ecosystem/",
        ecosystemCards: [
          {
            badge: "Primary workflow binding",
            title: "Codex workflows",
            desc: "Use CortexPilot when Codex-driven work needs one command tower, one case record, and one replayable proof path.",
            href: "/command-tower",
            prefetch: true,
          },
          {
            badge: "Primary workflow binding",
            title: "Claude Code workflows",
            desc: "The same operator surface works for Claude Code-style coding loops that need governed visibility, approvals, and evidence before promotion.",
            href: "/command-tower",
            prefetch: true,
          },
          {
            badge: "Protocol surface",
            title: "Read-only MCP",
            desc: "MCP is a real protocol surface here, but the current boundary is read-only. External tools can inspect truth without mutating it.",
            href: "/runs",
            prefetch: true,
          },
          {
            badge: "Adjacent ecosystem",
            title: "OpenHands and comparison layer",
            desc: "OpenHands belongs in the broader ecosystem layer, while OpenCode stays comparison-only and OpenClaw stays out of the main front door.",
            href: "/ecosystem/",
          },
        ],
        integrationTitle: "Choose the right adoption path",
        integrationDescription:
          "Use the compatibility matrix as the main router, keep the proof-first guide as the fastest way to believe the product story, then open protocol, playbooks, packages, or AI surfaces only after the real job is clear.",
        proofFirstActionLabel: "See first proven workflow",
        proofFirstActionHref: "/use-cases/",
        integrationCards: [
          {
            badge: "Decision layer",
            title: "Compatibility matrix",
            desc: "Use one routing page to compare Codex, Claude Code, OpenClaw, read-only MCP, skills, and builder entrypoints before you choose a deeper path.",
            href: "/compatibility/",
          },
          {
            badge: "Truthful adoption map",
            title: "Integration guide",
            desc: "Use the integration guide when you need the deeper truthful answer for Codex, Claude Code, and OpenClaw positioning.",
            href: "/integrations/",
          },
          {
            badge: "Repo-owned playbooks",
            title: "Skills quickstart",
            desc: "Use the skills guide when your team needs repeatable playbooks instead of guessing from the `.agents/skills/` tree.",
            href: "/skills/",
          },
        ],
        aiSurfacesTitle: "AI surfaces in the real workflow",
        aiSurfacesDescription:
          "AI in CortexPilot is not a floating chat box. It already shows up as a pre-run advisor, a workflow-level explainer, and a run/compare operator brief.",
        aiSurfacesActionLabel: "Open AI + MCP + API surfaces",
        aiSurfacesActionHref: "/ai-surfaces/",
        aiSurfaceCards: [
          {
            badge: "Pre-run advisory",
            title: "Flight Plan copilot",
            desc: "PM intake can preview one bounded pre-run brief before execution starts, so approval and evidence expectations are visible early.",
            href: "/pm",
            prefetch: true,
          },
          {
            badge: "Workflow-level AI",
            title: "Workflow copilot",
            desc: "Workflow Cases already expose a workflow-scoped brief that explains queue posture, latest run context, and next operator action.",
            href: "/workflows",
            prefetch: true,
          },
          {
            badge: "Run-time AI",
            title: "Run and compare operator brief",
            desc: "Run Detail and compare surfaces can already explain deltas, proof, incident context, and the next action without pretending to execute recovery.",
            href: "/runs",
            prefetch: true,
          },
        ],
        builderTitle: "Builder entrypoints",
        builderDescription:
          "This is not a full SDK platform, but the builder entrypoints now include the read-only MCP quickstart, the API and contract quickstart, and the package-level client/shared surfaces.",
        builderQuickstartCtaLabel: "Open builder quickstart",
        builderQuickstartCtaHref: "/builders/",
        builderCards: [
          {
            badge: "Protocol quickstart",
            title: "Read-only MCP quickstart",
            desc: "Start here when you want the smallest truthful map for Codex and Claude Code workflow inspection before you read package internals.",
            href: "/mcp/",
          },
          {
            badge: "API quickstart",
            title: "API and contract quickstart",
            desc: "Start here when you want OpenAPI, contract-facing types, and the thin client entrypoint before you pick a package surface.",
            href: "/api/",
          },
          {
            badge: "Thin client surface",
            title: "@cortexpilot/frontend-api-client",
            desc: "Use the dashboard, desktop, and web client entry points when you want runs, Workflow Cases, approvals, and Command Tower reads from one import boundary.",
            href: "https://github.com/xiaojiou176-open/CortexPilot-public/blob/main/packages/frontend-api-client/README.md",
          },
          {
            badge: "Contract-facing",
            title: "@cortexpilot/frontend-api-contract",
            desc: "Use the contract package README first when you want the human guide to the generated API boundary before opening raw type files.",
            href: "https://github.com/xiaojiou176-open/CortexPilot-public/blob/main/packages/frontend-api-contract/docs/README.md",
          },
          {
            badge: "Presentation substrate",
            title: "@cortexpilot/frontend-shared",
            desc: "Use the shared brand copy, locale helpers, status presentation, and frontend-only types instead of rebuilding those surfaces per app.",
            href: "https://github.com/xiaojiou176-open/CortexPilot-public/blob/main/packages/frontend-shared/README.md",
          },
        ],
        liveCaseGalleryTitle: "Live Workflow Case gallery",
        liveCaseGalleryDescription:
          "Use real Workflow Cases as lightweight showcase assets. This baseline links to live case detail and share-ready recap instead of inventing demo-only gallery data.",
        liveCaseGalleryActionLabel: "Open Workflow Cases",
        liveCaseGalleryActionHref: "/workflows",
        firstTaskGuideTitle: "First-task guide (expandable)",
        firstTaskGuideDescription:
          "Start with the request, watch Command Tower, confirm the Workflow Case, then inspect Proof & Replay. It stays collapsed by default to keep the first screen quiet.",
        firstTaskGuideSummary: "Show the four-step first-task flow",
        firstTaskGuideSteps: [
          {
            href: "/pm",
            prefetch: true,
            step: "Step 1",
            title: "Describe the request (goal + acceptance)",
            desc: "State the goal and acceptance target in one sentence, then let the system open the session.",
          },
          {
            href: "/command-tower",
            prefetch: false,
            step: "Step 2",
            title: "Watch live progress (confirm it is moving)",
            desc: "Open Command Tower and confirm the run is advancing instead of getting stuck.",
          },
          {
            href: "/workflows",
            prefetch: true,
            step: "Step 3",
            title: "Confirm the Workflow Case",
            desc: "Open Workflow Cases to confirm the durable case record, queue posture, and linked runs.",
          },
          {
            href: "/runs",
            prefetch: true,
            step: "Step 4",
            title: "Inspect Proof & Replay",
            desc: "Open the run ledger to inspect status, evidence, compare state, and replay state.",
          },
        ],
        optionalApprovalStep: {
          href: "/god-mode",
          prefetch: true,
          step: "Optional",
          title: "Approval checkpoint (only when review is required)",
          desc: "Use Quick approval to confirm the blocked step and complete the final release.",
        },
      },
      skipToMainContent: "Skip to dashboard content",
      navigationAriaLabel: "Dashboard navigation",
      topbarTitle: "AI engineering command tower",
      platformStatusAriaLabel: "Platform status overview",
      lowFrequencyToolsLabel: "Low-frequency tools",
      localeToggleAriaLabel: "Switch to Chinese",
      localeToggleButtonLabel: "中文",
      badges: {
        governanceView: "Governance view",
        liveVerificationRequired: "Live verification required",
        pageLevelStatus: "Page-level status",
      },
      approval: {
        pageTitle: "Manual approvals",
        pageSubtitle: "Review every HUMAN_APPROVAL_REQUIRED item in one place before resuming execution.",
        panelTitle: "God Mode",
        panelIntro:
          "God Mode separates pending approvals, read-only role gaps, and queue load failures. A quiet queue is not proof that approvals are globally unnecessary.",
        roleConfigurationAriaLabel: "Approval role configuration",
        operatorRoleLabel: "Operator role",
        operatorRoleUnconfigured: "Not configured",
        refreshPending: "Refresh pending approvals",
        refreshingPending: "Refreshing...",
        lastSuccessfulRefreshPrefix: "Last successful refresh:",
        actionsDisabledTitle: "Approval actions are read-only right now.",
        queueLoadingBadge: "Refreshing",
        queueLoadFailedBadge: "Load failed",
        queueIdleBadge: "No pending items",
        queuePendingBadge: (count: number) => `${count} pending approvals`,
        pendingTruthUnavailable: (error: string) => `Pending approval truth is unavailable: ${error}`,
        recoveryTip: "Recovery tip: confirm the login state and approval role before retrying.",
        lastAttemptPrefix: "Last attempt:",
        retryFetch: "Retry fetch",
        retryingFetch: "Retrying...",
        inspectConnection: "Open PM session to inspect connection",
        verifyAuthState: "Open Command Tower to verify auth state",
        loadingPending: "Loading pending approvals...",
        pendingQueueAriaLabel: "Pending approvals queue",
        reasonLabel: "Reason",
        requiredActionLabel: "Required action",
        resumeAtLabel: "Resume at",
        continueButton: "I am done, continue",
        continuingButton: "Approving...",
        manualHint:
          "When the event stream shows HUMAN_APPROVAL_REQUIRED, paste the run_id and approve it. The action will be written to the event log.",
        runIdLabel: "Run ID",
        runIdPlaceholder: "Paste run_id...",
        approveButton: "Approve",
        approvingButton: "Approving...",
        confirmTitle: "Confirm approval",
        confirmDescription: (runId: string) =>
          `Approve ${runId} to continue execution? This action writes to the event log and cannot be undone.`,
        cancel: "Cancel",
        confirmApproval: "Confirm approval",
        statusRefreshingQueue: "Refreshing pending approvals queue...",
        statusRetryingQueue: "Retrying pending approvals queue...",
        statusQueueRefreshed: (count: number) => `Pending approvals queue refreshed. ${count} item(s).`,
        statusRefreshFailed: (message: string, authError: boolean) =>
          authError
            ? `Pending approvals queue refresh failed: ${message}. Confirm permissions or sign in again before retrying.`
            : "Pending approvals queue refresh failed. Resolve the error and retry.",
        statusRetryFailed: (message: string, authError: boolean) =>
          authError
            ? `Retry failed: ${message}. Confirm permissions or sign in again before retrying.`
            : `Retry failed: ${message}.`,
        statusEnterRunId: "Enter run_id before approving.",
        statusSubmittingApproval: "Submitting approval...",
        statusApproved: "Approved.",
        statusFailed: (message: string) => `Failed: ${message}`,
      },
      commandTowerPage: {
        unavailableTitle: "Command Tower live overview is unavailable",
        unavailableNextAction:
          "Reload first. If live data is still missing, inspect runs for the latest verified state or start from PM to rebuild the active path.",
        unavailableBadge: "Live data missing",
        partialTitle: "Command Tower is running with partial truth",
        partialNextAction:
          "Use the visible overview as a partial snapshot only. Confirm runs or Workflow Cases directly before taking approval, rollback, or release decisions.",
        partialBadge: "Partial context",
        actions: {
          reload: "Reload Command Tower",
          viewRuns: "View runs",
          startFromPm: "Start from PM",
          openRuns: "Open runs",
          openWorkflowCases: "Open Workflow Cases",
        },
        fallbackLoading: "Loading Command Tower live overview...",
        srTitle: "Command Tower",
        srSubtitle: "Review risk and blockers first, then move into session handling.",
        liveHome: {
          loadingContextPanelAriaLabel: "Command Tower context panel",
          loadingContextPanelTitle: "Context",
          loadingContextPanelBody: "Loading the context panel...",
          loadingSessionBoard: "Loading the session board...",
          focusModeLabels: {
            all: "all",
            highRisk: "high risk",
            blocked: "blocked",
            running: "running",
          },
          liveStatus: {
            paused: "Live refresh paused",
            backoff: "Live refresh is backing off and retrying",
            degraded: "Live refresh is running with partial degradation",
            running: "Live refresh is running",
          },
          refreshHealth: {
            fullHealthy: "Full refresh healthy",
            refreshFailed: "Refresh failed",
            partialDegradation: (okCount: number) => `Partial degradation (${okCount}/3)`,
          },
          snapshot: {
            refreshFailed: "Cached snapshot (refresh failed, auto updates paused)",
            partialDegradation: "Cached snapshot (partial degradation, live updates may lag)",
            paused: "Cached snapshot (live refresh paused)",
          },
          freshness: {
            noSuccessfulRefresh: "No successful refresh yet",
            sourceFallback: (source: string) => `Last refresh source: ${source}`,
            lastSuccessfulSeconds: (seconds: number) => `Last successful refresh ${seconds}s ago`,
            lastSuccessfulMinutes: (minutes: number) => `Last successful refresh ${minutes}m ago`,
            lastSuccessfulHours: (hours: number) => `Last successful refresh ${hours}h ago`,
          },
          actionFeedback: {
            collapsedDrawer: "Collapsed the right context drawer",
            expandedDrawer: "Expanded the right context drawer",
            pinnedDrawer: "Pinned the right drawer",
            unpinnedDrawer: "Unpinned the right drawer",
            retryRefreshStart: "Retrying live refresh...",
            retryRefreshPartial: "Retry completed, but some data is still degraded",
            retryRefreshSuccess: "Retry succeeded and the live overview is updated",
            retryRefreshFailure: "Retry failed. Review failure events.",
            focusSwitchStart: "Refreshing the focus view...",
            focusSwitchPartial: "Focus view switched, but some data is degraded",
            focusSwitchSuccess: (modeLabel: string) => `Switched focus view to ${modeLabel}`,
            focusSwitchFailure: "Failed to switch the focus view. Review failure events.",
            copiedCurrentView: "Copied the current view link",
            copyUnavailable: "This environment cannot copy the current view link",
            copyFailedManual: "Copy failed. Copy the address bar link manually.",
            resumedLiveRefresh: "Resumed live refresh",
            pausedLiveRefresh: "Paused live refresh",
            exportedFailedSessions: "Exported failed sessions",
            focusedProjectKeyInput: "Focused the project key input",
            appliedDraftFilters: (count: number) => `Applied draft filters (${count} items)`,
            draftFiltersAlreadyMatch: "Draft filters already match the applied state",
          },
          layout: {
            overviewAriaLabel: "Command Tower workspace overview",
            overviewTitle: "Live posture and action entrypoints",
            overviewDescription: "The first screen keeps risk signals and primary actions visible. Detailed filters live in the right drawer.",
            sloDegraded: "SLO: degraded",
            sloWarning: "SLO: warning",
            focusButtonActive: "High-risk focused (click to show all)",
            focusButtonInactive: "Focus high-risk sessions",
            focusButtonActiveAriaLabel: "High-risk sessions are focused. Click again to restore all sessions.",
            focusButtonInactiveAriaLabel: "Focus high-risk sessions",
            focusButtonActiveTitle: "Only high-risk sessions are visible. Click again to restore all.",
            focusButtonInactiveTitle: "Show only high-risk sessions. Click again to restore all.",
            focusButtonActiveHint: "Only high-risk sessions are visible. Click the focus button again to restore the full list.",
            primaryActionOpenRisk: "Open first high-risk session",
            primaryActionGoToPm: "Go to PM and start a request",
            failureEvents: "Failure events",
            filterDrawerHint: "The filter console lives in the right context drawer (Alt+Shift+D)",
            degradedRefreshFailed: "Refresh failed: the list has switched to a cached snapshot. Review failure events before reloading.",
            degradedPartial: "Refresh is partially degraded: the list is running from a cached snapshot. Review failure events before proceeding.",
            snapshotTimestampOnly: (label: string) => `${label}. Timestamps only show when the snapshot was generated, not the live state.`,
            degradedActionsAriaLabel: "Degraded-state actions",
            reviewFailureEvents: "Review failure events",
            reviewRuns: "Review runs",
            reload: "Reload",
            riskSampleSummary: (total: number, failed: number, blocked: number, running: number) =>
              `Risk sample: ${total} sessions (high risk ${failed}, blocked ${blocked}, running ${running}).`,
            noLiveData: "Live data is unavailable right now. Start a new session or retry refresh later.",
            dataUnavailable: "Live data is unavailable right now. Start a new session or retry refresh later.",
            dataUnavailableActionsAriaLabel: "Degraded-state primary actions",
            sessionBoardAriaLabel: "Command Tower session board",
            sessionBoardMeta: (visible: number, total: number) =>
              `This list stays in sync with the quick actions above and currently shows ${visible} / ${total} sessions with risk-first ordering.`,
            cachedSnapshotBadge: "Cached snapshot",
            sessionBoardListAriaLabel: "Session board list",
            laneQuickActionsAriaLabel: (laneTitle: string) => `${laneTitle} quick actions`,
            liveLaneSwitchToLive: "Switch to live refresh",
            liveLaneSwitchToPaused: "Switch to paused analysis",
            riskLaneRestoreFullView: "Restore full view",
            riskLaneSwitchToHighRisk: "Switch to high-risk view",
            actionsLaneOpenFirstRisk: "Open first risk session",
            laneNote: "Each lane card exposes quick actions so you can jump straight into live control, risk focus, or the next operator step.",
          },
          drawer: {
            projectKeyPlaceholder: "e.g. cortexpilot",
            focusViewSwitcherAriaLabel: "Focus view switcher",
          },
          viewModel: {
            quickActions: {
              refreshDescription: "Pull overview, sessions, and alerts immediately.",
              liveDescription: "Control the live refresh cadence so you can pause on the current snapshot.",
              exportDescription: "Export failed sessions as JSON for triage or review.",
              copyDescription: "Share the current filters, focus mode, and live state with collaborators.",
              focusDescription: "Jump to the project key input to tighten the filter flow.",
              toggleDrawerDescription: "Change the right drawer density to favor the workspace or the context tools.",
              togglePinDescription: "Toggle whether the drawer stays pinned or scrolls with the page.",
              applyDescription: "Promote the draft state into the applied filters and trigger a refresh.",
              pauseAction: "Pause live",
              resumeAction: "Resume live",
              exportAction: "Export failed sessions",
              focusAction: "Focus",
              expandAction: "Expand",
              collapseAction: "Collapse",
              pinAction: "Pin",
              unpinAction: "Unpin",
            },
            contextHealth: {
              liveEngine: "Live engine",
              runningValue: (intervalMs: number) => `Running (${intervalMs}ms)`,
              pausedValue: "Paused",
              sloHealth: "SLO health",
              focusHit: "Focus hit",
              filterState: "Filter state",
              filtersApplied: (count: number) => `${count} filters applied`,
              filtersOff: "Filters off",
            },
            drawerPrompts: {
              criticalAlerts: (count: number) => `Detected ${count} critical alerts. Triage them first and verify the suggested actions.`,
              currentIssue: (label: string) => `Current issue: ${label}. Run Refresh now first to confirm whether it persists.`,
              unappliedDraftFilters: (count: number) => `Detected ${count} unapplied draft filters. Apply them before judging the risk trend.`,
              riskCounts: (failed: number, blocked: number) =>
                `High-risk sessions ${failed}, blocked sessions ${blocked}. Use the focus switcher to narrow quickly.`,
              paused: "Live refresh is paused. Resume live monitoring after the current analysis.",
              stable: "The current posture is stable. Run a routine refresh, then spot-check session details for hidden blockers.",
            },
            priorityLanes: {
              liveTitle: "Live Lane",
              liveSummary: (status: string, intervalMs: number) => `${status} · interval ${intervalMs}ms`,
              riskTitle: "Risk Lane",
              riskSummary: (failed: number, blocked: number, critical: number) =>
                `Failed ${failed} · Blocked ${blocked} · critical ${critical}`,
              actionsTitle: "Action Lane",
              draftFiltersWaiting: (count: number) => `${count} draft filters waiting`,
              refreshFirst: "Refresh first and focus high-risk sessions",
              primaryActionsReady: "Primary actions are ready",
              liveBadge: "Live",
              pausedBadge: "Paused",
              pendingBadge: "Pending",
              convergingBadge: "Converging",
              readyBadge: "Ready",
            },
          },
        },
      },
      runDetailPage: {
        title: "Run detail",
        subtitle: "Follow one run across status, event evidence, and replay comparison.",
        openCompareSurface: "Open compare surface",
        degradedTitle: "Run detail is partially degraded",
        degradedNextAction:
          "Retry this page first. If the same source is still unavailable, inspect the surviving Run Detail tabs and then return to the run list.",
        degradedBadge: "Partial data",
        reloadAction: "Reload run detail",
        backToRunsAction: "Back to run list",
        compareDecisionTitle: "Compare decision",
        compareMissing: "No structured compare report is attached yet.",
        compareAligned: "Current run looks aligned with the selected baseline.",
        compareNeedsReview: "Compare found deltas that need operator review before you trust this run.",
        compareNextStepMissing: "Next step: Generate or refresh a compare report for this run.",
        compareNextStepAligned: "Next step: Review proof and finalize the outcome.",
        compareNextStepNeedsReview:
          "Next step: Open compare and decide whether to replay, investigate, or keep the run blocked.",
        incidentActionTitle: "Incident action",
        incidentMissing: "No incident pack is attached yet.",
        incidentNextStepFallback: "Use reports and timeline to determine the next operator action.",
        proofActionTitle: "Proof action",
        proofMissing: "No proof pack is attached yet.",
        proofNextStepFallback: "Inspect the run reports before promoting or sharing any result.",
      },
      workflowDetailPage: {
        title: "Workflow Case detail",
        subtitle:
          "Classify risk first, then confirm the case summary, run mapping, queue posture, and event timeline before taking governance action.",
        riskSummaryAriaLabel: "Workflow risk summary",
        highRiskLabel: "High-risk state",
        normalRiskLabel: "Normal state",
        shareAssetCta: "Open share-ready case asset",
        degradedTitle: "Workflow Case is in read-only degraded mode",
        degradedNextAction:
          "Use the visible case identity, event timeline, and run mapping for diagnosis only. Wait for the data path to recover before taking approval, rollback, replay, or queue actions.",
        degradedBadge: "Read-only",
        degradedIdentityTitle: "Identity snapshot (degraded)",
        degradedRunMappingTitle: "Run mapping samples (degraded)",
        degradedRunMappingEmpty: "No verifiable run mapping is available in degraded mode.",
        degradedRunMappingReadonlyNote:
          "Read-only note: use the run chain for assessment only, not for direct governance actions.",
        degradedEventTimelineTitle: "Event timeline sample (degraded)",
        degradedEventTimelineReadonlyNote:
          "Events remain visible, but governance actions should wait until the data path is restored.",
        retryLoadAction: "Retry load",
        backToWorkflowListAction: "Back to workflow list",
        governanceEntryDisabled: "Governance entry (disabled in degraded mode)",
        summaryStatus: "Current status",
        summaryRunMappings: "Run mappings",
        summaryEvents: "Events",
        summaryRunMappingsHint: "Use this to locate the current execution path.",
        summaryEventsHint: "Filter failed and rollback events first.",
        queuePostureNote: "The web surface can now advance the queue directly when an operator role is configured.",
        caseFieldLabels: {
          workflowId: "workflow_id",
          name: "Name",
          updatedAt: "Updated at",
          namespace: "Namespace",
          taskQueue: "Task queue",
          owner: "Owner",
          project: "Project",
          verdict: "Verdict",
          runs: "Runs",
        },
      },
      workflowListPage: {
        title: "Workflow Cases",
        subtitle:
          "Workflow Cases keep queue posture, linked runs, verdict, and later Proof & Replay decisions attached to the same operating record.",
        summaryAriaLabel: "Workflow Case operator summary",
        countsBadge: (workflowCount: number, queueCount: number) =>
          `${workflowCount} workflows / ${queueCount} queue items`,
        metricLabels: {
          workflowCases: "Workflow Cases",
          queueSla: "Queue / SLA",
          nextRecommendedAction: "Next recommended action",
        },
        casesWithQueuedWork: (count: number) => `Cases with queued work: ${count}`,
        eligibleNow: (eligibleCount: number, atRiskCount: number) =>
          `Eligible now: ${eligibleCount} / at risk: ${atRiskCount}`,
        recommendedActions: {
          runNext: "Run the next queued task to move the active Workflow Case chain forward.",
          reviewTiming: "Review queue timing and SLA state, then dispatch when the next case becomes eligible.",
          openWorkflow: "Open a Workflow Case and queue the latest run contract to start the next operator loop.",
          createFirstWorkflow: "Create the first Workflow Case from PM intake, then return here to dispatch queued work.",
        },
        emptyTitle: "No workflow cases yet",
        emptyHint: "A Workflow Case is opened automatically on first execution.",
        tableCaption: "Workflow list",
        tableHeaders: {
          workflowId: "Workflow ID",
          status: "Status",
          namespace: "Namespace",
          taskQueue: "Task queue",
          runs: "Runs",
        },
        verdictPrefix: "verdict",
        queueSummary: (count: number, slaState: string) => `queue: ${count} / SLA ${slaState}`,
      },
      runsPage: {
        title: "Proof & Replay",
        subtitle:
          "Use this spine to inspect run evidence, compare posture, and replay decisions. Failed-run triage is only one lane inside the broader proof desk.",
        countsBadge: (runCount: number) => `${runCount} runs`,
        warningTitle: "Proof & Replay is currently running with partial truth.",
        warningNextStep: "Use the visible run records as a read-only snapshot, then confirm the affected Run Detail before making a governance decision.",
        metricLabels: {
          runInventory: "Run inventory",
          replayPosture: "Replay posture",
          operatorPriority: "Operator priority",
        },
        inventorySubline: "Total runs currently visible to the dashboard proof desk",
        failureHeadline: (failed: number) => `Failed ${failed}`,
        successHeadline: (success: number) => `Succeeded ${success}`,
        failureSubline: (success: number, running: number) => `Failure-first · Succeeded ${success} · Running ${running}`,
        successSubline: (running: number, failed: number) => `Success-first · Running ${running} · Failed ${failed}`,
        operatorPriorityHeadline: (failed: number) => `Review failed runs first: ${failed}`,
        operatorPriorityClearHeadline: "No failed runs need proof review right now",
        operatorPrioritySubline: "Open the failed lane first, then inspect proof, compare, and replay from Run Detail.",
        operatorPriorityClearSubline: "The failed lane is clear. Continue monitoring fresh runs and open PM when a new request needs to enter the loop.",
        operatorPrimaryActionFailed: "Open failed proof lane",
        operatorPrimaryActionClear: "Start a new task",
        operatorSecondaryAction: "View failed events",
        filterAriaLabel: "Proof & Replay status filter",
        filters: {
          all: "All runs",
          failed: "Failed",
          running: "Running",
          success: "Succeeded",
        },
        firstScreenLimit: (visibleCount: number) =>
          `The first screen is capped at the latest ${visibleCount} runs so proof review stays readable.`,
      },
      contractsPage: {
        title: "Contracts",
        subtitle:
          "Use the contract desk to inspect execution authority, bundle posture, runtime binding, and guardrails before trusting a task to continue.",
        countsBadge: (contractCount: number) => `${contractCount} contracts`,
        searchLabel: "Search",
        searchPlaceholder: "Filter by task_id / run_id / path",
        applyFilter: "Apply filter",
        filterSummary: (visible: number, total: number, defaultLimit: number) =>
          `Showing ${visible} / ${total} contracts. Default first-screen limit: ${defaultLimit}.`,
        warningTitle: "The contract desk is partially degraded.",
        warningNextStep: "Use this read-only snapshot to confirm contract identity, then reopen the affected run or workflow once the contract path recovers.",
        emptyTitle: "No contracts yet",
        emptyHint: "Contracts are generated automatically when work is assigned.",
        fieldLabels: {
          taskId: "Task ID",
          runId: "Run ID",
          assignedRole: "Assigned role",
          executionAuthority: "Execution authority",
          skillsBundle: "Skills bundle",
          mcpBundle: "MCP bundle",
          runtimeBinding: "Runtime binding",
          runtimeCapability: "Runtime capability",
          toolExecution: "Tool execution",
          allowedPaths: "Allowed paths",
          acceptanceTests: "Acceptance tests",
          toolPermissions: "Tool permissions",
        },
        fallbackValues: {
          unknownSource: "unknown",
          unknownContract: "Contract",
          notAssigned: "Not assigned",
          notPublished: "Not published",
          notDerived: "Not derived",
          unrestricted: "Unrestricted",
          noAcceptanceTests: "None",
          defaultPermissions: "Default",
        },
        fullJsonSummary: "Full contract JSON",
        moreHidden: (count: number) => `${count} more contracts are hidden.`,
        showAll: "Show all",
      },
      agentsPage: {
        title: "Agents",
        subtitle:
          "Open the role desk to confirm execution seats, runtime bindings, and scheduler posture. Treat capacity numbers as supporting evidence, not the product story.",
        openCommandTower: "Open command tower",
        warningTitle: "The role desk is currently in degraded snapshot mode.",
        warningNextStep: "Re-check the affected run or workflow before taking approval, replay, or release actions.",
        summaryAriaLabel: "Role desk summary",
        metricLabels: {
          riskDesk: "Blocked or failed lanes",
          executionSeats: "Live execution seats",
          schedulerPosture: "Scheduler posture",
        },
        metricBadges: {
          riskActive: "Operator focus first",
          riskClear: "No failing lanes",
          schedulerNeedsAction: "Needs scheduler action",
          schedulerStable: "Stable right now",
        },
        metricSublines: {
          risk: (statuses: number, healthy: number) => `State machine ${statuses} / Non-failed ${healthy}`,
          riskHint: "This card tracks runtime state only. Use it to decide which lane needs evidence review first.",
          execution: (activeAgents: number, capacityRatio: number) => `Bound agents ${activeAgents} (attach rate ${capacityRatio}%)`,
          executionHint: "This card confirms registered seats and bindings. It does not describe pending scheduler backlog.",
          scheduler: (unassignedStatuses: number, unassignedFailedStatuses: number) =>
            `Unassigned tasks ${unassignedStatuses} / Unassigned failures ${unassignedFailedStatuses}`,
          schedulerHint: (lockedAgentCount: number) =>
            `Agents holding locks ${lockedAgentCount}; this measures queue posture, not agent health.`,
        },
        actions: {
          inspectRiskDesk: "View pending details",
          inspectRoleDesk: "View role catalog",
          openFailedEvents: "Failed events",
        },
        roleCatalog: {
          title: "Role desk (read-only mirror)",
          subtitle:
            "This registry-backed view shows role purpose, bundle posture, runtime binding, and execution authority without promoting the catalog into the authority source.",
          fullList: "Full list",
          registryUnavailable: "The role registry is temporarily unavailable. Execution-lane triage remains available.",
          noMatches: "No role catalog entries match the current filter.",
          headers: {
            role: "Role",
            skillsBundle: "Skills bundle",
            mcpBundle: "MCP bundle",
            runtimeBinding: "Runtime binding",
            executionAuthority: "Execution authority",
            registeredSeats: "Registered seats",
          },
          noRolePurpose: "No role purpose published yet.",
          readOnlyMirror: "Read-only derived mirror",
          lockedSuffix: "locked",
        },
        filters: {
          title: "Role, seat, and scheduler filters",
          subtitle:
            "Use role and keyword filters to separate registered execution seats from scheduler backlog and failure records.",
          searchPlaceholder: "Search run / agent / task / path",
          allRoles: "All roles",
          applyFilter: "Apply filter",
          hint: "Leave the fields empty to inspect the full desk, then apply a filter once the investigation path is clear.",
          clearFilter: "Clear filter",
        },
        stateMachine: {
          title: "Execution lane triage",
          subtitle:
            'Use this table to inspect lanes run by run. "Pending scheduling" means scheduler backlog, not an automatic agent fault.',
          summaryBadge: (statuses: number, sample: number) => `State machine ${statuses} (first-screen sample ${sample})`,
          failedBadge: (failed: number, currentPageFailed: number) =>
            `Failed lanes ${failed} (current page ${currentPageFailed})`,
          unassignedFailuresBadge: (count: number) => `Unassigned failures ${count}`,
          viewFailedRuns: "View failed runs in bulk",
          emptyTitle: "No active runs",
          sampleHint: (visible: number) =>
            `The first screen shows the ${visible} samples that need the most triage. Continue paging for the rest.`,
          headers: {
            runId: "Run ID",
            taskId: "Task ID",
            role: "Role",
            agentId: "Agent ID",
            flowStage: "Flow stage",
            executionContext: "Execution context",
            governanceAction: "Governance action",
          },
          pendingScheduling: "Pending scheduling",
          pendingSchedulingHint: "No agent is assigned yet. The task is waiting in the scheduler queue.",
          schedulingFailed: "Scheduling failed",
          executionContextAriaLabel: "Execution-context summary",
          governanceActionsAriaLabel: "Run governance actions",
          detail: "Detail",
          detailFailedTitle: "Failed stage: diagnose and replay from run detail.",
          detailDefaultTitle: "View run detail",
          missingRunId: "Run ID missing",
        },
        registeredInventory: {
          title: (count: number) => `Registered execution seats (expandable, ${count} items)`,
          registryUnavailable: "The role registry is unavailable right now. Only the execution-lane and lock views remain.",
          emptyTitle: "No registered agents",
          tableAriaLabel: "Registered execution seat summary table",
          headers: {
            agentId: "Agent ID",
            role: "Role",
            lockCount: "Lock count",
            lockedPaths: "Locked paths",
          },
        },
        locks: {
          title: (total: number, pageCount: number) => `Lock posture (${total} total, ${pageCount} on this page)`,
          emptyTitle: "No lock records",
          tableAriaLabel: "Lock posture table",
          headers: {
            lockId: "Lock ID",
            runId: "Run ID",
            agentId: "Agent ID",
            role: "Role",
            path: "Path",
            timestamp: "Timestamp",
          },
        },
        pagination: {
          status: (page: number, totalPages: number, pageSize: number) => `Page ${page} / ${totalPages} (${pageSize} rows per page)`,
          previous: "Previous",
          next: "Next",
        },
      },
      sectionPrimary: "Core loop",
      sectionAdvanced: "Inspectors",
      labels: {
        overview: "Overview",
        pmIntake: "PM intake",
        commandTower: "Command Tower",
        runs: "Runs",
        quickApproval: "Quick approval",
        search: "Search",
        agents: "Agents",
        workflowCases: "Workflow Cases",
        events: "Events",
        reviews: "Reviews",
        diffGate: "Diff gate",
        tests: "Tests",
        contracts: "Contracts",
        policies: "Policies",
        locks: "Locks",
        worktrees: "Worktrees",
      },
    },
    desktop: {
      sectionPrimary: "Core loop",
      sectionAdvanced: "Inspectors",
      sectionGovernance: "Governance",
      shellAriaLabel: "CortexPilot Command Tower desktop shell",
      skipToMainContent: "Skip to main content",
      workspacePickerLabel: "Workspace picker",
      selectWorkspace: "Select workspace",
      loadingPageStyles: "Loading page styles...",
      loadingPage: "Loading page...",
      localeToggleAriaLabel: "Switch to Chinese",
      localeToggleButtonLabel: "中文",
      commandTower: {
        title: "Command Tower",
        subtitle: "Desktop stays focused on execution and operator decisions; deeper governance analysis moves to the web view.",
        currentModePrefix: "Current mode:",
        badges: {
          liveRefresh: "Live refresh",
          paused: "Paused",
          backoff: "Backoff",
          sloPrefix: "SLO: ",
        },
        actions: {
          refreshProgress: "Refresh progress",
          refreshing: "Refreshing...",
          pauseAutoRefresh: "Pause auto-refresh",
          resumeAutoRefresh: "Resume auto-refresh",
          resumeWork: "Resume work",
          openWebDeepAnalysis: "Open web deep analysis",
          showAdvancedDetail: "Show advanced detail",
          hideAdvancedDetail: "Hide advanced detail",
        },
        collapsedHint: "Advanced operator detail stays collapsed by default so the first screen remains action-focused.",
        webHandoffIntro: "Desktop owns the execution loop: refresh, pause, enter a session, and make operator decisions. For long-list analysis or complex filtering, use the",
        webAnalysisView: "web analysis view",
        metrics: {
          totalSessions: "Total sessions",
          active: "Active",
          failed: "Failed",
          blocked: "Blocked",
        },
        filterTitle: "Filters",
        filterHint: "Filters only affect the session list and can be combined with focus mode.",
        statusLegend: "Status",
        projectKey: "Project key",
        sort: "Sort",
        apply: "Apply",
        reset: "Reset",
        draftNotApplied: "Draft not applied",
        focusLabels: {
          all: "All",
          highRisk: "High risk",
          blocked: "Blocked",
          running: "Running",
        },
        refreshHealth: {
          fullSuccess: "Full refresh succeeded",
          fullFailure: "Full pipeline refresh failed",
          partialSuccess: (okCount: number) => `Partial refresh succeeded (${okCount}/3)`,
        },
        sectionLabels: {
          overview: "Overview",
          sessions: "Sessions",
          alerts: "Alerts",
          healthy: "Healthy",
          issue: "Issue",
        },
        errorIssueBadge: "Issue",
        errorRecommendedAction: "Recommended action: retry the refresh first. If it keeps failing, inspect network reachability and backend availability.",
        retryRefresh: "Retry refresh",
        retrying: "Retrying...",
        pauseLiveTriage: "Pause live triage",
        noSessionsForFilters: "No sessions match the current filters.",
        noSessionsForFocus: "No sessions match the current focus mode.",
        viewAll: "View all",
        sessionBoardTitle: "Session board",
        sessionBoardCount: (visible: number, total: number) => `Showing ${visible} / ${total} sessions`,
        noSessionsYet: "No sessions yet.",
        refreshNow: "Refresh now",
        viewAllSessions: "View all sessions",
        blockingHotspots: "Blocking hotspots",
        drawer: {
          ariaLabel: "Command Tower context drawer",
          title: "Context",
          close: "Close drawer",
          quickActions: "Quick actions",
          health: "Health",
          inspectionPrompts: "Inspection prompts",
          alerts: "Alerts",
          export: "Export",
          copy: "Copy",
          running: "RUNNING",
          paused: "PAUSED",
          focusHits: "Focus hits",
          filterState: "Filter state",
          allFilters: "ALL",
          noAlerts: "System healthy. No alerts right now.",
          reviewAlertState: "Review alert state",
          records: (count: number) => `${count} records`,
          criticalCount: (count: number) => `${count} critical`,
        },
      },
      runDetail: {
        backToList: "Back to list",
        taskLabelPrefix: "Task",
        liveModeActive: "LIVE",
        liveModePaused: "PAUSED",
        liveTogglePauseTitle: "Pause live updates",
        liveToggleResumeTitle: "Resume live updates",
        loadErrorPrefix: "Run detail failed to load:",
        loadErrorNextStep: "Next step: retry loading first. If it still fails, return to the list and open the run again.",
        retryLoad: "Retry load",
        noDetailPayload: "No detail payload is available for this run yet.",
        noDetailNextStep: "Next step: retry loading first. If it still fails, return to the list and select the run again.",
        pendingApprovalWithCount: (count: number) =>
          `This run is waiting for human approval (${count} item(s)). Next step: complete the approval before continuing.`,
        pendingApprovalWithoutCount:
          "This run is marked as awaiting human approval. Next step: complete the approval before continuing.",
        operatorCopilotTitle: "AI operator copilot",
        operatorCopilotIntro:
          "Generate one bounded operator brief grounded in current run, compare, proof, incident, workflow, queue, and approval truth.",
        operatorCopilotButton: "Generate operator brief",
        tabs: {
          events: (count: number) => `Event timeline (${count})`,
          diff: "Change diff",
          reports: (count: number) => `Reports (${count})`,
          tools: (count: number) => `Tool calls (${count})`,
          chain: "Chain flow",
          contract: "Contract policy",
          replay: "Replay compare",
        },
        summaryCards: {
          overviewTitle: "Run overview",
          executionRolesTitle: "Execution roles",
          evidenceTitle: "Evidence and traceability",
        },
        bindingReadModel: {
          title: "Role binding read model",
          authority: "Authority",
          source: "Source",
          executionAuthority: "Execution authority",
          skillsBundle: "Skills bundle",
          mcpBundle: "MCP bundle",
          runtimeBinding: "Runtime binding",
          runtimeCapability: "Runtime capability",
          toolExecution: "Tool execution",
          readOnlyNote:
            "Read-only note: this mirrors the persisted binding summary. task_contract still owns execution authority.",
        },
        completionGovernance: {
          title: "Completion governance",
          workerPromptContracts: "Worker prompt contracts",
          unblockTasks: "Unblock tasks",
          onIncomplete: "On incomplete",
          onBlocked: "On blocked",
          doneChecks: "DoD checks",
          unblockOwner: "Unblock owner",
          unblockMode: "Unblock mode",
          unblockTrigger: "Unblock trigger",
          advisoryNote:
            "Derived from persisted worker prompt contracts and unblock tasks. These summaries stay advisory; task_contract still owns execution authority.",
        },
        fieldLabels: {
          runId: "Run ID",
          taskId: "Task ID",
          status: "Status",
          executionSemantic: "Execution semantic",
          failureCode: "Failure code",
          failureSummary: "Failure summary",
          nextAction: "Next action",
          currentOwner: "Current owner",
          assignedExecution: "Assigned execution",
          createdAt: "Created at",
          traceId: "Trace ID",
          workflow: "Workflow",
          failureReason: "Failure reason",
          allowedPaths: "Allowed paths",
        },
        tableHeaders: {
          time: "Time",
          event: "Event",
          level: "Level",
          taskId: "Task ID",
          tool: "Tool",
          status: "Status",
          duration: "Duration",
          error: "Error",
        },
        actionBar: {
          promoteEvidence: "Promote evidence",
          rollback: "Rollback",
          reject: "Reject",
          refresh: "Refresh",
        },
        emptyStates: {
          noExecutionRoleStatus: "No execution role status is available yet.",
          executionRolesNextStep: "Next step: use Retry fetch to request a fresh payload.",
          retryFetch: "Retry fetch",
          noEvidenceSummary: "No evidence summary is available yet.",
          evidenceNextStep: "Next step: refresh the payload and try again.",
          refreshData: "Refresh data",
          noEvents: "No events are available yet.",
          eventsNextStep: "Next step: refresh events and request a fresh payload.",
          refreshEvents: "Refresh events",
          noDiff: "No diff content is available yet.",
          diffNextStep: "Next step: retry loading. If it stays empty, return to Event timeline and inspect execution progress there.",
          backToEventTimeline: "Back to Event timeline",
          noReports: "No reports are available yet.",
          reportsNextStep: "Next step: refresh reports and request a fresh payload.",
          refreshReports: "Refresh reports",
          noToolCalls: "No tool-call records are available yet.",
          toolCallsNextStep: "Next step: refresh tool calls and request a fresh payload.",
          refreshToolCalls: "Refresh tool calls",
          noChainFlow: "No chain-flow content is available yet.",
          chainNextStep: "Next step: refresh chain flow and request a fresh payload.",
          refreshChain: "Refresh chain flow",
          chainSpecTitle: "Chain Spec (chain.json)",
          chainReportTitle: "Chain Report",
          noContractSnapshot: "No contract snapshot is available yet.",
          contractNextStep: "Next step: refresh contract data and request a fresh payload.",
          refreshContract: "Refresh contract",
          replayTitle: "Replay compare",
          replayDescription: "Choose a baseline run to compare evidence-chain differences.",
          selectBaselineRun: "Select a baseline run...",
          runReplay: "Run replay",
          replayResult: "Replay result",
          compareDecisionTitle: "Compare decision",
          compareAligned: "The current run looks aligned with the selected baseline.",
          compareNeedsReview: "Compare found at least one delta, so this run still needs operator review.",
          compareNextStep: "Next step: review compare, proof, and incident context before deciding to replay, approve, or keep the run blocked.",
          actionContextTitle: "Action context",
          proofPrefix: "Proof:",
          incidentPrefix: "Incident:",
          noProofIncident: "No proof or incident pack is attached yet. Continue from the reports below.",
          compareSummaryTitle: "Compare summary",
          openCompareSurface: "Open compare surface",
          proofPackTitle: "Proof pack",
          relatedReportsTitle: "Related reports",
          testReportTitle: "test_report.json",
          reviewReportTitle: "review_report.json",
          evidenceReportTitle: "evidence_report.json",
        },
      },
      workflowDetail: {
        backToList: "Back to workflow list",
        queuePriority: "Queue priority",
        queueScheduledAt: "Queue scheduled at",
        queueDeadlineAt: "Queue deadline at",
        operatorRoleLabel: "Operator role",
        roleGateReason:
          "This environment has not published an operator role yet, so queue actions remain read-only until the command tower can prove who is allowed to dispatch work.",
        queueSummary: (queueCount: number, eligibleCount: number) =>
          `Queued items visible: ${queueCount}. Ready now: ${eligibleCount}.`,
        queueLatestRun: "Queue latest run contract",
        runNextQueuedTask: "Run next queued task",
        queueingTask: "Queueing...",
        runningTask: "Running...",
        noRunAvailable: "No run is available to enqueue.",
        queuedNotice: (taskId: string) => `Queued ${taskId}. Refreshing the workflow view...`,
        startedNotice: (runId: string) => `Started queued work as run ${runId}. Refreshing the workflow view...`,
        invalidScheduledAt: "Queue scheduled at must be a valid local date/time.",
        invalidDeadlineAt: "Queue deadline at must be a valid local date/time.",
        queueEmptyReason: "queue empty",
        workflowCopilotTitle: "Workflow Case copilot",
        workflowCopilotIntro:
          "Generate one bounded workflow brief grounded in workflow status, queue posture, the latest linked run, proof, compare, incident, and approval truth.",
        workflowCopilotButton: "Explain this workflow case",
        workflowCopilotTakeaways: "Latest run gap, proof, and truth coverage",
        workflowCopilotPosture: "Queue, SLA, and approval posture",
        workflowCopilotQuestions: [
          "What is the most important workflow case risk right now?",
          "What is the queue and SLA posture for this workflow case?",
          "What is the biggest gap between the latest run and the current workflow state?",
          "What should the operator do first to move this workflow case forward?",
          "Which truth surfaces are still missing or partial?",
        ],
        nextOperatorActionTitle: "Next Operator Action",
        nextOperatorActionHint: "Workflow Cases should be operated as case records, not as detached run rows.",
        recommendedActionQueued:
          "Queued work already exists. The next high-value action is to run the next queued task and watch the case move.",
        recommendedActionNoQueue:
          "No queued work exists yet. Queue the latest run contract to move this Workflow Case into SLA tracking.",
        recommendedActionNoRun:
          "No run is available yet. Start or resume a run before you queue this Workflow Case.",
        summaryTitle: "Workflow Case Summary",
        readModelTitle: "Workflow read model",
        noReadModel: "No workflow read model is attached yet.",
        relatedRunsTitle: (count: number) => `Related Runs (${count})`,
        noRelatedRuns: "No related runs",
        eventsTitle: (count: number) => `Events (${count})`,
        noEvents: "No events",
        queueSlaTitle: (count: number) => `Queue / SLA (${count})`,
        noQueuedWork: "No queued work for this workflow case.",
        queueMeta: (priority: string, sla: string) => `priority ${priority} / sla ${sla}`,
        summaryLabels: {
          status: "status",
          objective: "objective",
          owner: "owner",
          project: "project",
          verdict: "verdict",
          pmSessions: "pm_sessions",
          summary: "summary",
        },
        readModelLabels: {
          authority: "authority",
          executionAuthority: "execution_authority",
          source: "source",
          sourceRunId: "source_run_id",
          skillsBundle: "skills_bundle",
          mcpBundle: "mcp_bundle",
          runtimeBinding: "runtime_binding",
          readOnlyNote:
            "Read-only note: this workflow summary mirrors the latest linked run binding summary. The task contract still owns execution authority.",
        },
      },
      overview: {
        title: "Operator overview",
        subtitle:
          "Follow the primary path: start one workflow case, watch Command Tower, confirm the Workflow Case, then verify Proof & Replay. Only open approvals when the flow asks for one.",
        refreshData: "Refresh data",
        metricsAriaLabel: "Overview metrics",
        metricLabels: {
          totalSessions: "Total sessions",
          activeNow: "Active now",
          failureRatio: "Failure ratio",
          blockedQueue: "Blocked queue",
        },
        primaryActionsTitle: "Primary actions",
        optionalStepLabel: "Optional step",
        approvalCheckpoint: "Approval checkpoint",
        approvalCheckpointDesc:
          "Use the approval workspace only when the flow pauses for human confirmation.",
        currentProgressTitle: "Current progress",
        progressCards: {
          runningNow: "Running now",
          runningNowHint: 'Open "Runs" to follow the active work.',
          runningNowEmpty: "No tasks are running right now. Start a new one from the PM entrypoint.",
          needsAttention: "Needs attention",
          needsAttentionHint:
            "Prioritize the affected Run detail and decide whether to rollback, reject, or replay.",
          needsAttentionEmpty: "No failed tasks are currently visible.",
          riskEvents: "Risk events",
          riskEventsHint: "Inspect the event stream to locate the blocking root cause.",
          riskEventsEmpty: "Recent events do not show warning signals.",
        },
        recentRunsTitle: "Recent runs",
        recentRunsHint: "Open Run detail from here to review evidence and resolve outcomes.",
        noRunsYet: "No runs yet. Start your first request from the PM entrypoint.",
        viewAllRuns: "View all runs",
        recentEventsTitle: "Recent exceptions",
        viewAllExceptions: "View all exceptions",
        noExceptionsYet:
          "No exception signals yet. Failed runs and risk events will appear here after tasks start running.",
        openEventStream: "Open event stream",
        viewRun: "View Run",
        runningNowTitle: "Running now",
        recentExceptionTaskRequiresAttention: (taskId: string) => `Task ${taskId} requires attention`,
        recentExceptionOperatorEventFallback: "Operator event",
        recentExceptionLevelPrefix: "Level",
        recentExceptionRunPrefix: "Run",
        tableHeaders: {
          runId: "Run ID",
          taskId: "Task ID",
          status: "Status",
          createdAt: "Created at",
          time: "Time",
          exception: "Exception",
          details: "Details",
          action: "Action",
        },
        quickActions: {
          step1Label: "Step 1 · Brief PM",
          step1Desc:
            "Start at the PM entrypoint, state the goal and acceptance criteria, and let the system open the session.",
          step2Label: "Step 2 · Watch progress",
          step2Desc: "Use Command Tower to monitor session state, alerts, and pipeline health.",
          step3Label: "Step 3 · Review Workflow Cases",
          step3Desc:
            "Open Workflow Cases to confirm queue posture, operating verdict, and the current case record.",
          step4Label: "Step 4 · Verify Proof & Replay",
          step4Desc: "Open runs to inspect status, evidence chain, compare state, and replay results.",
        },
      },
      approval: {
        pageTitle: "Quick approval",
        pageSubtitle: "Manual approval queue for critical runs that are blocked pending human confirmation.",
        refresh: "Refresh",
        warningBanner:
          "This surface separates pending approvals, queue load failure, and manual approval input. A quiet queue is not proof that approval is globally unnecessary.",
        queueTitle: "Approval Queue",
        pendingBadge: (count: number) => `${count} pending`,
        criticalBadge: "CRITICAL",
        noPendingText:
          "No runs are waiting for approval in the current queue. This is not evidence that approval is disabled or unnecessary everywhere.",
        summaryLabel: "Summary",
        taskIdLabel: "Task ID",
        failureReasonLabel: "Failure reason",
        approveExecution: "Approve execution",
        manualInputTitle: "Manual Approval Input",
        manualInputHint: "Enter a Run ID to approve a task that is not currently listed in the queue",
        runIdLabel: "Run ID",
        runIdPlaceholder: "Enter Run ID",
        approve: "Approve",
        confirmDialogAriaLabel: "Approval confirmation dialog",
        closeConfirmDialogAriaLabel: "Close approval confirmation dialog",
        confirmTitle: "Confirm approval",
        confirmDescription: (runId: string) => `Approve run ${runId}? This action cannot be undone.`,
        cancel: "Cancel",
        confirmApproval: "Confirm approval",
        approvedToast: (runId: string) => `Approved ${runId}`,
      },
      labels: {
        overview: "Overview",
        pmIntake: "PM intake",
        commandTower: "Command Tower",
        runs: "Runs",
        runDetail: "Run Detail",
        runCompare: "Run Compare",
        workflowCases: "Workflow Cases",
        workflowCaseDetail: "Workflow Case Detail",
        quickApproval: "Quick approval",
        search: "Search",
        events: "Events",
        contracts: "Contracts",
        reviews: "Reviews",
        tests: "Tests",
        policies: "Policies",
        agents: "Agents",
        locks: "Locks",
        worktrees: "Worktrees",
        diffGate: "Diff gate",
        sessionView: "Session View",
      },
    },
  },
  "zh-CN": {
    brandTitle: "CortexPilot",
    brandSubtitle: "规划 · 派工 · 追踪 · 续跑 · 验真",
    dashboard: {
      homePhase2: {
        heroTitle: "AI 工程的指挥塔",
        heroSubtitle:
          "别再盯着 AI coding 一步一步催了。CortexPilot 会围绕 Codex / Claude Code 去规划、派工、追踪、续跑和验真，把长期工程任务收进一条受治理的操作路径、一份案例记录和一套可核对的证明链。",
        startFirstTaskLabel: "启动首个任务",
        startNewTaskLabel: "启动新任务",
        viewLatestRunsLabel: "查看最近 runs",
        investigateHighRiskFailuresLabel: "排查高风险失败",
        handleLatestFailureLabel: "处理最近失败",
        productSpineTitle: "规划、派工、追踪、续跑、验真",
        productSpineDescription:
          "首页先讲操作主循环，再用三块真相面把这条主线钉牢：Command Tower、Workflow Cases 和 Proof & Replay。",
        productSpineCards: [
          {
            href: "/command-tower",
            title: "Command Tower",
            desc: "把分散的会话、队列姿态和高风险漂移收进一个指挥塔里，而不是继续盯着零散窗口当保姆。",
          },
          {
            href: "/workflows",
            title: "Workflow Cases",
            desc: "把请求、队列、判定、证明和关联 runs 绑成一条可委派、可续跑的案例记录。",
          },
          {
            href: "/runs",
            title: "Proof & Replay",
            desc: "在真正信任结果前，先看证据包、对比重跑和失败回放，把“做完了”变成能验的事实。",
          },
        ],
        publicTemplatesTitle: "一个已证明工作流，两个展示扩展",
        publicTemplatesDescription:
          "先从 `news_digest` 开始。它是官方公开基线。`topic_brief` 和 `page_brief` 仍然有用，但在拿到各自健康证明包之前，它们仍属于展示路径。",
        publicTemplatesActionLabel: "打开证明包",
        publicTemplatesActionHref: "/use-cases/",
        publicTemplateCards: [
          {
            href: "/pm?template=news_digest",
            badge: "已发布验证的首跑",
            title: "news_digest",
            desc: "围绕一个主题生成新闻摘要，同时保留可审计的证据链。",
            bestFor: "适合最快证明导向的公开路径。",
            example: "Seattle tech and AI + 3 个来源域名 + 24h",
            proof: "Proof 状态：官方公开基线",
            fields: ["topic", "sources[]", "time_range", "max_results"],
          },
          {
            href: "/pm?template=topic_brief",
            badge: "公开展示",
            title: "topic_brief",
            desc: "把一个有边界的话题简报做成只读 workflow case，并附带搜索证据。",
            bestFor: "适合围绕一个主题和最近时间窗做窄范围简报。",
            example: "Seattle tech and AI + 7d + 5 results",
            proof: "Proof 状态：公开，但尚未作为发布级基线",
            fields: ["topic", "time_range", "max_results"],
          },
          {
            href: "/pm?template=page_brief",
            badge: "公开展示",
            title: "page_brief",
            desc: "围绕单个 URL 和浏览器证据生成只读 workflow case。",
            bestFor: "适合单页比整段主题更重要的情况。",
            example: "https://example.com + focused summary request",
            proof: "Proof 状态：浏览器证据展示路径",
            fields: ["url", "focus"],
          },
        ],
        publicAdvantagesTitle: "指挥塔背后的三层工程能力",
        publicAdvantagesDescription:
          "CortexPilot 不是再包一层花哨 prompt，而是把 prompt、context 和 harness 这三类最容易失控的东西，都拉进显式、可检查、可演进的系统里。",
        publicAdvantageCards: [
          {
            href: "/pm",
            title: "Prompt Engineering",
            desc: "把任务合同、范围、约束、交付物和验收条件讲清楚，而不是继续给模型塞一坨大 prompt。",
          },
          {
            href: "/workflows",
            title: "Context Engineering",
            desc: "让正确的上下文留在正确的脑子里：案例真相、角色绑定、队列姿态和交接材料都要显式管理，而不是任由窗口慢慢变脏。",
          },
          {
            href: "/contracts",
            title: "Harness Engineering",
            desc: "把 contract、approval、runtime binding 和 proof surface 全部接进轨道与护栏里，让系统能安全续跑，而不是只赌模型发挥。",
          },
        ],
        ecosystemTitle: "与当前 coding-agent 生态的关系",
        ecosystemDescription:
          "前门继续以 Codex、Claude Code 和只读 MCP 为主轴。OpenHands 和 comparison-only 工具只放在生态层，不放进 hero。",
        ecosystemAction: "打开生态地图",
        ecosystemActionHref: "/ecosystem/",
        ecosystemCards: [
          {
            badge: "主工作流绑定",
            title: "Codex 工作流",
            desc: "当 Codex 驱动的工作需要统一指挥塔、案例记录和可回放证明路径时，就该由 CortexPilot 承接。",
            href: "/command-tower",
            prefetch: true,
          },
          {
            badge: "主工作流绑定",
            title: "Claude Code 工作流",
            desc: "同一套操作面也适用于 Claude Code 风格的编码循环，重点在于治理可见性、审批和证据。",
            href: "/command-tower",
            prefetch: true,
          },
          {
            badge: "协议层",
            title: "只读 MCP",
            desc: "这里的 MCP 是真实协议面，但当前边界仍然是只读。外部工具可以读取真相，不能修改真相。",
            href: "/runs",
            prefetch: true,
          },
          {
            badge: "相邻生态",
            title: "OpenHands 与 comparison 层",
            desc: "OpenHands 留在更广的生态层；OpenCode 维持 comparison-only，OpenClaw 继续不进主前门。",
            href: "/ecosystem/",
          },
        ],
        integrationTitle: "选择正确的采用路径",
        integrationDescription:
          "先把 compatibility matrix 当成主路由，把 proof-first 指南当成最快建立信任的入口，再在任务真正明确后进入协议、playbook、package 或 AI 页面。",
        proofFirstActionLabel: "查看首个已证明工作流",
        proofFirstActionHref: "/use-cases/",
        integrationCards: [
          {
            badge: "决策入口",
            title: "Compatibility matrix",
            desc: "如果你想先用一页看懂 Codex、Claude Code、OpenClaw、只读 MCP、skills 和 builder 入口的关系，就从这里开始。",
            href: "/compatibility/",
          },
          {
            badge: "真实采用地图",
            title: "Integration guide",
            desc: "如果你需要更深入地理解 Codex、Claude Code 和 OpenClaw 的定位边界，而不是只看路由摘要，就看这里。",
            href: "/integrations/",
          },
          {
            badge: "Repo-owned playbook",
            title: "Skills quickstart",
            desc: "如果你的团队需要可复用的 agent playbook，而不是自己从 `.agents/skills/` 猜规则，就从这里开始。",
            href: "/skills/",
          },
        ],
        aiSurfacesTitle: "AI 功能已经进入主工作流",
        aiSurfacesDescription:
          "CortexPilot 里的 AI 不是漂浮聊天框。它已经分别出现在执行前建议、工作流解释，以及运行/对比的操作摘要里。",
        aiSurfacesActionLabel: "打开 AI + MCP + API 页面",
        aiSurfacesActionHref: "/ai-surfaces/",
        aiSurfaceCards: [
          {
            badge: "执行前建议",
            title: "Flight Plan 副驾驶",
            desc: "PM intake 现在可以在执行前先生成一份有边界的建议摘要，让审批和证据预期更早可见。",
            href: "/pm",
            prefetch: true,
          },
          {
            badge: "工作流级 AI",
            title: "Workflow 副驾驶",
            desc: "Workflow Case 已经能给出工作流级别的解释，覆盖队列姿态、最新 run 上下文和下一步操作。",
            href: "/workflows",
            prefetch: true,
          },
          {
            badge: "运行时 AI",
            title: "Run / Compare 操作摘要",
            desc: "Run Detail 和 compare 面已经能解释差异、证明、incident 上下文和下一步动作，而不假装自己在执行恢复。",
            href: "/runs",
            prefetch: true,
          },
        ],
        builderTitle: "Builder 入口",
        builderDescription:
          "这还不是完整 SDK 平台，但 builder 入口现在已经同时覆盖 read-only MCP quickstart、API and contract quickstart，以及 package 级 client/shared surface。",
        builderQuickstartCtaLabel: "打开 builder 快速入口",
        builderQuickstartCtaHref: "/builders/",
        builderCards: [
          {
            badge: "协议快速入口",
            title: "Read-only MCP quickstart",
            desc: "如果你想先拿到一张最短、最真实的 MCP 地图，再回头看 package 细节，就从这里开始。",
            href: "/mcp/",
          },
          {
            badge: "API 快速入口",
            title: "API and contract quickstart",
            desc: "如果你想先看 OpenAPI、contract-facing types 和 thin client 入口，再决定接哪一层，就从这里开始。",
            href: "/api/",
          },
          {
            badge: "薄客户端",
            title: "@cortexpilot/frontend-api-client",
            desc: "当你想从一个导入边界里拿到 runs、Workflow Cases、approvals 和 Command Tower 读取能力时，就从这里开始。",
            href: "https://github.com/xiaojiou176-open/CortexPilot-public/blob/main/packages/frontend-api-client/README.md",
          },
          {
            badge: "契约层",
            title: "@cortexpilot/frontend-api-contract",
            desc: "如果你想先看生成契约边界的人类说明，再决定要不要打开原始类型文件，就先从这个 README 开始。",
            href: "https://github.com/xiaojiou176-open/CortexPilot-public/blob/main/packages/frontend-api-contract/docs/README.md",
          },
          {
            badge: "表现层 substrate",
            title: "@cortexpilot/frontend-shared",
            desc: "品牌 copy、locale helper、status presentation 和 frontend-only types 已经集中到这一层，而不是散落在各 app 里。",
            href: "https://github.com/xiaojiou176-open/CortexPilot-public/blob/main/packages/frontend-shared/README.md",
          },
        ],
        liveCaseGalleryTitle: "真实 Workflow Case 画廊",
        liveCaseGalleryDescription:
          "把真实 Workflow Cases 作为轻量 showcase asset 来使用。这里会直接链接 live case detail 和可分享 recap，而不是伪造 demo-only 画廊数据。",
        liveCaseGalleryActionLabel: "打开 Workflow Cases",
        liveCaseGalleryActionHref: "/workflows",
        firstTaskGuideTitle: "首个任务指南（可展开）",
        firstTaskGuideDescription:
          "从请求开始，观察 Command Tower，确认 Workflow Case，再检查 Proof & Replay。默认折叠，避免首屏过吵。",
        firstTaskGuideSummary: "显示四步首跑流程",
        firstTaskGuideSteps: [
          {
            href: "/pm",
            prefetch: true,
            step: "第 1 步",
            title: "描述请求（目标 + 验收）",
            desc: "用一句话说清楚目标和验收标准，然后让系统打开 session。",
          },
          {
            href: "/command-tower",
            prefetch: false,
            step: "第 2 步",
            title: "观察实时进展（确认它在前进）",
            desc: "打开 Command Tower，确认 run 在推进而不是卡住。",
          },
          {
            href: "/workflows",
            prefetch: true,
            step: "第 3 步",
            title: "确认 Workflow Case",
            desc: "打开 Workflow Cases，确认持久案例记录、队列姿态和关联 runs。",
          },
          {
            href: "/runs",
            prefetch: true,
            step: "第 4 步",
            title: "检查 Proof & Replay",
            desc: "打开 run 台账，检查状态、证据、compare 状态和 replay 状态。",
          },
        ],
        optionalApprovalStep: {
          href: "/god-mode",
          prefetch: true,
          step: "可选",
          title: "审批检查点（仅在需要 review 时）",
          desc: "用 Quick approval 确认被阻塞步骤，并完成最后放行。",
        },
      },
      skipToMainContent: "跳到控制台主内容",
      navigationAriaLabel: "控制台导航",
      topbarTitle: "AI 工程指挥塔",
      platformStatusAriaLabel: "平台状态概览",
      lowFrequencyToolsLabel: "低频工具",
      localeToggleAriaLabel: "切换到英文",
      localeToggleButtonLabel: "EN",
      badges: {
        governanceView: "治理视图",
        liveVerificationRequired: "需要实时核验",
        pageLevelStatus: "页面级状态",
      },
      approval: {
        pageTitle: "人工审批",
        pageSubtitle: "在恢复执行前，把所有 HUMAN_APPROVAL_REQUIRED 项集中审阅一遍。",
        panelTitle: "人工裁决",
        panelIntro:
          "人工裁决页会把待审批项、只读权限缺口和队列拉取失败分开显示。队列安静，不代表全局不再需要审批。",
        roleConfigurationAriaLabel: "审批角色配置",
        operatorRoleLabel: "操作角色",
        operatorRoleUnconfigured: "未配置",
        refreshPending: "刷新待审批队列",
        refreshingPending: "刷新中...",
        lastSuccessfulRefreshPrefix: "最近一次成功刷新：",
        actionsDisabledTitle: "当前审批操作为只读。",
        queueLoadingBadge: "刷新中",
        queueLoadFailedBadge: "加载失败",
        queueIdleBadge: "没有待处理项",
        queuePendingBadge: (count: number) => `${count} 条待审批`,
        pendingTruthUnavailable: (error: string) => `待审批真相暂不可用：${error}`,
        recoveryTip: "恢复建议：先确认登录状态和审批角色，再进行重试。",
        lastAttemptPrefix: "最近一次尝试：",
        retryFetch: "重试拉取",
        retryingFetch: "重试中...",
        inspectConnection: "打开 PM 会话检查连接",
        verifyAuthState: "打开指挥塔检查认证状态",
        loadingPending: "正在加载待审批队列...",
        pendingQueueAriaLabel: "待审批队列",
        reasonLabel: "原因",
        requiredActionLabel: "需要动作",
        resumeAtLabel: "恢复位置",
        continueButton: "我已确认，继续执行",
        continuingButton: "审批中...",
        manualHint:
          "当事件流出现 HUMAN_APPROVAL_REQUIRED 时，把 run_id 粘贴到这里后批准。该动作会被写入事件日志。",
        runIdLabel: "运行 ID",
        runIdPlaceholder: "粘贴 run_id...",
        approveButton: "批准",
        approvingButton: "审批中...",
        confirmTitle: "确认批准",
        confirmDescription: (runId: string) =>
          `批准 ${runId} 并继续执行吗？该操作会写入事件日志，且不可撤销。`,
        cancel: "取消",
        confirmApproval: "确认批准",
        statusRefreshingQueue: "正在刷新待审批队列...",
        statusRetryingQueue: "正在重试待审批队列...",
        statusQueueRefreshed: (count: number) => `待审批队列已刷新。当前 ${count} 条。`,
        statusRefreshFailed: (message: string, authError: boolean) =>
          authError
            ? `待审批队列刷新失败：${message}。请先确认权限或重新登录后再试。`
            : "待审批队列刷新失败。请先处理错误再重试。",
        statusRetryFailed: (message: string, authError: boolean) =>
          authError
            ? `重试失败：${message}。请先确认权限或重新登录后再试。`
            : `重试失败：${message}。`,
        statusEnterRunId: "请先输入 run_id 再批准。",
        statusSubmittingApproval: "正在提交审批...",
        statusApproved: "已批准。",
        statusFailed: (message: string) => `失败：${message}`,
      },
      commandTowerPage: {
        unavailableTitle: "指挥塔实时总览暂不可用",
        unavailableNextAction:
          "先重试。如果实时数据仍然缺失，就打开运行记录确认最后一个已验证状态，或从 PM 入口重新建立主路径。",
        unavailableBadge: "实时数据缺失",
        partialTitle: "指挥塔当前只提供部分真相",
        partialNextAction:
          "当前可见总览只能算部分快照。做审批、回滚或发布判断前，先直接核对 Runs 或 Workflow Cases。",
        partialBadge: "上下文不完整",
        actions: {
          reload: "重载指挥塔",
          viewRuns: "查看运行记录",
          startFromPm: "从 PM 入口开始",
          openRuns: "打开运行记录",
          openWorkflowCases: "打开工作流案例",
        },
        fallbackLoading: "正在加载指挥塔实时总览...",
        srTitle: "指挥塔",
        srSubtitle: "先查看风险与阻塞，再进入会话处理。",
        liveHome: {
          loadingContextPanelAriaLabel: "指挥塔上下文面板",
          loadingContextPanelTitle: "上下文",
          loadingContextPanelBody: "正在加载上下文面板...",
          loadingSessionBoard: "正在加载会话面板...",
          focusModeLabels: {
            all: "全部",
            highRisk: "高风险",
            blocked: "阻塞",
            running: "运行中",
          },
          liveStatus: {
            paused: "实时刷新已暂停",
            backoff: "实时刷新正在退避并重试",
            degraded: "实时刷新正在运行，但当前只拿到部分数据",
            running: "实时刷新运行中",
          },
          refreshHealth: {
            fullHealthy: "完整刷新健康",
            refreshFailed: "刷新失败",
            partialDegradation: (okCount: number) => `部分降级（${okCount}/3）`,
          },
          snapshot: {
            refreshFailed: "缓存快照（刷新失败，自动更新已暂停）",
            partialDegradation: "缓存快照（部分降级，实时更新可能滞后）",
            paused: "缓存快照（实时刷新已暂停）",
          },
          freshness: {
            noSuccessfulRefresh: "还没有成功刷新记录",
            sourceFallback: (source: string) => `最近刷新来源：${source}`,
            lastSuccessfulSeconds: (seconds: number) => `上次成功刷新距今 ${seconds} 秒`,
            lastSuccessfulMinutes: (minutes: number) => `上次成功刷新距今 ${minutes} 分钟`,
            lastSuccessfulHours: (hours: number) => `上次成功刷新距今 ${hours} 小时`,
          },
          actionFeedback: {
            collapsedDrawer: "已收起右侧上下文抽屉",
            expandedDrawer: "已展开右侧上下文抽屉",
            pinnedDrawer: "已固定右侧抽屉",
            unpinnedDrawer: "已取消固定右侧抽屉",
            retryRefreshStart: "正在重试实时刷新...",
            retryRefreshPartial: "重试已完成，但仍有部分数据降级",
            retryRefreshSuccess: "重试成功，实时总览已更新",
            retryRefreshFailure: "重试失败。请查看失败事件。",
            focusSwitchStart: "正在刷新焦点视图...",
            focusSwitchPartial: "焦点视图已切换，但仍有部分数据降级",
            focusSwitchSuccess: (modeLabel: string) => `已切换到 ${modeLabel}`,
            focusSwitchFailure: "焦点视图切换失败。请查看失败事件。",
            copiedCurrentView: "已复制当前视图链接",
            copyUnavailable: "当前环境无法复制当前视图链接",
            copyFailedManual: "复制失败，请手动复制地址栏链接。",
            resumedLiveRefresh: "已恢复实时刷新",
            pausedLiveRefresh: "已暂停实时刷新",
            exportedFailedSessions: "已导出失败会话",
            focusedProjectKeyInput: "已聚焦项目键输入框",
            appliedDraftFilters: (count: number) => `已应用草稿筛选（${count} 项）`,
            draftFiltersAlreadyMatch: "当前草稿筛选与已应用状态一致",
          },
          layout: {
            overviewAriaLabel: "指挥塔工作区总览",
            overviewTitle: "实时态势与动作入口",
            overviewDescription: "第一屏始终把风险信号和主动作放在最前面，细筛选放在右侧抽屉。",
            sloDegraded: "SLO：降级",
            sloWarning: "SLO：告警",
            focusButtonActive: "已聚焦高风险（点击查看全部）",
            focusButtonInactive: "聚焦高风险会话",
            focusButtonActiveAriaLabel: "当前只显示高风险会话。再次点击可恢复全部会话。",
            focusButtonInactiveAriaLabel: "聚焦高风险会话",
            focusButtonActiveTitle: "当前只显示高风险会话。再次点击可恢复全部。",
            focusButtonInactiveTitle: "只显示高风险会话。再次点击可恢复全部。",
            focusButtonActiveHint: "当前只显示高风险会话。再次点击焦点按钮即可恢复完整列表。",
            primaryActionOpenRisk: "打开首个高风险会话",
            primaryActionGoToPm: "前往 PM 并发起请求",
            failureEvents: "失败事件",
            filterDrawerHint: "筛选控制台位于右侧上下文抽屉（Alt+Shift+D）",
            degradedRefreshFailed: "刷新失败：列表已切换到缓存快照。重新加载前请先查看失败事件。",
            degradedPartial: "刷新出现部分降级：列表当前运行在缓存快照上。继续之前请先查看失败事件。",
            snapshotTimestampOnly: (label: string) => `${label}。时间戳只表示快照生成时间，不代表实时状态。`,
            degradedActionsAriaLabel: "降级状态动作",
            reviewFailureEvents: "查看失败事件",
            reviewRuns: "查看运行记录",
            reload: "重新加载",
            riskSampleSummary: (total: number, failed: number, blocked: number, running: number) =>
              `风险样本：共 ${total} 个会话（高风险 ${failed}、阻塞 ${blocked}、运行中 ${running}）。`,
            noLiveData: "当前没有实时数据。先启动一个新会话，或稍后再重试刷新。",
            dataUnavailable: "当前没有实时数据。先启动一个新会话，或稍后再重试刷新。",
            dataUnavailableActionsAriaLabel: "降级主动作",
            sessionBoardAriaLabel: "指挥塔会话面板",
            sessionBoardMeta: (visible: number, total: number) =>
              `这个列表会和上方快捷动作保持同步，当前按风险优先顺序显示 ${visible} / ${total} 个会话。`,
            cachedSnapshotBadge: "缓存快照",
            sessionBoardListAriaLabel: "会话面板列表",
            laneQuickActionsAriaLabel: (laneTitle: string) => `${laneTitle} 快捷动作`,
            liveLaneSwitchToLive: "切到实时刷新",
            liveLaneSwitchToPaused: "切到暂停分析",
            riskLaneRestoreFullView: "恢复完整视图",
            riskLaneSwitchToHighRisk: "切到高风险视图",
            actionsLaneOpenFirstRisk: "打开首个风险会话",
            laneNote: "每张 lane 卡都暴露了快捷动作，这样你可以直接跳到实时控制、风险聚焦或下一步操作。",
          },
          drawer: {
            projectKeyPlaceholder: "例如 cortexpilot",
            focusViewSwitcherAriaLabel: "焦点视图切换器",
          },
          viewModel: {
            quickActions: {
              refreshDescription: "立即拉取总览、会话和告警。",
              liveDescription: "控制实时刷新节奏，这样你可以停在当前快照上做分析。",
              exportDescription: "把失败会话导出成 JSON，方便排查或复核。",
              copyDescription: "把当前筛选、焦点模式和实时状态分享给协作者。",
              focusDescription: "快速跳到项目键输入框，缩短筛选路径。",
              toggleDrawerDescription: "切换右侧抽屉密度，在主工作区和上下文工具之间取舍。",
              togglePinDescription: "切换抽屉是固定在页面上，还是跟随页面滚动。",
              applyDescription: "把草稿筛选提升为已应用筛选，并触发一次刷新。",
              pauseAction: "暂停实时",
              resumeAction: "恢复实时",
              exportAction: "导出失败会话",
              focusAction: "聚焦",
              expandAction: "展开",
              collapseAction: "收起",
              pinAction: "固定",
              unpinAction: "取消固定",
            },
            contextHealth: {
              liveEngine: "实时引擎",
              runningValue: (intervalMs: number) => `运行中（${intervalMs}ms）`,
              pausedValue: "已暂停",
              sloHealth: "SLO 健康度",
              focusHit: "焦点命中",
              filterState: "筛选状态",
              filtersApplied: (count: number) => `已应用 ${count} 个筛选`,
              filtersOff: "筛选关闭",
            },
            drawerPrompts: {
              criticalAlerts: (count: number) => `检测到 ${count} 个严重告警。先处理它们，再核对建议动作是否成立。`,
              currentIssue: (label: string) => `当前问题：${label}。先执行一次“立即刷新”，确认它是否仍然存在。`,
              unappliedDraftFilters: (count: number) => `检测到 ${count} 个未应用的草稿筛选。先应用，再判断风险趋势。`,
              riskCounts: (failed: number, blocked: number) =>
                `高风险会话 ${failed} 个，阻塞会话 ${blocked} 个。用焦点切换器先收窄范围。`,
              paused: "实时刷新当前已暂停。完成这一轮分析后，记得恢复实时监控。",
              stable: "当前态势稳定。先做一次例行刷新，再抽查几个会话详情，防止隐藏阻塞。",
            },
            priorityLanes: {
              liveTitle: "实时 Lane",
              liveSummary: (status: string, intervalMs: number) => `${status} · 间隔 ${intervalMs}ms`,
              riskTitle: "风险 Lane",
              riskSummary: (failed: number, blocked: number, critical: number) =>
                `失败 ${failed} · 阻塞 ${blocked} · 严重 ${critical}`,
              actionsTitle: "动作 Lane",
              draftFiltersWaiting: (count: number) => `有 ${count} 个草稿筛选待应用`,
              refreshFirst: "先刷新，再聚焦高风险会话",
              primaryActionsReady: "主动作已就绪",
              liveBadge: "实时",
              pausedBadge: "暂停",
              pendingBadge: "待处理",
              convergingBadge: "收敛中",
              readyBadge: "已就绪",
            },
          },
        },
      },
      runDetailPage: {
        title: "运行详情",
        subtitle: "沿着状态、事件证据和回放对比，完整跟踪这一条 Run。",
        openCompareSurface: "打开对比视图",
        degradedTitle: "运行详情当前处于部分降级状态",
        degradedNextAction:
          "先重试当前页面。如果同一数据源仍不可用，就先查看还能显示的 Run Detail 标签页，再回到运行列表。",
        degradedBadge: "部分数据",
        reloadAction: "重新加载运行详情",
        backToRunsAction: "返回运行列表",
        compareDecisionTitle: "对比判断",
        compareMissing: "当前还没有附带结构化 compare 报告。",
        compareAligned: "当前 Run 与所选基线看起来是一致的。",
        compareNeedsReview: "Compare 发现了差异，在信任这个 Run 之前仍需要操作员复核。",
        compareNextStepMissing: "下一步：为这个 Run 生成或刷新 compare 报告。",
        compareNextStepAligned: "下一步：复核 proof 并完成最终结论。",
        compareNextStepNeedsReview: "下一步：打开 compare，决定是重放、调查，还是继续阻塞这个 Run。",
        incidentActionTitle: "事件处置",
        incidentMissing: "当前还没有附带 incident pack。",
        incidentNextStepFallback: "先结合报告和时间线判断下一步操作。",
        proofActionTitle: "证明动作",
        proofMissing: "当前还没有附带 proof pack。",
        proofNextStepFallback: "在提升或分享任何结果前，先检查当前 Run 报告。",
      },
      workflowDetailPage: {
        title: "工作流案例详情",
        subtitle: "先判断风险，再确认案例摘要、Run 映射、队列姿态和事件时间线，然后再做治理动作。",
        riskSummaryAriaLabel: "工作流风险摘要",
        highRiskLabel: "高风险状态",
        normalRiskLabel: "正常状态",
        shareAssetCta: "打开可分享案例资产",
        degradedTitle: "工作流案例当前处于只读降级模式",
        degradedNextAction:
          "现在只能用可见的案例身份、事件时间线和 Run 映射来做诊断。在数据链路恢复前，不要执行审批、回滚、重放或队列动作。",
        degradedBadge: "只读",
        degradedIdentityTitle: "身份快照（降级）",
        degradedRunMappingTitle: "Run 映射样本（降级）",
        degradedRunMappingEmpty: "降级模式下当前没有可验证的 Run 映射。",
        degradedRunMappingReadonlyNote: "只读说明：这里只能拿 Run 链路做判断，不能直接拿来执行治理动作。",
        degradedEventTimelineTitle: "事件时间线样本（降级）",
        degradedEventTimelineReadonlyNote: "事件仍可见，但治理动作应等数据链路恢复后再进行。",
        retryLoadAction: "重新加载",
        backToWorkflowListAction: "返回工作流列表",
        governanceEntryDisabled: "治理入口（降级模式已禁用）",
        summaryStatus: "当前状态",
        summaryRunMappings: "Run 映射",
        summaryEvents: "事件数",
        summaryRunMappingsHint: "用它来定位当前执行路径。",
        summaryEventsHint: "先过滤失败和回滚事件。",
        queuePostureNote: "当操作角色已配置时，Web 面已经可以直接推进队列。",
        caseFieldLabels: {
          workflowId: "workflow_id",
          name: "名称",
          updatedAt: "更新时间",
          namespace: "命名空间",
          taskQueue: "任务队列",
          owner: "负责人",
          project: "项目",
          verdict: "结论",
          runs: "Runs",
        },
      },
      workflowListPage: {
        title: "工作流案例",
        subtitle:
          "工作流案例会把队列姿态、关联 Runs、结论，以及后续的 Proof & Replay 决策都绑在同一条操作记录上。",
        summaryAriaLabel: "工作流案例操作摘要",
        countsBadge: (workflowCount: number, queueCount: number) =>
          `${workflowCount} 个工作流 / ${queueCount} 个队列项`,
        metricLabels: {
          workflowCases: "工作流案例",
          queueSla: "队列 / SLA",
          nextRecommendedAction: "下一步建议动作",
        },
        casesWithQueuedWork: (count: number) => `已有排队工作的案例：${count}`,
        eligibleNow: (eligibleCount: number, atRiskCount: number) =>
          `当前可执行：${eligibleCount} / 有风险：${atRiskCount}`,
        recommendedActions: {
          runNext: "直接运行下一条排队任务，把当前工作流案例链继续往前推进。",
          reviewTiming: "先检查队列时机和 SLA 状态，等下一条案例变成可执行后再派发。",
          openWorkflow: "先打开一个工作流案例，再把最新 Run 合约排进队列，启动下一轮操作闭环。",
          createFirstWorkflow: "先从 PM intake 创建第一条工作流案例，然后再回到这里派发排队工作。",
        },
        emptyTitle: "当前还没有工作流案例",
        emptyHint: "先从 PM 入口创建第一条工作流案例，再回到这里确认 queue、proof 和下一步操作如何连成一条线。",
        tableCaption: "工作流列表",
        tableHeaders: {
          workflowId: "工作流 ID",
          status: "状态",
          namespace: "命名空间",
          taskQueue: "任务队列",
          runs: "Runs",
        },
        verdictPrefix: "结论",
        queueSummary: (count: number, slaState: string) => `队列：${count} / SLA ${slaState}`,
      },
      runsPage: {
        title: "Proof & Replay",
        subtitle:
          "这里是 Run 证据、对比姿态和重放决策的主入口。失败分流只是其中一条操作 lane，不是这张页面的全部意义。",
        countsBadge: (runCount: number) => `${runCount} 个 runs`,
        warningTitle: "Proof & Replay 当前处于部分真相模式。",
        warningNextStep: "先把当前可见 runs 当成只读快照，再进入对应的 Run Detail 做治理判断。",
        metricLabels: {
          runInventory: "运行库存",
          replayPosture: "重放姿态",
          operatorPriority: "当前操作优先级",
        },
        inventorySubline: "当前 Dashboard 在 Proof & Replay 面能看到的总 runs",
        failureHeadline: (failed: number) => `失败 ${failed}`,
        successHeadline: (success: number) => `成功 ${success}`,
        failureSubline: (success: number, running: number) => `先看失败 · 成功 ${success} · 运行中 ${running}`,
        successSubline: (running: number, failed: number) => `先看成功面 · 运行中 ${running} · 失败 ${failed}`,
        operatorPriorityHeadline: (failed: number) => `先复核失败 runs：${failed}`,
        operatorPriorityClearHeadline: "当前没有失败 runs 需要复核",
        operatorPrioritySubline: "优先打开失败 lane，再从 Run Detail 看 proof、compare 和 replay。",
        operatorPriorityClearSubline: "失败 lane 目前是空的。继续观察新 runs，或者从 PM 入口发起下一条请求。",
        operatorPrimaryActionFailed: "打开失败证明 lane",
        operatorPrimaryActionClear: "启动新任务",
        operatorSecondaryAction: "查看失败事件",
        filterAriaLabel: "Proof & Replay 状态筛选",
        filters: {
          all: "全部 runs",
          failed: "失败",
          running: "运行中",
          success: "成功",
        },
        firstScreenLimit: (visibleCount: number) =>
          `首屏只显示最新 ${visibleCount} 条 runs，避免证明复核面一上来就过载。`,
      },
      contractsPage: {
        title: "合约",
        subtitle:
          "把这里当成 command tower 的 contract desk：先确认执行权、bundle 姿态、runtime 绑定和护栏，再决定这条任务应不应该继续往前跑。",
        countsBadge: (contractCount: number) => `${contractCount} 份合约`,
        searchLabel: "搜索",
        searchPlaceholder: "按 task_id / run_id / path 过滤",
        applyFilter: "应用筛选",
        filterSummary: (visible: number, total: number, defaultLimit: number) =>
          `当前显示 ${visible} / ${total} 份合约。默认首屏上限：${defaultLimit}。`,
        warningTitle: "Contract desk 当前处于部分降级状态。",
        warningNextStep: "先把这份只读快照当成身份和护栏核对面，再回到对应 run 或 workflow 继续判断。",
        emptyTitle: "当前还没有合约",
        emptyHint: "任务一旦被正式派工，系统会自动生成对应合约。",
        fieldLabels: {
          taskId: "任务 ID",
          runId: "运行 ID",
          assignedRole: "分配角色",
          executionAuthority: "执行权",
          skillsBundle: "Skills bundle",
          mcpBundle: "MCP bundle",
          runtimeBinding: "Runtime 绑定",
          runtimeCapability: "Runtime 能力",
          toolExecution: "工具执行",
          allowedPaths: "允许路径",
          acceptanceTests: "验收测试",
          toolPermissions: "工具权限",
        },
        fallbackValues: {
          unknownSource: "未知来源",
          unknownContract: "合约",
          notAssigned: "尚未分配",
          notPublished: "尚未发布",
          notDerived: "尚未派生",
          unrestricted: "未限制",
          noAcceptanceTests: "无",
          defaultPermissions: "默认",
        },
        fullJsonSummary: "查看完整合约 JSON",
        moreHidden: (count: number) => `还有 ${count} 份合约未在首屏展开。`,
        showAll: "显示全部",
      },
      agentsPage: {
        title: "代理",
        subtitle:
          "把这里当成 role / control-plane desk：先确认哪些执行 lane 失稳、哪些 seats 真实绑定、scheduler 当前卡在哪，再往下钻 task 细节。",
        openCommandTower: "打开指挥塔",
        warningTitle: "当前代理总览处于降级快照模式。做治理动作前，请重新核对 Run Detail。",
        warningNextStep: "做审批、重放或发布判断前，先回到对应 run 或 workflow 复核最新真相。",
        summaryAriaLabel: "角色控制台摘要",
        metricLabels: {
          riskDesk: "失稳执行 lane",
          executionSeats: "在线执行 seats",
          schedulerPosture: "调度姿态",
        },
        metricBadges: {
          riskActive: "先处理操作风险",
          riskClear: "当前无失败 lane",
          schedulerNeedsAction: "需要调度动作",
          schedulerStable: "当前稳定",
        },
        metricSublines: {
          risk: (statuses: number, healthy: number) => `状态机总数 ${statuses} / 非失败 ${healthy}`,
          riskHint: "这张卡只看 runtime lane 状态，用来决定先去哪条线做证据复核。",
          execution: (activeAgents: number, capacityRatio: number) => `已绑定代理 ${activeAgents}（attach rate ${capacityRatio}%）`,
          executionHint: "这张卡确认 seat 和 binding 是否在线，不负责描述等待调度的 backlog。",
          scheduler: (unassignedStatuses: number, unassignedFailedStatuses: number) =>
            `未分配任务 ${unassignedStatuses} / 未分配失败 ${unassignedFailedStatuses}`,
          schedulerHint: (lockedAgentCount: number) => `当前有 ${lockedAgentCount} 个持锁代理；它反映的是队列姿态，不是代理健康度。`,
        },
        actions: {
          inspectRiskDesk: "查看待处理详情",
          inspectRoleDesk: "查看角色目录",
          openFailedEvents: "失败事件",
        },
        roleCatalog: {
          title: "角色 desk（只读镜像）",
          subtitle:
            "这张 registry-backed 视图展示角色目的、bundle 姿态、runtime 绑定和执行权，但不会把目录本身抬升成 authority source。",
          fullList: "完整列表",
          registryUnavailable: "角色 registry 当前不可用。你仍可继续查看 execution lane 和 lock posture。",
          noMatches: "当前筛选条件下没有匹配的角色目录项。",
          headers: {
            role: "角色",
            skillsBundle: "Skills bundle",
            mcpBundle: "MCP bundle",
            runtimeBinding: "Runtime 绑定",
            executionAuthority: "执行权",
            registeredSeats: "已注册 seats",
          },
          noRolePurpose: "当前还没有发布角色目的说明。",
          readOnlyMirror: "只读派生镜像",
          lockedSuffix: "已加锁",
        },
        filters: {
          title: "角色、seat 与 scheduler 筛选",
          subtitle: "用角色和关键词把已绑定 seats、scheduler backlog 和失败记录拆开看，避免把不同问题混成一张板。",
          searchPlaceholder: "搜索 run / agent / task / path",
          allRoles: "全部角色",
          applyFilter: "应用筛选",
          hint: "字段留空时就是完整 role desk；只有当调查路径明确后，再应用筛选。",
          clearFilter: "清除筛选",
        },
        stateMachine: {
          title: "执行 lane 分诊",
          subtitle: "按 run 逐条看执行 lane。这里的“待调度”表示 scheduler backlog，不等于代理本身出故障。",
          summaryBadge: (statuses: number, sample: number) => `状态机 ${statuses} 条（首屏样本 ${sample} 条）`,
          failedBadge: (failed: number, currentPageFailed: number) => `失败 lanes ${failed} 条（当前页 ${currentPageFailed} 条）`,
          unassignedFailuresBadge: (count: number) => `未分配失败 ${count} 条`,
          viewFailedRuns: "批量查看失败 runs",
          emptyTitle: "当前没有活动 runs",
          sampleHint: (visible: number) => `首屏优先展示最需要分诊的 ${visible} 条样本；其余内容继续翻页查看。`,
          headers: {
            runId: "运行 ID",
            taskId: "任务 ID",
            role: "角色",
            agentId: "代理 ID",
            flowStage: "流程阶段",
            executionContext: "执行上下文",
            governanceAction: "治理动作",
          },
          pendingScheduling: "待调度",
          pendingSchedulingHint: "当前还没有分配代理，这条任务仍在 scheduler 队列中等待。",
          schedulingFailed: "调度失败",
          executionContextAriaLabel: "执行上下文摘要",
          governanceActionsAriaLabel: "运行治理动作",
          detail: "详情",
          detailFailedTitle: "当前阶段失败：进入 Run Detail 做诊断和 replay 判断。",
          detailDefaultTitle: "查看 Run Detail",
          missingRunId: "缺少 Run ID",
        },
        registeredInventory: {
          title: (count: number) => `已注册执行 seats（可展开，${count} 项）`,
          registryUnavailable: "角色 registry 当前不可用，暂时只能查看 execution lane 和 lock posture。",
          emptyTitle: "当前没有已注册代理",
          tableAriaLabel: "已注册执行 seats 摘要表",
          headers: {
            agentId: "代理 ID",
            role: "角色",
            lockCount: "锁数量",
            lockedPaths: "已锁路径",
          },
        },
        locks: {
          title: (total: number, pageCount: number) => `锁姿态（共 ${total} 条，本页 ${pageCount} 条）`,
          emptyTitle: "当前没有锁记录",
          tableAriaLabel: "锁姿态表",
          headers: {
            lockId: "锁 ID",
            runId: "运行 ID",
            agentId: "代理 ID",
            role: "角色",
            path: "路径",
            timestamp: "时间戳",
          },
        },
        pagination: {
          status: (page: number, totalPages: number, pageSize: number) => `第 ${page} / ${totalPages} 页（每页 ${pageSize} 条）`,
          previous: "上一页",
          next: "下一页",
        },
      },
      sectionPrimary: "核心主线",
      sectionAdvanced: "检查与治理",
      labels: {
        overview: "总览",
        pmIntake: "PM 入口",
        commandTower: "指挥塔",
        runs: "运行记录",
        quickApproval: "快速审批",
        search: "检索",
        agents: "代理",
        workflowCases: "工作流案例",
        events: "事件流",
        reviews: "评审",
        diffGate: "差异门禁",
        tests: "测试",
        contracts: "合约",
        policies: "策略",
        locks: "锁管理",
        worktrees: "工作树",
      },
    },
    desktop: {
      sectionPrimary: "核心主线",
      sectionAdvanced: "检查与治理",
      sectionGovernance: "治理",
      shellAriaLabel: "CortexPilot 指挥塔桌面端",
      skipToMainContent: "跳到主内容",
      workspacePickerLabel: "工作区切换器",
      selectWorkspace: "选择工作区",
      loadingPageStyles: "正在加载页面样式...",
      loadingPage: "正在加载页面...",
      localeToggleAriaLabel: "切换到英文",
      localeToggleButtonLabel: "EN",
      commandTower: {
        title: "指挥塔",
        subtitle: "桌面端聚焦执行与操作决策；更深的治理分析留给 Web 视图。",
        currentModePrefix: "当前模式：",
        badges: {
          liveRefresh: "实时刷新",
          paused: "已暂停",
          backoff: "退避中",
          sloPrefix: "SLO：",
        },
        actions: {
          refreshProgress: "更新进展",
          refreshing: "刷新中...",
          pauseAutoRefresh: "暂停自动刷新",
          resumeAutoRefresh: "恢复自动刷新",
          resumeWork: "继续处理",
          openWebDeepAnalysis: "打开 Web 深度分析",
          showAdvancedDetail: "展开专家信息",
          hideAdvancedDetail: "收起专家信息",
        },
        collapsedHint: "默认先收起高级操作细节，让第一屏保持执行优先。",
        webHandoffIntro: "桌面端负责执行主循环：刷新、暂停、进入会话并作出操作决策。若要做长列表分析或复杂筛选，请使用",
        webAnalysisView: "Web 分析视图",
        metrics: {
          totalSessions: "会话总数",
          active: "活跃",
          failed: "失败",
          blocked: "阻塞",
        },
        filterTitle: "筛选器",
        filterHint: "筛选器只影响会话列表，可与 focus mode 组合使用。",
        statusLegend: "状态",
        projectKey: "项目键",
        sort: "排序",
        apply: "应用",
        reset: "重置",
        draftNotApplied: "草稿未应用",
        focusLabels: {
          all: "全部",
          highRisk: "高风险",
          blocked: "阻塞",
          running: "运行中",
        },
        refreshHealth: {
          fullSuccess: "完整刷新成功",
          fullFailure: "整条刷新链路失败",
          partialSuccess: (okCount: number) => `部分刷新成功（${okCount}/3）`,
        },
        sectionLabels: {
          overview: "总览",
          sessions: "会话",
          alerts: "告警",
          healthy: "健康",
          issue: "异常",
        },
        errorIssueBadge: "问题",
        errorRecommendedAction: "建议动作：先重试刷新。如果仍然失败，再检查网络连通性和后端可用性。",
        retryRefresh: "重试刷新",
        retrying: "重试中...",
        pauseLiveTriage: "暂停实时排查",
        noSessionsForFilters: "当前筛选条件下没有匹配的会话。",
        noSessionsForFocus: "当前 focus 模式下没有匹配的会话。",
        viewAll: "查看全部",
        sessionBoardTitle: "会话面板",
        sessionBoardCount: (visible: number, total: number) => `显示 ${visible} / ${total} 个会话`,
        noSessionsYet: "还没有会话。",
        refreshNow: "立即刷新",
        viewAllSessions: "查看全部会话",
        blockingHotspots: "阻塞热点",
        drawer: {
          ariaLabel: "指挥塔上下文抽屉",
          title: "上下文",
          close: "关闭抽屉",
          quickActions: "快捷动作",
          health: "健康状态",
          inspectionPrompts: "排查提示",
          alerts: "告警",
          export: "导出",
          copy: "复制",
          running: "运行中",
          paused: "已暂停",
          focusHits: "焦点命中",
          filterState: "筛选状态",
          allFilters: "全部",
          noAlerts: "系统当前健康，没有告警。",
          reviewAlertState: "查看告警状态",
          records: (count: number) => `${count} 条记录`,
          criticalCount: (count: number) => `${count} 个严重`,
        },
      },
      runDetail: {
        backToList: "返回列表",
        taskLabelPrefix: "任务",
        liveModeActive: "运行中",
        liveModePaused: "已暂停",
        liveTogglePauseTitle: "暂停实时更新",
        liveToggleResumeTitle: "恢复实时更新",
        loadErrorPrefix: "Run 详情加载失败：",
        loadErrorNextStep: "下一步：先重试加载。如果仍然失败，就回到列表重新打开这个 Run。",
        retryLoad: "重试加载",
        noDetailPayload: "当前还没有这个 Run 的详情负载。",
        noDetailNextStep: "下一步：先重试加载。如果仍然失败，就回到列表重新选择这个 Run。",
        pendingApprovalWithCount: (count: number) =>
          `这个 Run 正在等待人工审批（${count} 项）。下一步：先完成审批再继续。`,
        pendingApprovalWithoutCount:
          "这个 Run 被标记为等待人工审批。下一步：先完成审批再继续。",
        operatorCopilotTitle: "AI 操作员副驾驶",
        operatorCopilotIntro:
          "生成一份有边界的操作员摘要，基于当前 run、compare、proof、incident、workflow、queue 和 approval 真相。",
        operatorCopilotButton: "生成操作摘要",
        tabs: {
          events: (count: number) => `事件时间线（${count}）`,
          diff: "变更差异",
          reports: (count: number) => `报告（${count}）`,
          tools: (count: number) => `工具调用（${count}）`,
          chain: "链路流转",
          contract: "合约策略",
          replay: "回放对比",
        },
        summaryCards: {
          overviewTitle: "Run 总览",
          executionRolesTitle: "执行角色",
          evidenceTitle: "证据与可追溯性",
        },
        bindingReadModel: {
          title: "角色绑定只读模型",
          authority: "权威来源",
          source: "来源",
          executionAuthority: "执行权威",
          skillsBundle: "技能包",
          mcpBundle: "MCP 包",
          runtimeBinding: "运行时绑定",
          runtimeCapability: "运行时能力",
          toolExecution: "工具执行",
          readOnlyNote:
            "只读说明：这里展示的是持久化的角色绑定摘要镜像；`task_contract` 仍然掌握执行权威。",
        },
        completionGovernance: {
          title: "完成治理摘要",
          workerPromptContracts: "工作者提示合约",
          unblockTasks: "解阻塞任务",
          onIncomplete: "未完成时",
          onBlocked: "阻塞时",
          doneChecks: "完成定义检查",
          unblockOwner: "解阻塞负责人",
          unblockMode: "解阻塞模式",
          unblockTrigger: "解阻塞触发器",
          advisoryNote:
            "这些摘要来自持久化的工作者提示合约和解阻塞任务；它们只提供参考，`task_contract` 仍然掌握执行权威。",
        },
        fieldLabels: {
          runId: "Run ID",
          taskId: "任务 ID",
          status: "状态",
          executionSemantic: "执行语义",
          failureCode: "失败代码",
          failureSummary: "失败摘要",
          nextAction: "下一步动作",
          currentOwner: "当前负责人",
          assignedExecution: "当前执行分配",
          createdAt: "创建时间",
          traceId: "追踪 ID",
          workflow: "工作流",
          failureReason: "失败原因",
          allowedPaths: "允许路径",
        },
        tableHeaders: {
          time: "时间",
          event: "事件",
          level: "级别",
          taskId: "任务 ID",
          tool: "工具",
          status: "状态",
          duration: "耗时",
          error: "错误",
        },
        actionBar: {
          promoteEvidence: "提升为证据",
          rollback: "回滚",
          reject: "拒绝",
          refresh: "刷新",
        },
        emptyStates: {
          noExecutionRoleStatus: "当前还没有执行角色状态。",
          executionRolesNextStep: "下一步：点击“重试拉取”，请求一份新的负载。",
          retryFetch: "重试拉取",
          noEvidenceSummary: "当前还没有证据摘要。",
          evidenceNextStep: "下一步：刷新负载后再试一次。",
          refreshData: "刷新数据",
          noEvents: "当前还没有事件记录。",
          eventsNextStep: "下一步：刷新事件，并请求一份新的负载。",
          refreshEvents: "刷新事件",
          noDiff: "当前还没有差异内容。",
          diffNextStep: "下一步：先重试加载。如果仍然为空，就回到事件时间线继续看执行进展。",
          backToEventTimeline: "返回事件时间线",
          noReports: "当前还没有报告。",
          reportsNextStep: "下一步：刷新报告，并请求一份新的负载。",
          refreshReports: "刷新报告",
          noToolCalls: "当前还没有工具调用记录。",
          toolCallsNextStep: "下一步：刷新工具调用，并请求一份新的负载。",
          refreshToolCalls: "刷新工具调用",
          noChainFlow: "当前还没有链路流转内容。",
          chainNextStep: "下一步：刷新链路流转，并请求一份新的负载。",
          refreshChain: "刷新链路流转",
          chainSpecTitle: "链路规格（chain.json）",
          chainReportTitle: "链路报告",
          noContractSnapshot: "当前还没有合约快照。",
          contractNextStep: "下一步：刷新合约数据，并请求一份新的负载。",
          refreshContract: "刷新合约",
          replayTitle: "回放对比",
          replayDescription: "选择一个基线 run，比较证据链差异。",
          selectBaselineRun: "选择一个基线 run...",
          runReplay: "运行回放",
          replayResult: "回放结果",
          compareDecisionTitle: "对比结论",
          compareAligned: "当前 run 与所选基线看起来是一致的。",
          compareNeedsReview: "对比发现至少一个 delta，所以这个 run 仍然需要操作员复核。",
          compareNextStep: "下一步：先检查 compare、proof 和 incident 上下文，再决定是回放、批准还是继续阻塞。",
          actionContextTitle: "动作上下文",
          proofPrefix: "Proof：",
          incidentPrefix: "Incident：",
          noProofIncident: "当前没有附带 proof 或 incident pack。先从下面的报告继续排查。",
          compareSummaryTitle: "对比摘要",
          openCompareSurface: "打开对比视图",
          proofPackTitle: "Proof 包",
          relatedReportsTitle: "相关报告",
          testReportTitle: "test_report.json",
          reviewReportTitle: "review_report.json",
          evidenceReportTitle: "evidence_report.json",
        },
      },
      workflowDetail: {
        backToList: "返回工作流列表",
        queuePriority: "队列优先级",
        queueScheduledAt: "计划执行时间",
        queueDeadlineAt: "截止时间",
        operatorRoleLabel: "操作角色",
        roleGateReason:
          "当前环境还没有发布可执行的操作角色，所以队列动作保持只读；先确认这条 command tower 由谁负责，再回来推进队列。",
        queueSummary: (queueCount: number, eligibleCount: number) =>
          `当前可见队列项：${queueCount}。现在可执行：${eligibleCount}。`,
        queueLatestRun: "排入最新 Run 合约",
        runNextQueuedTask: "运行下一条排队任务",
        queueingTask: "加入队列中...",
        runningTask: "运行中...",
        noRunAvailable: "当前没有可加入队列的 Run。",
        queuedNotice: (taskId: string) => `已将 ${taskId} 加入队列，正在刷新工作流视图...`,
        startedNotice: (runId: string) => `已启动排队工作，Run 为 ${runId}。正在刷新工作流视图...`,
        invalidScheduledAt: "计划执行时间必须是有效的本地日期时间。",
        invalidDeadlineAt: "截止时间必须是有效的本地日期时间。",
        queueEmptyReason: "队列为空",
        workflowCopilotTitle: "AI 工作流副驾驶",
        workflowCopilotIntro:
          "生成一份有边界的工作流摘要，基于 workflow 状态、队列姿态、最新 linked run、proof、compare、incident 与 approval 真相。",
        workflowCopilotButton: "解释这个工作流案例",
        workflowCopilotTakeaways: "最新 Run 差距、证据与真相覆盖",
        workflowCopilotPosture: "队列、SLA 与审批姿态",
        workflowCopilotQuestions: [
          "当前最重要的工作流案例风险是什么？",
          "这个工作流案例当前的队列和 SLA 姿态如何？",
          "最新 Run 和当前工作流状态之间最大的差距是什么？",
          "操作员下一步最应该先做什么？",
          "还有哪些真相面仍然缺失或不完整？",
        ],
        nextOperatorActionTitle: "下一步操作",
        nextOperatorActionHint: "工作流案例应该作为案例记录来运营，而不是孤立的 Run 行。",
        recommendedActionQueued: "已有排队工作。下一步最有价值的动作是运行下一条排队任务并观察案例前进。",
        recommendedActionNoQueue: "当前还没有排队工作。先把最新 Run 合约加入队列，让这个工作流案例进入 SLA 跟踪。",
        recommendedActionNoRun: "当前没有可用 Run。先启动或恢复一个 Run，再把这个工作流案例送入队列。",
        summaryTitle: "工作流案例摘要",
        readModelTitle: "工作流只读模型",
        noReadModel: "当前还没有附加工作流只读模型。",
        relatedRunsTitle: (count: number) => `相关 Run（${count}）`,
        noRelatedRuns: "当前没有相关 Run",
        eventsTitle: (count: number) => `事件（${count}）`,
        noEvents: "当前没有事件",
        queueSlaTitle: (count: number) => `队列 / SLA（${count}）`,
        noQueuedWork: "这个工作流案例当前没有排队工作。",
        queueMeta: (priority: string, sla: string) => `优先级 ${priority} / SLA ${sla}`,
        summaryLabels: {
          status: "状态",
          objective: "目标",
          owner: "负责人",
          project: "项目",
          verdict: "结论",
          pmSessions: "PM 会话",
          summary: "摘要",
        },
        readModelLabels: {
          authority: "权威来源",
          executionAuthority: "执行权威",
          source: "来源",
          sourceRunId: "来源 Run",
          skillsBundle: "技能包",
          mcpBundle: "MCP 包",
          runtimeBinding: "运行时绑定",
          readOnlyNote:
            "只读说明：这里展示的是最新 linked run 的绑定摘要镜像；`task_contract` 仍然掌握执行权威。",
        },
      },
      overview: {
        title: "新手起步",
        subtitle:
          "首次使用建议先走一遍单主流程：先创建一个工作流案例，再看 Command Tower，然后确认 Workflow Case，最后核对 Proof & Replay。只有真的出现人工确认时，才进入审批面。",
        refreshData: "刷新数据",
        metricsAriaLabel: "总览指标",
        metricLabels: {
          totalSessions: "会话总数",
          activeNow: "当前活跃",
          failureRatio: "失败占比",
          blockedQueue: "阻塞队列",
        },
        primaryActionsTitle: "主步骤",
        optionalStepLabel: "可选步骤",
        approvalCheckpoint: "审批确认",
        approvalCheckpointDesc: "只有流程暂停并等待人工确认时，才进入审批工作区。",
        currentProgressTitle: "当前进展",
        progressCards: {
          runningNow: "运行中",
          runningNowHint: "打开“运行记录”追踪当前活跃工作。",
          runningNowEmpty: "当前没有正在运行的任务。先从 PM 入口发起一个新的请求。",
          needsAttention: "需要关注",
          needsAttentionHint: "优先打开对应 Run 详情，判断是回滚、拒绝还是重放。",
          needsAttentionEmpty: "当前没有失败任务。",
          riskEvents: "风险事件",
          riskEventsHint: "打开事件流定位阻塞根因。",
          riskEventsEmpty: "最近没有明显的风险信号。",
        },
        recentRunsTitle: "最近运行",
        recentRunsHint: "从这里进入 Run 详情，查看证据并处理结果。",
        noRunsYet: "还没有运行记录。先从 PM 入口发起你的第一个请求。",
        viewAllRuns: "查看全部运行",
        recentEventsTitle: "最近异常",
        viewAllExceptions: "查看全部异常",
        noExceptionsYet: "还没有异常信号。失败任务和风险事件会在任务运行后出现在这里。",
        openEventStream: "打开事件流",
        viewRun: "查看 Run",
        runningNowTitle: "运行中",
        recentExceptionTaskRequiresAttention: (taskId: string) => `任务 ${taskId} 需要关注`,
        recentExceptionOperatorEventFallback: "操作事件",
        recentExceptionLevelPrefix: "级别",
        recentExceptionRunPrefix: "Run",
        tableHeaders: {
          runId: "Run ID",
          taskId: "Task ID",
          status: "状态",
          createdAt: "创建时间",
          time: "时间",
          exception: "异常",
          details: "详情",
          action: "操作",
        },
        quickActions: {
          step1Label: "主步骤 1 · 发需求",
          step1Desc: "从 PM 入口开始，说明目标和验收标准，让系统先建立会话。",
          step2Label: "主步骤 2 · 看进度",
          step2Desc: "通过 Command Tower 观察会话状态、告警和执行进度。",
          step3Label: "主步骤 3 · 看案例",
          step3Desc: "打开 Workflow Cases，确认队列姿态、运行结论和当前案例记录。",
          step4Label: "主步骤 4 · 核证据",
          step4Desc: "打开运行记录，核对状态、证据链、对比结果和回放信息。",
        },
      },
      approval: {
        pageTitle: "快速审批",
        pageSubtitle: "处理那些因为等待人工确认而阻塞的关键运行。",
        refresh: "刷新",
        warningBanner:
          "这个界面会把待审批队列、队列拉取失败、以及手动批准输入分开显示。队列安静，不代表全局不需要审批。",
        queueTitle: "审批队列",
        pendingBadge: (count: number) => `${count} 条待处理`,
        criticalBadge: "关键",
        noPendingText:
          "当前队列里没有等待审批的运行。这并不代表别的路径上也不再需要审批。",
        summaryLabel: "摘要",
        taskIdLabel: "任务 ID",
        failureReasonLabel: "失败原因",
        approveExecution: "批准执行",
        manualInputTitle: "手动审批输入",
        manualInputHint: "输入一个 Run ID，批准当前不在列表里的任务",
        runIdLabel: "运行 ID",
        runIdPlaceholder: "输入 Run ID",
        approve: "批准",
        confirmDialogAriaLabel: "审批确认弹窗",
        closeConfirmDialogAriaLabel: "关闭审批确认弹窗",
        confirmTitle: "确认批准",
        confirmDescription: (runId: string) => `批准运行 ${runId} 吗？该操作不可撤销。`,
        cancel: "取消",
        confirmApproval: "确认批准",
        approvedToast: (runId: string) => `已批准 ${runId}`,
      },
      labels: {
        overview: "总览",
        pmIntake: "PM 入口",
        commandTower: "指挥塔",
        runs: "运行记录",
        runDetail: "运行详情",
        runCompare: "运行对比",
        workflowCases: "工作流案例",
        workflowCaseDetail: "工作流案例详情",
        quickApproval: "快速审批",
        search: "检索",
        events: "事件流",
        contracts: "合约",
        reviews: "评审",
        tests: "测试",
        policies: "策略",
        agents: "代理",
        locks: "锁管理",
        worktrees: "工作树",
        diffGate: "差异门禁",
        sessionView: "会话视图",
      },
    },
  },
};

function normalizeLocale(locale: string | undefined | null): UiLocale {
  return locale === "zh-CN" ? "zh-CN" : "en";
}

export function getUiCopy(locale: string | undefined | null = DEFAULT_UI_LOCALE): UiCopy {
  return UI_COPY[normalizeLocale(locale)];
}
