// API Gateway público: única entrada del navegador a REST y GraphQL.
const express = require('express');
const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '50kb' }));
const API_URL = (process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const GRAPHQL_URL = process.env.GRAPHQL_INTERNAL_URL || 'http://127.0.0.1:4001/graphql';
const allowedOrigins = (process.env.CORS_ORIGINS || 'http://127.0.0.1:5500,http://localhost:5500').split(',').map(x => x.trim());
const requestCounts = new Map();

app.use((req, res, next) => {
  const bucket = Math.floor(Date.now() / 60000);
  const key = `${req.ip}:${bucket}`;
  const count = requestCounts.get(key) || 0;
  if (count >= Number(process.env.RATE_LIMIT_PER_MINUTE || 120)) return res.status(429).json({ detail: 'Límite de solicitudes superado' });
  requestCounts.set(key, count + 1);
  for (const storedKey of requestCounts.keys()) if (!storedKey.endsWith(`:${bucket}`)) requestCounts.delete(storedKey);
  next();
});
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && allowedOrigins.includes(origin)) res.setHeader('Access-Control-Allow-Origin', origin);
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type, Idempotency-Key, X-Request-ID');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

app.all(/^\/api\/(.*)$/, async (req, res) => {
  const allowed = /^(auth|clientes|productos|pedidos|pagos|admin)(\/|$)/.test(req.params[0]);
  if (!allowed || !['GET', 'POST', 'PUT', 'DELETE'].includes(req.method)) return res.status(404).json({ detail: 'Ruta no disponible' });
  try {
    const query = req.url.includes('?') ? req.url.slice(req.url.indexOf('?')) : '';
    const upstream = await fetch(`${API_URL}/${req.params[0]}${query}`, {
      method: req.method,
      headers: {
        ...(req.headers.authorization ? { Authorization: req.headers.authorization } : {}),
        ...(req.headers['idempotency-key'] ? { 'Idempotency-Key': req.headers['idempotency-key'] } : {}),
        ...(req.headers['x-webhook-secret'] ? { 'X-Webhook-Secret': req.headers['x-webhook-secret'] } : {}),
        ...(req.headers['content-type'] ? { 'Content-Type': req.headers['content-type'] } : {})
      },
      ...(['POST', 'PUT'].includes(req.method) ? { body: JSON.stringify(req.body || {}) } : {}),
      signal: AbortSignal.timeout(6000)
    });
    res.status(upstream.status);
    if (upstream.status === 204) return res.end();
    res.type('application/json').send(await upstream.text());
  } catch (_) {
    res.status(503).json({ detail: 'Servicio backend temporalmente no disponible' });
  }
});

app.post('/graphql', async (req, res) => {
  try {
    const upstream = await fetch(GRAPHQL_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(req.headers.authorization ? { Authorization: req.headers.authorization } : {})
      },
      body: JSON.stringify(req.body || {}),
      signal: AbortSignal.timeout(7000)
    });
    res.status(upstream.status).type('application/json').send(await upstream.text());
  } catch (_) {
    res.status(503).json({ errors: [{ message: 'GraphQL Gateway temporalmente no disponible', extensions: { code: 'UPSTREAM_UNAVAILABLE' } }] });
  }
});

app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'api-gateway' }));
const port = Number(process.env.PORT || 4000);
app.listen(port, '0.0.0.0', () => console.log(`API Gateway escuchando en 0.0.0.0:${port}`));
