import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom'; 
// ---> MUDANÇA: Importar API_URL <---
import { API_URL, login, getCurrentUser, getSolicitacoes, createSolicitacao, updateSolicitacao } from './api';
import './App.css';
import logo from './assets/logo-onesid.png';
import LoginPage from './LoginPage';

// --- COMPONENTE DO FORMULÁRIO (SolicitacaoForm) ---
// (Sem alterações, omitido para brevidade. O código dele permanece o mesmo)
const SolicitacaoForm = ({ onSolicitacaoCriada }) => {
    const [npj, setNpj] = useState('');
    const [numeroProcesso, setNumeroProcesso] = useState('');
    const [numeroSolicitacao, setNumeroSolicitacao] = useState('');
    const [valor, setValor] = useState('');
    const [dataSolicitacao, setDataSolicitacao] = useState(new Date().toISOString().split('T')[0]);
    const [aguardandoConfirmacao, setAguardandoConfirmacao] = useState(true);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [success, setSuccess] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccess('');

        try {
            const dados = {
                npj,
                numero_processo: numeroProcesso || null,
                numero_solicitacao: numeroSolicitacao,
                valor: parseFloat(valor),
                data_solicitacao: dataSolicitacao,
                aguardando_confirmacao: aguardandoConfirmacao
            };
            await createSolicitacao(dados);
            setSuccess('Solicitação criada com sucesso!');
            setNpj('');
            setNumeroProcesso('');
            setNumeroSolicitacao('');
            setValor('');
            setDataSolicitacao(new Date().toISOString().split('T')[0]);
            setAguardandoConfirmacao(true);
            setTimeout(() => setSuccess(''), 3000);
            onSolicitacaoCriada();
        } catch (err) {
            setError('Erro ao criar solicitação: ' + (err.response?.data?.detail || err.message || 'Verifique os dados'));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="card">
            <h2>Adicionar Solicitação de Custa</h2>
            <form onSubmit={handleSubmit} className="solicitacao-form">
                <div className="form-group">
                    <input id="npj" type="text" value={npj} onChange={(e) => setNpj(e.target.value)} placeholder="NPJ *" required />
                </div>
                <div className="form-group">
                    <input id="numeroProcesso" type="text" value={numeroProcesso} onChange={(e) => setNumeroProcesso(e.target.value)} placeholder="Número do Processo (Opcional)" />
                </div>
                <div className="form-group">
                    <input id="numeroSolicitacao" type="text" value={numeroSolicitacao} onChange={(e) => setNumeroSolicitacao(e.target.value)} placeholder="Número da Solicitação *" required />
                </div>
                 <div className="form-group">
                    <input id="valor" type="number" step="0.01" value={valor} onChange={(e) => setValor(e.target.value)} placeholder="Valor (R$) *" required />
                </div>
                <div className="form-group">
                    <input id="dataSolicitacao" type="date" value={dataSolicitacao} onChange={(e) => setDataSolicitacao(e.target.value)} required />
                </div>
                <div className="form-group-checkbox checkbox-container">
                    <input id="aguardandoConfirmacao" type="checkbox" checked={aguardandoConfirmacao} onChange={(e) => setAguardandoConfirmacao(e.target.checked)} />
                    <label htmlFor="aguardandoConfirmacao">Aguardando Confirmação</label>
                </div>
                <button type="submit" disabled={isLoading}>
                    {isLoading ? 'Salvando...' : 'Salvar Solicitação'}
                </button>
                {error && <p className="form-message error">{error}</p>}
                {success && <p className="form-message success">{success}</p>}
            </form>
        </div>
    );
};


