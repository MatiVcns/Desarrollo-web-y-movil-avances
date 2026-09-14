const mongoose = require('mongoose');

const productoSchema = new mongoose.Schema({
  nombre: {
    type: String,
    required: true,
    trim: true
  },
  categoria: {
    type: String,
    required: true,
    trim: true
  },
  precio: {
    type: Number,
    required: true,
    min: 0
  },
  stock: {
    type: Number,
    required: true,
    min: 0
  }
});

module.exports = mongoose.model('Producto', productoSchema);
