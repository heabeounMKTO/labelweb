<script>
  import { onMount } from 'svelte';
  import axios from 'axios';

  const API_URL = 'http://localhost:9100';
  

  let moveDestination = $state('');
  let imageDirectory = $state('');
  let currentDirectory = $state(''); // Track current directory for cache clearing
  let pathsLoaded = $state(false);
  let images = $state([]);
  let currentIndex = $state(0);
  let currentImagePath = $state(null);
  let imageElement = $state(null);
  let canvasElement = $state(null);
  let ctx = $state(null);
  let lastMoved = $state(null);
  let shapes = $state([]);
  let currentShape = $state(null);
  let isDrawing = $state(false);
  let startPoint = $state(null);
  let selectedShapeIndex = $state(-1);
  let showLabels = $state(true);
  
  let currentLabel = $state('');
  let labels = $state([]); // Cached labels for current directory session
  let customLabel = $state('');
  let popupSearchQuery = $state('');
  
  // Derived filtered labels for popup
  let filteredLabels = $derived(
    labels.filter(label => 
      label.toLowerCase().includes(popupSearchQuery.toLowerCase())
    )
  );
  
  let imageWidth = $state(0);
  let imageHeight = $state(0);
  let scale = $state(1);
  let offsetX = $state(0);
  let offsetY = $state(0);
  let minScale = $state(0.1);
  let maxScale = $state(5);
  
  let totalImages = $state(0);
  let saveStatus = $state('');
  let isCanvasHovered = $state(false);
  let showLabelPopup = $state(false);
  let popupPosition = $state({ x: 0, y: 0 });
  let pendingShape = $state(null);
  
  // Color palette for different labels
  const labelColors = [
    '#ff0000', '#00ff00', '#0000ff', '#ffff00', '#ff00ff', '#00ffff',
    '#ff8800', '#88ff00', '#0088ff', '#ff0088', '#8800ff', '#00ff88'
  ];
  
  function getLabelColor(label) {
    const index = labels.indexOf(label);
    return index >= 0 ? labelColors[index % labelColors.length] : '#ff0000';
  }
  
  // Load persisted paths from storage
  async function loadPersistedPaths() {
    try {
      const imagePathResult = await window.storage.get('bbox-image-directory');
      const movePathResult = await window.storage.get('bbox-move-destination');
      if (imagePathResult?.value) {
        imageDirectory = imagePathResult.value;
        console.log('Loaded persisted image directory:', imageDirectory);
      }
      
      if (movePathResult?.value) {
        moveDestination = movePathResult.value;
        console.log('Loaded persisted move destination:', moveDestination);
      }
      
      pathsLoaded = true;
    } catch (error) {
      console.log('No persisted paths found or error loading:', error);
      pathsLoaded = true;
    }
  }
  
  // Persist image directory to storage
  async function persistImageDirectory() {
    try {
      await window.storage.set('bbox-image-directory', imageDirectory);
      console.log('Persisted image directory:', imageDirectory);
    } catch (error) {
      console.error('Failed to persist image directory:', error);
    }
  }
  
  // Persist move destination to storage
  async function persistMoveDestination() {
    try {
      await window.storage.set('bbox-move-destination', moveDestination);
      console.log('Persisted move destination:', moveDestination);
    } catch (error) {
      console.error('Failed to persist move destination:', error);
    }
  }
  
  async function loadImagesFromDirectory() {
    if (!imageDirectory.trim()) {
      alert('Please enter an image directory path');
      return;
    }
    
    // Persist the path
    await persistImageDirectory();
    
    try {
      // Check if directory changed - if so, clear label cache
      if (currentDirectory !== imageDirectory) {
        console.log('New directory detected, clearing label cache');
        labels = [];
        currentLabel = '';
        currentDirectory = imageDirectory;
      }
      
      const response = await axios.get(`${API_URL}/images/all`, {
        params: { image_path: imageDirectory, limit: 10000 }
      });
      images = response.data.images;
      totalImages = response.data.total;
      
      if (images.length > 0) {
        await loadImage(0);
      }
    } catch (error) {
      console.error('Failed to load images:', error);
      alert('Failed to load images from directory. Check the path and try again.');
    }
  }
  
  async function setDestinationDirectory() {
    // Persist the path
    await persistMoveDestination();
    console.log("Destination set to", moveDestination);
  }
  
  onMount(() => {
    console.log('Component mounted');
    // Load persisted paths
    loadPersistedPaths();
    // Setup canvas after a small delay to ensure DOM is ready
    setTimeout(() => {
      setupCanvas();
    }, 100);
  });
  
  async function loadImage(index) {
    if (index < 0 || index >= images.length) return;
    
    currentIndex = index;
    currentImagePath = images[index];
    shapes = [];
    selectedShapeIndex = -1;
    imageWidth = 0;
    imageHeight = 0;
    imageElement = null;
    
    console.log('Loading image:', currentImagePath);
    
    // Load annotation first
    let loadedShapes = [];
    try {
      const response = await axios.get(`${API_URL}/annotation/load`, {
        params: { image_path: currentImagePath }
      });
      
      if (response.data) {
        loadedShapes = response.data.shapes || [];
        
        // Cache unique labels from loaded shapes (add to session cache if not exists)
        loadedShapes.forEach(shape => {
          if (shape.label && !labels.includes(shape.label)) {
            console.log('Adding new label to cache:', shape.label);
            labels = [...labels, shape.label];
          }
        });
        
        console.log('Loaded annotation with', loadedShapes.length, 'shapes');
      }
    } catch (error) {
      console.error('Failed to load annotation:', error);
    }
    
    // Load image and wait for it to complete
    const imageUrl = `${API_URL}/images/single?image_path=${encodeURIComponent(currentImagePath)}`;
    console.log('Loading image from:', imageUrl);
    
    const img = new Image();
    img.crossOrigin = "anonymous";
    
    // Use a promise to ensure image loads before continuing
    await new Promise((resolve, reject) => {
      img.onload = () => {
        console.log('Image loaded successfully:', img.width, 'x', img.height);
        imageElement = img;
        imageWidth = img.width;
        imageHeight = img.height;
        resolve();
      };
      img.onerror = (e) => {
        console.error('Failed to load image:', e);
        console.error('Image URL was:', imageUrl);
        reject(e);
      };
      img.src = imageUrl;
    });
    
    // Now set shapes after image is loaded
    shapes = loadedShapes;
    
    // Wait a bit for DOM to update, then fit and draw
    await new Promise(resolve => setTimeout(resolve, 50));
    
    if (!canvasElement) {
      console.error('Canvas not ready after image load');
      setupCanvas();
    }
    
    fitImageToCanvas();
    redraw();
  }
  
  function setupCanvas() {
    console.log('Setting up canvas, element:', canvasElement);
    if (!canvasElement) {
      console.error('Canvas element not found!');
      return;
    }
    ctx = canvasElement.getContext('2d');
    console.log('Canvas context:', ctx);
    
    canvasElement.addEventListener('mousedown', handleMouseDown);
    canvasElement.addEventListener('mousemove', handleMouseMove);
    canvasElement.addEventListener('mouseup', handleMouseUp);
  }
  
  function fitImageToCanvas() {
    if (!imageElement || !canvasElement) return;
    
    const containerWidth = canvasElement.parentElement.clientWidth;
    const containerHeight = canvasElement.parentElement.clientHeight;
    
    const scaleX = containerWidth / imageWidth;
    const scaleY = containerHeight / imageHeight;
    minScale = Math.min(scaleX, scaleY, 1);
    scale = minScale;
    
    canvasElement.width = imageWidth * scale;
    canvasElement.height = imageHeight * scale;
    
    offsetX = 0;
    offsetY = 0;
  }
  
  function zoomIn() {
    scale = Math.min(scale * 1.2, maxScale);
    redraw();
  }
  
  function zoomOut() {
    scale = Math.max(scale / 1.2, minScale);
    redraw();
  }
  
  function resetZoom() {
    fitImageToCanvas();
    redraw();
  }
  
  function screenToImage(x, y) {
    const rect = canvasElement.getBoundingClientRect();
    const canvasX = x - rect.left;
    const canvasY = y - rect.top;
    return {
      x: (canvasX - offsetX) / scale,
      y: (canvasY - offsetY) / scale
    };
  }
  
  function handleMouseDown(e) {
    const point = screenToImage(e.clientX, e.clientY);
    
    // Check if clicking on existing shape
    selectedShapeIndex = -1;
    for (let i = shapes.length - 1; i >= 0; i--) {
      const shape = shapes[i];
      const [p1, p2] = shape.points;
      const minX = Math.min(p1[0], p2[0]);
      const maxX = Math.max(p1[0], p2[0]);
      const minY = Math.min(p1[1], p2[1]);
      const maxY = Math.max(p1[1], p2[1]);
      
      if (point.x >= minX && point.x <= maxX && point.y >= minY && point.y <= maxY) {
        selectedShapeIndex = i;
        redraw();
        return;
      }
    }
    
    // Start drawing new box
    isDrawing = true;
    startPoint = point;
    currentShape = {
      label: currentLabel,
      points: [[point.x, point.y], [point.x, point.y]],
      shape_type: 'rectangle',
      flags: {},
      group_id: null
    };
  }
  
  function handleMouseMove(e) {
    if (!isDrawing || !currentShape) return;
    
    const point = screenToImage(e.clientX, e.clientY);
    currentShape.points[1] = [point.x, point.y];
    redraw();
  }
  
  function handleMouseUp(e) {
    if (!isDrawing || !currentShape) return;
    
    const point = screenToImage(e.clientX, e.clientY);
    currentShape.points[1] = [point.x, point.y];
    
    // Only add if box has minimum size
    const width = Math.abs(currentShape.points[1][0] - currentShape.points[0][0]);
    const height = Math.abs(currentShape.points[1][1] - currentShape.points[0][1]);
    
    if (width > 5 && height > 5) {
      // Show label selection popup
      const rect = canvasElement.getBoundingClientRect();
      popupPosition = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      pendingShape = currentShape;
      showLabelPopup = true;
    }
    
    isDrawing = false;
    currentShape = null;
    redraw();
  }
  
  function selectLabelForShape(label) {
    if (pendingShape) {
      pendingShape.label = label;
      shapes = [...shapes, pendingShape];
      
      // Cache label for this directory session if it doesn't exist
      if (!labels.includes(label)) {
        console.log('Caching new label for session:', label);
        labels = [...labels, label];
      }
      
      redraw();
    }
    showLabelPopup = false;
    pendingShape = null;
    popupSearchQuery = '';
  }
  
  function cancelLabelSelection() {
    showLabelPopup = false;
    pendingShape = null;
    popupSearchQuery = '';
  }
  
  function addLabelFromPopup() {
    if (popupSearchQuery.trim()) {
      selectLabelForShape(popupSearchQuery.trim());
    }
  }
  
  function redraw() {
    if (!ctx || !imageElement) {
      console.log('Cannot redraw - ctx:', !!ctx, 'imageElement:', !!imageElement, 'canvas:', !!canvasElement);
      return;
    }
    
    console.log('Redrawing canvas:', canvasElement.width, 'x', canvasElement.height);
    
    ctx.clearRect(0, 0, canvasElement.width, canvasElement.height);
    
    // Draw image
    try {
      ctx.drawImage(imageElement, offsetX, offsetY, imageWidth * scale, imageHeight * scale);
      console.log('Drew image at scale:', scale);
    } catch (e) {
      console.error('Error drawing image:', e);
    }
    
    // Draw shapes with different colors
    shapes.forEach((shape, index) => {
      const [p1, p2] = shape.points;
      const x = Math.min(p1[0], p2[0]) * scale + offsetX;
      const y = Math.min(p1[1], p2[1]) * scale + offsetY;
      const w = Math.abs(p2[0] - p1[0]) * scale;
      const h = Math.abs(p2[1] - p1[1]) * scale;
      
      // Draw box with label-specific color
      const color = getLabelColor(shape.label);
      ctx.strokeStyle = index === selectedShapeIndex ? '#ffffff' : color;
      ctx.lineWidth = index === selectedShapeIndex ? 3 : 2;
      ctx.strokeRect(x, y, w, h);
      
      // Draw label with background
      if (showLabels) {
        ctx.fillStyle = color;
        ctx.font = '14px Arial';
        
        // Build label text with confidence if available
        let labelText = shape.label;
        if (shape.group_id) {
          const confidence = parseFloat(shape.group_id);
          if (!isNaN(confidence)) {
            labelText += ` ${(confidence * 100).toFixed(1)}%`;
          }
        }
        
        const textWidth = ctx.measureText(labelText).width;
        ctx.fillRect(x, y - 20, textWidth + 8, 18);
        ctx.fillStyle = '#000';
        ctx.fillText(labelText, x + 4, y - 6);
      }
    });
    
    // Draw current shape
    if (currentShape) {
      const [p1, p2] = currentShape.points;
      const x = Math.min(p1[0], p2[0]) * scale + offsetX;
      const y = Math.min(p1[1], p2[1]) * scale + offsetY;
      const w = Math.abs(p2[0] - p1[0]) * scale;
      const h = Math.abs(p2[1] - p1[1]) * scale;
      
      ctx.strokeStyle = '#ffff00';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);
    }
  }
  