// --- COMPONENTE DA TABELA (SolicitacoesTable) ---
const SolicitacoesTable = ({ solicitacoes, onDataRefresh }) => {
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedSolicitacao, setSelectedSolicitacao] = useState(null);
    const [isModalLoading, setIsModalLoading] = useState(false);
    const [modalError, setModalError] = useState('');

    const openModal = (solicitacao) => {
        setSelectedSolicitacao(solicitacao);
        setIsModalOpen(true);
        setModalError('');
    };

    const closeModal = () => {
        if (isModalLoading) return;
        setIsModalOpen(false);
        setSelectedSolicitacao(null);
    };

    const formatData = (dataString) => {
        if (!dataString) return 'N/A';
        try {
            const dataUTC = new Date(dataString.endsWith('Z') || dataString.includes('+') ? dataString : dataString + 'Z');
            if (isNaN(dataUTC.getTime())) {
                const parts = dataString.split('-');
                if (parts.length === 3) {
                    const dataOnly = new Date(Date.UTC(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2])));
                     if (!isNaN(dataOnly.getTime())) {
                         return dataOnly.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
                     }
                }
                return dataString;
            }
            if (dataString.includes('T') || dataString.includes(' ')) {
                return dataUTC.toLocaleString('pt-BR', {});
            } else {
                return dataUTC.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
            }
        } catch (e) {
             console.error("Erro formatando data:", dataString, e);
            return dataString;
        }
    };

    // ---> MUDANÇA: Função formatComprovantes agora usa API_URL <---
    const formatComprovantes = (paths) => {
        if (!paths) return <li>Nenhum</li>;
        let links = [];
        try {
            if (Array.isArray(paths)) { links = paths; }
            else if (typeof paths === 'string' && paths.startsWith('[')) { links = JSON.parse(paths); }
            // Fallback para string simples (legado)
            else if (typeof paths === 'string' && paths.trim() !== '') { links = [paths]; } 
        } catch (e) { console.error("Erro ao parsear comprovantes_path:", paths, e); return <li>Erro ao ler caminhos</li>; }
        
        if (!Array.isArray(links) || links.length === 0) return <li>Nenhum</li>;
        
        return links.map((link, index) => {
            // link agora é o caminho relativo (ex: 'NPJ_LIMPO/arquivo.pdf')
            const nomeArquivo = link.split(/[\\/]/).pop() || 'Comprovante';
            
            // ---> MUDANÇA: Construir a URL completa para o backend <---
            // Garante que não haja barras duplicadas
            const staticPath = "static/comprovantes";
            const downloadUrl = `${API_URL.replace(/\/$/, '')}/${staticPath}/${link.replace(/^\//, '')}`;
            
            return (
                <li key={index}>
                    {/* Adicionado atributo 'download' para sugerir download */}
                    <a href={downloadUrl} target="_blank" rel="noopener noreferrer" download={nomeArquivo}>
                        {nomeArquivo}
                    </a>
                </li>
            );
        });
    };

     const getRoboStatusClass = (statusRobo) => {
        const s = (statusRobo || 'pendente').toLowerCase();
        if (s.includes('erro')) { return 'erro'; }
        if (s.includes('finalizado')) { return 'finalizado'; }
        return 'pendente';
    };

    const handleResetPendente = async () => {
        if (!selectedSolicitacao) return;
        setIsModalLoading(true);
        setModalError('');
        try {
            await updateSolicitacao(selectedSolicitacao.id, {
                status_robo: "Pendente",
                status_portal: null,
                ultima_verificacao_robo: null
            });
            if (onDataRefresh) { onDataRefresh(); }
            closeModal();
        } catch (err) {
            console.error("Erro ao resetar solicitação:", err);
            setModalError('Falha ao resetar: ' + (err.response?.data?.detail || err.message));
        } finally {
            setIsModalLoading(false);
        }
    };


    return (
        <div className="process-table-container card">
            <h2>Solicitações Cadastradas</h2>
             <div className="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>NPJ</th>
                            <th>Nº Solicitação</th>
                            <th>Valor (R$)</th>
                            <th>Data Solicitação</th>
                            <th>Criado Por</th>
                            <th>Status</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {solicitacoes.length > 0 ? (
                            solicitacoes.map(item => {
                                const statusRoboClasse = getRoboStatusClass(item.status_robo);
                                // O texto prioriza o status do portal, se existir.
                                const statusText = item.status_portal || item.status_robo || 'Pendente';
                                
                                return (
                                    <tr key={item.id}>
                                        <td>{item.npj}</td>
                                        <td>{item.numero_solicitacao}</td>
                                        <td>{typeof item.valor === 'number' ? item.valor.toFixed(2) : parseFloat(item.valor || 0).toFixed(2)}</td>
                                        <td>{formatData(item.data_solicitacao)}</td>
                                        <td>{item.usuario?.username || 'Desconhecido'}</td>
                                        <td>
                                          <div className="status-cell">
                                            <span 
                                              className={`status-indicator status-${statusRoboClasse}`}
                                              title={`Status Robô: ${item.status_robo || 'Pendente'}`}
                                            ></span>
                                            <span className="status-text">
                                              {statusText}
                                            </span>
                                          </div>
                                        </td>
                                        <td>
                                            <button onClick={() => openModal(item)} className="action-button" title="Ver Detalhes e Ações">
                                                👁️
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })
                        ) : ( <tr><td colSpan="7">Nenhuma solicitação cadastrada ainda.</td></tr> )}
                    </tbody>
                </table>
             </div>

            {/* Modal (Renderizado via Portal) */}
             {isModalOpen && selectedSolicitacao && createPortal(
                <div className="modal-backdrop" onClick={closeModal}>
                    <div className="modal-content" onClick={e => e.stopPropagation()}>
                        <h3>Detalhes da Solicitação (ID: {selectedSolicitacao.id})</h3>
                        <div className="modal-details">
                            <p><strong>NPJ:</strong> {selectedSolicitacao.npj}</p>
                            <p><strong>Nº Processo:</strong> {selectedSolicitacao.numero_processo || 'N/A'}</p>
                            <p><strong>Nº Solicitação:</strong> {selectedSolicitacao.numero_solicitacao}</p>
                            <p><strong>Valor:</strong> R$ {typeof selectedSolicitacao.valor === 'number' ? selectedSolicitacao.valor.toFixed(2) : parseFloat(selectedSolicitacao.valor || 0).toFixed(2)}</p>
                            <p><strong>Data da Solicitação:</strong> {formatData(selectedSolicitacao.data_solicitacao)}</p>
                            <p><strong>Criado por:</strong> {selectedSolicitacao.usuario?.username || 'Desconhecido'}</p>
                            <hr />
                            <p><strong>Status Portal:</strong> {selectedSolicitacao.status_portal || 'N/A'}</p>
                            <p><strong>Status Robô:</strong> {selectedSolicitacao.status_robo || 'Pendente'}</p>
                            <p><strong>Última Verificação Robô:</strong> {formatData(selectedSolicitacao.ultima_verificacao_robo)}</p>
                            <p><strong>Aguardando Confirmação (Usuário):</strong> {selectedSolicitacao.aguardando_confirmacao ? 'Sim' : 'Não'}</p>
                            <hr />
                            <p><strong>Comprovantes/Documentos:</strong></p>
                            <ul className="comprovantes-list">{formatComprovantes(selectedSolicitacao.comprovantes_path)}</ul>
                        </div>
                        <div className="modal-actions">
                            {modalError && <p className="form-message error">{modalError}</p>}
                            <button 
                                onClick={handleResetPendente} 
                                className="modal-button-reset" 
                                disabled={isModalLoading}
                            >
                                {isModalLoading ? "Resetando..." : "Resetar para Pendente"}
                            </button>
                            <button onClick={closeModal} className="modal-close-button" disabled={isModalLoading}>
                                Fechar
                            </button>
                        </div>
                    </div>
                </div>,
                document.getElementById('modal-root')
            )}
        </div>
    );
};


