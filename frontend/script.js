// ==============================
// ELEMENTOS DE LA PÁGINA
// ==============================

const buscador = document.getElementById("buscador");
let productos = document.querySelectorAll(".producto");
const filtros = document.querySelectorAll(".filtro");
let botonesCarrito = document.querySelectorAll(".agregar-carrito");
const contadorCarrito = document.getElementById("contador-carrito");
const sinResultados = document.getElementById("sin-resultados");


// ==============================
// VARIABLES GENERALES
// ==============================

let categoriaSeleccionada = "todos";
let cantidadCarrito = 0;
let clienteToken = null; // Se mantiene en memoria para no persistir JWT en localStorage.
const carritoItems = new Map();
let productoActualId = null;
const gatewayBase = window.WEIRD_STYLE_GATEWAY || "http://127.0.0.1:4000";

async function solicitarApi(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    try {
        return await fetch(`${gatewayBase}/api${path}`, { ...options, headers });
    } catch (_) {
        return fetch(`http://127.0.0.1:8000${path}`, { ...options, headers });
    }
}

function actualizarCarrito() {
    cantidadCarrito = [...carritoItems.values()].reduce((total, linea) => total + linea.cantidad, 0);
    if (contadorCarrito) contadorCarrito.textContent = cantidadCarrito;
    const resumen = document.getElementById("resumen-carrito");
    if (resumen) resumen.textContent = cantidadCarrito;
}

function agregarLineaCarrito(productoId, nombre, cantidad = 1, talla = "M") {
    if (!productoId) {
        alert("El catálogo todavía no se ha conectado al backend. Intenta nuevamente en unos segundos.");
        return;
    }
    const key = `${productoId}:${talla}`;
    const existente = carritoItems.get(key);
    carritoItems.set(key, { producto_id: productoId, nombre, cantidad: (existente?.cantidad || 0) + cantidad, talla });
    actualizarCarrito();
}


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

