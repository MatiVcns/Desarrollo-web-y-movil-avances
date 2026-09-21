const buscador = document.getElementById("buscador");
const productos = document.querySelectorAll(".producto");

buscador.addEventListener("input", function () {
    const texto = buscador.value.toLowerCase();

    productos.forEach(function (producto) {
        const nombre = producto.querySelector("h3").textContent.toLowerCase();

        if (nombre.includes(texto)) {
            producto.style.display = "";
        } else {
            producto.style.display = "none";
        }
    });
});