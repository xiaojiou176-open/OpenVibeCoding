"use client";

import { useReportWebVitals } from "next/web-vitals";

import { reportWebVitals } from "../app/reportWebVitals";

export default function WebVitalsBridge() {
  useReportWebVitals(reportWebVitals);
  return null;
}