// --- COMPONENTE PRINCIPAL DA APLICAÇÃO ---
function App() {
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [currentUser, setCurrentUser] = useState(null);
    const [solicitacoes, setSolicitacoes] = useState([]);
    const [error, setError] = useState('');

    const fetchData = async () => {
        console.log("Chamando fetchData...");
        try {
            const userResponse = await getCurrentUser();
            console.log("Dados do usuário recebidos:", userResponse);
            setCurrentUser(userResponse);
            const solicitacoesResponse = await getSolicitacoes();
             console.log("Solicitações recebidas:", solicitacoesResponse);
            setSolicitacoes(solicitacoesResponse.sort((a, b) => b.id - a.id));
            setIsLoggedIn(true);
            setError('');
        } catch (err) {
             console.error("Erro detalhado em fetchData:", err);
            let detailedError = err.message || 'Verifique a conexão';
            if (err.response) {
                detailedError = `Erro ${err.response.status}: ${err.response.data?.detail || err.message}`;
                 if (err.response.status === 401) { handleLogout(); detailedError = "Sessão expirada. Faça login novamente."; }
            } else if (err.request) { detailedError = "Sem resposta do servidor."; }
             setError('Erro ao buscar dados: ' + detailedError);
             if (!localStorage.getItem('token')) { setIsLoggedIn(false); setCurrentUser(null); }
        } finally { setIsLoading(false); }
    };

    useEffect(() => {
        console.log("Verificando token...");
        const token = localStorage.getItem('token');
        if (token) { console.log("Token encontrado. Buscando dados..."); fetchData(); }
        else { console.log("Nenhum token. Indo para login."); setIsLoading(false); }
    }, []);

    const handleLoginSuccess = (loginData) => {
        console.log("Login OK, buscando dados...");
        setIsLoading(true);
        fetchData();
    };

    const handleLogout = () => {
        console.log("Executando logout...");
        localStorage.removeItem('token');
        setIsLoggedIn(false);
        setCurrentUser(null);
        setSolicitacoes([]);
        setError('');
        setIsLoading(false);
    };

    const handleDataNeedsRefresh = () => {
        console.log("Solicitação de atualização de dados recebida, buscando...");
        fetchData();
    };

    if (isLoading) { return <div className="loading-screen">Carregando...</div>; }

    if (!isLoggedIn) { return <LoginPage onLoginSuccess={handleLoginSuccess} />; }

    return (
        <div className="App main-app">
            <header className="app-header">
                <img src={logo} alt="OneSid Logo" className="logo" />
                <div className="user-info">
                    <span>Olá, {currentUser?.username || 'Usuário'}</span>
                    <button onClick={handleLogout} className="logout-button">Sair</button>
                </div>
            </header>
            <main>
                {error && <p className="global-error-message">{error}</p>}
                <SolicitacaoForm onSolicitacaoCriada={handleDataNeedsRefresh} />
                <SolicitacoesTable 
                    solicitacoes={solicitacoes} 
                    onDataRefresh={handleDataNeedsRefresh} 
                />
            </main>
        </div>
    );
}

export default App;

