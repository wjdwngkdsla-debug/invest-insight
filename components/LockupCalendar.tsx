"use client";




import { useEffect, useMemo, useState } from "react";
import Link from "next/link";




export type CalendarEventKind = "lockup" | "forecast" | "sub" | "listing";




// 단일일 이벤트 (락업해제, 상장)
export interface CalendarEvent {
  date: string; // YYYY-MM-DD
  name: string;
  code: string;
  kind?: CalendarEventKind; // 기본 lockup
}




// 기간 이벤트 (수요예측, 청약) — 주 단위 가로 바로 그린다
export interface CalendarRangeEvent {
  start: string;
  end: string;
  name: string;
  code: string;
  kind: "forecast" | "sub";
}




const ALL_KINDS: CalendarEventKind[] = ["lockup", "forecast", "sub", "listing"];
const KIND_LABEL: Record<CalendarEventKind, string> = {
  lockup: "락업 해제",
  forecast: "수요예측",
  sub: "청약",
  listing: "상장",
};
// 같은 날 표시 순서: 락업해제 → 상장 → 수요예측 → 청약
const KIND_ORDER: Record<CalendarEventKind, number> = { lockup: 0, listing: 1, forecast: 2, sub: 3 };




// 기간형 바 — 은은한 배경 (수요예측은 톤 다운한 보라)
const BAR_STYLE: Record<"forecast" | "sub", string> = {
  forecast: "bg-violet-50/60 text-violet-500 hover:bg-violet-100",
  sub: "bg-amber-50 text-amber-800 hover:bg-amber-100",
};




const DOT_COLOR: Record<CalendarEventKind, string> = {
  lockup: "bg-blue-400",
  forecast: "bg-violet-300",
  sub: "bg-amber-400",
  listing: "bg-emerald-500",
};




// 필터 토글 칩 (활성 시)
const FILTER_ACTIVE: Record<CalendarEventKind, string> = {
  lockup: "bg-blue-50 text-blue-700",
  forecast: "bg-violet-50/70 text-violet-500",
  sub: "bg-amber-50 text-amber-800",
  listing: "bg-emerald-50 text-emerald-800",
};




// 팝오버 카테고리 그룹 배경
const GROUP_BG: Record<CalendarEventKind, string> = {
  lockup: "bg-blue-50/70",
  forecast: "bg-violet-50/70",
  sub: "bg-amber-50/70",
  listing: "bg-emerald-50/70",
};




interface DayCell {
  day: number;
  dateStr: string;
}




const WEEKDAY_LABELS = ["월", "화", "수", "목", "금"];




