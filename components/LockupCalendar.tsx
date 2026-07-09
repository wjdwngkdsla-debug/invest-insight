"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

export interface CalendarEvent {
  date: string; // YYYY-MM-DD (거래가능일)
  name: string;
  code: string;
}

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

export function LockupCalendar({
  events,
  holidays,
}: {
  events: CalendarEvent[];
  holidays: Record<string, string>;
}) {
  const today = kstToday();
  const [year, setYear] = useState(today.year);
  const [month, setMonth] = useState(today.month);

  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const event of events) {
      const list = map.get(event.date) || [];
      if (!list.some((item) => item.code === event.code)) list.push(event);
      map.set(event.date, list);
    }
    return map;
  }, [events]);

  const weeks = useMemo(() => buildWeeks(year, month), [year, month]);

  function moveMonth(delta: number) {
    const moved = new Date(year, month + delta, 1);
    setYear(moved.getFullYear());
    setMonth(moved.getMonth());
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-bold">
          {year}년 {month + 1}월 락업 해제 캘린더
        </h2>
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
        {weeks.flat().map((cell, index) => {
          if (!cell) return <div key={`empty-${index}`} className="min-h-20 rounded-lg bg-gray-50/60" />;
          const holidayName = holidays[cell.dateStr];
          const dayEvents = eventsByDate.get(cell.dateStr) || [];
          const isToday = cell.dateStr === today.dateStr;
          return (
            <div
              key={cell.dateStr}
              className={`min-h-20 rounded-lg border p-1.5 ${
                holidayName ? "border-rose-100 bg-rose-50/70" : "border-gray-100 bg-white"
              } ${isToday ? "ring-2 ring-blue-400" : ""}`}
            >
              <p className={`text-[11px] font-semibold ${holidayName ? "text-rose-400" : "text-gray-400"}`}>
                {cell.day}
              </p>
              {holidayName ? (
                <p className="mt-2 text-center text-[13px] font-semibold leading-snug text-rose-500">
                  {holidayName}
                </p>
              ) : (
                <div className="mt-1 space-y-1">
                  {dayEvents.slice(0, 3).map((event) => (
                    <Link
                      key={event.code}
                      href={`/stock/${event.code}`}
                      className="block truncate rounded bg-blue-50 px-1.5 py-0.5 text-[11px] font-medium text-blue-700 hover:bg-blue-100"
                    >
                      {event.name}
                    </Link>
                  ))}
                  {dayEvents.length > 3 && (
                    <p className="px-1 text-[10px] text-gray-400">+{dayEvents.length - 3}개 더</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