async function undoMove() {
    if (!lastMoved) {
        console.log("No move to undo");
        return;
    }
    
    console.log("Undoing move:", lastMoved);
    
    try {
        let origDirPath = lastMoved.original_img.split('/').slice(0, -1).join('/');
        console.log("Moving back to:", origDirPath);
        
        // Use params instead of body
        let _undo = await axios.post(`${API_URL}/move`, null, {
            params: {
                destination_path: origDirPath,
                image_path: lastMoved.dest_img
            }
        });
        
        console.log("Undo successful:", _undo.data);
        
        const restoredPath = lastMoved.original_img;
        lastMoved = null;
        
        await loadImagesFromDirectory();
        currentImagePath = restoredPath;
        
    } catch (error) {
        console.error("Undo failed:", error);
        alert("Failed to undo move");
    }
}
async function saveAnnotation() {
    if (!currentImagePath) return;

    let move_dest_path = null;
    if (moveDestination !== "") {
        move_dest_path = moveDestination;
    }

    try {
        saveStatus = 'Saving...';

        let _move = await axios.post(`${API_URL}/annotation`, {
            shapes: shapes,
            imagePath: currentImagePath,
            imageHeight: imageHeight,
            imageWidth: imageWidth
        }, {
            params: { image_path: currentImagePath, dest_path: move_dest_path }
        });
        
        console.log("Save response:", _move.data);
        
        // Only set lastMoved if there was actually a move
        if (_move.data?.move_data && move_dest_path) {
            lastMoved = {
                dest_img: _move.data.move_data.dest_img,
                dest_json: _move.data.move_data.dest_json,
                original_json: _move.data.move_data.orig_json,
                original_img: _move.data.move_data.orig_img
            };
            console.log("lastMoved set to:", lastMoved);
        } else {
            console.log("No move performed, lastMoved unchanged");
        }
        
        saveStatus = '✓ Saved';
        setTimeout(() => saveStatus = '', 2000);
        
        await loadImagesFromDirectory();
        
    } catch (error) {
        console.error('Failed to save annotation:', error);
        saveStatus = '✗ Error';
        setTimeout(() => saveStatus = '', 2000);
    }
}
  
  function nextImage() {
    if (currentIndex < images.length - 1) {
      loadImage(currentIndex + 1);
    }
  }
  
  function prevImage() {
    if (currentIndex > 0) {
      loadImage(currentIndex - 1);
    }
  }
  
  function deleteSelected() {
    if (selectedShapeIndex >= 0) {
      shapes = shapes.filter((_, i) => i !== selectedShapeIndex);
      selectedShapeIndex = -1;
      redraw();
    }
  }
  
  function duplicateSelected() {
    if (selectedShapeIndex >= 0) {
      const shape = shapes[selectedShapeIndex];
      const newShape = {
        ...shape,
        points: shape.points.map(p => [p[0] + 10, p[1] + 10])
      };
      shapes = [...shapes, newShape];
      redraw();
    }
  }
  
  function addCustomLabel() {
    if (customLabel && !labels.includes(customLabel)) {
      labels = [...labels, customLabel];
      currentLabel = customLabel;
      customLabel = '';
    }
  }
  
  // Keyboard shortcuts - only when canvas is hovered
  function handleKeydown(e) {
    // Only handle shortcuts when canvas is hovered or popup is open
    if (!isCanvasHovered && !showLabelPopup) return;
    
    // Close popup with Escape
    if (showLabelPopup && e.key === 'Escape') {
      e.preventDefault();
      cancelLabelSelection();
      return;
    }
    
    // Number keys for label selection in popup
    if (showLabelPopup && e.key >= '1' && e.key <= '9') {
      e.preventDefault();
      const index = parseInt(e.key) - 1;
      if (index < filteredLabels.length) {
        selectLabelForShape(filteredLabels[index]);
      }
      return;
    }
    
    // Enter key to add new label in popup
    if (showLabelPopup && e.key === 'Enter') {
      e.preventDefault();
      addLabelFromPopup();
      return;
    }
    
    // Prevent defaults for our shortcuts
    if (['d', 'a', 's', 'e', ' ', '+', '-', '0'].includes(e.key.toLowerCase()) || 
        (e.ctrlKey && ['s', 'd'].includes(e.key.toLowerCase()))) {
      e.preventDefault();
    }
    
    switch(e.key.toLowerCase()) {
      case 'd':
        if (!e.ctrlKey) nextImage();
        else duplicateSelected();
        break;
      case 'a':
        if (!e.ctrlKey) prevImage();
        break;
      case 's':
        if (e.ctrlKey) saveAnnotation();
        break;
      case 'escape':
        isDrawing = false;
        currentShape = null;
        selectedShapeIndex = -1;
        redraw();
        break;
      case 'delete':
        deleteSelected();
        break;
      case ' ':
        showLabels = !showLabels;
        redraw();
        break;
      case '+':
      case '=':
        zoomIn();
        break;
      case '-':
      case '_':
        zoomOut();
        break;
      case '0':
        resetZoom();
        break;
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="app">
  <div class="sidebar">
    <h1>Bbox Annotator</h1>
    
    <div class="section">
      <h3>Image Directory</h3>
      <input 
        type="text" 
        bind:value={imageDirectory}
        placeholder="/path/to/images"
        onkeydown={(e) => e.key === 'Enter' && loadImagesFromDirectory()}
      />
      <button onclick={loadImagesFromDirectory} class="load-btn">
        Load Directory
      </button>
      <input 
        type="text" 
        bind:value={moveDestination}
        placeholder="/path/to/move"
        onkeydown={(e) => e.key === 'Enter' && setDestinationDirectory()}
      />
      <button onclick={setDestinationDirectory} class="load-btn">
        Set Move Directory
      </button>
    </div>
    
    {#if images.length > 0}
      <div class="stats">
        <div class="stat-item">
          <span class="stat-label">Total:</span>
          <span class="stat-value">{totalImages}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Current:</span>
          <span class="stat-value">{currentIndex + 1}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Shapes:</span>
          <span class="stat-value">{shapes.length}</span>
        </div>
      </div>
    {/if}
    
    <div class="section">
      <h3>Labels ({labels.length})</h3>
      {#if labels.length > 0}
        <select bind:value={currentLabel}>
          <option value="">-- Select --</option>
          {#each labels as label}
            <option value={label}>{label}</option>
          {/each}
        </select>
      {:else}
        <p class="no-labels">No labels yet. Draw a bbox to add one!</p>
      {/if}
      
      <div class="custom-label">
        <input 
          type="text" 
          bind:value={customLabel}
          placeholder="Add new label"
          onkeydown={(e) => e.key === 'Enter' && addCustomLabel()}
        />
        <button onclick={addCustomLabel}>Add</button>
      </div>
    </div>
    
    <div class="section">
      <h3>Shapes ({shapes.length})</h3>
      <div class="shapes-list">
        {#each shapes as shape, i}
          <div 
            class="shape-item" 
            class:selected={i === selectedShapeIndex}
            onclick={() => { selectedShapeIndex = i; redraw(); }}
          >
            <div class="shape-label">{shape.label}</div>
            {#if shape.group_id}
              <div class="shape-confidence">
                {(parseFloat(shape.group_id) * 100).toFixed(1)}%
              </div>
            {/if}
          </div>
        {/each}
      </div>
      
      {#if shapes.length > 0}
        <div class="shape-stats">
          <h4>Statistics</h4>
          {#each Object.entries(shapes.reduce((acc, s) => {
            acc[s.label] = (acc[s.label] || 0) + 1;
            return acc;
          }, {})) as [label, count]}
            <div class="stat-row">
              <span class="stat-color" style:background-color={getLabelColor(label)}></span>
              <span class="stat-label">{label}</span>
              <span class="stat-count">{count}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
    
    <div class="section">
      <h3>Hotkeys</h3>
      <div class="hotkeys">
        <div><kbd>D</kbd> Next image</div>
        <div><kbd>A</kbd> Previous image</div>
        <div><kbd>Ctrl+S</kbd> Save</div>
        <div><kbd>Esc</kbd> Cancel</div>
        <div><kbd>Del</kbd> Delete</div>
        <div><kbd>Ctrl+D</kbd> Duplicate</div>
        <div><kbd>Space</kbd> Toggle labels</div>
        <div><kbd>+/-</kbd> Zoom in/out</div>
        <div><kbd>0</kbd> Reset zoom</div>
        <div><kbd>1-9</kbd> Quick label</div>
      </div>
    </div>
  </div>
  
  <div class="main">
    <div class="toolbar">
      <button onclick={prevImage} disabled={currentIndex === 0 || images.length === 0}>
        ← Previous (A)
      </button>
      <span class="image-info">
        {#if currentImagePath}
          {currentIndex + 1} / {totalImages} - {currentImagePath.split('/').pop()}
        {:else}
          No image loaded
        {/if}
      </span>
      <button onclick={nextImage} disabled={currentIndex === images.length - 1 || images.length === 0}>
        Next (D) →
      </button>
      
      <div class="zoom-controls">
        <button onclick={zoomOut} disabled={!currentImagePath} title="Zoom Out (-)">-</button>
        <span class="zoom-level">{Math.round(scale * 100)}%</span>
        <button onclick={zoomIn} disabled={!currentImagePath} title="Zoom In (+)">+</button>
        <button onclick={resetZoom} disabled={!currentImagePath} title="Reset Zoom (0)">⟲</button>
      </div>

      <button onclick={undoMove} class="undo-btn" disabled={!currentImagePath}>
        {lastMoved ? 'UNDO' : 'No last moved!'}
      </button>

      <button onclick={saveAnnotation} class="save-btn" disabled={!currentImagePath}>
        {saveStatus || 'Save (Ctrl+S)'}
      </button>
    </div>
    
    <div class="canvas-container">
      {#if !currentImagePath}
        <div class="empty-state">
          <p>👆 Enter a directory path and click "Load Directory" to start annotating</p>
        </div>
      {/if}
      <div class="canvas-wrapper">
        <canvas 
          bind:this={canvasElement}
          style:display={currentImagePath ? 'block' : 'none'}
          onmouseenter={() => isCanvasHovered = true}
          onmouseleave={() => isCanvasHovered = false}
        ></canvas>
        
        {#if showLabelPopup}
          <div 
            class="label-popup"
            style:left="{popupPosition.x}px"
            style:top="{popupPosition.y}px"
          >
            <div class="popup-header">Select or Add Label</div>
            <div class="popup-search">
              <input 
                type="text"
                bind:value={popupSearchQuery}
                placeholder="Search or type new label..."
                onkeydown={(e) => {
                  if (e.key === 'Enter') addLabelFromPopup();
                  e.stopPropagation();
                }}
                autofocus
              />
            </div>
            
            {#if popupSearchQuery.trim() && !labels.includes(popupSearchQuery.trim())}
              <div 
                class="label-option new-label"
                onclick={() => selectLabelForShape(popupSearchQuery.trim())}
              >
                <span class="label-number">+</span>
                Add "{popupSearchQuery.trim()}"
              </div>
            {/if}
            
            {#if filteredLabels.length > 0}
              {#each filteredLabels.slice(0, 9) as label, index}
                <div 
                  class="label-option"
                  style:border-left="4px solid {getLabelColor(label)}"
                  onclick={() => selectLabelForShape(label)}
                >
                  <span class="label-number">{index + 1}</span>
                  {label}
                </div>
              {/each}
            {:else if !popupSearchQuery.trim()}
              <div class="no-labels-popup">Start typing to add a label</div>
            {/if}
            
            <div class="popup-footer">
              <button onclick={cancelLabelSelection}>Cancel (Esc)</button>
            </div>
          </div>
        {/if}
      </div>
    </div>
  </div>
</div>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: #1a1a1a;
    color: #fff;
  }
  
  .app {
    display: flex;
    height: 100vh;
    overflow: hidden;
  }
  
  .sidebar {
    width: 280px;
    background: #2a2a2a;
    padding: 20px;
    overflow-y: auto;
    border-right: 1px solid #3a3a3a;
  }
  
  h1 {
    margin: 0 0 20px 0;
    font-size: 24px;
    color: #4a9eff;
  }
  
  h3 {
    margin: 0 0 10px 0;
    font-size: 14px;
    color: #aaa;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  
  .stats {
    background: #1a1a1a;
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 20px;
  }
  
  .stat-item {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  
  .stat-label {
    color: #999;
  }
  
  .stat-value {
    color: #4a9eff;
    font-weight: bold;
  }
  
  .section {
    margin-bottom: 25px;
  }
  
  select, input {
    width: 100%;
    padding: 8px;
    background: #1a1a1a;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    color: #fff;
    font-size: 14px;
    box-sizing: border-box;
  }
  
  .load-btn {
    width: 100%;
    margin-top: 10px;
    background: #9b59b6;
  }
  
  .load-btn:hover {
    background: #8e44ad;
  }
  
  .custom-label {
    display: flex;
    gap: 5px;
    margin-top: 10px;
  }
  
  .custom-label input {
    flex: 1;
  }
  
  .custom-label button {
    padding: 8px 12px;
  }
  
  .shapes-list {
    max-height: 200px;
    overflow-y: auto;
    background: #1a1a1a;
    border-radius: 4px;
    padding: 5px;
  }
  
  .shape-item {
    padding: 8px;
    margin-bottom: 2px;
    background: #2a2a2a;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.2s;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .shape-item:hover {
    background: #3a3a3a;
  }
  
  .shape-item.selected {
    background: #4a9eff;
    color: #000;
  }
  
  .shape-label {
    flex: 1;
  }
  
  .shape-confidence {
    background: rgba(0, 0, 0, 0.3);
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
    color: #4aff9e;
  }
  
  .shape-item.selected .shape-confidence {
    background: rgba(0, 0, 0, 0.2);
    color: #000;
  }
  
  .shape-stats {
    margin-top: 15px;
    padding: 10px;
    background: #1a1a1a;
    border-radius: 4px;
  }
  
  .shape-stats h4 {
    margin: 0 0 10px 0;
    font-size: 12px;
    color: #aaa;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  
  .stat-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    font-size: 13px;
  }
  
  .stat-color {
    width: 12px;
    height: 12px;
    border-radius: 2px;
  }
  
  .stat-label {
    flex: 1;
    color: #ccc;
  }
  
  .stat-count {
    background: #2a2a2a;
    padding: 2px 8px;
    border-radius: 3px;
    font-weight: bold;
    color: #4a9eff;
    font-size: 12px;
  }
  
  .hotkeys {
    font-size: 12px;
    line-height: 1.8;
  }
  
  kbd {
    background: #1a1a1a;
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid #3a3a3a;
    font-family: monospace;
    color: #4a9eff;
  }
  
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  
  .toolbar {
    background: #2a2a2a;
    padding: 15px;
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid #3a3a3a;
  }
  
  .image-info {
    flex: 1;
    text-align: center;
    font-size: 14px;
    color: #aaa;
  }
  
  button {
    background: #4a9eff;
    color: #fff;
    border: none;
    padding: 10px 20px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    transition: background 0.2s;
  }
  
  button:hover:not(:disabled) {
    background: #3a8eef;
  }
  
  button:disabled {
    background: #3a3a3a;
    color: #666;
    cursor: not-allowed;
  }
  
  .save-btn {
    background: #2ecc71;
  }
    .undo-btn {
    background: #a2a2a;
  }
  
  .save-btn:hover:not(:disabled) {
    background: #27ae60;
  }
  
  .canvas-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #1a1a1a;
    padding: 20px;
    overflow: hidden;
    position: relative;
  }
  
  .canvas-wrapper {
    position: relative;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .empty-state {
    text-align: center;
    color: #666;
    font-size: 18px;
    position: absolute;
  }
  
  canvas {
    border: 1px solid #3a3a3a;
    cursor: crosshair;
  }
  
  .zoom-controls {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 0 10px;
    border-left: 1px solid #3a3a3a;
    border-right: 1px solid #3a3a3a;
  }
  
  .zoom-level {
    min-width: 50px;
    text-align: center;
    color: #aaa;
    font-size: 13px;
  }
  
  .label-popup {
    position: absolute;
    background: #2a2a2a;
    border: 2px solid #4a9eff;
    border-radius: 8px;
    padding: 0;
    min-width: 250px;
    max-width: 350px;
    max-height: 500px;
    overflow-y: auto;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    z-index: 1000;
    transform: translate(-50%, 10px);
  }
  
  .popup-header {
    background: #4a9eff;
    color: #fff;
    padding: 10px;
    font-weight: bold;
    text-align: center;
    border-radius: 6px 6px 0 0;
  }
  
  .popup-search {
    padding: 10px;
    border-bottom: 1px solid #3a3a3a;
  }
  
  .popup-search input {
    width: 100%;
    padding: 8px;
    background: #1a1a1a;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    color: #fff;
    font-size: 14px;
  }
  
  .popup-search input:focus {
    outline: none;
    border-color: #4a9eff;
  }
  
  .label-option {
    padding: 10px 15px;
    cursor: pointer;
    transition: background 0.2s;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  
  .label-option:hover {
    background: #3a3a3a;
  }
  
  .label-option.new-label {
    background: #1a3a1a;
    color: #4aff9e;
    border-left: 4px solid #4aff9e !important;
  }
  
  .label-option.new-label:hover {
    background: #2a4a2a;
  }
  
  .label-number {
    background: #1a1a1a;
    color: #4a9eff;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 12px;
    font-weight: bold;
    min-width: 20px;
    text-align: center;
  }
  
  .no-labels-popup {
    padding: 20px;
    text-align: center;
    color: #666;
    font-style: italic;
  }
  
  .no-labels {
    padding: 10px;
    text-align: center;
    color: #666;
    font-size: 13px;
    font-style: italic;
    background: #1a1a1a;
    border-radius: 4px;
  }
  
  .popup-footer {
    padding: 10px;
    border-top: 1px solid #3a3a3a;
    text-align: center;
  }
  
  .popup-footer button {
    width: 100%;
    background: #555;
  }
  
  .popup-footer button:hover {
    background: #666;
  }
</style>
