<script lang="ts">
  import { onMount, tick } from 'svelte';
  import axios from 'axios';

  const API_URL = 'http://localhost:9100';

  // ── Types ──────────────────────────────────────────────────────────────────
  type Point     = [number, number];
  type Shape     = { label: string; points: [Point, Point]; shape_type: 'rectangle'; flags: Record<string, unknown>; group_id: string | null; };
  type MoveRecord= { dest_img: string; dest_json: string; original_json: string; original_img: string; };
  type Handle    = 'tl'|'tc'|'tr'|'ml'|'mr'|'bl'|'bc'|'br'|'body';

  // ── Persisted UI prefs (all saved to localStorage) ─────────────────────────
  const STORE = {
    get:    (k: string, fb: string)  => { try { return localStorage.getItem('bbox-' + k) ?? fb; } catch { return fb; } },
    set:    (k: string, v: string)   => { try { localStorage.setItem('bbox-' + k, v); } catch {} },
    getNum: (k: string, fb: number)  => { const v = parseFloat(STORE.get(k, String(fb))); return isNaN(v) ? fb : v; },
  };

  // ── State — all UI prefs pre-loaded from localStorage ─────────────────────
  let imageDirectory     = $state(STORE.get('image-directory', ''));
  let moveDestination    = $state(STORE.get('move-destination', ''));
  let darkMode           = $state(STORE.get('theme', 'dark') === 'dark');
  let interactionMode    = $state<'draw'|'edit'>(STORE.get('mode', 'draw') as 'draw'|'edit');
  let showLabels         = $state(STORE.get('show-labels', 'true') === 'true');
  let sidebarWidth       = $state(STORE.getNum('sidebar-width', 220));
  let filmstripHeight    = $state(STORE.getNum('filmstrip-height', 76));
  let sidebarCollapsed   = $state(false); // auto only

  let currentDirectory   = $state('');
  let images             = $state<string[]>([]);
  let currentIndex       = $state(0);
  let currentImagePath   = $state<string | null>(null);
  let lastMoved          = $state<MoveRecord | null>(null);
  let shapes             = $state<Shape[]>([]);
  let isDrawing          = $state(false);
  let currentShape       = $state<Shape | null>(null);
  let selectedShapeIndex = $state(-1);
  let currentLabel       = $state('');
  let labels             = $state<string[]>([]);
  let customLabel        = $state('');
  let popupSearchQuery   = $state('');
  let imageWidth         = $state(0);
  let imageHeight        = $state(0);
  let canvasScale        = $state(1);
  let minCanvasScale     = $state(0.1);
  let totalImages        = $state(0);
  let saveStatus         = $state<''|'saving'|'ok'|'err'>('');
  let showLabelPopup     = $state(false);
  let popupPosition      = $state({ x: 0, y: 0 });
  let pendingShape       = $state<Shape | null>(null);
  let showHotkeys        = $state(false);
  let toastMsg           = $state('');
  let toastType          = $state<'ok'|'err'|'info'>('info');
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  // Sidebar rename
  let editingLabelIndex  = $state(-1);
  let editingLabelValue  = $state('');
  let labelInputEl: HTMLInputElement | null = null;

  // Edit mode drag/resize
  let activeHandle       = $state<Handle | null>(null);
  let dragStartPt        = $state<Point | null>(null);
  let dragOrigPts        = $state<[Point,Point] | null>(null);
  let hoveredShapeIndex  = $state(-1);
  let hoveredHandle      = $state<Handle | null>(null);

  // Pan
  let panOffset  = $state({ x: 0, y: 0 });
  let isPanning  = $state(false);
  let panStart   = $state({ x: 0, y: 0 });

  // Sidebar / filmstrip resize
  let isResizingSidebar   = $state(false);
  let isResizingFilmstrip = $state(false);
  let resizeStartX = 0, resizeStartW = 0;
  let resizeStartY = 0, resizeStartH = 0;

  const SIDEBAR_MIN = 160, SIDEBAR_MAX = 420;
  const FILMSTRIP_MIN = 48, FILMSTRIP_MAX = 160;
  const THUMB_VISIBLE = 9;

  // Refs
  let imageElement:    HTMLImageElement | null     = null;
  let canvasElement:   HTMLCanvasElement | null    = null;
  let ctx:             CanvasRenderingContext2D | null = null;
  let canvasContainer: HTMLDivElement | null       = null;
  let thumbsEl:        HTMLDivElement | null       = null;

  // ── Derived ────────────────────────────────────────────────────────────────
  let filteredLabels = $derived(labels.filter(l => l.toLowerCase().includes(popupSearchQuery.toLowerCase())));
  let thumbRange     = $derived({ start: Math.max(0, currentIndex - THUMB_VISIBLE), end: Math.min(images.length, currentIndex + THUMB_VISIBLE + 1) });
  let thumbSize      = $derived(Math.max(36, filmstripHeight - 20));

  // ── Hotkeys list (single source of truth for strip + modal) ───────────────
  const HOTKEYS: [string, string][] = [
    ['D',        'Next image'],
    ['A',        'Prev image'],
    ['Ctrl+S',   'Save'],
    ['E',        'Draw / Edit mode'],
    ['Esc',      'Deselect / cancel'],
    ['Del',      'Delete selected'],
    ['Ctrl+D',   'Duplicate'],
    ['Space',    'Toggle labels'],
    ['Scroll',   'Zoom'],
    ['Alt+Drag', 'Pan'],
    ['+/−',      'Zoom in/out'],
    ['0',        'Reset zoom'],
    ['1–9',      'Quick label'],
    ['?',        'Hotkeys help'],
  ];

  // ── Label colours ──────────────────────────────────────────────────────────
  const COLORS = ['#e63946','#2a9d8f','#e9c46a','#457b9d','#f4a261','#a8dadc','#8ecae6','#b5838d','#6d6875','#52b788','#ff6b6b','#4ecdc4','#ffe66d','#a8e6cf','#ffd3b6'];
  function getLabelColor(label: string) { const i = labels.indexOf(label); return i >= 0 ? COLORS[i % COLORS.length] : COLORS[0]; }

  // ── Persist prefs via $effect ──────────────────────────────────────────────
  $effect(() => { STORE.set('theme',            darkMode ? 'dark' : 'light'); });
  $effect(() => { STORE.set('mode',             interactionMode); });
  $effect(() => { STORE.set('show-labels',      String(showLabels)); });
  $effect(() => { STORE.set('sidebar-width',    String(sidebarWidth)); });
  $effect(() => { STORE.set('filmstrip-height', String(filmstripHeight)); });
  $effect(() => { STORE.set('image-directory',  imageDirectory); });
  $effect(() => { STORE.set('move-destination', moveDestination); });

  // ── Canvas $effect ─────────────────────────────────────────────────────────
  $effect(() => {
    if (!canvasElement) return;
    ctx = canvasElement.getContext('2d');
    const md = (e: MouseEvent) => handleMouseDown(e);
    const mm = (e: MouseEvent) => handleMouseMove(e);
    const mu = (e: MouseEvent) => handleMouseUp(e);
    const wh = (e: WheelEvent) => handleWheel(e);
    canvasElement.addEventListener('mousedown', md);
    canvasElement.addEventListener('mousemove', mm);
    canvasElement.addEventListener('mouseup',   mu);
    canvasElement.addEventListener('wheel',     wh, { passive: false });
    return () => {
      canvasElement?.removeEventListener('mousedown', md);
      canvasElement?.removeEventListener('mousemove', mm);
      canvasElement?.removeEventListener('mouseup',   mu);
      canvasElement?.removeEventListener('wheel',     wh);
    };
  });

  // ── Global resize mouse events ─────────────────────────────────────────────
  $effect(() => {
    function onMove(e: MouseEvent) {
      if (isResizingSidebar) {
        sidebarWidth = Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, resizeStartW + (e.clientX - resizeStartX)));
      }
      if (isResizingFilmstrip) {
        filmstripHeight = Math.max(FILMSTRIP_MIN, Math.min(FILMSTRIP_MAX, resizeStartH - (e.clientY - resizeStartY)));
      }
    }
    function onUp() {
      isResizingSidebar = false; isResizingFilmstrip = false;
      document.body.style.cursor = ''; document.body.style.userSelect = '';
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',   onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  });

  // ── Auto-collapse sidebar ──────────────────────────────────────────────────
  $effect(() => {
    function check() { sidebarCollapsed = window.innerWidth < 800; }
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  });

  onMount(() => { /* state already loaded from STORE on declaration */ });

  // ── Toast ──────────────────────────────────────────────────────────────────
  function toast(msg: string, type: 'ok'|'err'|'info' = 'info', ms = 2400) {
    if (toastTimer) clearTimeout(toastTimer);
    toastMsg = msg; toastType = type;
    toastTimer = setTimeout(() => { toastMsg = ''; }, ms);
  }

  // ── Coords ────────────────────────────────────────────────────────────────
  function screenToImage(cx: number, cy: number): Point {
    if (!canvasElement) return [0, 0];
    const r = canvasElement.getBoundingClientRect();
    return [(cx - r.left) / canvasScale, (cy - r.top) / canvasScale];
  }

  // ── Image loading ──────────────────────────────────────────────────────────
  async function loadImagesFromDirectory(keepIndex = false) {
    if (!imageDirectory.trim()) { toast('Enter a directory path', 'err'); return; }
    if (currentDirectory !== imageDirectory) { labels = []; currentLabel = ''; currentDirectory = imageDirectory; }
    try {
      const res = await axios.get(`${API_URL}/images/all`, { params: { image_path: imageDirectory, limit: 10000 } });
      images = res.data.images; totalImages = res.data.total;

      // Pre-load all labels from existing annotation JSONs in the directory
      try {
        const lblRes = await axios.get(`${API_URL}/labels/all`, { params: { image_path: imageDirectory } });
        for (const l of lblRes.data.labels) {
          if (!labels.includes(l)) labels = [...labels, l];
        }
      } catch { /* non-fatal */ }

      if (images.length > 0) {
        const idx = keepIndex ? Math.min(currentIndex, images.length - 1) : 0;
        await loadImage(idx);
      }
    } catch { toast('Failed to load directory', 'err'); }
  }

  async function setDestinationDirectory() { toast('Move destination set', 'ok'); }

  async function loadImage(index: number) {
    if (index < 0 || index >= images.length) return;
    currentIndex = index; currentImagePath = images[index];
    shapes = []; selectedShapeIndex = -1; imageWidth = 0; imageHeight = 0;
    imageElement = null; panOffset = { x: 0, y: 0 };
    activeHandle = null; dragStartPt = null; editingLabelIndex = -1;

    let loaded: Shape[] = [];
    try {
      const res = await axios.get(`${API_URL}/annotation/load`, { params: { image_path: currentImagePath } });
      if (res.data) {
        loaded = res.data.shapes ?? [];
        loaded.forEach(s => { if (s.label && !labels.includes(s.label)) labels = [...labels, s.label]; });
      }
    } catch {}

    const img = new Image(); img.crossOrigin = 'anonymous';
    await new Promise<void>((resolve, reject) => {
      img.onload  = () => { imageElement = img; imageWidth = img.width; imageHeight = img.height; resolve(); };
      img.onerror = reject;
      img.src = `${API_URL}/images/single?image_path=${encodeURIComponent(currentImagePath!)}`;
    });

    shapes = loaded;
    await tick();
    // Retry fitCanvasToImage until container has real dimensions
    // (can be zero briefly during a reactive re-render)
    let attempts = 0;
    while ((!canvasContainer || canvasContainer.clientWidth === 0) && attempts++ < 10) {
      await new Promise(r => setTimeout(r, 16));
    }
    fitCanvasToImage(); redraw(); scrollThumbsToCenter();
  }

  // ── Canvas sizing & zoom ───────────────────────────────────────────────────
  function fitCanvasToImage() {
    if (!imageElement || !canvasContainer) return;
    const cw = canvasContainer.clientWidth - 40, ch = canvasContainer.clientHeight - 40;
    minCanvasScale = Math.min(cw / imageWidth, ch / imageHeight, 1);
    canvasScale = minCanvasScale; panOffset = { x: 0, y: 0 }; updateCanvasSize();
  }
  function updateCanvasSize() {
    if (!imageElement || !canvasElement) return;
    canvasElement.width  = Math.round(imageWidth  * canvasScale);
    canvasElement.height = Math.round(imageHeight * canvasScale);
  }
  function zoomAt(factor: number, px?: number, py?: number) {
    if (!imageElement) return;
    const old = canvasScale;
    canvasScale = Math.max(minCanvasScale, Math.min(5, old * factor));
    updateCanvasSize();
    if (px !== undefined && py !== undefined) {
      panOffset.x = px - (px - panOffset.x) * (canvasScale / old);
      panOffset.y = py - (py - panOffset.y) * (canvasScale / old);
    }
    redraw();
  }
  function zoomIn()    { zoomAt(1.2); }
  function zoomOut()   { zoomAt(1 / 1.2); }
  function resetZoom() { canvasScale = minCanvasScale; panOffset = { x: 0, y: 0 }; updateCanvasSize(); redraw(); }
  function handleWheel(e: WheelEvent) {
    e.preventDefault(); e.stopPropagation();
    const r = canvasElement!.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
  }

  // ── Handle hit detection ───────────────────────────────────────────────────
  const HS = 7;
  function getHandleRects(s: Shape): Record<Handle, {x:number,y:number,w:number,h:number}> {
    const [p1,p2] = s.points;
    const lx=Math.min(p1[0],p2[0])*canvasScale, ly=Math.min(p1[1],p2[1])*canvasScale;
    const rx=Math.max(p1[0],p2[0])*canvasScale, ry=Math.max(p1[1],p2[1])*canvasScale;
    const mx=(lx+rx)/2, my=(ly+ry)/2, hh=HS/2;
    return {
      tl:{x:lx-hh,y:ly-hh,w:HS,h:HS}, tc:{x:mx-hh,y:ly-hh,w:HS,h:HS}, tr:{x:rx-hh,y:ly-hh,w:HS,h:HS},
      ml:{x:lx-hh,y:my-hh,w:HS,h:HS}, mr:{x:rx-hh,y:my-hh,w:HS,h:HS},
      bl:{x:lx-hh,y:ry-hh,w:HS,h:HS}, bc:{x:mx-hh,y:ry-hh,w:HS,h:HS}, br:{x:rx-hh,y:ry-hh,w:HS,h:HS},
      body:{x:lx,y:ly,w:rx-lx,h:ry-ly},
    };
  }
  function hitHandle(sx: number, sy: number, s: Shape): Handle | null {
    const rects = getHandleRects(s);
    for (const h of (['tl','tc','tr','ml','mr','bl','bc','br'] as Handle[])) {
      const r = rects[h]; if (sx>=r.x&&sx<=r.x+r.w&&sy>=r.y&&sy<=r.y+r.h) return h;
    }
    const b = rects.body; return (sx>=b.x&&sx<=b.x+b.w&&sy>=b.y&&sy<=b.y+b.h) ? 'body' : null;
  }
  const CURSOR_MAP: Record<Handle,string> = { tl:'nw-resize',tr:'ne-resize',bl:'sw-resize',br:'se-resize',tc:'n-resize',bc:'s-resize',ml:'w-resize',mr:'e-resize',body:'move' };

  // ── Mouse handlers ─────────────────────────────────────────────────────────
  function handleMouseDown(e: MouseEvent) {
    if (!canvasElement || !imageElement) return;
    if (e.button === 1 || (e.button === 0 && e.altKey)) { isPanning=true; panStart={x:e.clientX-panOffset.x,y:e.clientY-panOffset.y}; return; }
    if (e.button !== 0) return;
    const r=canvasElement.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
    const imgPt = screenToImage(e.clientX, e.clientY);

    if (interactionMode === 'edit') {
      for (let i=shapes.length-1; i>=0; i--) {
        const h = hitHandle(sx, sy, shapes[i]);
        if (h) {
          selectedShapeIndex=i; activeHandle=h; dragStartPt=imgPt;
          dragOrigPts=[[...shapes[i].points[0]] as Point, [...shapes[i].points[1]] as Point];
          editingLabelIndex=i; editingLabelValue=shapes[i].label;
          setTimeout(()=>labelInputEl?.focus(), 50); redraw(); return;
        }
      }
      selectedShapeIndex=-1; editingLabelIndex=-1; redraw(); return;
    }

    // Draw mode
    isDrawing=true;
    currentShape={ label:currentLabel, points:[[imgPt[0],imgPt[1]],[imgPt[0],imgPt[1]]], shape_type:'rectangle', flags:{}, group_id:null };
  }

  function handleMouseMove(e: MouseEvent) {
    if (!canvasElement) return;
    const r=canvasElement.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;

    if (isPanning) { panOffset={x:e.clientX-panStart.x,y:e.clientY-panStart.y}; redraw(); return; }

    // Edit mode: dragging a handle or body
    if (activeHandle && dragStartPt && dragOrigPts) {
      const pt=screenToImage(e.clientX,e.clientY), dx=pt[0]-dragStartPt[0], dy=pt[1]-dragStartPt[1];
      const [o1,o2]=dragOrigPts; let x1=o1[0],y1=o1[1],x2=o2[0],y2=o2[1];
      if (activeHandle==='body') { x1+=dx;y1+=dy;x2+=dx;y2+=dy; }
      else {
        if (activeHandle.includes('l')) x1=o1[0]+dx;
        if (activeHandle.includes('r')) x2=o2[0]+dx;
        if (activeHandle.includes('t')) y1=o1[1]+dy;
        if (activeHandle.includes('b')) y2=o2[1]+dy;
        if (activeHandle==='ml'||activeHandle==='mr') { y1=o1[1];y2=o2[1]; }
        if (activeHandle==='tc'||activeHandle==='bc') { x1=o1[0];x2=o2[0]; }
      }
      shapes[selectedShapeIndex]={...shapes[selectedShapeIndex],points:[[x1,y1],[x2,y2]]};
      canvasElement.style.cursor=CURSOR_MAP[activeHandle];
      redraw(); return;
    }

    // Edit mode: hover highlight (no active drag)
    if (interactionMode==='edit') {
      let found=false;
      for (let i=shapes.length-1;i>=0;i--) {
        const h=hitHandle(sx,sy,shapes[i]);
        if (h) { hoveredShapeIndex=i; hoveredHandle=h; canvasElement.style.cursor=CURSOR_MAP[h]; found=true; break; }
      }
      if (!found) { hoveredShapeIndex=-1; hoveredHandle=null; canvasElement.style.cursor='default'; }
      redraw(); return;
    }

    // Draw mode: update in-progress bbox
    if (isDrawing && currentShape) {
      const pt=screenToImage(e.clientX,e.clientY);
      currentShape={...currentShape,points:[currentShape.points[0],[pt[0],pt[1]]]};
      redraw();
    }
  }

  function handleMouseUp(e: MouseEvent) {
    if (!canvasElement) return;

    if (isPanning) { isPanning=false; return; }

    if (activeHandle) {
      const s=shapes[selectedShapeIndex];
      shapes[selectedShapeIndex]={...s,points:[[Math.min(s.points[0][0],s.points[1][0]),Math.min(s.points[0][1],s.points[1][1])],[Math.max(s.points[0][0],s.points[1][0]),Math.max(s.points[0][1],s.points[1][1])]]};
      activeHandle=null; dragStartPt=null; dragOrigPts=null; redraw(); return;
    }

    if (!isDrawing || !currentShape) return;
    const pt=screenToImage(e.clientX,e.clientY);
    const fs:Shape={...currentShape,points:[currentShape.points[0],[pt[0],pt[1]]]};
    const w=Math.abs(fs.points[1][0]-fs.points[0][0]), h=Math.abs(fs.points[1][1]-fs.points[0][1]);
    if (w>5&&h>5) {
      const r=canvasElement.getBoundingClientRect();
      popupPosition={x:e.clientX-r.left,y:e.clientY-r.top}; pendingShape=fs; showLabelPopup=true;
    }
    isDrawing=false; currentShape=null; redraw();
  }

  // ── Label popup ────────────────────────────────────────────────────────────
  function selectLabelForShape(label: string) {
    if (!pendingShape) return;
    pendingShape.label=label; shapes=[...shapes,pendingShape];
    if (!labels.includes(label)) labels=[...labels,label];
    currentLabel=label; showLabelPopup=false; pendingShape=null; popupSearchQuery=''; redraw();
  }
  function cancelLabelSelection() { showLabelPopup=false; pendingShape=null; popupSearchQuery=''; }
  function addLabelFromPopup()     { if (popupSearchQuery.trim()) selectLabelForShape(popupSearchQuery.trim()); }

  // ── Rename ─────────────────────────────────────────────────────────────────
  function commitRename() {
    if (editingLabelIndex < 0) return;
    const v=editingLabelValue.trim(); if (!v) return;
    const old=shapes[editingLabelIndex].label;
    shapes[editingLabelIndex]={...shapes[editingLabelIndex],label:v};
    if (!labels.includes(v)) labels=[...labels,v];
    if (!shapes.some(s=>s.label===old)) labels=labels.filter(l=>l!==old);
    redraw();
  }

  // ── Redraw ─────────────────────────────────────────────────────────────────
  function redraw() {
    if (!ctx||!imageElement||!canvasElement) return;
    ctx.clearRect(0,0,canvasElement.width,canvasElement.height);
    ctx.drawImage(imageElement,0,0,imageWidth*canvasScale,imageHeight*canvasScale);

    shapes.forEach((shape,idx) => {
      const [p1,p2]=shape.points;
      const x=Math.min(p1[0],p2[0])*canvasScale, y=Math.min(p1[1],p2[1])*canvasScale;
      const w=Math.abs(p2[0]-p1[0])*canvasScale, h=Math.abs(p2[1]-p1[1])*canvasScale;
      const col=getLabelColor(shape.label);
      const isSel=idx===selectedShapeIndex, isHov=idx===hoveredShapeIndex&&interactionMode==='edit';
      ctx!.fillStyle=hexAlpha(col,isSel?0.18:isHov?0.10:0.05); ctx!.fillRect(x,y,w,h);
      ctx!.strokeStyle=isSel?'#fff':col; ctx!.lineWidth=isSel?2:1.5;
      ctx!.setLineDash(isSel?[5,3]:[]); ctx!.strokeRect(x,y,w,h); ctx!.setLineDash([]);
      if (isSel&&interactionMode==='edit') drawHandles(shape,col);
      if (showLabels) {
        const text=labelText(shape); ctx!.font='600 11px "IBM Plex Mono",monospace';
        const tw=ctx!.measureText(text).width, bx=x, by=y>=18?y-18:y+h+2;
        ctx!.fillStyle=col; ctx!.fillRect(bx,by,tw+8,16); ctx!.fillStyle='#000'; ctx!.fillText(text,bx+4,by+11);
      }
    });

    if (currentShape) {
      const [p1,p2]=currentShape.points;
      const x=Math.min(p1[0],p2[0])*canvasScale, y=Math.min(p1[1],p2[1])*canvasScale;
      const w=Math.abs(p2[0]-p1[0])*canvasScale, h=Math.abs(p2[1]-p1[1])*canvasScale;
      ctx!.strokeStyle='#fff'; ctx!.lineWidth=1.5; ctx!.setLineDash([4,4]);
      ctx!.strokeRect(x,y,w,h); ctx!.setLineDash([]);
      const dim=`${Math.abs(currentShape.points[1][0]-currentShape.points[0][0]).toFixed(0)}×${Math.abs(currentShape.points[1][1]-currentShape.points[0][1]).toFixed(0)}`;
      ctx!.font='600 11px "IBM Plex Mono",monospace'; const dw=ctx!.measureText(dim).width;
      ctx!.fillStyle='rgba(0,0,0,0.75)'; ctx!.fillRect(x+w/2-dw/2-5,y+h/2-10,dw+10,18);
      ctx!.fillStyle='#fff'; ctx!.textAlign='center'; ctx!.fillText(dim,x+w/2,y+h/2+3); ctx!.textAlign='left';
    }
  }

  function drawHandles(s: Shape, col: string) {
    const rects=getHandleRects(s);
    (['tl','tc','tr','ml','mr','bl','bc','br'] as Handle[]).forEach(h => {
      const r=rects[h]; ctx!.fillStyle='#fff'; ctx!.fillRect(r.x,r.y,r.w,r.h);
      ctx!.strokeStyle=col; ctx!.lineWidth=1.5; ctx!.strokeRect(r.x,r.y,r.w,r.h);
    });
  }

  function labelText(s: Shape) {
    let t=s.label||'?'; if (s.group_id) { const c=parseFloat(s.group_id); if(!isNaN(c)) t+=` ${(c*100).toFixed(0)}%`; } return t;
  }
  function hexAlpha(hex: string, a: number) {
    return `rgba(${parseInt(hex.slice(1,3),16)},${parseInt(hex.slice(3,5),16)},${parseInt(hex.slice(5,7),16)},${a})`;
  }

  // ── Save / Undo / Navigate ─────────────────────────────────────────────────
  async function saveAnnotation() {
    if (!currentImagePath) return; saveStatus='saving';
    try {
      const savedPath = currentImagePath;
      const savedIndex = currentIndex;
      const res=await axios.post(`${API_URL}/annotation`,{shapes,imagePath:savedPath,imageHeight,imageWidth},{params:{image_path:savedPath,dest_path:moveDestination||null}});
      const moved = !!(res.data?.move_data && moveDestination);
      if (moved) lastMoved={dest_img:res.data.move_data.dest_img,dest_json:res.data.move_data.dest_json,original_json:res.data.move_data.orig_json,original_img:res.data.move_data.orig_img};
      saveStatus='ok'; toast(moved ? 'Saved & moved' : 'Saved', 'ok'); setTimeout(()=>(saveStatus=''),2000);

      // Fetch fresh image list
      const res2 = await axios.get(`${API_URL}/images/all`, { params: { image_path: imageDirectory, limit: 10000 } });
      const freshImages: string[] = res2.data.images;
      const freshTotal: number = res2.data.total;

      if (freshImages.length === 0) {
        images = []; totalImages = 0; currentImagePath = null; return;
      }

      if (moved) {
        // Image was moved out — clamp to new list so we land on the next one
        const nextIdx = Math.min(savedIndex, freshImages.length - 1);
        images = freshImages; totalImages = freshTotal;
        await tick();
        await loadImage(nextIdx);
      } else {
        // No move — reload same image to refresh annotation state
        images = freshImages; totalImages = freshTotal;
        await tick();
        await loadImage(savedIndex);
      }
    } catch { saveStatus='err'; toast('Save failed','err'); setTimeout(()=>(saveStatus=''),2000); }
  }

  async function undoMove() {
    if (!lastMoved) return;
    try {
      await axios.post(`${API_URL}/move`,null,{params:{destination_path:lastMoved.original_img.split('/').slice(0,-1).join('/'),image_path:lastMoved.dest_img}});
      const restored=lastMoved.original_img; lastMoved=null;
      await loadImagesFromDirectory(true); currentImagePath=restored; toast('Move undone','ok');
    } catch { toast('Undo failed','err'); }
  }

  function nextImage()        { if (currentIndex<images.length-1) loadImage(currentIndex+1); }
  function prevImage()        { if (currentIndex>0) loadImage(currentIndex-1); }
  function deleteSelected()   { if (selectedShapeIndex>=0) { shapes=shapes.filter((_,i)=>i!==selectedShapeIndex); selectedShapeIndex=-1; editingLabelIndex=-1; redraw(); } }
  function duplicateSelected(){ if (selectedShapeIndex>=0) { const s=shapes[selectedShapeIndex]; shapes=[...shapes,{...s,points:[[s.points[0][0]+10,s.points[0][1]+10],[s.points[1][0]+10,s.points[1][1]+10]]}]; redraw(); } }
  function addCustomLabel()   { if (customLabel&&!labels.includes(customLabel)) { labels=[...labels,customLabel]; currentLabel=customLabel; customLabel=''; } }

  // ── Filmstrip ──────────────────────────────────────────────────────────────
  function scrollThumbsToCenter() {
    if (!thumbsEl) return;
    const target=(currentIndex-thumbRange.start)*(thumbSize+4)-thumbsEl.clientWidth/2+thumbSize/2;
    thumbsEl.scrollTo({left:target,behavior:'smooth'});
  }
  function thumbUrl(p: string) { return `${API_URL}/images/single?image_path=${encodeURIComponent(p)}`; }

  // ── Keyboard ───────────────────────────────────────────────────────────────
  // Block hotkeys only when the user is actively typing in a text field.
  // Never use isCanvasHovered as a gate — it breaks hotkeys whenever the user
  // clicks sidebar items, toolbar buttons, or anything outside the canvas.
  function isTyping(): boolean {
    const el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || (el as HTMLElement).isContentEditable;
  }

  function handleKeydown(e: KeyboardEvent) {
    // Always handle these regardless of focus
    if (e.key==='?'||(e.key==='/'&&e.shiftKey)) { showHotkeys=!showHotkeys; return; }
    if (e.key==='Escape'&&showHotkeys) { showHotkeys=false; return; }
    if (e.ctrlKey&&e.key==='r') { e.preventDefault(); return; }

    // Label popup intercepts its own keys
    if (showLabelPopup) {
      if (e.key==='Escape') { e.preventDefault(); cancelLabelSelection(); return; }
      if (e.key==='Enter')  { e.preventDefault(); addLabelFromPopup(); return; }
      if (e.key>='1'&&e.key<='9') { e.preventDefault(); const i=parseInt(e.key)-1; if(i<filteredLabels.length) selectLabelForShape(filteredLabels[i]); return; }
      return;
    }

    // All other hotkeys: skip only if user is typing in a text field
    if (isTyping()) return;

    if (e.key.toLowerCase()==='e'&&!e.ctrlKey) { interactionMode=interactionMode==='draw'?'edit':'draw'; return; }
    if (['d','a',' ','+','-','0'].includes(e.key.toLowerCase())||(e.ctrlKey&&['s','d'].includes(e.key.toLowerCase()))) e.preventDefault();

    switch (e.key.toLowerCase()) {
      case 'd': if(!e.ctrlKey) nextImage(); else duplicateSelected(); break;
      case 'a': if(!e.ctrlKey) prevImage(); break;
      case 's': if(e.ctrlKey) saveAnnotation(); break;
      case 'escape': isDrawing=false;currentShape=null;selectedShapeIndex=-1;editingLabelIndex=-1;redraw(); break;
      case 'delete': case 'backspace': deleteSelected(); break;
      case ' ': showLabels=!showLabels; redraw(); break;
      case '+': case '=': zoomIn(); break;
      case '-': case '_': zoomOut(); break;
      case '0': resetZoom(); break;
    }
  }

  function confColor(g: string|null) {
    if (!g) return 'var(--text-muted)'; const c=parseFloat(g); if(isNaN(c)) return 'var(--text-muted)';
    return c>=0.8?'#52b788':c>=0.5?'#e9c46a':'#e63946';
  }

  // ── Sidebar / filmstrip resize start ──────────────────────────────────────
  function startSidebarResize(e: MouseEvent) {
    e.preventDefault(); isResizingSidebar=true; resizeStartX=e.clientX; resizeStartW=sidebarWidth;
    document.body.style.cursor='ew-resize'; document.body.style.userSelect='none';
  }
  function startFilmstripResize(e: MouseEvent) {
    e.preventDefault(); isResizingFilmstrip=true; resizeStartY=e.clientY; resizeStartH=filmstripHeight;
    document.body.style.cursor='ns-resize'; document.body.style.userSelect='none';
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="app" class:dark={darkMode} class:light={!darkMode}>

  <!-- ── Sidebar ───────────────────────────────────────────────────────────── -->
  <aside class="sidebar" class:collapsed={sidebarCollapsed} style:width="{sidebarCollapsed ? 48 : sidebarWidth}px">
    <div class="sidebar-scroll">

      <div class="brand">
        <span class="brand-mark">▣</span>
        {#if !sidebarCollapsed}<span class="brand-name">BBOX</span>{/if}
        <button class="icon-btn" onclick={toggleTheme} style="margin-left:auto" title="Toggle theme">
          {darkMode ? '○' : '●'}
        </button>
      </div>

      {#if !sidebarCollapsed}

        <div class="section">
          <label class="section-label">SOURCE</label>
          <input type="text" bind:value={imageDirectory} placeholder="/path/to/images"
            onkeydown={(e) => e.key==='Enter'&&loadImagesFromDirectory()} />
          <button class="btn-primary" onclick={loadImagesFromDirectory}>Load</button>
        </div>

        <div class="section">
          <label class="section-label">MOVE DEST</label>
          <input type="text" bind:value={moveDestination} placeholder="/path/to/dest (optional)"
            onkeydown={(e) => e.key==='Enter'&&setDestinationDirectory()} />
          <button class="btn-ghost" onclick={setDestinationDirectory}>Set</button>
        </div>

        {#if images.length > 0}
          <div class="counters">
            <div class="counter"><span>{currentIndex+1}</span><small>cur</small></div>
            <div class="counter-sep">/</div>
            <div class="counter"><span>{totalImages}</span><small>total</small></div>
            <div class="counter-sep">·</div>
            <div class="counter"><span>{shapes.length}</span><small>shapes</small></div>
          </div>
        {/if}

        <div class="section">
          <label class="section-label">LABELS</label>
          {#each labels as label}
            <div class="label-chip" class:label-active={currentLabel===label} onclick={()=>currentLabel=label}>
              <span class="dot" style:background={getLabelColor(label)}></span>
              <span class="lname">{label}</span>
            </div>
          {/each}
          <div class="add-row">
            <input type="text" bind:value={customLabel} placeholder="new label…" onkeydown={(e)=>e.key==='Enter'&&addCustomLabel()} />
            <button class="icon-btn" onclick={addCustomLabel}>+</button>
          </div>
        </div>

        <div class="section">
          <label class="section-label">SHAPES</label>
          <div class="shapes-list">
            {#each shapes as shape, i}
              <div class="shape-row" class:shape-sel={i===selectedShapeIndex}
                onclick={()=>{ selectedShapeIndex=i; editingLabelIndex=i; editingLabelValue=shape.label; redraw(); setTimeout(()=>labelInputEl?.focus(),50); }}>
                <span class="dot" style:background={getLabelColor(shape.label)}></span>
                {#if editingLabelIndex===i}
                  <input class="inline-rename" bind:this={labelInputEl} bind:value={editingLabelValue}
                    onblur={commitRename}
                    onkeydown={(e)=>{ if(e.key==='Enter'){commitRename();e.currentTarget.blur();} e.stopPropagation(); }}
                    onclick={(e)=>e.stopPropagation()} />
                {:else}
                  <span class="sname">{shape.label||'—'}</span>
                {/if}
                {#if shape.group_id}
                  <span class="sconf" style:color={confColor(shape.group_id)}>{(parseFloat(shape.group_id)*100).toFixed(0)}%</span>
                {/if}
                <button class="sdel" onclick={(e)=>{ e.stopPropagation(); shapes=shapes.filter((_,j)=>j!==i); if(selectedShapeIndex===i)selectedShapeIndex=-1; redraw(); }}>×</button>
              </div>
            {/each}
            {#if shapes.length===0}<span class="empty-note">no shapes yet</span>{/if}
          </div>
        </div>

        <!-- ── Hotkey strip ──────────────────────────────────────────────── -->
        <div class="section hk-section">
          <label class="section-label">
            HOTKEYS
            <button class="hk-expand" onclick={()=>showHotkeys=true} title="Full reference">↗</button>
          </label>
          <div class="hk-list">
            {#each HOTKEYS as [key, desc]}
              <div class="hk-row">
                <span class="hk-key">{key}</span>
                <span class="hk-desc">{desc}</span>
              </div>
            {/each}
          </div>
        </div>

      {:else}
        <div class="collapsed-icons">
          <button class="icon-btn" onclick={prevImage}            title="Prev (A)">↑</button>
          <button class="icon-btn" onclick={nextImage}            title="Next (D)">↓</button>
          <button class="icon-btn" onclick={saveAnnotation}       title="Save (Ctrl+S)">✓</button>
          <button class="icon-btn" onclick={()=>showHotkeys=true} title="Hotkeys (?)">?</button>
        </div>
      {/if}
    </div>

    <!-- Sidebar horizontal resize grip -->
    {#if !sidebarCollapsed}
      <div class="grip-x" onmousedown={startSidebarResize}></div>
    {/if}
  </aside>

  <!-- ── Main ──────────────────────────────────────────────────────────────── -->
  <div class="main">

    <!-- Toolbar -->
    <div class="toolbar">
      <div class="tl">
        <button class="nav-btn" onclick={prevImage} disabled={currentIndex===0||images.length===0}>←</button>
        <span class="img-name">{currentImagePath?currentImagePath.split('/').pop():'no image'}</span>
        <button class="nav-btn" onclick={nextImage} disabled={currentIndex>=images.length-1||images.length===0}>→</button>
      </div>
      <div class="tc">
        <div class="mode-pill">
          <button class="mode-opt" class:mode-on={interactionMode==='draw'} onclick={()=>interactionMode='draw'}>Draw</button>
          <button class="mode-opt" class:mode-on={interactionMode==='edit'} onclick={()=>interactionMode='edit'}>Edit</button>
        </div>
      </div>
      <div class="tr">
        <div class="zoom-row">
          <button class="icon-btn" onclick={zoomOut}   disabled={!currentImagePath}>−</button>
          <span class="zoom-val">{Math.round(canvasScale*100)}%</span>
          <button class="icon-btn" onclick={zoomIn}    disabled={!currentImagePath}>+</button>
          <button class="icon-btn" onclick={resetZoom} disabled={!currentImagePath} title="Reset zoom">⊡</button>
        </div>
        <button class="tb-btn" onclick={undoMove} disabled={!lastMoved}>Undo</button>
        <button class="tb-btn tb-save" onclick={saveAnnotation} disabled={!currentImagePath}
          class:tb-saving={saveStatus==='saving'} class:tb-ok={saveStatus==='ok'} class:tb-err={saveStatus==='err'}>
          {saveStatus==='saving'?'…':saveStatus==='ok'?'Saved':saveStatus==='err'?'Error':'Save'}
        </button>
        <button class="icon-btn" onclick={()=>showHotkeys=true} title="Hotkeys (?)">?</button>
      </div>
    </div>

    <!-- Canvas -->
    <div class="canvas-area" bind:this={canvasContainer}>
      {#if !currentImagePath}
        <div class="splash"><span class="splash-mark">▣</span><p>Load an image directory to begin</p></div>
      {/if}
      <div class="pan-wrapper" style:transform="translate({panOffset.x}px,{panOffset.y}px)">
        <canvas bind:this={canvasElement}
          style:display={currentImagePath?'block':'none'}
        ></canvas>

        {#if showLabelPopup}
          <div class="label-popup" style:left="{popupPosition.x}px" style:top="{popupPosition.y}px">
            <div class="popup-title">label</div>
            <input type="text" bind:value={popupSearchQuery} placeholder="search or type…"
              onkeydown={(e)=>{ if(e.key==='Enter') addLabelFromPopup(); e.stopPropagation(); }} autofocus />
            {#if popupSearchQuery.trim()&&!labels.includes(popupSearchQuery.trim())}
              <div class="popup-opt popup-new" onclick={()=>selectLabelForShape(popupSearchQuery.trim())}>
                <span class="pop-key">+</span> add "{popupSearchQuery.trim()}"
              </div>
            {/if}
            {#each filteredLabels.slice(0,9) as label, i}
              <div class="popup-opt" style:border-left="3px solid {getLabelColor(label)}" onclick={()=>selectLabelForShape(label)}>
                <span class="pop-key">{i+1}</span> {label}
              </div>
            {/each}
            {#if filteredLabels.length===0&&!popupSearchQuery.trim()}
              <div class="popup-empty">type to create a label</div>
            {/if}
            <button class="popup-cancel" onclick={cancelLabelSelection}>cancel</button>
          </div>
        {/if}
      </div>
    </div>

    <!-- Filmstrip vertical resize grip + filmstrip -->
    {#if images.length > 0}
      <div class="grip-y" onmousedown={startFilmstripResize}></div>
      <div class="filmstrip" bind:this={thumbsEl} style:height="{filmstripHeight}px">
        {#each images.slice(thumbRange.start, thumbRange.end) as img, relIdx}
          {@const absIdx = thumbRange.start + relIdx}
          <div class="thumb" class:thumb-on={absIdx===currentIndex}
            style:width="{thumbSize}px" style:height="{thumbSize}px"
            onclick={()=>loadImage(absIdx)}>
            <img src={thumbUrl(img)} alt="" loading="lazy" />
            <span class="thumb-idx">{absIdx+1}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- ── Hotkeys Modal ──────────────────────────────────────────────────────── -->
  {#if showHotkeys}
    <div class="modal-back" onclick={()=>showHotkeys=false}>
      <div class="modal" onclick={(e)=>e.stopPropagation()}>
        <div class="modal-hdr">
          <span>Keyboard Shortcuts</span>
          <button class="icon-btn" onclick={()=>showHotkeys=false}>×</button>
        </div>
        <div class="hk-grid">
          {#each HOTKEYS as [key, desc]}
            <span class="hk-grid-key">{key}</span><span class="hk-grid-desc">{desc}</span>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  <!-- ── Toast ─────────────────────────────────────────────────────────────── -->
  {#if toastMsg}
    <div class="toast" class:toast-ok={toastType==='ok'} class:toast-err={toastType==='err'}>{toastMsg}</div>
  {/if}
</div>

<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

  :global(*) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) { overflow: hidden; }

  .dark {
    --bg: #0d0d0d; --surface: #161616; --surface2: #1f1f1f; --surface3: #2a2a2a;
    --border: #2e2e2e; --border2: #3a3a3a;
    --text: #e8e8e8; --text-muted: #555; --text-dim: #333;
  }
  .light {
    --bg: #f4f4f4; --surface: #ffffff; --surface2: #f0f0f0; --surface3: #e8e8e8;
    --border: #d8d8d8; --border2: #c0c0c0;
    --text: #111; --text-muted: #888; --text-dim: #ccc;
  }

  .app { display: flex; height: 100vh; overflow: hidden; background: var(--bg); color: var(--text); font-family: 'IBM Plex Sans', system-ui, sans-serif; font-size: 13px; }

  /* ── Sidebar ─────────────────────────────────────────────────────────────── */
  .sidebar {
    flex-shrink: 0; position: relative;
    background: var(--surface); border-right: 1px solid var(--border);
    overflow: visible; min-width: 48px; transition: width 0.12s ease;
  }
  .sidebar.collapsed { width: 48px !important; }

  .sidebar-scroll { width: 100%; height: 100%; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; }
  .sidebar-scroll::-webkit-scrollbar { width: 3px; }
  .sidebar-scroll::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

  /* Grip handles */
  .grip-x {
    position: absolute; top: 0; right: -3px; width: 6px; height: 100%;
    cursor: ew-resize; z-index: 20; background: transparent; transition: background 0.15s;
  }
  .grip-x:hover { background: var(--border2); }

  .grip-y {
    width: 100%; height: 6px; cursor: ns-resize; background: transparent;
    border-top: 1px solid var(--border); flex-shrink: 0; transition: background 0.15s;
  }
  .grip-y:hover { background: var(--border2); }

  .brand { display: flex; align-items: center; gap: 8px; padding: 13px 14px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); z-index: 2; flex-shrink: 0; }
  .brand-mark { font-size: 18px; flex-shrink: 0; }
  .brand-name { font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; letter-spacing: 0.2em; white-space: nowrap; overflow: hidden; }

  .icon-btn { background: transparent; border: 1px solid var(--border); color: var(--text-muted); padding: 4px 8px; border-radius: 2px; cursor: pointer; font-size: 13px; line-height: 1; transition: border-color 0.1s, color 0.1s; flex-shrink: 0; }
  .icon-btn:hover:not(:disabled) { border-color: var(--border2); color: var(--text); }
  .icon-btn:disabled { color: var(--text-dim); cursor: not-allowed; }

  .section { padding: 14px 14px 12px; border-bottom: 1px solid var(--border); }
  .section-label { display: flex; align-items: center; justify-content: space-between; font-family: 'IBM Plex Mono', monospace; font-size: 9px; font-weight: 600; letter-spacing: 0.12em; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; }

  input[type=text] { width: 100%; padding: 7px 9px; background: var(--surface2); border: 1px solid var(--border); color: var(--text); font-family: 'IBM Plex Mono', monospace; font-size: 11px; border-radius: 2px; outline: none; transition: border-color 0.15s; }
  input[type=text]:focus { border-color: var(--border2); }

  .btn-primary { width: 100%; margin-top: 7px; padding: 7px; background: var(--text); color: var(--bg); border: none; border-radius: 2px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 0.05em; cursor: pointer; transition: opacity 0.15s; }
  .btn-primary:hover { opacity: 0.85; }

  .btn-ghost { width: 100%; margin-top: 7px; padding: 7px; background: transparent; color: var(--text-muted); border: 1px solid var(--border); border-radius: 2px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; cursor: pointer; transition: border-color 0.15s, color 0.15s; }
  .btn-ghost:hover { border-color: var(--border2); color: var(--text); }

  .counters { display: flex; align-items: baseline; gap: 6px; padding: 12px 14px; border-bottom: 1px solid var(--border); }
  .counter { display: flex; flex-direction: column; align-items: center; }
  .counter span { font-family: 'IBM Plex Mono', monospace; font-size: 20px; font-weight: 600; line-height: 1; }
  .counter small { font-size: 9px; color: var(--text-muted); letter-spacing: 0.08em; margin-top: 2px; }
  .counter-sep { color: var(--text-dim); font-size: 16px; }

  .label-chip { display: flex; align-items: center; gap: 7px; padding: 5px 8px; margin-bottom: 3px; border-radius: 2px; cursor: pointer; transition: background 0.1s; border: 1px solid transparent; }
  .label-chip:hover { background: var(--surface2); }
  .label-chip.label-active { background: var(--surface3); border-color: var(--border2); }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .lname { font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .add-row { display: flex; gap: 6px; margin-top: 8px; }
  .add-row input { flex: 1; }

  .shapes-list { max-height: 200px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .shape-row { display: flex; align-items: center; gap: 6px; padding: 5px 6px; border-radius: 2px; cursor: pointer; transition: background 0.1s; border: 1px solid transparent; }
  .shape-row:hover { background: var(--surface2); }
  .shape-row.shape-sel { background: var(--surface3); border-color: var(--border2); }
  .sname { flex: 1; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .inline-rename { flex: 1; padding: 1px 4px; font-size: 12px; background: var(--surface2); border: 1px solid var(--border2); color: var(--text); border-radius: 2px; }
  .sconf { font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 600; }
  .sdel { background: transparent; border: none; color: var(--text-dim); cursor: pointer; font-size: 14px; padding: 0 2px; line-height: 1; transition: color 0.1s; }
  .sdel:hover { color: #e63946; }
  .empty-note { font-size: 11px; color: var(--text-dim); padding: 4px 2px; }

  /* Hotkey strip */
  .hk-section { flex: 1; }
  .hk-expand { background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 11px; padding: 0 2px; line-height: 1; transition: color 0.1s; }
  .hk-expand:hover { color: var(--text); }
  .hk-list { display: flex; flex-direction: column; }
  .hk-row { display: flex; align-items: baseline; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--border); }
  .hk-row:last-child { border-bottom: none; }
  .hk-key { font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 600; color: var(--text); min-width: 64px; flex-shrink: 0; white-space: nowrap; }
  .hk-desc { font-size: 11px; color: var(--text-muted); }

  .collapsed-icons { display: flex; flex-direction: column; gap: 6px; padding: 12px 6px; align-items: center; }

  /* ── Main ────────────────────────────────────────────────────────────────── */
  .main { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }

  .toolbar { display: flex; align-items: center; gap: 10px; padding: 0 14px; height: 44px; background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0; }
  .tl { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
  .tc { display: flex; justify-content: center; flex-shrink: 0; }
  .tr { display: flex; align-items: center; gap: 8px; flex: 1; justify-content: flex-end; }

  .nav-btn { background: transparent; border: 1px solid var(--border); color: var(--text); padding: 4px 10px; border-radius: 2px; cursor: pointer; font-size: 13px; transition: border-color 0.1s; }
  .nav-btn:hover:not(:disabled) { border-color: var(--border2); }
  .nav-btn:disabled { color: var(--text-dim); cursor: not-allowed; }
  .img-name { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 280px; }

  .mode-pill { display: flex; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; }
  .mode-opt { padding: 4px 14px; background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 0.06em; transition: background 0.1s, color 0.1s; }
  .mode-opt:not(:last-child) { border-right: 1px solid var(--border); }
  .mode-opt:hover { background: var(--surface2); }
  .mode-opt.mode-on { background: var(--surface3) !important; color: var(--text) !important; }

  .zoom-row { display: flex; align-items: center; gap: 4px; }
  .zoom-val { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text-muted); min-width: 44px; text-align: center; }

  .tb-btn { padding: 5px 14px; border-radius: 2px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 0.04em; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
  .tb-btn:hover:not(:disabled) { border-color: var(--border2); color: var(--text); }
  .tb-btn:disabled { color: var(--text-dim); cursor: not-allowed; }
  .tb-save { background: var(--text); color: var(--bg); border-color: var(--text); }
  .tb-save:hover:not(:disabled) { opacity: 0.85; }
  .tb-saving { opacity: 0.5; }
  .tb-ok  { background: #52b788 !important; border-color: #52b788 !important; color: #000 !important; }
  .tb-err { background: #e63946 !important; border-color: #e63946 !important; color: #fff !important; }

  .canvas-area { flex: 1; display: flex; align-items: center; justify-content: center; background: var(--bg); overflow: hidden; position: relative; }
  .pan-wrapper { position: relative; display: inline-flex; align-items: center; justify-content: center; will-change: transform; }
  canvas { display: block; border: 1px solid var(--border); }
  .splash { position: absolute; text-align: center; pointer-events: none; }
  .splash-mark { font-size: 48px; color: var(--text-dim); display: block; margin-bottom: 12px; }
  .splash p { color: var(--text-muted); font-size: 13px; }

  /* Filmstrip */
  .filmstrip { flex-shrink: 0; display: flex; align-items: center; gap: 4px; padding: 0 12px; background: var(--surface); border-top: 1px solid var(--border); overflow-x: auto; scroll-behavior: smooth; }
  .filmstrip::-webkit-scrollbar { height: 3px; }
  .filmstrip::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }
  .thumb { position: relative; flex-shrink: 0; border: 1px solid var(--border); border-radius: 2px; cursor: pointer; overflow: hidden; transition: border-color 0.1s; }
  .thumb:hover { border-color: var(--border2); }
  .thumb.thumb-on { border-color: var(--text) !important; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .thumb-idx { position: absolute; bottom: 2px; right: 4px; font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: #fff; text-shadow: 0 0 3px #000; }

  /* Label popup */
  .label-popup { position: absolute; background: var(--surface); border: 1px solid var(--border2); border-radius: 3px; min-width: 220px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); z-index: 1000; transform: translate(-50%,8px); overflow: hidden; }
  .popup-title { padding: 8px 12px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 9px; font-weight: 600; letter-spacing: 0.1em; color: var(--text-muted); border-bottom: 1px solid var(--border); }
  .label-popup input { margin: 8px 10px; width: calc(100% - 20px); }
  .popup-opt { padding: 8px 12px; cursor: pointer; display: flex; align-items: center; gap: 10px; font-size: 12px; border-left: 3px solid transparent; transition: background 0.1s; }
  .popup-opt:hover { background: var(--surface2); }
  .popup-new { color: #52b788; border-left-color: #52b788 !important; }
  .pop-key { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--text-muted); background: var(--surface3); padding: 1px 5px; border-radius: 2px; min-width: 18px; text-align: center; }
  .popup-empty { padding: 12px; font-size: 11px; color: var(--text-muted); text-align: center; }
  .popup-cancel { width: 100%; padding: 8px; background: transparent; border: none; border-top: 1px solid var(--border); color: var(--text-muted); font-size: 11px; cursor: pointer; font-family: 'IBM Plex Mono', monospace; transition: color 0.1s; }
  .popup-cancel:hover { color: var(--text); }

  /* Modal */
  .modal-back { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 2000; }
  .modal { background: var(--surface); border: 1px solid var(--border2); border-radius: 3px; min-width: 380px; max-width: 480px; box-shadow: 0 16px 48px rgba(0,0,0,0.5); }
  .modal-hdr { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--border); font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; letter-spacing: 0.08em; }
  .hk-grid { display: grid; grid-template-columns: auto 1fr; }
  .hk-grid-key { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; color: var(--text); padding: 7px 16px; white-space: nowrap; border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .hk-grid-desc { padding: 7px 16px; font-size: 12px; color: var(--text-muted); border-bottom: 1px solid var(--border); }

  /* Toast */
  .toast { position: fixed; bottom: 80px; right: 20px; padding: 8px 16px; background: var(--surface2); border: 1px solid var(--border2); border-radius: 2px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text); box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 1500; animation: fadeUp 0.2s ease; }
  .toast-ok  { border-left: 3px solid #52b788; }
  .toast-err { border-left: 3px solid #e63946; }
  @keyframes fadeUp { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
</style>
