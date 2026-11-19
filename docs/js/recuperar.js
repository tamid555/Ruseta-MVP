const urlApi = 'https://ruseta-mvp.onrender.com';

document.addEventListener('DOMContentLoaded', () => {
    const loginBox = document.querySelector('.login-box');
    const paso1Form = document.getElementById('paso1Form');
    const paso2Form = document.getElementById('paso2Form');
    const subtitulo = document.getElementById('subtitulo');

    const emailInput = document.getElementById('emailRecuperar');
    const btnEnviarCodigo = document.getElementById('btnEnviarCodigo');
    const msgPaso1 = document.getElementById('msgPaso1');

    const codigoInput = document.getElementById('codigo');
    const nuevaPasswordInput = document.getElementById('nuevaPassword');
    const btnCambiarPassword = document.getElementById('btnCambiarPassword');
    const msgPaso2 = document.getElementById('msgPaso2');

    let correoGuardado = '';

    function animarError(elementoMsg, texto) {
        elementoMsg.className = 'msg-error';
        elementoMsg.textContent = texto;
        loginBox.classList.add('shake');
        setTimeout(() => loginBox.classList.remove('shake'), 400);
    }

    btnEnviarCodigo.addEventListener('click', async () => {
        const email = emailInput.value.trim();
        if (!email) {
            animarError(msgPaso1, 'Ingresa tu correo electrónico');
            return;
        }

        msgPaso1.textContent = '';
        btnEnviarCodigo.textContent = 'Enviando código...';
        btnEnviarCodigo.disabled = true;

        try {
            const respuesta = await fetch(`${urlApi}/api/solicitar-recuperacion`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            const datos = await respuesta.json();

            if (respuesta.ok) {
                correoGuardado = email;
                paso1Form.style.display = 'none';
                paso2Form.style.display = 'block';
                subtitulo.textContent = 'Revisa tu correo e ingresa el código';
            } else {
                animarError(msgPaso1, datos.detail || 'No se encontró ese correo');
            }
        } catch (error) {
            animarError(msgPaso1, 'Error de conexión con el servidor');
        } finally {
            btnEnviarCodigo.textContent = 'ENVIAR CÓDIGO';
            btnEnviarCodigo.disabled = false;
        }
    });

    btnCambiarPassword.addEventListener('click', async () => {
        const codigo = codigoInput.value.trim();
        const nueva_password = nuevaPasswordInput.value;

        if (!codigo || !nueva_password) {
            animarError(msgPaso2, 'Completa todos los campos');
            return;
        }
        if (nueva_password.length < 6) {
            animarError(msgPaso2, 'La contraseña debe tener al menos 6 caracteres');
            return;
        }

        msgPaso2.textContent = '';
        btnCambiarPassword.textContent = 'Actualizando...';
        btnCambiarPassword.disabled = true;

        try {
            const respuesta = await fetch(`${urlApi}/api/restablecer-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: correoGuardado,
                    codigo: codigo,
                    nueva_password: nueva_password
                })
            });
            const datos = await respuesta.json();

            if (respuesta.ok) {
                msgPaso2.className = 'msg-ok';
                msgPaso2.textContent = 'Contraseña actualizada. Redirigiendo...';
                setTimeout(() => { window.location.href = 'index.html'; }, 1500);
            } else {
                animarError(msgPaso2, datos.detail || 'Código inválido o expirado');
            }
        } catch (error) {
            animarError(msgPaso2, 'Error de conexión con el servidor');
        } finally {
            btnCambiarPassword.textContent = 'RESTABLECER CONTRASEÑA';
            btnCambiarPassword.disabled = false;
        }
    });
});