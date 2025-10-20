// Substitua todo o conteúdo de painel-rpa/src/LoginPage.js

import React, { useState } from 'react'; // A CORREÇÃO ESTÁ AQUI
import { login } from './api';
import './LoginPage.css';
import logo from './assets/logo-onesid.png';

function LoginPage({ onLoginSuccess }) {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        console.log('[LoginPage] Iniciando tentativa de login...');

        try {
            const data = await login(username, password);
            console.log('[LoginPage] API de login retornou SUCESSO. Dados recebidos:', data);
            onLoginSuccess(data);
        } catch (err) {
            const errorMessage = err.message || 'Falha no login. Verifique suas credenciais.';
            console.error('[LoginPage] API de login retornou ERRO:', errorMessage);
            setError(errorMessage);
        }
    };

    return (
        <div className="login-container">
            <div className="login-box">
                <img src={logo} alt="OneSid Logo" className="login-logo" />
                <h2>Acessar Painel</h2>
                <form onSubmit={handleSubmit}>
                    <div className="input-group">
                        <input
                            type="text"
                            id="username"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            placeholder="Usuário"
                            required
                        />
                    </div>
                    <div className="input-group">
                        <input
                            type="password"
                            id="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="Senha"
                            required
                        />
                    </div>
                    <button type="submit" className="login-button">Entrar</button>
                    {error && <p className="error-message">{error}</p>}
                </form>
            </div>
        </div>
    );
}

export default LoginPage;