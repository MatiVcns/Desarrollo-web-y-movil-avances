// ==============================
// ELEMENTOS DE LA PÁGINA
// ==============================

const buscador = document.getElementById("buscador");
const productos = document.querySelectorAll(".producto");
const filtros = document.querySelectorAll(".filtro");
const botonesCarrito = document.querySelectorAll(".agregar-carrito");
const contadorCarrito = document.getElementById("contador-carrito");
const sinResultados = document.getElementById("sin-resultados");


// ==============================
// VARIABLES GENERALES
// ==============================

let categoriaSeleccionada = "todos";
let cantidadCarrito = 0;


// ==============================
// MOSTRAR PRODUCTOS
// ==============================

function actualizarProductos() {

    const textoBusqueda = buscador.value
        .toLowerCase()
        .trim();

    let productosVisibles = 0;

    productos.forEach(function (producto) {

        const nombre = producto
            .querySelector("h3")
            .textContent
            .toLowerCase();

        const categoria = producto.dataset.categoria;

        const coincideBusqueda =
            nombre.includes(textoBusqueda);

        const coincideCategoria =
            categoriaSeleccionada === "todos" ||
            categoria === categoriaSeleccionada;

        if (coincideBusqueda && coincideCategoria) {

            producto.style.display = "block";
            productosVisibles++;

        } else {

            producto.style.display = "none";

        }

    });


    // Mostrar mensaje si no existen resultados

    if (productosVisibles === 0) {

        sinResultados.style.display = "block";

    } else {

        sinResultados.style.display = "none";

    }

}


// ==============================
// BUSCADOR
// ==============================

buscador.addEventListener("input", function () {

    actualizarProductos();

});


// ==============================
// FILTROS
// ==============================

filtros.forEach(function (boton) {

    boton.addEventListener("click", function () {

        categoriaSeleccionada =
            boton.dataset.filtro;


        // Quitar selección anterior

        filtros.forEach(function (filtro) {

            filtro.classList.remove("activo");

        });


        // Marcar filtro seleccionado

        boton.classList.add("activo");


        // Actualizar productos

        actualizarProductos();

    });

});


// ==============================
// CARRITO DESDE LAS TARJETAS
// ==============================

botonesCarrito.forEach(function (boton) {

    boton.addEventListener("click", function () {

        cantidadCarrito++;

        contadorCarrito.textContent =
            cantidadCarrito;


        // Cambio temporal del botón

        const textoOriginal =
            boton.textContent;

        boton.textContent = "✓ Agregado";

        boton.disabled = true;


        setTimeout(function () {

            boton.textContent =
                textoOriginal;

            boton.disabled = false;

        }, 800);

    });

});


// ==============================
// ELEMENTOS DEL MODAL
// ==============================

const modalProducto =
    document.getElementById("modal-producto");

const cerrarModal =
    document.getElementById("cerrar-modal");

const modalImagen =
    document.getElementById("modal-imagen-principal");

const modalNombre =
    document.getElementById("modal-nombre");

const modalPrecio =
    document.getElementById("modal-precio");

const imagenAnterior =
    document.getElementById("imagen-anterior");

const imagenSiguiente =
    document.getElementById("imagen-siguiente");

const puntosImagen =
    document.querySelectorAll(".punto-imagen");

const botonesTalla =
    document.querySelectorAll(".talla");

const restarCantidad =
    document.getElementById("restar-cantidad");

const sumarCantidad =
    document.getElementById("sumar-cantidad");

const cantidadProducto =
    document.getElementById("cantidad-producto");

const modalAgregarCarrito =
    document.getElementById("modal-agregar-carrito");


// ==============================
// VARIABLES DEL MODAL
// ==============================

let cantidadModal = 1;

let tallaSeleccionada = "";

let imagenesProductoActual = [];

let indiceImagenActual = 0;


// ==============================
// ACTUALIZAR INDICADOR DE IMAGEN
// ==============================

function actualizarIndicadorImagen() {

    puntosImagen.forEach(function (punto, indice) {

        punto.classList.remove("activo");

        if (indice === indiceImagenActual) {

            punto.classList.add("activo");

        }

    });

}


// ==============================
// MOSTRAR IMAGEN DE GALERÍA
// ==============================

function mostrarImagen(indice) {

    if (imagenesProductoActual.length === 0) {
        return;
    }


    modalImagen.style.opacity = "0";


    setTimeout(function () {

        modalImagen.src =
            imagenesProductoActual[indice];

        modalImagen.style.opacity = "1";

        actualizarIndicadorImagen();

    }, 150);

}


// ==============================
// ABRIR PRODUCTO
// ==============================

