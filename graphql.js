const express = require('express');
const { ApolloServer, gql, ApolloError } = require('apollo-server-express');
const { GraphQLError } = require('graphql');

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '50kb' }));
const API_URL = (process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const isProduction = process.env.NODE_ENV === 'production';

const typeDefs = gql`
  type Producto { id: ID!, nombre: String!, categoria: String!, precio: Int!, talla: String!, color: String!, stock: Int!, imagen: String, tags: [String!]!, activo: Boolean! }
  type LineaPedido { producto_id: ID!, nombre: String!, precio_unitario: Int!, cantidad: Int!, talla: String!, subtotal: Int! }
  type Pedido { id: ID!, items: [LineaPedido!]!, total: Int!, estado: String!, direccion_entrega: String!, creado_en: String }
  type LineaResumen { producto_id: ID!, nombre: String!, precio_actual: Int, cantidad: Int!, subtotal_pagado: Int!, disponible: Boolean! }
  type ResumenPedido { pedido_id: ID!, estado: String!, total: Int!, lineas: [LineaResumen!]! }
  type Resultado { message: String! }
  input ProductoInput { nombre: String!, categoria: String!, precio: Int!, talla: String!, color: String!, stock: Int!, imagen: String, tags: [String!], activo: Boolean }
  type Query {
    getProductos(q: String, categoria: String, limit: Int = 50): [Producto!]!
    getProductoById(id: ID!): Producto
    misPedidos: [Pedido!]!
    resumenPedido(id: ID!): ResumenPedido!
  }
  type Mutation {
    addProducto(input: ProductoInput!): Producto!
    updProducto(id: ID!, input: ProductoInput!): Producto!
    delProducto(id: ID!): Resultado!
  }
`;

async function api(path, { token, method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = token.startsWith('Bearer ') ? token : `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method, headers, ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(5000)
    });
  } catch (error) {
    throw new ApolloError('Servicio backend temporalmente no disponible', 'UPSTREAM_UNAVAILABLE');
  }
  const payload = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const code = response.status === 401 ? 'UNAUTHENTICATED' : response.status === 403 ? 'FORBIDDEN' : 'UPSTREAM_ERROR';
    throw new ApolloError(payload.detail || 'Solicitud no aceptada', code, { httpStatus: response.status });
  }
  return payload;
}

const resolvers = {
  Query: {
    getProductos: (_, { q, categoria, limit = 50 }) => {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (categoria) params.set('categoria', categoria);
      params.set('limit', String(Math.min(Math.max(limit, 1), 100)));
      return api(`/productos?${params}`);
    },
    getProductoById: (_, { id }) => api(`/productos/${encodeURIComponent(id)}`),
    misPedidos: (_, __, ctx) => api('/pedidos/mios', { token: ctx.authorization }),
    resumenPedido: async (_, { id }, ctx) => {
      if (!ctx.authorization) throw new ApolloError('Autenticación requerida', 'UNAUTHENTICATED');
      const pedido = await api(`/pedidos/${encodeURIComponent(id)}`, { token: ctx.authorization });
      const ids = [...new Set(pedido.items.map(item => item.producto_id))];
      let productos = [];
      try { productos = await api(`/productos?ids=${encodeURIComponent(ids.join(','))}&limit=30`); } catch (_) {}
      const disponibles = new Map(productos.map(producto => [producto.id, producto]));
      const lineas = pedido.items.map(item => {
        const producto = disponibles.get(item.producto_id);
        return { producto_id: item.producto_id, nombre: item.nombre, precio_actual: producto?.precio ?? null,
          cantidad: item.cantidad, subtotal_pagado: item.subtotal, disponible: Boolean(producto && producto.activo && producto.stock > 0) };
      });
      return { pedido_id: pedido.id, estado: pedido.estado, total: pedido.total, lineas };
    }
  },
  Mutation: {
    addProducto: (_, { input }, ctx) => api('/productos', { token: ctx.authorization, method: 'POST', body: input }),
    updProducto: (_, { id, input }, ctx) => api(`/productos/${encodeURIComponent(id)}`, { token: ctx.authorization, method: 'PUT', body: input }),
    delProducto: async (_, { id }, ctx) => {
      await api(`/productos/${encodeURIComponent(id)}`, { token: ctx.authorization, method: 'DELETE' });
      return { message: 'Producto desactivado' };
    }
  }
};

async function start() {
  const server = new ApolloServer({
    typeDefs, resolvers,
    introspection: !isProduction,
    validationRules: [context => {
      let depth = 0;
      return { Field: { enter() { depth += 1; if (depth > 8) context.reportError(new GraphQLError('Profundidad GraphQL máxima: 8')); }, leave() { depth -= 1; } } };
    }],
    context: ({ req }) => ({ authorization: req.headers.authorization }),
    formatError: error => ({
      message: error.message,
      extensions: { code: error.extensions?.code || 'INTERNAL_SERVER_ERROR' }
    })
  });
  await server.start();
  server.applyMiddleware({ app, path: '/graphql', cors: false });
  app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'graphql-gateway' }));
  const port = Number(process.env.PORT || 4001);
  app.listen(port, '0.0.0.0', () => console.log(`GraphQL Gateway privado escuchando en 0.0.0.0:${port}`));
}
start().catch(error => { console.error('No se pudo iniciar GraphQL Gateway:', error.message); process.exit(1); });
