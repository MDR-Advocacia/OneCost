import React, { useState, useEffect } from 'react';
// CORREÇÃO: Removido checkLoginStatus do import, adicionado getCurrentUser e login (necessário para LoginPage interno)
import { login, getCurrentUser, getSolicitacoes, createSolicitacao } from './api';
import './App.css'; // Assume que este CSS contém os estilos do LoginPage.css também
import logo from './assets/logo-onesid.png'; // Garante que o logo seja importado

// --- COMPONENTE DO FORMULÁRIO ---
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
                numero_processo: numeroProcesso,
                numero_solicitacao: numeroSolicitacao,
                valor: parseFloat(valor),
                data_solicitacao: dataSolicitacao,
                aguardando_confirmacao: aguardandoConfirmacao
            };
            await createSolicitacao(dados);
            setSuccess('Solicitação criada com sucesso!');
            // Limpa o formulário
            setNpj('');
            setNumeroProcesso('');
            setNumeroSolicitacao('');
            setValor('');
            setDataSolicitacao(new Date().toISOString().split('T')[0]); // Reseta a data
            setAguardandoConfirmacao(true); // Reseta o checkbox
            // Chama a função do componente pai para atualizar a lista
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
                    {/* <label htmlFor="npj">NPJ</label> */}
                    <input
                        id="npj"
                        type="text"
                        value={npj}
                        onChange={(e) => setNpj(e.target.value)}
                        placeholder="NPJ *"
                        required
                    />
                </div>
                <div className="form-group">
                   {/* <label htmlFor="numeroProcesso">Número do Processo (Opcional)</label> */}
                    <input
                        id="numeroProcesso"
                        type="text"
                        value={numeroProcesso}
                        onChange={(e) => setNumeroProcesso(e.target.value)}
                        placeholder="Número do Processo (Opcional)"
                    />
                </div>
                <div className="form-group">
                   {/* <label htmlFor="numeroSolicitacao">Número da Solicitação</label> */}
                    <input
                        id="numeroSolicitacao"
                        type="text"
                        value={numeroSolicitacao}
                        onChange={(e) => setNumeroSolicitacao(e.target.value)}
                        placeholder="Número da Solicitação *"
                        required
                    />
                </div>
                 <div className="form-group">
                   {/* <label htmlFor="valor">Valor (R$)</label> */}
                    <input
                        id="valor"
                        type="number"
                        step="0.01"
                        value={valor}
                        onChange={(e) => setValor(e.target.value)}
                        placeholder="Valor (R$) *"
                        required
                    />
                </div>
                <div className="form-group">
                    {/* <label htmlFor="dataSolicitacao">Data da Solicitação</label> */}
                    <input
                        id="dataSolicitacao"
                        type="date"
                        value={dataSolicitacao}
                        onChange={(e) => setDataSolicitacao(e.target.value)}
                        required
                    />
                </div>
                <div className="form-group-checkbox checkbox-container">
                    <input
                        id="aguardandoConfirmacao"
                        type="checkbox"
                        checked={aguardandoConfirmacao}
                        onChange={(e) => setAguardandoConfirmacao(e.target.checked)}
                    />
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


