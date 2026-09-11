"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Globe, { type GlobeInstance } from "globe.gl";
import { AmbientLight, DirectionalLight, MeshPhongMaterial, Color } from "three";
import borderData from "@/data/trade/borders.json";
import { Minus, Plus, RotateCcw, Pause, Play, Maximize, Minimize, Map, Globe2, Sun, Moon, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { countryInfo, signed, usdText, kgText, type summarizeTrade } from "@/lib/trade";
import { exportHeightRatio, referenceBarColor, flatBarColor } from "./map-style";

const FlatTradeMap = dynamic(() => import("./FlatTradeMap"), { ssr: false });

type Country = ReturnType<typeof summarizeTrade>["countries"][number];
type Located = Country & { lat: number; lon: number };
type Feature = { id: string; geometry: { type: string; coordinates: unknown }; properties?: { name?: string } };
type Props = { countries: Country[]; selected: string; onSelect: (code: string) => void; region?: string };
const ORIGIN = { lat: 36.5, lon: 127.8, code: "KR", name: "대한민국" };
const features = borderData as unknown as Feature[];

export default function TradeMap({ countries, selected, onSelect, region = "all" }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const globeRef = useRef<GlobeInstance | null>(null);
  const flatApi = useRef<{ zoom: (factor: number) => void; reset: () => void } | null>(null);
  const callbacks = useRef({ countries, onSelect, selected });
  const [rotating, setRotating] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [flat, setFlat] = useState(false);
  const [flatLoaded, setFlatLoaded] = useState(false);
  const [themes, setThemes] = useState({ globe: true, flat: false });
  const dark = flat ? themes.flat : themes.globe;
  const toggleTheme = () => setThemes(t => ({ ...t, [flat ? "flat" : "globe"]: !dark }));
  const [showList, setShowList] = useState(true);
  const [focusRequest, setFocusRequest] = useState(0);
  useEffect(() => { callbacks.current = { countries, onSelect, selected }; }, [countries, onSelect, selected]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let globe: GlobeInstance | undefined;
    let resize: ResizeObserver | undefined;
    let alive = true;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const pick = (code: string) => {
      if (callbacks.current.countries.some(c => c.code === code)) {
        callbacks.current.onSelect(code);
        setRotating(false);
      }
    };
    try {
      globe = new Globe(element, { rendererConfig: { antialias: true, alpha: true, preserveDrawingBuffer: true }, animateIn: false });
      const g = globe;
      globeRef.current = g;
      g.onZoom(pov => {
        element.dataset.longitude = pov.lng.toFixed(4);
        element.dataset.latitude = pov.lat.toFixed(4);
        element.dataset.altitude = pov.altitude.toFixed(4);
      });
      g.width(element.clientWidth).height(element.clientHeight).backgroundColor("rgba(0,0,0,0)")
        .globeImageUrl("/globe/earth-night.jpg").bumpImageUrl("/globe/topology.png")
        .atmosphereColor("#3b82f6").atmosphereAltitude(0.18)
        .polygonsData(features).polygonAltitude(0.003)
        .polygonCapColor(() => "rgba(0,0,0,0)")
        .polygonSideColor(() => "rgba(0,0,0,0)").polygonStrokeColor(() => "rgba(120,150,200,0.15)")
        .polygonLabel(() => "").pointLabel(() => "").arcLabel(() => "")
        .onPolygonHover(f => setHovered(f ? (f as Feature).id : null))
        .onPolygonClick(f => pick((f as Feature).id))
        .onPointHover(p => setHovered(p ? (p as Located).code : null))
        .onPointClick(p => pick((p as Located).code))
        .pointLat("lat").pointLng("lon").pointResolution(24)
        .labelsData([ORIGIN]).labelLat("lat").labelLng("lon").labelText("code")
        .labelSize(1.5).labelDotRadius(0.18).labelColor(() => "#ffffff").labelAltitude(0.04);
      const material = g.globeMaterial() as MeshPhongMaterial;
      material.specular = new Color("#222222");
      material.bumpScale = 1;
      material.shininess = 5;
      const sunlight = new DirectionalLight(0xffffff, 0.6);
      sunlight.position.set(-250, 200, 300);
      const fill = new DirectionalLight(0xdbeaff, 0.6);
      fill.position.set(200, -100, -150);
      g.lights([new AmbientLight(0xffffff, 1.3), sunlight, fill]);
      const controls = g.controls();
      controls.autoRotate = !reduced; controls.autoRotateSpeed = 1.14;
      controls.enableDamping = true; controls.dampingFactor = 0.075;
      controls.enableZoom = true; controls.enablePan = false; controls.rotateSpeed = 0.65;
      controls.minDistance = 125; controls.maxDistance = 1000;
      const onStart = () => { if (alive) setRotating(false); };
      controls.addEventListener("start", onStart);
      const altitude = () => wrap.current?.classList.contains("globe-expanded") ? Math.max(2.6, 2.8 / (element.clientWidth / element.clientHeight)) : Math.max(1.8, 2.2 / (element.clientWidth / element.clientHeight));
      g.pointOfView({ lat: 26, lng: 115, altitude: altitude() }, 0);
      resize = new ResizeObserver(() => {
        if (element.clientWidth && element.clientHeight) {
          g.width(element.clientWidth).height(element.clientHeight);
          if (g.pointOfView().altitude > 1.4) g.pointOfView({ altitude: altitude() }, 0);
        }
      });
      resize.observe(element);
      g.onGlobeReady(() => { if (alive) element.dataset.ready = "true"; });
      if (reduced) queueMicrotask(() => { if (alive) setRotating(false); });
      return () => {
        alive = false; resize?.disconnect(); controls.removeEventListener("start", onStart);
        g.pauseAnimation(); g._destructor(); g.renderer().dispose(); globeRef.current = null; delete element.dataset.ready;
      };
    } catch {
      queueMicrotask(() => { if (alive) setFailed(true); });
      globe?._destructor();
    }
    return () => { alive = false; resize?.disconnect(); };
  }, []);

  useEffect(() => {
    const g = globeRef.current;
    if (!g) return;
    const located = countries.filter((c): c is Located => c.lat !== null && c.lon !== null && c.usd > 0 && (region === "all" || c.region === region));
    const max = Math.max(1, ...located.map(c => c.usd));
    g.pointsData(located).pointAltitude(p => exportHeightRatio((p as Located).usd, max) * 0.55)
      .pointRadius(0.72)
      .pointColor(p => referenceBarColor((p as Located).usd, max));
    g.polygonCapColor(f => {
      const id = (f as Feature).id, c = located.find(c => c.code === id);
      if (id === selected && c) return "rgba(200,255,0,0.16)";
      return "rgba(0,0,0,0)";
    });
    const c = located.find(c => c.code === selected);
    if (c) {
      g.controls().autoRotate = false;
      queueMicrotask(() => setRotating(false));
      g.pointOfView({ lat: c.lat, lng: c.lon, altitude: Math.max(expanded ? 2.6 : 1.9, (expanded ? 2.8 : 2.2) / ((host.current?.clientWidth ?? 600) / (host.current?.clientHeight ?? 500))) }, 950);
      g.labelsData([ORIGIN, c]);
    } else g.labelsData([ORIGIN]);
    if (expanded && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const timer = window.setTimeout(() => setRotating(true), 1200);
      return () => window.clearTimeout(timer);
    }
  }, [countries, selected, region, focusRequest, expanded]);

  useEffect(() => {
    const g = globeRef.current;
    if (!g) return;
    g.controls().autoRotate = rotating && !flat;
    g.controls().enabled = !flat;
    if (flat) g.pauseAnimation(); else g.resumeAnimation();
  }, [rotating, flat]);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", close);
    return () => { document.body.style.overflow = previous; window.removeEventListener("keydown", close); };
  }, [expanded]);
  useEffect(() => {
    const change = () => { if (!document.fullscreenElement) setExpanded(false); };
    document.addEventListener("fullscreenchange", change);
    return () => document.removeEventListener("fullscreenchange", change);
  }, []);
  const detailCode = expanded && selected !== "all" ? selected : hovered ?? (selected !== "all" ? selected : null);
  const hoveredInfo = detailCode ? countryInfo(detailCode) : null;
  const hoveredData = countries.find(c => c.code === detailCode);
  const toggleExpanded = async () => {
    if (expanded) {
      if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
      setExpanded(false);
    } else {
      setExpanded(true); setFlat(false);
      setRotating(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
      await wrap.current?.requestFullscreen?.().catch(() => {});
    }
  };
  const reset = () => {
    if (flat) { flatApi.current?.reset(); onSelect("all"); return; }
    const g = globeRef.current, el = host.current;
    if (g && el) g.pointOfView({ lat: 26, lng: 115, altitude: Math.max(1.8, 2.2 / (el.clientWidth / el.clientHeight)) }, 700);
    onSelect("all");
  };
  const zoom = (factor: number) => {
    if (flat) { flatApi.current?.zoom(factor); return; }
    const g = globeRef.current;
    if (g) g.pointOfView({ altitude: Math.min(6, Math.max(0.3, g.pointOfView().altitude / factor)) }, 350);
  };
  return <div ref={wrap} data-view={flat ? "flat" : "globe"} data-theme={dark ? "dark" : "light"} className={`trade-map-wrap globe-wrap${flat ? " is-flat" : ""}${expanded ? " globe-expanded" : ""}${dark ? " map-dark" : ""}`}>
    <div ref={host} className="trade-map globe-layer" aria-hidden={flat} aria-label="드래그로 회전하고 휠 또는 두 손가락으로 확대하는 수출 지구본" />
    {flatLoaded && <div className="flat-layer" aria-hidden={!flat}><FlatTradeMap countries={countries} selected={selected} region={region} active={flat} dark={dark} focusRequest={focusRequest} onSelect={onSelect} onHover={setHovered} apiRef={flatApi} /></div>}
    <div className="map-controls">
      <button aria-label={flat ? "지구본으로 보기" : "평면 지도로 보기"} aria-pressed={flat} title={flat ? "지구본으로 보기" : "평면 지도로 보기"} onClick={() => { setFlatLoaded(true); setHovered(null); setFlat(v => !v); }}>{flat ? <Globe2 size={16} /> : <Map size={16} />}</button>
      <button aria-label={dark ? "밝은 지도" : "어두운 지도"} title={dark ? "밝은 지도" : "어두운 지도"} onClick={toggleTheme}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
      {expanded && <button aria-label={showList ? "국가 목록 닫기" : "국가 목록 열기"} title={showList ? "국가 목록 닫기" : "국가 목록 열기"} onClick={() => setShowList(v => !v)}>{showList ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}</button>}
      <button disabled={flat} aria-label={rotating ? "자동 회전 정지" : "자동 회전 시작"} title={flat ? "지구본에서 자동 회전" : rotating ? "자동 회전 정지" : "자동 회전 시작"} onClick={() => setRotating(v => !v)}>{rotating ? <Pause size={16} /> : <Play size={16} />}</button>
      <button aria-label="지도 확대" title="확대" onClick={() => zoom(1.33)}><Plus size={16} /></button>
      <button aria-label="지도 축소" title="축소" onClick={() => zoom(0.77)}><Minus size={16} /></button>
      <button aria-label="지도 초기화" title="한국 중심으로" onClick={reset}><RotateCcw size={15} /></button>
      <button aria-label={expanded ? "지도 화면 축소" : "지도 화면 확대"} title={expanded ? "화면 축소" : "화면 확대"} onClick={toggleExpanded}>{expanded ? <Minimize size={16} /> : <Maximize size={16} />}</button>
    </div>
    <aside className={`map-detail-column${expanded && showList ? " with-list" : ""}`}>
      {hoveredInfo && hoveredData && <div className="globe-tooltip"><strong>{hoveredInfo.name}</strong><span>{usdText(hoveredData.usd)}</span><span>{kgText(hoveredData.kg)} · {hoveredData.usdPerKg === null ? "kg당 자료 없음" : `${Math.round(hoveredData.usdPerKg).toLocaleString("ko-KR")} 달러/kg`}</span><span>전년 대비 {signed(hoveredData.change)}</span></div>}
      {expanded && showList && <div className="map-country-list" aria-label="전체화면 국가 목록"><strong>국가별 수출</strong><div>{countries.filter(c => c.usd > 0 && (region === "all" || c.region === region)).map(c => <button key={c.code} aria-pressed={selected === c.code} onClick={() => { onSelect(c.code); setFocusRequest(v => v + 1); setHovered(null); }}><span>{c.name}</span><span>{usdText(c.usd)}</span></button>)}</div></div>}
    </aside>
    <div className="map-legend"><span><i style={{ background: flat ? flatBarColor(0, 1, dark) : referenceBarColor(0, 1) }} />수출액 낮음</span><span><i style={{ background: flat ? flatBarColor(1, 1, dark) : referenceBarColor(1, 1) }} />높음</span><span title="수출액의 제곱근에 비례하며 작은 수출국에도 최소 높이를 적용합니다. 정확한 금액과 비중은 국가별 상세 및 표에 표시됩니다.">높이: 제곱근 보정 · 최소 높이 적용</span></div>
    {failed && <div className="map-loading">3D 지도를 표시할 수 없습니다. 아래 국가별 표에서 확인할 수 있습니다.</div>}
  </div>;
}
