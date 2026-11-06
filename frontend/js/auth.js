document.addEventListener('DOMContentLoaded', () => {
    const loginBox = document.querySelector('.login-box');
    const loginBtn = document.getElementById('btnLogin');
    const guestBtn = document.getElementById('btnGuest');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');

    // 1. Clic en INICIAR SESIÓN
    loginBtn.addEventListener('click', () => {
        const email = emailInput.value.trim();
        const password = passwordInput.value.trim();

        if (!email || !password) {
            // Animación de sacudida si faltan campos
            loginBox.classList.add('shake');
            setTimeout(() => loginBox.classList.remove('shake'), 400);
        } else {
            loginBtn.textContent = "Verificando...";
            loginBtn.style.opacity = "0.7";
            
            setTimeout(() => {
                alert(`¡Bienvenido! Validando datos para: ${email}`);
                loginBtn.textContent = "INICIAR SESIÓN";
                loginBtn.style.opacity = "1";
            }, 800);
        }
    });

    // 2. Clic en Continuar como Invitado
    guestBtn.addEventListener('click', () => {
        loginBox.style.transition = 'all 0.4s ease';
        loginBox.style.opacity = '0';
        loginBox.style.transform = 'scale(0.9)';

        setTimeout(() => {
            alert('Modo Invitado activo. Redirigiendo al mapa de Cúcuta...');
            // Restaurar visualmente en caso de que cierren la alerta
            loginBox.style.opacity = '1';
            loginBox.style.transform = 'scale(1)';
            
            // Aquí en el futuro agregaremos el código para cambiar a mapa.html
            // 2. Clic en Continuar como Invitado
    guestBtn.addEventListener('click', () => {
        loginBox.style.transition = 'all 0.4s ease';
        loginBox.style.opacity = '0';
        loginBox.style.transform = 'scale(0.9)';

        setTimeout(() => {
            // Redirigir a la pantalla del mapa
            window.location.href = 'mapa.html';
        }, 500);
    });
        }, 500);
    });
});