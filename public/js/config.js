(function () {
  // Resolves the backend base URL for both local development and Vercel.
  // Locally the FastAPI server runs on http://127.0.0.1:8000.
  // On Vercel the backend is a same-origin serverless function under /api,
  // so an empty base makes every call relative (e.g. fetch('/api/overview')).
  var host = window.location.hostname;
  var isLocal = host === 'localhost' || host === '127.0.0.1' || host === '' ||
    window.location.protocol === 'file:';
  window.API_BASE = isLocal ? 'http://127.0.0.1:8000' : '';
})();
