const express = require('express');
const cors = require('cors');
const mongoose = require('mongoose');
const { ApolloServer, gql } = require('apollo-server-express');

const Producto = require('./models/producto');

const typeDefs = gql`
  type Producto {
    id: ID!
    nombre: String!
    categoria: String!
    precio: Float!
    stock: Int!
  }

  input ProductoInput {
    nombre: String!
    categoria: String!
    precio: Float!
    stock: Int!
  }

  type Alert {
    message: String!
  }

  type Query {
    getProductos: [Producto]
    getProductoById(id: ID!): Producto
  }

  type Mutation {
    addProducto(input: ProductoInput!): Producto
    updProducto(id: ID!, input: ProductoInput!): Producto
    delProducto(id: ID!): Alert
  }
`;

const resolvers = {
  Query: {
    getProductos: async () => {
      return await Producto.find();
    },

    getProductoById: async (_, { id }) => {
      return await Producto.findById(id);
    }
  },

  Mutation: {
    addProducto: async (_, { input }) => {
      const nuevoProducto = new Producto(input);
      return await nuevoProducto.save();
    },

    updProducto: async (_, { id, input }) => {
      return await Producto.findByIdAndUpdate(
        id,
        input,
        { new: true, runValidators: true }
      );
    },

    delProducto: async (_, { id }) => {
      const eliminado = await Producto.findByIdAndDelete(id);

      if (!eliminado) {
        return { message: 'Producto no encontrado' };
      }

      return { message: 'Producto eliminado correctamente' };
    }
  }
};

async function iniciarServidor() {
  const app = express();
  app.use(cors());

  const mongoUri =
    process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/weirdstyle';

  try {
    await mongoose.connect(mongoUri);
    console.log('MongoDB conectado');
  } catch (error) {
    console.error('Error al conectar con MongoDB:', error.message);
    process.exit(1);
  }

  const server = new ApolloServer({
    typeDefs,
    resolvers
  });

  await server.start();
  server.applyMiddleware({ app, path: '/graphql' });

  const PORT = process.env.PORT || 4000;

  app.listen(PORT, () => {
    console.log(`GraphQL iniciado en http://localhost:${PORT}${server.graphqlPath}`);
  });
}

iniciarServidor();
