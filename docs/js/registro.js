const urlApi = 'http://127.0.0.1:8000';

document.addEventListener('DOMContentLoaded', () => {
    const registroBox = document.querySelector('.login-box');
    const btnRegistro = document.getElementById('btnRegistro');
    const txtNombre = document.getElementById('nombre');
    const txtEmail = document.getElementById('email');
    const txtPassword = document.getElementById('password');
    const txtConfirmar = document.getElementById('confirmar');
    const msgError = document.getElementById('msgError');

    function mostrarError(texto) {
        msgError.className = 'msg-error';
        msgError.textContent = texto;
        registroBox.classList.add('shake');
        setTimeout(() => registroBox.classList.remove('shake'), 400);
    }

    btnRegistro.addEventListener('click', async () => {
        const nombre = txtNombre.value.trim();
        const email = txtEmail.value.trim();
        const password = txtPassword.value;
        const confirmar = txtConfirmar.value;

        // Validaciones rápidas en el navegador (el servidor las vuelve a revisar)
        if (!nombre || !email || !password || !confirmar) {
            mostrarError('Completa todos los campos');
            return;
        }
        if (password.length < 6) {
            mostrarError('La contraseña debe tener al menos 6 caracteres');
            return;
        }
        if (password !== confirmar) {
            mostrarError('Las contraseñas no coinciden');
            return;
        }

        msgError.textContent = '';
        btnRegistro.textContent = 'Creando cuenta...';
        btnRegistro.disabled = true;

        try {
            const respuesta = await fetch(`${urlApi}/api/registro`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nombre, email, password })
            });
            const datos = await respuesta.json();

            if (respuesta.ok) {
                msgError.className = 'msg-ok';
                msgError.textContent = 'Cuenta creada. Te llevamos al inicio de sesión...';
                setTimeout(() => { window.location.href = 'index.html'; }, 1500);
            } else {
                const mensaje = typeof datos.detail === 'string' ? datos.detail : 'Revisa los datos ingresados';
                mostrarError(mensaje);
            }
        } catch (error) {
            mostrarError('No se pudo conectar con el servidor');
        } finally {
            btnRegistro.textContent = 'CREAR CUENTA';
            btnRegistro.disabled = false;
        }
    });
});