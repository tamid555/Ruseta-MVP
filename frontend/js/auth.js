const urlApi = 'http://127.0.0.1:8000';

document.addEventListener('DOMContentLoaded', () => {
    const loginBox = document.querySelector('.login-box');
    const loginBtn = document.getElementById('btnLogin');
    const guestBtn = document.getElementById('btnGuest');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const msgError = document.getElementById('msgError');

    function mostrarError(texto) {
        msgError.textContent = texto;
        loginBox.classList.add('shake');
        setTimeout(() => loginBox.classList.remove('shake'), 400);
    }

    // 1. Iniciar sesión (consulta al backend)
    loginBtn.addEventListener('click', async () => {
        const email = emailInput.value.trim();
        const password = passwordInput.value.trim();

        if (!email || !password) {
            mostrarError('Completa el correo y la contraseña');
            return;
        }

        msgError.textContent = '';
        loginBtn.textContent = 'Verificando...';
        loginBtn.disabled = true;

        try {
            const respuesta = await fetch(`${urlApi}/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const datos = await respuesta.json();

            if (respuesta.ok) {
                sessionStorage.setItem('usuarioRuseta', JSON.stringify(datos.usuario));
                window.location.href = 'mapa.html';
            } else {
                const mensaje = typeof datos.detail === 'string' ? datos.detail : 'No se pudo iniciar sesión';
                mostrarError(mensaje);
                passwordInput.value = '';
                passwordInput.focus();
            }
        } catch (error) {
            mostrarError('No se pudo conectar con el servidor');
        } finally {
            loginBtn.textContent = 'INICIAR SESIÓN';
            loginBtn.disabled = false;
        }
    });

    // Enter en la contraseña = clic en iniciar sesión
    passwordInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') loginBtn.click();
    });

    // 2. Invitado
    guestBtn.addEventListener('click', () => {
        sessionStorage.setItem('usuarioRuseta', JSON.stringify({ nombre: 'Invitado', esInvitado: true }));
        loginBox.style.transition = 'all 0.4s ease';
        loginBox.style.opacity = '0';
        loginBox.style.transform = 'scale(0.9)';
        setTimeout(() => { window.location.href = 'mapa.html'; }, 500);
    });
});