function conectarBotonesCarrito() {
    botonesCarrito.forEach(function (boton) {
    boton.addEventListener("click", function () {

        const tarjeta = boton.closest(".producto");
        agregarLineaCarrito(boton.dataset.productoId, boton.dataset.producto || tarjeta?.querySelector("h3")?.textContent || "Producto");


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
}
conectarBotonesCarrito();


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

function conectarModalProductos() {
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
        productoActualId = producto.dataset.productoId || null;

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
}
conectarModalProductos();


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


    agregarLineaCarrito(productoActualId, modalNombre.textContent, cantidadModal, tallaSeleccionada);


    modalAgregarCarrito.textContent =
        "✓ AGREGADO AL CARRITO";


    modalAgregarCarrito.disabled = true;


    setTimeout(function () {

        modalAgregarCarrito.textContent =
            "AGREGAR AL CARRITO";

        modalAgregarCarrito.disabled = false;

    }, 1000);

});



function mostrarProductosBackend(productosBackend) {
    const contenedor = document.querySelector(".lista-productos");

    if (!contenedor) {
        console.error("No se encontró el contenedor de productos");
        return;
    }

    const productosActivos = productosBackend.filter(
        producto => producto.activo === true
    );

    // Crear las tarjetas con los datos reales de la API.
    // No reemplazar el HTML hasta que la respuesta esté disponible.
    const fragmento = document.createDocumentFragment();
    productosActivos.forEach(function (dato) {
        const tarjeta = document.createElement("article");
        tarjeta.className = "producto";
        tarjeta.dataset.productoId = dato.id;
        tarjeta.dataset.categoria = dato.categoria.toLowerCase();
        const rutaImagen = dato.imagen || "images/polera.png";
        tarjeta.dataset.imagen = rutaImagen.split("/").pop().replace(/\.[^.]+$/, "");

        const imagenCaja = document.createElement("div");
        imagenCaja.className = "imagen-producto";
        const imagen = document.createElement("img");
        imagen.src = rutaImagen;
        imagen.alt = dato.nombre;
        imagenCaja.appendChild(imagen);

        const informacion = document.createElement("div");
        informacion.className = "info-producto";
        const nombre = document.createElement("h3");
        nombre.textContent = dato.nombre;
        const categoria = document.createElement("p");
        categoria.className = "categoria-producto";
        categoria.textContent = dato.categoria;
        const precio = document.createElement("p");
        precio.className = "precio";
        precio.textContent = "$" + Number(dato.precio).toLocaleString("es-CL");
        const boton = document.createElement("button");
        boton.className = "agregar-carrito";
        boton.dataset.producto = dato.nombre;
        boton.dataset.productoId = dato.id;
        boton.textContent = "Agregar al carrito";
        informacion.append(nombre, categoria, precio, boton);
        tarjeta.append(imagenCaja, informacion);
        fragmento.appendChild(tarjeta);
    });

    contenedor.replaceChildren(fragmento);
    productos = document.querySelectorAll(".producto");
    botonesCarrito = document.querySelectorAll(".agregar-carrito");
    conectarBotonesCarrito();
    conectarModalProductos();
    actualizarProductos();

    console.log(
        "Productos activos disponibles:",
        productosActivos.length
    );

    console.log(
        "Productos preparados para mostrar:",
        productosBackend.length
    );
}


// ==============================
// PRUEBA DE CONEXIÓN CON FASTAPI
// ==============================

async function probarConexionBackend() {
    try {
        let productosBackend;
        try {
            const respuestaGraphQL = await fetch(`${gatewayBase}/graphql`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    query: "query Catalogo { getProductos(limit: 100) { id nombre categoria precio talla color stock tags imagen activo } }"
                })
            });
            const resultadoGraphQL = await respuestaGraphQL.json();
            if (!respuestaGraphQL.ok || resultadoGraphQL.errors) throw new Error("GraphQL no disponible");
            productosBackend = resultadoGraphQL.data.getProductos;
        } catch (errorGraphQL) {
            // Compatibilidad con el modo de desarrollo en que solo se inicia FastAPI.
            const respuesta = await fetch(`${gateway}/api/productos`).catch(() => fetch("http://127.0.0.1:8000/productos"));
            if (!respuesta.ok) throw new Error(`Error HTTP: ${respuesta.status}`);
            productosBackend = await respuesta.json();
        }
        mostrarProductosBackend(productosBackend);

        console.log(
            "Productos recibidos desde MongoDB:",
            productosBackend
        );

    } catch (error) {
        console.error(
            "Error al conectar con FastAPI:",
            error
        );
    }
}

// Registro, login, compra e historial mediante los contratos del backend.
const campoCuentaNombre = document.getElementById("cuenta-nombre");
const campoCuentaEmail = document.getElementById("cuenta-email");
const campoCuentaPassword = document.getElementById("cuenta-password");
const estadoCuenta = document.getElementById("estado-cuenta");
const botonLogout = document.getElementById("boton-logout");
document.getElementById("form-cuenta")?.addEventListener("submit", evento => evento.preventDefault());

document.getElementById("boton-registro")?.addEventListener("click", async () => {
    if (!campoCuentaNombre.value.trim()) { estadoCuenta.textContent = "Ingresa tu nombre para crear una cuenta."; return; }
    try {
        const response = await solicitarApi("/auth/register", { method: "POST", body: JSON.stringify({ nombre: campoCuentaNombre.value, email: campoCuentaEmail.value, password: campoCuentaPassword.value }) });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo crear la cuenta");
        estadoCuenta.textContent = `Cuenta creada para ${data.email}. Ahora inicia sesión.`;
    } catch (error) { estadoCuenta.textContent = error.message; }
});

document.getElementById("boton-login")?.addEventListener("click", async () => {
    try {
        const response = await solicitarApi("/auth/login", { method: "POST", body: JSON.stringify({ email: campoCuentaEmail.value, password: campoCuentaPassword.value }) });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo iniciar sesión");
        clienteToken = data.access_token;
        const perfilResponse = await solicitarApi("/auth/me", { headers: { Authorization: `Bearer ${clienteToken}` } });
        const perfil = await perfilResponse.json();
        if (!perfilResponse.ok) throw new Error(perfil.detail || "No se pudo cargar el perfil");
        estadoCuenta.textContent = `Sesión iniciada: ${perfil.nombre} (${perfil.rol}).`;
        botonLogout.hidden = false;
    } catch (error) { estadoCuenta.textContent = error.message; }
});

