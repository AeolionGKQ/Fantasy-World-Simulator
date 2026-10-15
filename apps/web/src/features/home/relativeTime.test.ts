import { describe, expect, it } from "vitest";
import { relativeTime } from "./relativeTime";

describe("relativeTime", () => {
  const now = new Date("2026-10-15T12:00:00");

  it("describes recent times relatively", () => {
    expect(relativeTime("2026-10-15T11:59:40", now)).toBe("刚刚");
    expect(relativeTime("2026-10-15T11:35:00", now)).toBe("25 分钟前");
    expect(relativeTime("2026-10-15T09:00:00", now)).toBe("3 小时前");
    expect(relativeTime("2026-10-12T12:00:00", now)).toBe("3 天前");
  });

  it("falls back to a calendar date after a week", () => {
    expect(relativeTime("2026-10-01T08:00:00", now)).toBe("10 月 1 日");
    expect(relativeTime("2025-12-30T08:00:00", now)).toBe("2025 年 12 月 30 日");
  });

  it("returns an empty string for missing or invalid input", () => {
    expect(relativeTime(undefined, now)).toBe("");
    expect(relativeTime("not a date", now)).toBe("");
  });
});