// 서버(UTC)와 브라우저가 같은 "한국 기준 오늘"을 계산하도록 절대시간에서 유도
function kstToday(): { year: number; month: number; dateStr: string } {
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const year = kst.getUTCFullYear();
  const month = kst.getUTCMonth(); // 0-based
  const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(kst.getUTCDate()).padStart(2, "0")}`;
  return { year, month, dateStr };
}




// 해당 월을 월~금 5칸 주 단위로 배열 (주말 제외, 빈 칸은 null)
function buildWeeks(year: number, month: number): (DayCell | null)[][] {
  const weeks: (DayCell | null)[][] = [];
  let current: (DayCell | null)[] = [];
  const lastDay = new Date(year, month + 1, 0).getDate();




  for (let day = 1; day <= lastDay; day++) {
    const weekday = new Date(year, month, day).getDay(); // 0=일 ... 6=토
    if (weekday === 0 || weekday === 6) continue;
    if (weekday === 1 && current.length > 0) {
      while (current.length < 5) current.push(null);
      weeks.push(current);
      current = [];
    }
    if (current.length === 0 && weekday > 1) {
      for (let pad = 1; pad < weekday; pad++) current.push(null);
    }
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    current.push({ day, dateStr });
  }
  if (current.length > 0) {
    while (current.length < 5) current.push(null);
    weeks.push(current);
  }
  return weeks;
}




function shortDate(s: string): string {
  const [, m, d] = s.split("-");
  return `${Number(m)}/${Number(d)}`;
}




interface WeekBar {
  s: number; // 시작 칸 (0~4)
  e: number; // 끝 칸
  lane: number;
  ev: CalendarRangeEvent;
  contLeft: boolean; // 이전 주에서 이어짐
  contRight: boolean; // 다음 주로 이어짐
}




export function LockupCalendar({
  events,
  rangeEvents = [],
  holidays,
}: {
  events: CalendarEvent[];
  rangeEvents?: CalendarRangeEvent[];
  holidays: Record<string, string>;
}) {
  const initialToday = kstToday();
  const [year, setYear] = useState(initialToday.year);
  const [month, setMonth] = useState(initialToday.month);
  // "오늘" 강조는 접속 시점 기준이어야 한다. 빌드 시점(SSR) 값에 굳지 않게 마운트 후 재계산.
  // (이 값이 굳어서 새로고침=빌드날짜, 탭이동=현재날짜로 엇갈리던 버그 수정)
  const [today, setToday] = useState(initialToday);
  useEffect(() => {
    const timer = window.setTimeout(() => setToday(kstToday()), 0);
    return () => window.clearTimeout(timer);
  }, []);
  // 범례 = 토글 필터. 초기값은 전체 표시
  const [active, setActive] = useState<Set<CalendarEventKind>>(new Set(ALL_KINDS));
  const allActive = active.size === ALL_KINDS.length;




  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const event of events) {
      const list = map.get(event.date) || [];
      if (!list.some((item) => item.code === event.code && (item.kind || "lockup") === (event.kind || "lockup"))) {
        list.push(event);
      }
      map.set(event.date, list);
    }
    for (const list of map.values()) {
      list.sort((a, b) => KIND_ORDER[a.kind || "lockup"] - KIND_ORDER[b.kind || "lockup"]);
    }
    return map;
  }, [events]);




  const weeks = useMemo(() => buildWeeks(year, month), [year, month]);




  function moveMonth(delta: number) {
    const moved = new Date(year, month + delta, 1);
    setYear(moved.getFullYear());
    setMonth(moved.getMonth());
  }




  function toggleKind(kind: CalendarEventKind) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }




  // 주 안에서 기간 바 배치 (겹치면 다음 줄로 — 간단한 레인 배정)
  function computeWeekBars(week: (DayCell | null)[]): { bars: WeekBar[]; laneCount: number } {
    const bars: WeekBar[] = [];
    for (const ev of rangeEvents) {
      if (!active.has(ev.kind)) continue;
      let s = -1;
      let e = -1;
      week.forEach((cell, i) => {
        if (cell && ev.start <= cell.dateStr && cell.dateStr <= ev.end) {
          if (s < 0) s = i;
          e = i;
        }
      });
      if (s < 0) continue;
      bars.push({
        s,
        e,
        lane: 0,
        ev,
        contLeft: (week[s] as DayCell).dateStr > ev.start,
        contRight: (week[e] as DayCell).dateStr < ev.end,
      });
    }
    bars.sort((a, b) => a.s - b.s || b.e - a.e);
    const laneEnds: number[] = [];
    for (const bar of bars) {
      let lane = laneEnds.findIndex((end) => end < bar.s);
      if (lane < 0) {
        lane = laneEnds.length;
        laneEnds.push(bar.e);
      } else {
        laneEnds[lane] = bar.e;
      }
      bar.lane = lane;
    }
    return { bars, laneCount: laneEnds.length };
  }




  // 특정 날짜의 전체 일정(바 + 칩) — "+N개 더" 팝오버에 카테고리별로 보여준다
  function dayAllItems(dateStr: string): { kind: CalendarEventKind; name: string; code: string }[] {
    const chips = (eventsByDate.get(dateStr) || [])
      .filter((ev) => active.has(ev.kind || "lockup"))
      .map((ev) => ({ kind: (ev.kind || "lockup") as CalendarEventKind, name: ev.name, code: ev.code }));
    const bars = rangeEvents
      .filter((ev) => active.has(ev.kind) && ev.start <= dateStr && dateStr <= ev.end)
      .map((ev) => ({ kind: ev.kind as CalendarEventKind, name: ev.name, code: ev.code }));
    return [...chips, ...bars].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
  }




  function chipHref(ev: { kind: CalendarEventKind; code: string }): string {
    return ev.kind === "lockup" ? `/stock/${ev.code}` : "/ipo";
  }




  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className="text-base font-bold">
            {year}년 {month + 1}월 락업 해제 캘린더
          </h2>
          {/* 범례 겸 토글 필터 */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium">
            <button
              onClick={() => setActive(allActive ? new Set() : new Set(ALL_KINDS))}
              className={`rounded-full px-2.5 py-0.5 transition-colors ${
                allActive ? "bg-gray-900 text-white" : "border border-gray-200 bg-white text-gray-500 hover:bg-gray-50"
              }`}
            >
              전체
            </button>
            {ALL_KINDS.map((kind) => {
              const on = active.has(kind);
              return (
                <button
                  key={kind}
                  onClick={() => toggleKind(kind)}
                  className={`flex items-center gap-1 rounded-full px-2.5 py-0.5 transition-colors ${
                    on ? FILTER_ACTIVE[kind] : "border border-gray-100 bg-white text-gray-300 hover:bg-gray-50"
                  }`}
                >
                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${on ? DOT_COLOR[kind] : "bg-gray-200"}`} />
                  {KIND_LABEL[kind]}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex items-center gap-1 text-sm">
          <button
            onClick={() => moveMonth(-1)}
            aria-label="이전 달"
            className="rounded-md border border-gray-200 bg-white px-2.5 py-1 text-gray-600 hover:bg-gray-50"
          >
            ‹
          </button>
          <button
            onClick={() => {
              setYear(today.year);
              setMonth(today.month);
            }}
            className="rounded-md border border-gray-200 bg-white px-2.5 py-1 text-gray-600 hover:bg-gray-50"
          >
            오늘
          </button>
          <button
            onClick={() => moveMonth(1)}
            aria-label="다음 달"
            className="rounded-md border border-gray-200 bg-white px-2.5 py-1 text-gray-600 hover:bg-gray-50"
          >
            ›
          </button>
        </div>
      </div>




      <div className="grid grid-cols-5 gap-1.5">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="pb-1 text-center text-xs font-semibold text-gray-400">
            {label}
          </div>
        ))}
      </div>




      <div className="space-y-1.5">
        {weeks.map((week, weekIndex) => {
          const { bars, laneCount } = computeWeekBars(week);
          const chipRowBase = 2 + laneCount;
          return (
            <div key={weekIndex} className="relative">
              {/* 배경 셀 레이어 (테두리·휴장일·오늘 표시) */}
              <div className="absolute inset-0 grid grid-cols-5 gap-1.5">
                {week.map((cell, i) => {
                  if (!cell) return <div key={i} className="rounded-lg bg-gray-50/60" />;
                  const holidayName = holidays[cell.dateStr];
                  const isToday = cell.dateStr === today.dateStr;
                  return (
                    <div
                      key={i}
                      className={`rounded-lg border ${
                        holidayName ? "border-rose-100 bg-rose-50/70" : "border-gray-100 bg-white"
                      } ${isToday ? "ring-2 ring-blue-400" : ""}`}
                    />
                  );
                })}
              </div>




              {/* 내용 레이어 — 바가 칸 경계를 가로질러 이어진다 */}
              <div className="relative grid min-h-20 grid-cols-5 gap-x-1.5 pb-1" style={{ gridAutoRows: "min-content" }}>
                {week.map((cell, i) => {
                  const holidayName = cell ? holidays[cell.dateStr] : undefined;
                  return (
                    <div key={`day-${i}`} style={{ gridColumn: i + 1, gridRow: 1 }} className="px-1.5 pb-0.5 pt-1.5">
                      {cell && (
                        <p className={`truncate text-[11px] font-semibold ${holidayName ? "text-rose-400" : "text-gray-400"}`}>
                          {cell.day}
                          {holidayName ? ` · ${holidayName}` : ""}
                        </p>
                      )}
                    </div>
                  );
                })}




                {bars.map((bar, barIndex) => (
                  <Link
                    key={`bar-${barIndex}`}
                    href="/ipo"
                    style={{ gridColumn: `${bar.s + 1} / ${bar.e + 2}`, gridRow: 2 + bar.lane }}
                    className={`mb-1 flex min-w-0 items-baseline gap-1 px-1.5 py-0.5 text-[11px] font-medium ${BAR_STYLE[bar.ev.kind]} ${
                      bar.contLeft ? "" : "ml-1 rounded-l-md"
                    } ${bar.contRight ? "" : "mr-1 rounded-r-md"}`}
                  >
                    <span className="truncate">{bar.ev.name}</span>
                    {bar.e > bar.s && (
                      <span className="shrink-0 text-[10px] opacity-60">
                        {shortDate(bar.ev.start)}~{shortDate(bar.ev.end)}
                      </span>
                    )}
                  </Link>
                ))}




                {week.flatMap((cell, i) => {
                  if (!cell || holidays[cell.dateStr]) return [];
                  const dayChips = (eventsByDate.get(cell.dateStr) || []).filter((ev) => active.has(ev.kind || "lockup"));
                  const limit = laneCount > 0 ? 2 : 3;
                  const visible = dayChips.slice(0, limit);
                  const hiddenCount = dayChips.length - visible.length;
                  const nodes = visible.map((ev, j) => {
                    const kind = (ev.kind || "lockup") as CalendarEventKind;
                    return (
                      <Link
                        key={`chip-${i}-${j}`}
                        href={chipHref({ kind, code: ev.code })}
                        style={{ gridColumn: i + 1, gridRow: chipRowBase + j }}
                        className={`mx-1 mb-1 flex min-w-0 items-center gap-1 rounded px-1 py-0.5 text-[11px] font-medium ${
                          kind === "listing"
                            ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200"
                            : "text-gray-700 hover:bg-blue-50"
                        }`}
                      >
                        {kind !== "listing" && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_COLOR[kind]}`} />}
                        <span className="truncate">{ev.name}</span>
                      </Link>
                    );
                  });
                  if (hiddenCount > 0) {
                    const allItems = dayAllItems(cell.dateStr);
                    const grouped = ALL_KINDS.map((kind) => ({
                      kind,
                      items: allItems.filter((item) => item.kind === kind),
                    })).filter((group) => group.items.length > 0);
                    nodes.push(
                      <div
                        key={`more-${i}`}
                        style={{ gridColumn: i + 1, gridRow: chipRowBase + visible.length }}
                        className="group relative px-1.5"
                      >
                        <p className="cursor-default text-[10px] text-gray-400">+{hiddenCount}개 더</p>
                        {/* 데스크톱 hover 팝오버 — 카테고리별 배경. 캘린더 밖으로 안 나가게 방향 자동 결정. */}
                        {(() => {
                          const horizontal = i >= 3 ? "right-full mr-1.5" : "left-full ml-1.5";
                          // 마지막 주면 위로 뜨게(아래로 넘칠 위험), 아니면 위 맞춤으로 아래 흐름
                          const vertical = weekIndex >= weeks.length - 1 ? "bottom-0" : "top-0";
                          return (
                            <div
                              className={`pointer-events-none absolute z-50 hidden w-60 rounded-lg border border-gray-200 bg-white p-2.5 opacity-0 shadow-xl transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100 lg:block ${horizontal} ${vertical}`}
                            >
                          <p className="mb-1.5 px-1 text-[12px] font-bold text-gray-700">
                            {month + 1}월 {cell.day}일 일정 상세
                          </p>
                          <div className="space-y-1.5">
                            {grouped.map((group) => (
                              <div key={group.kind} className={`rounded-md p-1.5 ${GROUP_BG[group.kind]}`}>
                                <p className="px-1 text-[10px] font-semibold text-gray-500">
                                  {KIND_LABEL[group.kind]} ({group.items.length}건)
                                </p>
                                <div className="mt-0.5 space-y-0.5">
                                  {group.items.map((item, itemIndex) => (
                                    <Link
                                      key={`${item.code}-${itemIndex}`}
                                      href={chipHref(item)}
                                      className="flex min-w-0 items-center gap-1.5 rounded px-1 py-0.5 text-[11px] font-medium text-gray-700 hover:bg-white/70"
                                    >
                                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_COLOR[item.kind]}`} />
                                      <span className="truncate">{item.name}</span>
                                    </Link>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                          );
                        })()}
                      </div>
                    );
                  }
                  return nodes;
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
