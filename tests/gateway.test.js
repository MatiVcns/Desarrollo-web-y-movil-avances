const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const net = require('node:net');
const { spawn } = require('node:child_process');
const path = require('node:path');

async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function waitFor(url, child) {
  for (let i = 0; i < 60; i++) {
    if (child.exitCode !== null) throw new Error('GraphQL Gateway terminó antes de iniciar');
    try { const response = await fetch(url); if (response.ok) return; } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Tiempo de espera agotado al iniciar ${url}`);
}

test('GraphQL compone orders e inventory y propaga autorización', async t => {
  const apiPort = await freePort();
  const gqlPort = await freePort();
  const gatewayPort = await freePort();
  const upstream = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/pedidos/pedido-1') {
      assert.equal(req.headers.authorization, 'Bearer demo-token');
      res.end(JSON.stringify({ id: 'pedido-1', estado: 'pagado', total: 20000, direccion_entrega: 'Santiago', items: [{ producto_id: 'prod-1', nombre: 'Polera X', precio_unitario: 10000, cantidad: 2, talla: 'M', subtotal: 20000 }] }));
    } else if (req.url.startsWith('/productos?ids=')) {
      res.end(JSON.stringify([{ id: 'prod-1', nombre: 'Polera X', precio: 12000, activo: true, stock: 4 }]));
    } else {
      res.statusCode = 404; res.end(JSON.stringify({ detail: 'No encontrado' }));
    }
  });
  await new Promise(resolve => upstream.listen(apiPort, '127.0.0.1', resolve));
  const graphql = spawn(process.execPath, [path.join(__dirname, '..', 'graphql.js')], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, API_INTERNAL_URL: `http://127.0.0.1:${apiPort}`, PORT: String(gqlPort), NODE_ENV: 'test' },
    stdio: 'ignore'
  });
  const gateway = spawn(process.execPath, [path.join(__dirname, '..', 'server.js')], {
    cwd: path.join(__dirname, '..'),
    env: { ...process.env, API_INTERNAL_URL: `http://127.0.0.1:${apiPort}`, GRAPHQL_INTERNAL_URL: `http://127.0.0.1:${gqlPort}/graphql`, PORT: String(gatewayPort), NODE_ENV: 'test', RATE_LIMIT_PER_MINUTE: '1000' },
    stdio: 'ignore'
  });
  t.after(async () => {
    gateway.kill('SIGTERM');
    graphql.kill('SIGTERM');
    await new Promise(resolve => upstream.close(resolve));
  });
  await waitFor(`http://127.0.0.1:${gqlPort}/health`, graphql);
  await waitFor(`http://127.0.0.1:${gatewayPort}/health`, gateway);
  const query = 'query($id: ID!) { resumenPedido(id: $id) { pedido_id estado total lineas { nombre precio_actual subtotal_pagado disponible } } }';
  const response = await fetch(`http://127.0.0.1:${gatewayPort}/graphql`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer demo-token' },
    body: JSON.stringify({ query, variables: { id: 'pedido-1' } })
  });
  const result = await response.json();
  assert.equal(result.data.resumenPedido.estado, 'pagado');
  assert.equal(result.data.resumenPedido.lineas[0].precio_actual, 12000);
  assert.equal(result.data.resumenPedido.lineas[0].subtotal_pagado, 20000);
  assert.equal(result.data.resumenPedido.lineas[0].disponible, true);

  const denied = await fetch(`http://127.0.0.1:${gatewayPort}/graphql`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables: { id: 'pedido-1' } })
  });
  const deniedResult = await denied.json();
  assert.equal(deniedResult.errors[0].extensions.code, 'UNAUTHENTICATED');
});
