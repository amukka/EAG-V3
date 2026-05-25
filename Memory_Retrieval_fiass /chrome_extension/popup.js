const API_URL = 'http://localhost:5050/api';
let selectedFiles = [];

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const statusIndicator = document.getElementById('status-indicator');
  const msgArea = document.getElementById('message-area');
  const tabs = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');
  
  // File elements
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const fileList = document.getElementById('file-list');
  const indexFilesBtn = document.getElementById('index-files-btn');
  
  // Sandbox elements
  const sandboxFileList = document.getElementById('sandbox-file-list');
  const indexSandboxBtn = document.getElementById('index-sandbox-btn');
  const refreshSandboxBtn = document.getElementById('refresh-sandbox-btn');
  let selectedSandboxFiles = [];
  
  // URL elements
  const urlInput = document.getElementById('url-input');
  const indexUrlBtn = document.getElementById('index-url-btn');
  
  // Stats elements
  const refreshStatsBtn = document.getElementById('refresh-stats-btn');
  const statDocs = document.getElementById('stat-docs');
  const statChunks = document.getElementById('stat-chunks');

  // Check connection on load
  checkConnection();

  // Tab switching
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));
      
      tab.classList.add('active');
      document.getElementById(`${tab.dataset.tab}-tab`).classList.add('active');

      if (tab.dataset.tab === 'stats') {
        fetchStats();
      } else if (tab.dataset.tab === 'sandbox') {
        fetchSandboxFiles();
      }
    });
  });

  // --- FILE HANDLING ---
  fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
  });

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
      handleFiles(e.dataTransfer.files);
    }
  });

  function handleFiles(files) {
    Array.from(files).forEach(file => {
      if (!selectedFiles.find(f => f.name === file.name)) {
        selectedFiles.push(file);
      }
    });
    renderFileList();
  }

  function renderFileList() {
    fileList.innerHTML = '';
    selectedFiles.forEach((file, index) => {
      const el = document.createElement('div');
      el.className = 'file-item';
      el.innerHTML = `
        <span class="file-name" title="${file.name}">${file.name}</span>
        <span class="remove-file" data-index="${index}">✕</span>
      `;
      fileList.appendChild(el);
    });

    indexFilesBtn.disabled = selectedFiles.length === 0;

    document.querySelectorAll('.remove-file').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const idx = parseInt(e.target.dataset.index);
        selectedFiles.splice(idx, 1);
        renderFileList();
      });
    });
  }

  // --- INDEXING (Files) ---
  indexFilesBtn.addEventListener('click', async () => {
    if (selectedFiles.length === 0) return;
    
    indexFilesBtn.disabled = true;
    indexFilesBtn.textContent = 'Indexing...';
    let successCount = 0;
    
    for (const file of selectedFiles) {
      try {
        showMessage(`Reading ${file.name}...`, 'info');
        const content = await readFileAsText(file);
        
        showMessage(`Indexing ${file.name}...`, 'info');
        const res = await fetch(`${API_URL}/index`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: file.name,
            content: content
          })
        });
        
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        successCount++;
        
      } catch (err) {
        showMessage(`Failed to index ${file.name}: ${err.message}`, 'error');
        indexFilesBtn.disabled = false;
        indexFilesBtn.textContent = 'Index Selected Files';
        return; // Stop on first error
      }
    }
    
    showMessage(`Successfully indexed ${successCount} file(s)!`, 'success');
    selectedFiles = [];
    renderFileList();
    indexFilesBtn.disabled = false;
    indexFilesBtn.textContent = 'Index Selected Files';
  });

  function readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = (e) => reject(new Error('File reading failed'));
      reader.readAsText(file);
    });
  }

  // --- INDEXING (URL) ---
  indexUrlBtn.addEventListener('click', async () => {
    const url = urlInput.value.trim();
    if (!url) {
      showMessage('Please enter a valid URL', 'error');
      return;
    }
    
    indexUrlBtn.disabled = true;
    indexUrlBtn.textContent = 'Fetching & Indexing...';
    showMessage('Crawling URL...', 'info');
    
    try {
      const res = await fetch(`${API_URL}/index-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url })
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      
      showMessage(`Successfully indexed ${data.filename}!`, 'success');
      urlInput.value = '';
    } catch (err) {
      showMessage(`Error: ${err.message}`, 'error');
    } finally {
      indexUrlBtn.disabled = false;
      indexUrlBtn.textContent = 'Index URL via Crawl4AI';
    }
  });

  // --- SANDBOX FILES ---
  async function fetchSandboxFiles() {
    sandboxFileList.innerHTML = '<div class="sandbox-loading">Loading sandbox files...</div>';
    try {
      const res = await fetch(`${API_URL}/sandbox-files`);
      if (!res.ok) throw new Error('API server returned error');
      const data = await res.json();
      renderSandboxFileList(data.files || []);
    } catch (err) {
      sandboxFileList.innerHTML = `<div class="sandbox-error">Error loading files: ${err.message}</div>`;
    }
  }

  function renderSandboxFileList(files) {
    sandboxFileList.innerHTML = '';
    if (files.length === 0) {
      sandboxFileList.innerHTML = '<div class="sandbox-empty">No files found in sandbox</div>';
      indexSandboxBtn.disabled = true;
      return;
    }

    files.forEach(file => {
      const el = document.createElement('div');
      el.className = 'sandbox-file-item';
      
      const isChecked = selectedSandboxFiles.includes(file);
      // Show crawl button for markdown files that are not already crawled files
      const isCrawlable = file.endsWith('.md') && !file.includes('_crawled');
      
      el.innerHTML = `
        <div class="sandbox-file-info">
          <input type="checkbox" class="sandbox-file-checkbox" data-file="${file}" ${isChecked ? 'checked' : ''}>
          <span class="sandbox-file-name" title="${file}">${file}</span>
        </div>
        ${isCrawlable ? `<button class="crawl-btn" data-file="${file}">Crawl</button>` : ''}
      `;
      sandboxFileList.appendChild(el);
    });

    updateIndexSandboxBtn();

    // Event listener for checkboxes
    document.querySelectorAll('.sandbox-file-checkbox').forEach(checkbox => {
      checkbox.addEventListener('change', (e) => {
        const file = e.target.dataset.file;
        if (e.target.checked) {
          if (!selectedSandboxFiles.includes(file)) {
            selectedSandboxFiles.push(file);
          }
        } else {
          selectedSandboxFiles = selectedSandboxFiles.filter(f => f !== file);
        }
        updateIndexSandboxBtn();
      });
    });

    // Event listener for crawl buttons
    document.querySelectorAll('.crawl-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const file = e.target.dataset.file;
        btn.disabled = true;
        btn.textContent = 'Crawling...';
        btn.classList.add('crawling');
        showMessage(`Crawling links in ${file} via Crawl4AI...`, 'info');

        try {
          const res = await fetch(`${API_URL}/crawl-file`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: file })
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || 'Crawl failed');

          showMessage(`Successfully crawled! Saved as ${data.filename}`, 'success');
          
          // Auto-select the newly created crawled file
          if (!selectedSandboxFiles.includes(data.filename)) {
            selectedSandboxFiles.push(data.filename);
          }
          // Refresh the sandbox file list
          await fetchSandboxFiles();
        } catch (err) {
          showMessage(`Failed to crawl: ${err.message}`, 'error');
          btn.disabled = false;
          btn.textContent = 'Crawl';
          btn.classList.remove('crawling');
        }
      });
    });
  }

  function updateIndexSandboxBtn() {
    indexSandboxBtn.disabled = selectedSandboxFiles.length === 0;
  }

  indexSandboxBtn.addEventListener('click', async () => {
    if (selectedSandboxFiles.length === 0) return;
    
    indexSandboxBtn.disabled = true;
    indexSandboxBtn.textContent = 'Indexing...';
    let successCount = 0;
    
    for (const file of selectedSandboxFiles) {
      try {
        showMessage(`Indexing ${file}...`, 'info');
        const res = await fetch(`${API_URL}/index-sandbox`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: file })
        });
        
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        successCount++;
      } catch (err) {
        showMessage(`Failed to index ${file}: ${err.message}`, 'error');
        indexSandboxBtn.disabled = false;
        indexSandboxBtn.textContent = 'Index Selected Files';
        return;
      }
    }
    
    showMessage(`Successfully indexed ${successCount} sandbox file(s)!`, 'success');
    selectedSandboxFiles = [];
    indexSandboxBtn.disabled = false;
    indexSandboxBtn.textContent = 'Index Selected Files';
    await fetchSandboxFiles();
    fetchStats();
  });

  refreshSandboxBtn.addEventListener('click', fetchSandboxFiles);

  // --- STATS ---
  refreshStatsBtn.addEventListener('click', fetchStats);

  async function fetchStats() {
    statDocs.textContent = '...';
    statChunks.textContent = '...';
    try {
      const res = await fetch(`${API_URL}/status`);
      if (!res.ok) throw new Error('API unreachable');
      const data = await res.json();
      
      statDocs.textContent = data.indexed_documents;
      statChunks.textContent = data.total_chunks;
      
      statusIndicator.className = 'status-online';
      statusIndicator.title = 'Connected';
    } catch (err) {
      statDocs.textContent = 'Error';
      statChunks.textContent = 'Error';
      statusIndicator.className = 'status-offline';
      statusIndicator.title = 'Disconnected';
      showMessage('Failed to connect to backend', 'error');
    }
  }

  // --- UTILS ---
  async function checkConnection() {
    try {
      const res = await fetch(`${API_URL}/status`);
      if (res.ok) {
        statusIndicator.className = 'status-online';
        statusIndicator.title = 'Connected to Backend';
      } else {
        throw new Error();
      }
    } catch (e) {
      statusIndicator.className = 'status-offline';
      statusIndicator.title = 'Backend Offline';
      showMessage('Backend API offline. Is api_server.py running?', 'error');
    }
  }

  function showMessage(msg, type) {
    msgArea.textContent = msg;
    msgArea.className = `message-area msg-${type}`;
    if (type === 'success' || type === 'error') {
      setTimeout(() => {
        msgArea.textContent = '';
      }, 5000);
    }
  }
});
