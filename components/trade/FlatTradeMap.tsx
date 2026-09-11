"use client";

import { useEffect, useRef } from "react";
import {
  AmbientLight, CylinderGeometry, BufferGeometry, Color, DirectionalLight, DoubleSide,
  Group, LineBasicMaterial, LineLoop, Mesh, MeshBasicMaterial, MeshLambertMaterial,
  OrthographicCamera, Path, Raycaster, Scene, Shape, ShapeGeometry, Vector2, Vector3, WebGLRenderer, MOUSE, TOUCH,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import borderData from "@/data/trade/borders.json";
import { type summarizeTrade } from "@/lib/trade";
import { exportHeightRatio, inactiveCountryColor, flatBarColor } from "./map-style";

type Country = ReturnType<typeof summarizeTrade>["countries"][number];
type Props = {
  countries: Country[]; selected: string; region: string; active: boolean; dark: boolean; focusRequest: number;
  onSelect: (code: string) => void; onHover: (code: string | null) => void;
  apiRef: React.RefObject<{ zoom: (factor: number) => void; reset: () => void } | null>;
};
type Polygon = number[][][];

export default function FlatTradeMap({ countries, selected, region, active, dark, focusRequest, onSelect, onHover, apiRef }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const latest = useRef({ countries, selected, region, active, dark, focusRequest, onSelect, onHover });
  const update = useRef<(() => void) | null>(null);
  useEffect(() => { latest.current = { countries, selected, region, active, dark, focusRequest, onSelect, onHover }; update.current?.(); }, [countries, selected, region, active, dark, focusRequest, onSelect, onHover]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const scene = new Scene();
    const camera = new OrthographicCamera(-210, 210, 110, -110, 0.1, 2000);
    let renderer: WebGLRenderer;
    try { renderer = new WebGLRenderer({ alpha: true, antialias: true, preserveDrawingBuffer: true }); }
    catch { el.dataset.failed = "true"; return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableRotate = false;
    controls.mouseButtons.LEFT = MOUSE.PAN;
    controls.touches.ONE = TOUCH.PAN;
    controls.touches.TWO = TOUCH.DOLLY_PAN;
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.minZoom = 0.7;
    controls.maxZoom = 8;
    controls.screenSpacePanning = true;
    // Map longitude/latitude to the X/Z plane; use the same visibility correction as the globe.
    const land = new Group();
    const bars = new Group();
    scene.add(land, bars, new AmbientLight(0xffffff, 2));
    const light = new DirectionalLight(0xffffff, 2);
    light.position.set(-100, 300, 200);
    scene.add(light);
    const borderMaterial = new LineBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.85 });
    for (const feature of borderData) {
      const polygons: Polygon[] = feature.geometry.type === "Polygon"
        ? [feature.geometry.coordinates as Polygon] : feature.geometry.coordinates as Polygon[];
      for (const rings of polygons) {
        if (!rings[0]?.length) continue;
        const shape = new Shape(rings[0].map(([x, y]) => new Vector2(x, y)));
        for (const hole of rings.slice(1)) shape.holes.push(new Path(hole.map(([x, y]) => new Vector2(x, y))));
        const geometry = new ShapeGeometry(shape);
        geometry.rotateX(-Math.PI / 2);
        const mesh = new Mesh(geometry, new MeshBasicMaterial({ color: inactiveCountryColor, side: DoubleSide, transparent: true }));
        mesh.userData.code = feature.id;
        land.add(mesh);
        for (const ring of rings) {
          const line = new LineLoop(new BufferGeometry().setFromPoints(ring.map(([x, y]) => new Vector3(x, 0.12, -y))), borderMaterial);
          land.add(line);
        }
      }
    }
    let revealAt = performance.now();
    let wasActive = false;
    let lastData: Country[] | undefined;
    let lastRegion = "";
    let lastDark: boolean | undefined;
    let lastFocus = "";
    let travel: { start: number; from: Vector3; to: Vector3 } | null = null;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const reset = () => {
      travel = null;
      camera.position.set(0, 300, 155);
      controls.target.set(0, 0, -10);
      camera.zoom = 1;
      camera.updateProjectionMatrix();
      controls.update();
    };
    reset();
    apiRef.current = {
      zoom: factor => { camera.zoom = Math.min(8, Math.max(0.7, camera.zoom * factor)); camera.updateProjectionMatrix(); }, reset,
    };
    const sync = () => {
      const state = latest.current;
      borderMaterial.color.set(state.dark ? "#78949b" : "#ffffff");
      borderMaterial.opacity = state.dark ? 0.45 : 0.9;
      if (state.active && !wasActive) revealAt = performance.now();
      wasActive = state.active;
      const data = new Map(state.countries.filter(c => c.usd > 0 && (state.region === "all" || c.region === state.region)).map(c => [c.code, c]));
      for (const object of land.children) {
        if (!(object instanceof Mesh)) continue;
        const code = object.userData.code as string;
        const c = data.get(code);
        (object.material as MeshBasicMaterial).color.set(code === "KR" ? (state.dark ? "#899572" : "#889ca3") : c ? (state.dark ? "#365962" : "#bfd5d7") : (state.dark ? "#25363d" : "#e1e7e9"));
        (object.material as MeshBasicMaterial).opacity = 1;
        if (code === state.selected) (object.material as MeshBasicMaterial).color.lerp(new Color("#172b46"), 0.3);
      }
      if (lastData !== state.countries || lastRegion !== state.region || lastDark !== state.dark) {
        for (const object of [...bars.children]) {
          const mesh = object as Mesh<CylinderGeometry, MeshLambertMaterial>;
          mesh.geometry.dispose(); mesh.material.dispose(); bars.remove(mesh);
        }
        const max = Math.max(1, ...Array.from(data.values()).map(c => c.usd));
        for (const c of data.values()) {
          if (c.lat === null || c.lon === null) continue;
          const height = exportHeightRatio(c.usd, max) * 90;
          const mesh = new Mesh(new CylinderGeometry(1.65, 1.65, 1, 24), new MeshLambertMaterial({ color: flatBarColor(c.usd, max, state.dark) }));
          mesh.position.set(c.lon, height / 2, -c.lat);
          mesh.userData = { code: c.code, height };
          bars.add(mesh);
        }
        el.dataset.barCount = String(bars.children.length);
        lastData = state.countries; lastRegion = state.region; lastDark = state.dark;
        revealAt = performance.now();
      }
      controls.enabled = state.active;
      const focus = `${state.selected}:${state.focusRequest}:${state.active}`;
      if (state.active && lastFocus !== focus) {
        const c = state.countries.find(c => c.code === state.selected);
        if (c && c.lon !== null && c.lat !== null) travel = { start: performance.now(), from: controls.target.clone(), to: new Vector3(c.lon, 0, -c.lat) };
      }
      lastFocus = focus;
    };
    update.current = sync;
    sync();
    const resize = new ResizeObserver(() => {
      const width = el.clientWidth, height = el.clientHeight;
      if (!width || !height) return;
      const aspect = width / height;
      const halfHeight = Math.max(118, 215 / aspect);
      camera.left = -halfHeight * aspect; camera.right = halfHeight * aspect;
      camera.top = halfHeight; camera.bottom = -halfHeight;
      camera.updateProjectionMatrix(); renderer.setSize(width, height);
    });
    resize.observe(el);
    const raycaster = new Raycaster();
    const pointer = new Vector2();
    const hit = (event: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      return raycaster.intersectObjects([...bars.children, ...land.children.filter(o => o instanceof Mesh)], false)[0]?.object.userData.code as string | undefined;
    };
    let start: { x: number; y: number } | null = null;
    const down = (e: PointerEvent) => { travel = null; start = { x: e.clientX, y: e.clientY }; };
    const move = (e: PointerEvent) => { if (latest.current.active) latest.current.onHover(hit(e) ?? null); };
    const up = (e: PointerEvent) => {
      if (start && Math.hypot(e.clientX - start.x, e.clientY - start.y) < 5) {
        const code = hit(e);
        if (code && latest.current.countries.some(c => c.code === code)) latest.current.onSelect(code);
      }
      start = null;
    };
    const leave = () => latest.current.onHover(null);
    el.addEventListener("pointerdown", down); el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up); el.addEventListener("pointerleave", leave);
    let frame = 0;
    const render = () => {
      frame = requestAnimationFrame(render);
      if (!latest.current.active) return;
      const progress = reduced ? 1 : Math.min(1, (performance.now() - revealAt) / 1000);
      const eased = 1 - Math.pow(1 - progress, 3);
      for (const bar of bars.children) {
        const height = Math.max(0.015, bar.userData.height * eased);
        bar.scale.y = height; bar.position.y = height / 2;
      }
      if (travel) {
        const t = reduced ? 1 : Math.min(1, (performance.now() - travel.start) / 950);
        const next = travel.from.clone().lerp(travel.to, 1 - (1 - t) ** 3);
        camera.position.add(next.clone().sub(controls.target)); controls.target.copy(next);
        if (t === 1) travel = null;
      }
      controls.update(); renderer.render(scene, camera);
      el.dataset.ready = "true"; el.dataset.zoom = camera.zoom.toFixed(3); el.dataset.progress = progress.toFixed(3);
      el.dataset.pan = controls.target.x.toFixed(3);
    };
    render();
    return () => {
      cancelAnimationFrame(frame); resize.disconnect(); controls.dispose();
      el.removeEventListener("pointerdown", down); el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up); el.removeEventListener("pointerleave", leave);
      scene.traverse(object => {
        if (object instanceof Mesh || object instanceof LineLoop) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => material.dispose());
        }
      });
      renderer.dispose(); renderer.domElement.remove(); update.current = null; apiRef.current = null;
    };
  }, [apiRef]);
  return <div ref={host} className="trade-flat-map" aria-label="국가별 수출 막대가 표시된 평면 지도" />;
}
