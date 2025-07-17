/* Topology.jsx — unknown hidden by default + stable reload flash */
import React, { useEffect, useState, useMemo, useCallback, useRef } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import SpriteText from 'three-spritetext';
import {SigmaContainer,useLoadGraph,useRegisterEvents,useSigma,useSetSettings} from "@react-sigma/core";
import Graph from "graphology";
import FA2 from "graphology-layout-forceatlas2";
import { Loader2, Network } from "lucide-react";
import { useTopologyStore } from "@/store/useTopologyStore";
import { useNavigate } from "react-router-dom";

/* ------------------------------------------------------------------ */
/* 1. Palette & helpers                                               */
/* ------------------------------------------------------------------ */
const colorByType = {
  gateway : "#1d4ed8",
  extender: "#ca0ff0",
  sensor  : "#f97316",
  unknown : "#fd0000",
};

// palette de couleur selon quality
const qualityColor = {
  good:   "#16a34a",
  medium: "#f97316",
  poor:   "#dc2626",
  //unknown:"#999999",
};

const sizeByType = { gateway: 20, extender: 14, sensor: 8, unknown: 8 };
const kinds = [
  { key: "gateway",  label: "Gateways"  },
  { key: "extender", label: "Extenders" },
  { key: "sensor",   label: "Sensors"   },
  { key: "unknown",  label: "Unknown"   },
];

/* position pseudo-déterministe depuis l’ID (cercle unité) */
function hashPos(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 360;
  const a = (h / 360) * 2 * Math.PI;
  return { x: Math.cos(a), y: Math.sin(a) };
}

/* ------------------------------------------------------------------ */
/* 2. Construction du graphe                                          */
/* ------------------------------------------------------------------ */
function buildGraph(data, { visibleKinds }) {
  const graph = new Graph({ type: "undirected" });
  //const colorByKindEdge = { parent: "#60a5fa", neighbor: "#cbd5e1" };
  const originalIds = new Set(data.nodes.map((n) => String(n.id)));

  /* nœuds ----------------------------------------------------------- */
  data.nodes.forEach((n) => {
    if (!visibleKinds[n.type]) return;
    const { x, y } = hashPos(n.id);
    graph.addNode(String(n.id), {
      label: String(n.id),
      kind : n.type,
      x, y,
      color: colorByType[n.type],
      size : sizeByType[n.type],
    });
    
  });

  /* arêtes ---------------------------------------------------------- */
  data.links.forEach((e, i) => {
    const s = String(e.source);
    const t = String(e.target);

    /* si une extrémité manquante = unknown, ne la crée que si visible */
    [s, t].forEach((id) => {
      if (!graph.hasNode(id) && visibleKinds.unknown && !originalIds.has(id)) {
        const { x, y } = hashPos(id);
        graph.addNode(id, {
          label: id,
          kind : "unknown",
          x, y,
          color: colorByType.unknown,
          size : sizeByType.unknown,
        });
      }
    });

    /* trace l’arête seulement si les deux nœuds existent */
    if (graph.hasNode(s) && graph.hasNode(t)) {
      if (!graph.hasEdge(s, t) && !graph.hasEdge(t, s))
       graph.addEdge(s, t, {
         key: `e${i}`,
         color: qualityColor[e.quality] || qualityColor.unknown,
         metrics: e.metrics
       });
    }
  });

  /* layout stable --------------------------------------------------- */
  const settings = FA2.inferSettings(graph);
  FA2.assign(graph, { settings, iterations: 300 });
  return graph;
}

/* ------------------------------------------------------------------ */
/* 3. Loader Sigma + tooltips                                         */
/* ------------------------------------------------------------------ */
function GraphLoader({ data, filters }) {
  const loadGraph      = useLoadGraph();
  const sigma          = useSigma();          // ← pour exposer l’instance
  const registerEvents = useRegisterEvents();
  useSetSettings({ labelRenderedSizeThreshold: 12 });

  const graph = useMemo(() => buildGraph(data, filters), [data, filters]);

  useEffect(() => {
    loadGraph(graph);
    window.sigmaInstance = sigma;             // ← exposé pour le bouton Reload
  }, [graph, loadGraph, sigma]);

  /* tooltips -------------------------------------------------------- */
  useEffect(() => {
    const tip = document.createElement("div");
    tip.className =
      "pointer-events-none fixed z-50 rounded bg-gray-900 text-white text-xs px-2 py-1 opacity-0 transition-opacity";
    document.body.appendChild(tip);

    const show = (e) => {
      const node = e.node;
      if (!node) return;
      const attrs = graph.getNodeAttributes(node);
      tip.textContent = `${attrs.kind.toUpperCase()} — ${node}`;
      tip.style.left  = `${e.event.clientX + 8}px`;
      tip.style.top   = `${e.event.clientY + 8}px`;
      tip.style.opacity = "1";
    };
    const hide = () => (tip.style.opacity = "0");
    registerEvents({ enterNode: show, leaveNode: hide });
    return () => document.body.removeChild(tip);
  }, [graph, registerEvents]);

  return null;
}

