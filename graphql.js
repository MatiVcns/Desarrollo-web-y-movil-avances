const express = require('express');
const { ApolloServer, gql, ApolloError } = require('apollo-server-express');
const { GraphQLError, Kind } = require('graphql');

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '50kb' }));
const API_URL = (process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const INVENTORY_URL = (process.env.INVENTORY_URL || API_URL).replace(/\/$/, '');
const ORDERS_URL = (process.env.ORDERS_URL || API_URL).replace(/\/$/, '');
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

async function api(path, { token, method = 'GET', body, service = 'inventory' } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = token.startsWith('Bearer ') ? token : `Bearer ${token}`;
  const baseUrl = service === 'orders' ? ORDERS_URL : INVENTORY_URL;
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
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
      return api(`/productos?${params}`, { service: 'inventory' });
    },
    getProductoById: (_, { id }) => api(`/productos/${encodeURIComponent(id)}`, { service: 'inventory' }),
    misPedidos: (_, __, ctx) => api('/pedidos/mios', { token: ctx.authorization, service: 'orders' }),
    resumenPedido: async (_, { id }, ctx) => {
      if (!ctx.authorization) throw new ApolloError('Autenticación requerida', 'UNAUTHENTICATED');
      const pedido = await api(`/pedidos/${encodeURIComponent(id)}`, { token: ctx.authorization, service: 'orders' });
      const ids = [...new Set(pedido.items.map(item => item.producto_id))];
      let productos = [];
      try { productos = await api(`/productos?ids=${encodeURIComponent(ids.join(','))}&limit=30`, { service: 'inventory' }); } catch (_) {}
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
    addProducto: (_, { input }, ctx) => api('/productos', { token: ctx.authorization, method: 'POST', body: input, service: 'inventory' }),
    updProducto: (_, { id, input }, ctx) => api(`/productos/${encodeURIComponent(id)}`, { token: ctx.authorization, method: 'PUT', body: input, service: 'inventory' }),
    delProducto: async (_, { id }, ctx) => {
      await api(`/productos/${encodeURIComponent(id)}`, { token: ctx.authorization, method: 'DELETE', service: 'inventory' });
      return { message: 'Producto desactivado' };
    }
  }
};

const MAX_DEPTH = 8;
const MAX_COST = 25000;
const ROOT_FIELD_COST = 1000;

function listSize(field) {
  switch (field.name.value) {
    case 'getProductos': {
      const limit = field.arguments?.find(argument => argument.name.value === 'limit')?.value;
      if (!limit) return 50;
      return limit.kind === Kind.INT ? Math.min(100, Math.max(1, Number(limit.value))) : 100;
    }
    case 'misPedidos': return 100;
    case 'items':
    case 'lineas': return 30;
    case 'tags': return 20;
    default: return 1;
  }
}

// Estima el trabajo antes de invocar resolvers. El recorrido iterativo también
// acota expansiones de fragmentos y cobra cada alias como un campo separado.
function operationLimits(context) {
  return {
    OperationDefinition(operation) {
      const fragments = new Set();
      const stack = [{ selections: operation.selectionSet.selections, next: 0, depth: 0, weight: 1 }];
      let cost = 0;
      while (stack.length) {
        const frame = stack[stack.length - 1];
        if (frame.next === frame.selections.length) {
          stack.pop();
          if (frame.fragment) fragments.delete(frame.fragment);
          continue;
        }

        const selection = frame.selections[frame.next++];
        let depth = frame.depth;
        let weight = frame.weight;
        let selectionSet = selection.selectionSet;
        let fragment;
        if (selection.kind === Kind.FIELD) {
          const size = listSize(selection);
          cost += (depth === 0 ? ROOT_FIELD_COST : 0) + weight * (selectionSet ? 1 : size);
          depth++;
          weight *= size;
          if (depth > MAX_DEPTH) {
            context.reportError(new GraphQLError(`Profundidad GraphQL máxima: ${MAX_DEPTH}`, { nodes: selection }));
            return false;
          }
        } else {
          cost++;
          if (selection.kind === Kind.FRAGMENT_SPREAD) {
            fragment = selection.name.value;
            // Las reglas estándar rechazan fragmentos inexistentes o cíclicos.
            if (!fragments.has(fragment)) selectionSet = context.getFragment(fragment)?.selectionSet;
          }
        }

        if (cost > MAX_COST) {
          context.reportError(new GraphQLError(`Costo GraphQL máximo: ${MAX_COST} unidades`, { nodes: selection }));
          return false;
        }
        if (selectionSet) {
          if (fragment) fragments.add(fragment);
          stack.push({ selections: selectionSet.selections, next: 0, depth, weight, fragment });
        }
      }
    }
  };
}

async function start() {
  const server = new ApolloServer({
    typeDefs, resolvers,
    introspection: !isProduction,
    validationRules: [operationLimits],
    context: ({ req }) => ({ authorization: req.headers.authorization }),
    formatError: error => ({
      message: error.message,
      extensions: { code: error.extensions?.code || 'INTERNAL_SERVER_ERROR' }
    })
  });
  await server.start();
  app.post('/graphql', (req, res, next) => {
    if (Array.isArray(req.body)) {
      return res.status(400).json({ errors: [{ message: 'Envía una sola operación GraphQL por solicitud',
        extensions: { code: 'BAD_REQUEST' } }] });
    }
    next();
  });
  server.applyMiddleware({ app, path: '/graphql', cors: false });
  app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'graphql-gateway' }));
  const port = Number(process.env.PORT || 4001);
  app.listen(port, '0.0.0.0', () => console.log(`GraphQL Gateway privado escuchando en 0.0.0.0:${port}`));
}
start().catch(error => { console.error('No se pudo iniciar GraphQL Gateway:', error.message); process.exit(1); });