// --- COMPONENTE DA TABELA ---
const SolicitacoesTable = ({ solicitacoes }) => {
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedSolicitacao, setSelectedSolicitacao] = useState(null);

    const openModal = (solicitacao) => {
        setSelectedSolicitacao(solicitacao);
        setIsModalOpen(true);
    };

    const closeModal = () => {
        setIsModalOpen(false);
        setSelectedSolicitacao(null);
    };

    const formatData = (dataString) => {
        if (!dataString) return 'N/A';
        try {
            // Tenta formatar data e hora
            const data = new Date(dataString);
            if (isNaN(data.getTime())) return dataString; // Retorna string original se data for inválida

            if (dataString.includes('T') || dataString.includes(' ')) { // Verifica se tem hora
                return data.toLocaleString('pt-BR');
            }
            // Formata apenas data (adiciona fuso UTC para evitar problemas de dia)
            return data.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
        } catch (e) {
             console.error("Erro formatando data:", dataString, e);
            return dataString; // Retorna original em caso de erro
        }
    };

   const formatComprovantes = (paths) => {
        if (!paths) {
            return <li>Nenhum</li>;
        }
         // Se for string JSON, parseia
        let links = [];
        try {
             // Verifica se já é array (vindo de atualização recente) ou string JSON
            if (Array.isArray(paths)) {
                links = paths;
            } else if (typeof paths === 'string' && paths.startsWith('[')) {
                 links = JSON.parse(paths);
             } else if (typeof paths === 'string') {
                 // Assume que é um caminho único ou múltiplos separados por vírgula (legado)
                 links = paths.split(',').map(p => p.trim()).filter(p => p);
             }
        } catch (e) {
            console.error("Erro ao parsear comprovantes_path:", paths, e);
            return <li>Erro ao ler comprovantes</li>; // Informa erro
        }


        if (!Array.isArray(links) || links.length === 0) {
            return <li>Nenhum</li>;
        }

        return links.map((link, index) => {
            const nomeArquivo = link.split(/[\\/]/).pop() || 'Comprovante';
            // TODO: Criar URL de download no backend
            const downloadUrl = `#${link}`; // Placeholder
            return (
                <li key={index}>
                    <a href={downloadUrl} target="_blank" rel="noopener noreferrer">{nomeArquivo}</a>
                </li>
            );
        });
    };

     const getStatusClass = (status) => {
        if (!status) return 'status-pendente'; // Default
        return `status-${status.toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
     };


    return (
        <div className="process-table-container card"> {/* Adicionado card aqui */}
            <h2>Solicitações Cadastradas</h2>
             <div className="table-wrapper"> {/* Garante scroll horizontal se necessário */}
                <table>
                    <thead>
                        <tr>
                            <th>NPJ</th>
                            <th>Nº Solicitação</th>
                            <th>Valor (R$)</th>
                            <th>Data Solicitação</th>
                            <th>Criado Por</th>
                            <th>Status Portal</th>
                            <th>Status Robô</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {solicitacoes.length > 0 ? (
                            solicitacoes.map(item => (
                                <tr key={item.id}>
                                    <td>{item.npj}</td>
                                    <td>{item.numero_solicitacao}</td>
                                    <td>{typeof item.valor === 'number' ? item.valor.toFixed(2) : parseFloat(item.valor || 0).toFixed(2)}</td>
                                    <td>{formatData(item.data_solicitacao)}</td>
                                    <td>{item.usuario?.username || 'Desconhecido'}</td>
                                    <td>
                                        <span className={`status ${getStatusClass(item.status_portal)}`}>
                                            {item.status_portal || 'N/A'}
                                        </span>
                                    </td>
                                    <td>
                                        <span className={`status ${getStatusClass(item.status_robo)}`}>
                                            {item.status_robo || 'Pendente'}
                                        </span>
                                    </td>
                                    <td>
                                        <button onClick={() => openModal(item)} className="action-button" title="Ver Detalhes">
                                            👁️
                                        </button>
                                        {/* Adicionar outros botões aqui se necessário */}
                                    </td>
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan="8">Nenhuma solicitação cadastrada ainda.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
             </div> {/* Fim table-wrapper */}

            {/* O Modal continua aqui... */}
             {isModalOpen && selectedSolicitacao && (
                <div className="modal-backdrop" onClick={closeModal}>
                    <div className="modal-content" onClick={e => e.stopPropagation()}>
                        <h3>Detalhes da Solicitação</h3>
                        <div className="modal-details">
                            <p><strong>ID:</strong> {selectedSolicitacao.id}</p>
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
                            <p><strong>Comprovantes:</strong></p>
                            <ul className="comprovantes-list">
                                {formatComprovantes(selectedSolicitacao.comprovantes_path)}
                            </ul>
                        </div>
                        <button onClick={closeModal} className="modal-close-button">Fechar</button>
                    </div>
                </div>
            )}
        </div>
    );
};


// --- COMPONENTE DA TELA DE LOGIN (RESTAURADO) ---
const LoginPage = ({ onLoginSuccess }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false); // Adicionado estado de loading

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true); // Ativa loading
        setError('');
        try {
            // Usa a função login importada de api.js
            const responseData = await login(username, password);
            // api.js já salva o token no localStorage
            onLoginSuccess(responseData); // Chama a função do App.js
        } catch (err) {
            console.error('[LoginPage] Erro no handleSubmit:', err);
             let errorMessage = 'Falha no login. Verifique suas credenciais.';
             if (err.response && err.response.data && err.response.data.detail) {
                 errorMessage = err.response.data.detail; // Usa a mensagem de erro da API se disponível
             } else if (err.message) {
                 errorMessage = err.message;
             }
            setError(errorMessage);
            setIsLoading(false); // Desativa loading em caso de erro
        }
        // Não precisa mais desativar o loading aqui, pois onLoginSuccess fará o App.js recarregar
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
                            disabled={isLoading} // Desabilita input durante o loading
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
                            disabled={isLoading} // Desabilita input durante o loading
                        />
                    </div>
                    <button type="submit" className="login-button" disabled={isLoading}>
                        {isLoading ? 'Entrando...' : 'Entrar'}
                    </button>
                    {error && <p className="error-message">{error}</p>}
                </form>
            </div>
        </div>
    );
};


// --- COMPONENTE PRINCIPAL DA APLICAÇÃO ---
function App() {
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [currentUser, setCurrentUser] = useState(null); // Alterado para armazenar o objeto do usuário
    const [solicitacoes, setSolicitacoes] = useState([]);
    const [error, setError] = useState('');

    // Função para buscar todos os dados necessários
    const fetchData = async () => {
        setError(''); // Limpa erros anteriores
        console.log("Chamando fetchData...");
        try {
            // 1. Busca dados do usuário logado
            const userResponse = await getCurrentUser(); // Usa a função correta
            console.log("Dados do usuário recebidos:", userResponse);
            setCurrentUser(userResponse); // Armazena o objeto do usuário

            // 2. Busca lista de solicitações
            const solicitacoesResponse = await getSolicitacoes();
             console.log("Solicitações recebidas:", solicitacoesResponse);
             // Ordena as solicitações pela mais recente (maior ID) antes de setar
            setSolicitacoes(solicitacoesResponse.sort((a, b) => b.id - a.id));

            setIsLoggedIn(true); // Confirma que está logado

        } catch (err) {
             console.error("Erro detalhado em fetchData:", err);
            let detailedError = err.message || 'Verifique a conexão com a API';
            if (err.response) {
                // Erro vindo da API
                detailedError = `Erro ${err.response.status}: ${err.response.data?.detail || err.message}`;
                 if (err.response.status === 401) {
                    console.log("Token inválido ou expirado. Deslogando.");
                    handleLogout(); // Desloga se o token for inválido
                    detailedError = "Sessão expirada. Faça login novamente.";
                 }
            } else if (err.request) {
                 // Requisição feita mas sem resposta
                 detailedError = "Não foi possível conectar ao servidor. Verifique se o backend está rodando.";
            }
             setError('Erro ao buscar dados: ' + detailedError);
             // Mesmo com erro, se for 401, handleLogout já cuidou de setIsLoggedIn(false)
             // Se não for 401, talvez ainda esteja logado mas com erro de dados.
             // Vamos garantir que não fique em estado inconsistente:
             if (!localStorage.getItem('token')) {
                 setIsLoggedIn(false);
                 setCurrentUser(null);
             }
        } finally {
             setIsLoading(false); // Garante que o loading termine
        }
    };


    // Verifica o login inicial ao carregar o app
    useEffect(() => {
        console.log("Verificando token no localStorage...");
        const token = localStorage.getItem('token');
        if (token) {
            console.log("Token encontrado. Tentando buscar dados...");
            fetchData(); // Busca dados se o token existir
        } else {
            console.log("Nenhum token encontrado. Indo para tela de login.");
            setIsLoading(false); // Não está logado, termina o loading
        }
    }, []); // Array vazio garante que rode apenas uma vez ao montar

    const handleLoginSuccess = (loginData) => { // Aceita os dados do login
        console.log("Login bem-sucedido, buscando dados...");
        setIsLoading(true); // Ativa o loading enquanto busca dados pós-login
        // Não precisa setar o token aqui, pois api.js já faz isso
        fetchData(); // Busca os dados do usuário e solicitações
    };

    const handleLogout = () => {
        console.log("Executando logout...");
        localStorage.removeItem('token');
        setIsLoggedIn(false);
        setCurrentUser(null); // Limpa o usuário
        setSolicitacoes([]);
        setError(''); // Limpa erros
        setIsLoading(false); // Garante que não fique carregando
    };

    // Função para ser chamada pelo formulário (atualiza a lista)
    const handleSolicitacaoCriada = () => {
        console.log("Nova solicitação criada, atualizando a lista...");
        fetchData(); // Re-busca todas as solicitações
    };

    if (isLoading) {
        return <div className="loading-screen">Carregando...</div>; // Tela de loading melhorada
    }

    if (!isLoggedIn) {
         // Passa a função correta para LoginPage
        return <LoginPage onLoginSuccess={handleLoginSuccess} />; // RENDERIZA O LOGINPAGE DEFINIDO ACIMA
    }

    // Se logado, mostra o dashboard
    return (
        <div className="App main-app"> {/* Usando main-app para evitar conflito com App.css global se houver */}
            <header className="app-header">
                <img src={logo} alt="OneSid Logo" className="logo" />
                <div className="user-info">
                    {/* Exibe o username do objeto currentUser */}
                    <span>Olá, {currentUser?.username || 'Usuário'}</span>
                    <button onClick={handleLogout} className="logout-button">Sair</button>
                </div>
            </header>
            <main>
                {/* Mostra erro global se houver */}
                {error && <p className="form-message error" style={{ textAlign: 'center', marginBottom: '1rem' }}>{error}</p>}

                {/* Formulário para adicionar novas solicitações */}
                <SolicitacaoForm onSolicitacaoCriada={handleSolicitacaoCriada} />

                {/* Tabela de solicitações existentes */}
                <SolicitacoesTable solicitacoes={solicitacoes} />
            </main>
        </div>
    );
}

export default App;

