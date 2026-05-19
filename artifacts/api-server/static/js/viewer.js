(function() {
  let viewerImages = [];
  let viewerIdx = 0;
  let viewerOpen_ = false;

  window.viewerOpen = function(src, opts) {
    opts = opts || {};
    const overlay = document.getElementById('viewer-overlay');
    const img = document.getElementById('viewer-img');
    const articleEl = document.getElementById('viewer-article');
    const filenameEl = document.getElementById('viewer-filename');
    const infoEl = document.getElementById('viewer-info');
    const errorsEl = document.getElementById('viewer-errors');
    const origLink = document.getElementById('viewer-orig-link');

    viewerImages = opts.allImages || [{src}];
    viewerIdx = typeof opts.currentIdx === 'number' ? opts.currentIdx : 0;

    function showCurrent() {
      const current = viewerImages[viewerIdx] || {src};
      img.style.opacity = '0';
      img.src = current.src;
      img.onload = () => { img.style.opacity = '1'; };
    }

    articleEl.textContent = opts.article ? ('Артикул: ' + opts.article) : '';
    filenameEl.textContent = opts.filename || '';
    const dims = (opts.width && opts.height) ? (opts.width + '×' + opts.height + ' px') : '';
    const size = opts.size ? formatSize(opts.size) : '';
    infoEl.textContent = [dims, size].filter(Boolean).join(' · ');
    errorsEl.textContent = (opts.errors || []).join(' · ');
    origLink.href = opts.origUrl || src;

    showCurrent();
    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
    viewerOpen_ = true;
    document.body.style.overflow = 'hidden';
  };

  window.closeViewer = function() {
    const overlay = document.getElementById('viewer-overlay');
    overlay.classList.add('hidden');
    overlay.classList.remove('flex');
    viewerOpen_ = false;
    document.body.style.overflow = '';
  };

  window.viewerClose = function(e) {
    if (e.target === document.getElementById('viewer-overlay')) {
      closeViewer();
    }
  };

  window.viewerNav = function(dir) {
    if (!viewerOpen_ || !viewerImages.length) return;
    viewerIdx = (viewerIdx + dir + viewerImages.length) % viewerImages.length;
    const img = document.getElementById('viewer-img');
    img.style.opacity = '0';
    img.src = viewerImages[viewerIdx].src;
    img.onload = () => { img.style.opacity = '1'; };
  };

  function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1048576) return (bytes / 1024).toFixed(0) + ' КБ';
    return (bytes / 1048576).toFixed(2) + ' МБ';
  }
})();
