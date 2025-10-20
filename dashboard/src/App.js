import React, { useState, useEffect } from 'react';
import { login, checkLoginStatus } from './api';
import './App.css';

// --- COMPONENTE DA TELA DE LOGIN ---
const LoginPage = ({ onLoginSuccess }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        try {
            const response = await login(username, password);
            localStorage.setItem('token', response.data.access_token);
            onLoginSuccess();
        } catch (err) {
            setError('Falha no login. Verifique suas credenciais.');
            setIsLoading(false);
        }
    };

    return (
        <div className="login-container">
            <h2>Login - OneCost</h2>
            <form onSubmit={handleSubmit}>
                <input
                    type="text"
                    placeholder="Usuário"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                />
                <input
                    type="password"
                    placeholder="Senha"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                />
                <button type="submit" disabled={isLoading}>
                    {isLoading ? 'Entrando...' : 'Entrar'}
                </button>
                {error && <p className="error-message">{error}</p>}
            </form>
        </div>
    );
};

// --- COMPONENTE PRINCIPAL DA APLICAÇÃO ---
function App() {
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (token) {
            // No futuro, aqui faremos uma chamada real para validar o token
            setIsLoggedIn(true);
        }
        setIsLoading(false);
    }, []);

    const handleLogout = () => {
        localStorage.removeItem('token');
        setIsLoggedIn(false);
    };

    if (isLoading) {
        return <div>Carregando...</div>;
    }

    if (!isLoggedIn) {
        return <LoginPage onLoginSuccess={() => setIsLoggedIn(true)} />;
    }

    return (
        <div className="main-app">
            <header>
                <h1>Painel OneCost</h1>
                <button onClick={handleLogout}>Sair</button>
            </header>
            <main>
                <h2>Bem-vindo!</h2>
                <p>Você está logado no sistema.</p>
            </main>
        </div>
    );
}

export default App;

