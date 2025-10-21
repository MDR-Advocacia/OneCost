import React, { useState, useEffect } from 'react';
import LoginPage from './LoginPage';
import { getCurrentUser, getSolicitacoes, createSolicitacao } from './api';
import './App.css';
import logo from './assets/logo-onesid.png';

// --- COMPONENTE DO FORMULÁRIO DE NOVA SOLICITAÇÃO ---
const SolicitacaoForm = ({ onAdd, currentUser }) => {
    const [npj, setNpj] = useState('');
    const [numeroProcesso, setNumeroProcesso] = useState('');
    const [numeroSolicitacao, setNumeroSolicitacao] = useState('');
    const [valor, setValor] = useState('');
    const [dataSolicitacao, setDataSolicitacao] = useState(new Date().toISOString().split('T')[0]);
    const [aguardandoConfirmacao, setAguardandoConfirmacao] = useState(true);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        if (!npj || !numeroSolicitacao || !valor || !dataSolicitacao) {
            setError("Por favor, preencha todos os campos obrigatórios.");
            return;
        }

        try {
            const novaSolicitacao = {
                npj,
                numero_processo: numeroProcesso,
                numero_solicitacao: numeroSolicitacao,
                valor,
                data_solicitacao: dataSolicitacao,
                aguardando_confirmacao: aguardandoConfirmacao,
            };
            await createSolicitacao(novaSolicitacao);
            setSuccess('Solicitação adicionada com sucesso!');
            // Limpa o formulário
            setNpj('');
            setNumeroProcesso('');
            setNumeroSolicitacao('');
            setValor('');
            // Chama a função para atualizar a lista no componente pai
            onAdd(); 
        } catch (err) {
            setError('Falha ao adicionar solicitação. Tente novamente.');
            console.error(err);
        }
    };

    return (
        <div className="card">
            <h2>Adicionar Nova Custa</h2>
            <form onSubmit={handleSubmit} className="solicitacao-form">
                <input type="text" placeholder="NPJ *" value={npj} onChange={(e) => setNpj(e.target.value)} required />
                <input type="text" placeholder="Número do Processo" value={numeroProcesso} onChange={(e) => setNumeroProcesso(e.target.value)} />
                <input type="text" placeholder="Número da Solicitação *" value={numeroSolicitacao} onChange={(e) => setNumeroSolicitacao(e.target.value)} required />
                <input type="number" placeholder="Valor *" value={valor} onChange={(e) => setValor(e.target.value)} required step="0.01" />
                <input type="date" value={dataSolicitacao} onChange={(e) => setDataSolicitacao(e.target.value)} required />
                <div className="checkbox-container">
                    <input type="checkbox" id="aguardando" checked={aguardandoConfirmacao} onChange={(e) => setAguardandoConfirmacao(e.target.checked)} />
                    <label htmlFor="aguardando">Aguardando Confirmação</label>
                </div>
                <button type="submit">Adicionar Solicitação</button>
                {error && <p className="error-message">{error}</p>}
                {success && <p className="success-message">{success}</p>}
            </form>
        </div>
    );
};

// --- COMPONENTE DA TABELA DE SOLICITAÇÕES ---
const SolicitacoesTable = ({ solicitacoes }) => {
    return (
        <div className="card">
            <h2>Custas a Serem Monitoradas</h2>
            <div className="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>NPJ</th>
                            <th>Nº Processo</th>
                            <th>Nº Solicitação</th>
                            <th>Valor</th>
                            <th>Data</th>
                            <th>Status</th>
                            <th>Criado por</th>
                        </tr>
                    </thead>
                    <tbody>
                        {solicitacoes.length > 0 ? (
                            solicitacoes.map((s) => (
                                <tr key={s.id}>
                                    <td>{s.npj}</td>
                                    <td>{s.numero_processo}</td>
                                    <td>{s.numero_solicitacao}</td>
                                    <td>R$ {parseFloat(s.valor).toFixed(2)}</td>
                                    <td>{new Date(s.data_solicitacao + 'T00:00:00').toLocaleDateString()}</td>
                                    <td>{s.aguardando_confirmacao ? 'Aguardando' : 'Confirmado'}</td>
                                    <td>{s.usuario.username}</td>
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan="7">Nenhuma solicitação encontrada.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};


// --- COMPONENTE PRINCIPAL ---
function App() {
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [currentUser, setCurrentUser] = useState(null);
    const [solicitacoes, setSolicitacoes] = useState([]);

    const fetchInitialData = async () => {
        try {
            const user = await getCurrentUser();
            setCurrentUser(user);
            const solicitacoesData = await getSolicitacoes();
            setSolicitacoes(solicitacoesData);
            setIsLoggedIn(true);
        } catch (error) {
            console.error("Sessão inválida ou erro ao buscar dados", error);
            localStorage.removeItem('token');
            setIsLoggedIn(false);
            setCurrentUser(null);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (token) {
            fetchInitialData();
        } else {
            setIsLoading(false);
        }
    }, []);

    const handleLoginSuccess = () => {
        setIsLoading(true);
        fetchInitialData();
    };

    const handleLogout = () => {
        localStorage.removeItem('token');
        setIsLoggedIn(false);
        setCurrentUser(null);
        setSolicitacoes([]);
    };

    const handleSolicitacaoAdded = async () => {
        // Apenas recarrega a lista de solicitações
        const solicitacoesData = await getSolicitacoes();
        setSolicitacoes(solicitacoesData);
    };

    if (isLoading) {
        return <div className="loading-screen">Carregando...</div>;
    }

    if (!isLoggedIn) {
        return <LoginPage onLoginSuccess={handleLoginSuccess} />;
    }

    return (
        <div className="main-app">
            <header className="app-header">
                <img src={logo} alt="OneSid Logo" className="logo" />
                <div className="user-info">
                    <span>Olá, {currentUser?.username}</span>
                    <button onClick={handleLogout} className="logout-button">Sair</button>
                </div>
            </header>
            <main>
                <SolicitacaoForm onAdd={handleSolicitacaoAdded} currentUser={currentUser} />
                <SolicitacoesTable solicitacoes={solicitacoes} />
            </main>
        </div>
    );
}

export default App;
