import { describe, expect, it } from "vitest";
import { categoryLabel, formatDate, scoreBarColorClass, scoreColorClass } from "./format";

describe("scoreColorClass", () => {
  it.each([
    [95, "text-emerald-400"],
    [80, "text-emerald-400"],
    [79.9, "text-sky-400"],
    [65, "text-sky-400"],
    [64.9, "text-amber-400"],
    [45, "text-amber-400"],
    [44.9, "text-rose-400"],
    [0, "text-rose-400"],
  ])("maps score %s to %s", (score, expected) => {
    expect(scoreColorClass(score)).toBe(expected);
  });
});

describe("scoreBarColorClass", () => {
  it("uses the same thresholds as scoreColorClass, just for backgrounds", () => {
    expect(scoreBarColorClass(90)).toBe("bg-emerald-500");
    expect(scoreBarColorClass(10)).toBe("bg-rose-500");
  });
});

describe("categoryLabel", () => {
  it("title-cases snake_case category names", () => {
    expect(categoryLabel("technical_skill")).toBe("Technical Skill");
    expect(categoryLabel("work_rights")).toBe("Work Rights");
    expect(categoryLabel("location")).toBe("Location");
  });
});

describe("formatDate", () => {
  it("returns a dash for missing dates", () => {
    expect(formatDate(null)).toBe("-");
    expect(formatDate(undefined)).toBe("-");
  });

  it("falls back to the raw string for unparseable input", () => {
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });

  it("formats a valid ISO date", () => {
    // Just check it doesn't throw and returns a non-empty, non-dash string.
    const result = formatDate("2026-01-15T00:00:00Z");
    expect(result).not.toBe("-");
    expect(result.length).toBeGreaterThan(0);
  });
});