/* ------------------------------------------------------------------ */
/* 4. Composant principal                                             */
/* ------------------------------------------------------------------ */
export default function Topology() {
  const qsCompany    = new URLSearchParams(window.location.search).get("company") || "";
  const storeCompany = useTopologyStore.getState().company || "";
  const [company, setCompany] = useState(qsCompany || storeCompany);
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  /* unknown masqué par défaut ↓ */
  const [visibleKinds, setVisibleKinds] = useState({
    gateway : true,
    extender: true,
    sensor  : true,
    unknown : false,
  });
  const [viewMode, setViewMode] = useState("2d");
  const fg3DRef = useRef();  
  // Gestionnaire custom de la molette
    const handleWheel3D = (e) => {
    e.stopPropagation(); // empêcher tout autre listener deグ
    const fg = fg3DRef.current;
    if (!fg) return;

    // 2) Raycast sous la souris
    const renderer = fg.renderer();
    const camera   = fg.camera();
    const scene    = fg.scene();

    // Normaliser coords souris [-1,1]
    const rect = renderer.domElement.getBoundingClientRect();
    const mx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const my = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    const mouse = new THREE.Vector2(mx, my);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, camera);
    const hits = raycaster.intersectObjects(scene.children, true);
    // point 3D : soit le premier hit, soit le centre (0,0,0)
    const focusPoint = hits.length ? hits[0].point : new THREE.Vector3(0, 0, 0);

    // 3) Calcul du zoom : on déplace la caméra le long du vecteur
    const distance = camera.position.distanceTo(focusPoint);
    // facteur <1 = zoom in, >1 = zoom out
    const factor = e.deltaY < 0 ? 0.9 : 1.1;

    const dir = camera.position.clone().sub(focusPoint).normalize();
    const newPos = focusPoint.clone().add(dir.multiplyScalar(distance * factor));

    // 4) Animation
    fg.cameraPosition(newPos, focusPoint, 300);
    };
  const navigate    = useNavigate();
  const setTopology = useTopologyStore((s) => s.setTopology);

  /* fetch ----------------------------------------------------------- */
  const fetchData = useCallback(() => {
    if (!company) return;
    const cache = useTopologyStore.getState();
    if (cache.data && cache.company === company) {
      setData(cache.data);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`/api/topology/${company}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((g) => {
        const graph = g.graph || g;
        setData(graph);
        setTopology(company, graph);
      })
      .catch((err) => setError(err.toString()))
      .finally(() => setLoading(false));
  }, [company, setTopology]);
  useEffect(fetchData, [fetchData]);

  /* compte par type ------------------------------------------------- */
  const counts = useMemo(() => {
    const c = { gateway: 0, extender: 0, sensor: 0, unknown: 0 };
    if (data) data.nodes.forEach((n) => { c[n.type]++; });
    return c;
  }, [data]);

  /* données 3D ------------------------------------------------------ */
  const graphData3D = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const typeMap = new Map(data.nodes.map((n) => [n.id, n.type]));
    const nodes3d = data.nodes
      .filter((n) => visibleKinds[n.type])
      .map((n) => ({
        id: n.id,
        label: n.id,
        kind: n.type,
        color: colorByType[n.type],
        val: sizeByType[n.type],
      }));
    const links3d = data.links
      .filter(
        (l) =>
          visibleKinds[typeMap.get(l.source)] &&
          visibleKinds[typeMap.get(l.target)]
      )
      .map((l) => ({
        source: l.source,
        target: l.target,
        quality: l.quality,
      }));
    return { nodes: nodes3d, links: links3d };
  }, [data, visibleKinds]);

  /* rendu ----------------------------------------------------------- */
  if (!company)
    return (
      <p className="p-4">
        Add <code>?company=&lt;slug&gt;</code> in the URL.
      </p>
    );

  return (
    <div className="flex h-screen w-full gap-4 p-4 overflow-hidden">
      {/* -------- panneau latéral -------- */}
      <div className="w-72 shrink-0 overflow-y-auto rounded bg-white shadow p-4 space-y-6">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <Network size={18} /> Topology
        </div>

        {/* company input */}
        <div className="space-y-1 text-sm">
          <label className="font-medium">Company DB</label>
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 focus:outline-none focus:ring"
          />
          <button
            onClick={async() => {
              navigate(`/topology?company=${encodeURIComponent(company)}`);
              await fetchData();                 // ← attend la mise à jour
              const sigma = window.sigmaInstance;
              if (sigma) {
                const cam = sigma.getCamera();
                cam.animatedUnzoom({ duration: 300 });
                setTimeout(() => cam.animatedReset({ duration: 600 }), 300);
              }

              
                // pour 3D, on force le rafraîchissement du graphe + recentrage auto
                if (viewMode === "3d" && fg3DRef.current) {
                    fg3DRef.current.cameraPosition(
                        { x: 0, y: 0, z: 300 }, // position de la caméra
                        { x: 0, y: 0, z: 0 },   // point de focus
                        300                     // durée de l'animation
                    );
                }

            }}
            className="mt-1 w-full rounded bg-blue-600 py-1 font-medium text-white hover:bg-blue-700"
          >
            Reload
          </button>
        </div>

        {/* --- Mode d’affichage ------------------------------------ */}
        <div className="flex items-center space-x-3 text-sm">
            <span className="font-medium">2D</span>
            <label className="relative inline-flex items-center cursor-pointer">
                <input
                type="checkbox"
                className="sr-only peer"
                checked={viewMode === "3d"}
                onChange={() =>
                    setViewMode((m) => (m === "2d" ? "3d" : "2d"))
                }
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:bg-blue-600 transition-colors" />
                <div className="absolute left-1 top-1 bg-white w-4 h-4 rounded-full peer-checked:translate-x-5 transition-transform" />
            </label>
            <span className="font-medium">3D</span>
        </div>

        {/* résumé + filtres */}
        <div className="space-y-2 text-sm">
          {kinds.map(({ key, label }) => (
            <button
              key={key}
              onClick={() =>
                setVisibleKinds((v) => ({ ...v, [key]: !v[key] }))
              }
              className={`flex items-center w-full gap-2 rounded px-2 py-1 transition
                ${visibleKinds[key] ? "bg-gray-200" : "bg-gray-100 opacity-40"}`}
            >
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ background: colorByType[key] }}
              />
              <span className="flex-1">{label}</span>
              <span className="font-mono">{counts[key]}</span>
            </button>
          ))}
        </div>
      </div>
      

      {/* -------- zone graphe -------- */}
      <div className="relative flex-1 h-full">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70">
            <Loader2 className="animate-spin text-blue-600" size={32} />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 text-red-600">
            {error}
          </div>
        )}
        {data && !loading && !error && (
            viewMode === "2d" ? (
                <SigmaContainer
                    className="h-full w-full rounded bg-white shadow"
                    style={{ height: "100%", width: "100%" }}
                    settings={{ allowInvalidContainer: true }}
                >
                    <GraphLoader data={data} filters={{ visibleKinds }} />
                </SigmaContainer>
            ) : (
                <div className="h-full w-full" onWheel={(e) => e.stopPropagation()}>
                
                <ForceGraph3D
                    ref={fg3DRef}
                    graphData={graphData3D}
                
                    //sphères lisses
                    /*
                    nodeThreeObject={node => {
                        const sphere = new THREE.Mesh(
                        new THREE.SphereGeometry(sizeByType[node.kind] * 0.5, 100, 100),
                        new THREE.MeshLambertMaterial({ color: node.color })
                        );
                        // ② crée le label sprite
                        const label = new SpriteText(node.id);
                        label.color = '#000';               // couleur du texte
                        label.textHeight = 1.2;             // taille du sprite
                        label.position.set(0, sizeByType[node.kind] * 0.15, 5);
                        // on le place juste au-dessus de la sphère

                        // ③ on regroupe sphère + label dans un Object3D
                        const obj = new THREE.Group();
                        obj.add(sphere);
                        obj.add(label);
                        return obj;
                    }}*/

                    nodeThreeObject={node => {
                        const radius = (sizeByType[node.kind] || 1) * 0.2;

                        //  Crée la sphère
                        const sphereGeom = new THREE.SphereGeometry(radius, 100, 100);
                        const sphereMat  = new THREE.MeshLambertMaterial({ color: node.color });
                        const sphere     = new THREE.Mesh(sphereGeom, sphereMat);

                        //  Crée le sprite-texte
                        const label = new SpriteText(node.id);
                        label.textHeight = radius * 0.8;
                        label.color      = "#000000ff"; // couleur du texte
                        label.position.set(0, radius + label.textHeight / 2, 0);

                        //  Ajuste le label pour qu’il soit au-dessus de la sphère
                        label.material.depthTest  = false;
                        label.material.depthWrite = false;
                        label.renderOrder         = 999;

                        //  Regroupe sphère + label dans un groupe
                        const group = new THREE.Group();
                        group.add(sphere);
                        group.add(label);
                        return group;
                    }}
                
                    // particules 
                    linkDirectionalParticles={2}               // nombre de particules
                    linkDirectionalParticleSpeed={0.002}        // vitesse
                    linkDirectionalParticleWidth={0.7}         // épaisseur des particules
                    linkDirectionalParticleColor={link => qualityColor[link.quality] ?? qualityColor.unknown}

                    

                    //épaisseur des liens   
                    linkWidth={link => (link.kind === "parent" ? 0.5 : 0.5)}
                    linkCurveStrength={0.1}
                    
                    

                    // camera
                    enableNodeDrag={true}
                    controlType="orbit"
                    enableZoomPanInteraction={true}
                    enablePointerInteraction={true}
                    enableAutoRotate={true}
                    autoRotateSpeed={0.2}
                    d3AlphaDecay={0.02} 

                    linkThreeObjectExtend={true}                    
                    nodeColor={node => node.color}
                    linkColor={link => qualityColor[link.quality] ?? qualityColor.unknown}
                    backgroundColor="#ffffff"
                    nodeC
                    
                    height={window.innerHeight - 32}   
                    width={window.innerWidth - 300}    
                />
            </div>
            )
        )}
      </div>
    </div>
  );
} 