botonLogout?.addEventListener("click", () => {
    clienteToken = null;
    botonLogout.hidden = true;
    estadoCuenta.textContent = "Sesión cerrada.";
});

document.getElementById("boton-finalizar-pedido")?.addEventListener("click", async () => {
    const estadoPedido = document.getElementById("estado-pedido");
    if (!clienteToken) { estadoPedido.textContent = "Inicia sesión para crear el pedido."; return; }
    if (!carritoItems.size) { estadoPedido.textContent = "Agrega al menos un producto al carrito."; return; }
    const direccion = document.getElementById("direccion-entrega").value.trim();
    if (direccion.length < 5) { estadoPedido.textContent = "Ingresa una dirección de entrega válida."; return; }
    try {
        const pedidoResponse = await solicitarApi("/pedidos", {
            method: "POST", headers: { Authorization: `Bearer ${clienteToken}` },
            body: JSON.stringify({ items: [...carritoItems.values()].map(({ producto_id, cantidad, talla }) => ({ producto_id, cantidad, talla })), direccion_entrega: direccion, idempotency_key: `ws-${crypto.randomUUID()}` })
        });
        const pedido = await pedidoResponse.json();
        if (!pedidoResponse.ok) throw new Error(pedido.detail || "No se pudo crear el pedido");
        const pagoResponse = await solicitarApi(`/pagos/pedidos/${pedido.id}`, { method: "POST", headers: { Authorization: `Bearer ${clienteToken}`, "Idempotency-Key": `pay-${crypto.randomUUID()}` } });
        const pago = await pagoResponse.json();
        if (!pagoResponse.ok) throw new Error(pago.detail || "Pedido creado; no se pudo iniciar el pago.");
        carritoItems.clear();
        actualizarCarrito();
        estadoPedido.textContent = `Pedido ${pedido.id} creado por $${Number(pedido.total).toLocaleString("es-CL")}. Pago sandbox ${pago.estado}; pendiente de confirmación del proveedor.`;
    } catch (error) { estadoPedido.textContent = error.message; }
});

document.getElementById("boton-historial")?.addEventListener("click", async () => {
    const lista = document.getElementById("lista-pedidos");
    if (!clienteToken) { document.getElementById("estado-pedido").textContent = "Inicia sesión para consultar tu historial."; return; }
    try {
        const response = await fetch(`${gatewayBase}/graphql`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${clienteToken}` }, body: JSON.stringify({ query: "query { misPedidos { id estado total creado_en } }" }) });
        const result = await response.json();
        if (!response.ok || result.errors) throw new Error(result.errors?.[0]?.message || "No se pudo consultar el historial");
        lista.replaceChildren(...result.data.misPedidos.map(pedido => {
            const li = document.createElement("li");
            const detalle = document.createElement("span");
            detalle.textContent = `${pedido.id} — ${pedido.estado} — $${Number(pedido.total).toLocaleString("es-CL")} `;
            const botonResumen = document.createElement("button");
            botonResumen.type = "button";
            botonResumen.textContent = "Resumen agregado";
            botonResumen.addEventListener("click", async () => {
                try {
                    const respuesta = await fetch(`${gatewayBase}/graphql`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${clienteToken}` }, body: JSON.stringify({ query: "query($id: ID!) { resumenPedido(id: $id) { pedido_id estado total lineas { nombre cantidad precio_actual subtotal_pagado disponible } } }", variables: { id: pedido.id } }) });
                    const datos = await respuesta.json();
                    if (datos.errors) throw new Error(datos.errors[0].message);
                    const resumenPedido = datos.data.resumenPedido;
                    detalle.textContent = `${resumenPedido.pedido_id} — ${resumenPedido.estado} — ${resumenPedido.lineas.map(linea => `${linea.nombre} ×${linea.cantidad} (${linea.disponible ? "disponible" : "sin stock"})`).join(", ")}`;
                } catch (error) { detalle.textContent = error.message; }
            });
            li.append(detalle, botonResumen);
            return li;
        }));
    } catch (error) { document.getElementById("estado-pedido").textContent = error.message; }
});

actualizarCarrito();
probarConexionBackend();