productos.forEach(function (producto) {

    const imagenProducto =
        producto.querySelector(".imagen-producto");

    const nombreProducto =
        producto.querySelector("h3");


    imagenProducto.style.cursor = "pointer";
    nombreProducto.style.cursor = "pointer";


    function abrirProducto() {

        const nombre =
            producto.querySelector("h3").textContent;

        const precio =
            producto.querySelector(".precio").textContent;

        const archivoPrincipal =
            producto.dataset.imagen;


        // ==============================
        // GALERÍA DEL PRODUCTO
        // ==============================

        imagenesProductoActual = [

            `images/${archivoPrincipal}.png`,

            `images/${archivoPrincipal}-modelo.png`,

            `images/${archivoPrincipal}-detalle.png`

        ];


        indiceImagenActual = 0;


        // ==============================
        // INFORMACIÓN DEL PRODUCTO
        // ==============================

        modalImagen.src =
            imagenesProductoActual[0];

        modalImagen.alt = nombre;

        modalNombre.textContent =
            nombre;

        modalPrecio.textContent =
            precio;


        // ==============================
        // REINICIAR CANTIDAD
        // ==============================

        cantidadModal = 1;

        cantidadProducto.textContent =
            cantidadModal;


        // ==============================
        // REINICIAR TALLA
        // ==============================

        tallaSeleccionada = "";

        botonesTalla.forEach(function (boton) {

            boton.classList.remove("seleccionada");

        });


        // ==============================
        // REINICIAR INDICADOR
        // ==============================

        actualizarIndicadorImagen();


        // ==============================
        // MOSTRAR MODAL
        // ==============================

        modalProducto.classList.add("activo");

        document.body.style.overflow = "hidden";

    }


    imagenProducto.addEventListener(
        "click",
        abrirProducto
    );


    nombreProducto.addEventListener(
        "click",
        abrirProducto
    );

});


// ==============================
// FLECHA SIGUIENTE
// ==============================

imagenSiguiente.addEventListener("click", function (evento) {

    evento.stopPropagation();


    indiceImagenActual++;


    if (
        indiceImagenActual >=
        imagenesProductoActual.length
    ) {

        indiceImagenActual = 0;

    }


    mostrarImagen(indiceImagenActual);

});


// ==============================
// FLECHA ANTERIOR
// ==============================

imagenAnterior.addEventListener("click", function (evento) {

    evento.stopPropagation();


    indiceImagenActual--;


    if (indiceImagenActual < 0) {

        indiceImagenActual =
            imagenesProductoActual.length - 1;

    }


    mostrarImagen(indiceImagenActual);

});


// ==============================
// CERRAR MODAL
// ==============================

function cerrarProducto() {

    modalProducto.classList.remove("activo");

    document.body.style.overflow = "";

}


cerrarModal.addEventListener("click", function () {

    cerrarProducto();

});


// Cerrar haciendo clic en el fondo oscuro

modalProducto.addEventListener("click", function (evento) {

    if (evento.target === modalProducto) {

        cerrarProducto();

    }

});


// ==============================
// CERRAR CON ESC
// ==============================

document.addEventListener("keydown", function (evento) {

    if (
        evento.key === "Escape" &&
        modalProducto.classList.contains("activo")
    ) {

        cerrarProducto();

    }

});


// ==============================
// FLECHAS DEL TECLADO
// ==============================

document.addEventListener("keydown", function (evento) {

    if (
        !modalProducto.classList.contains("activo")
    ) {

        return;

    }


    // Flecha derecha

    if (evento.key === "ArrowRight") {

        indiceImagenActual++;

        if (
            indiceImagenActual >=
            imagenesProductoActual.length
        ) {

            indiceImagenActual = 0;

        }

        mostrarImagen(indiceImagenActual);

    }


    // Flecha izquierda

    if (evento.key === "ArrowLeft") {

        indiceImagenActual--;

        if (indiceImagenActual < 0) {

            indiceImagenActual =
                imagenesProductoActual.length - 1;

        }

        mostrarImagen(indiceImagenActual);

    }

});


// ==============================
// SELECCIONAR TALLA
// ==============================

botonesTalla.forEach(function (boton) {

    boton.addEventListener("click", function () {

        botonesTalla.forEach(function (otraTalla) {

            otraTalla.classList.remove(
                "seleccionada"
            );

        });


        boton.classList.add(
            "seleccionada"
        );


        tallaSeleccionada =
            boton.textContent.trim();

    });

});


// ==============================
// AUMENTAR CANTIDAD
// ==============================

sumarCantidad.addEventListener("click", function () {

    cantidadModal++;

    cantidadProducto.textContent =
        cantidadModal;

});


// ==============================
// DISMINUIR CANTIDAD
// ==============================

restarCantidad.addEventListener("click", function () {

    if (cantidadModal > 1) {

        cantidadModal--;

        cantidadProducto.textContent =
            cantidadModal;

    }

});


// ==============================
// AGREGAR DESDE EL MODAL
// ==============================

modalAgregarCarrito.addEventListener("click", function () {

    if (tallaSeleccionada === "") {

        alert("Selecciona una talla.");

        return;

    }


    cantidadCarrito += cantidadModal;


    contadorCarrito.textContent =
        cantidadCarrito;


    modalAgregarCarrito.textContent =
        "✓ AGREGADO AL CARRITO";


    modalAgregarCarrito.disabled = true;


    setTimeout(function () {

        modalAgregarCarrito.textContent =
            "AGREGAR AL CARRITO";

        modalAgregarCarrito.disabled = false;

    }, 1000);

});