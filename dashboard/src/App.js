import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { API_URL, login, getCurrentUser, getSolicitacoes, createSolicitacao, updateSolicitacao } from './api';
import './App.css';
import logo from './assets/logo-onesid.png';
import LoginPage from './LoginPage';

// --- COMPONENTE DO FORMULÁRIO (SolicitacaoForm) ---
const SolicitacaoForm = ({ onSolicitacaoCriada }) => {
    // ... (estado existente: npj, numeroProcesso, etc.)
    const [npj, setNpj] = useState('');
    const [numeroProcesso, setNumeroProcesso] = useState('');
    const [numeroSolicitacao, setNumeroSolicitacao] = useState('');
    const [valor, setValor] = useState('');
    const [dataSolicitacao, setDataSolicitacao] = useState(new Date().toISOString().split('T')[0]);
    // Este campo agora indica se o *usuário* marcou que precisa confirmação no portal
    const [precisaConfirmacaoUsuario, setPrecisaConfirmacaoUsuario] = useState(true);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [success, setSuccess] = useState('');


    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccess('');

        // Validação básica do valor (adicionado .trim())
        const valorLimpo = valor.trim();
        // Substitui vírgula por ponto para o parseFloat
        const valorFloat = parseFloat(valorLimpo.replace(',', '.'));

        // Verifica se é um número válido após a conversão
        if (isNaN(valorFloat)) {
            setError('Valor inválido. Use apenas números, ponto ou vírgula como separador decimal (ex: 1234.56 ou 1234,56).');
            setIsLoading(false);
            return;
        }

        // <<< REMOVIDA a validação extra com regex aqui >>>

        try {
            const dados = {
                npj,
                numero_processo: numeroProcesso || null,
                numero_solicitacao: numeroSolicitacao,
                valor: valorFloat, // Envia como float para a API
                data_solicitacao: dataSolicitacao,
                // Mapeia para o nome esperado pela API/modelo
                aguardando_confirmacao: precisaConfirmacaoUsuario
            };
            await createSolicitacao(dados);
            setSuccess('Solicitação criada com sucesso!');
            // Limpa o formulário
            setNpj('');
            setNumeroProcesso('');
            setNumeroSolicitacao('');
            setValor('');
            setDataSolicitacao(new Date().toISOString().split('T')[0]);
            setPrecisaConfirmacaoUsuario(true); // Reset para o default
            setTimeout(() => setSuccess(''), 3000); // Limpa msg de sucesso
            onSolicitacaoCriada(); // Atualiza a tabela
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
                {/* ... (inputs existentes para NPJ, Numero Processo, Numero Solicitacao) ... */}
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
                    {/* Input de valor com validação simples no frontend */}
                    <input
                        id="valor"
                        type="text" // Usar text para aceitar vírgula ou ponto
                        value={valor}
                        onChange={(e) => setValor(e.target.value)}
                        placeholder="Valor (R$) *"
                        required
                        // REMOVIDO pattern para confiar na validação JS
                        title="Use ponto ou vírgula como separador decimal (ex: 123.45 ou 123,45)"
                    />
                </div>
                <div className="form-group">
                    <input id="dataSolicitacao" type="date" value={dataSolicitacao} onChange={(e) => setDataSolicitacao(e.target.value)} required />
                </div>
                {/* Checkbox renomeado e com label mais claro */}
                <div className="form-group-checkbox checkbox-container">
                    <input
                        id="precisaConfirmacaoUsuario"
                        type="checkbox"
                        checked={precisaConfirmacaoUsuario}
                        onChange={(e) => setPrecisaConfirmacaoUsuario(e.target.checked)}
                    />
                    <label htmlFor="precisaConfirmacaoUsuario">Precisa de Confirmação no Portal BB?</label>
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
const SolicitacoesTable = ({ solicitacoes, onDataRefresh, currentUser }) => { // Recebe currentUser
    // ... (estado existente) ...
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedSolicitacao, setSelectedSolicitacao] = useState(null);
    const [isModalLoading, setIsModalLoading] = useState(false); // Para ações do modal
    const [modalError, setModalError] = useState('');

    const openModal = (solicitacao) => {
        setSelectedSolicitacao(solicitacao);
        setIsModalOpen(true);
        setModalError(''); // Limpa erro ao abrir
    };

    const closeModal = () => {
        if (isModalLoading) return; // Não fecha se estiver carregando
        setIsModalOpen(false);
        setSelectedSolicitacao(null);
    };

    // Formata data/hora ou só data
    const formatData = (dataString) => {
        // ... (código existente sem alterações) ...
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

    // Formata links de comprovantes
    const formatComprovantes = (paths) => {
        // ... (código existente sem alterações) ...
        if (!paths) return <li>Nenhum</li>;
        let links = [];
        try {
            if (Array.isArray(paths)) { links = paths; }
            else if (typeof paths === 'string' && paths.startsWith('[')) { links = JSON.parse(paths); }
            else if (typeof paths === 'string' && paths.trim() !== '') { links = [paths]; }
        } catch (e) { console.error("Erro ao parsear comprovantes_path:", paths, e); return <li>Erro ao ler caminhos</li>; }

        if (!Array.isArray(links) || links.length === 0) return <li>Nenhum</li>;

        return links.map((link, index) => {
            const nomeArquivo = link.split(/[\\/]/).pop() || `Comprovante_${index + 1}`;
            const staticPath = "static/comprovantes";
            const downloadUrl = `${API_URL.replace(/\/$/, '')}/${staticPath}/${link.replace(/^\//, '')}`;

            return (
                <li key={index}>
                    <a href={downloadUrl} target="_blank" rel="noopener noreferrer" download={nomeArquivo}>
                        {nomeArquivo}
                    </a>
                </li>
            );
        });
    };

    // Define classe CSS com base no status do robô
     const getRoboStatusClass = (statusRobo) => {
        // ... (código existente sem alterações) ...
        const s = (statusRobo || 'pendente').toLowerCase();
        if (s.includes('erro')) { return 'erro'; }
        if (s.includes('finalizado')) { return 'finalizado'; }
        if (s.includes('tratado')) { return 'finalizado'; } // Trata status customizado
        return 'pendente';
    };

    // Handler para o botão "Resetar para Pendente"
    const handleResetPendente = async () => {
        // ... (código existente sem alterações) ...
        if (!selectedSolicitacao) return;
        setIsModalLoading(true);
        setModalError('');
        try {
            await updateSolicitacao(selectedSolicitacao.id, {
                status_robo: "Pendente",
                status_portal: null,
                ultima_verificacao_robo: null,
                usuario_confirmacao_id: null,
                usuario_finalizacao_id: null,
                data_finalizacao: null
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

    // Handler para o botão "Marcar como Finalizado/Tratado"
    const handleFinalizarTratamento = async () => {
        // ... (código existente sem alterações) ...
        if (!selectedSolicitacao || !currentUser) return;
        setIsModalLoading(true);
        setModalError('');
        try {
            await updateSolicitacao(selectedSolicitacao.id, {
                finalizar: true
            });
            if (onDataRefresh) { onDataRefresh(); }
            closeModal();
        } catch (err) {
            console.error("Erro ao marcar como finalizado:", err);
            setModalError('Falha ao finalizar: ' + (err.response?.data?.detail || err.message));
        } finally {
            setIsModalLoading(false);
        }
    };

    // Determina se o botão de finalizar deve ser mostrado
    const mostrarBotaoFinalizar = selectedSolicitacao?.status_robo?.toLowerCase().includes('finalizado')
                               && !selectedSolicitacao?.usuario_finalizacao_id;

    // Função auxiliar para formatar o valor na tabela e no modal
    const formatValorDisplay = (valor) => {
        // Tenta converter para número, tratando string ou número
        const num = parseFloat(valor);
        if (!isNaN(num)) {
            return num.toFixed(2).replace('.', ','); // Formata com vírgula para pt-BR
        }
        // Se a conversão falhar (ou for null/undefined), retorna 'Inválido'
        console.warn("Valor inválido recebido:", valor);
        return 'Inválido';
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
                                // Prioriza status do portal, senão do robô, senão 'Pendente'
                                let statusText = item.status_portal || item.status_robo || 'Pendente';
                                // Se já foi finalizado pelo usuário, mostra isso
                                if(item.usuario_finalizacao_id) {
                                    statusText = `Tratado por ${item.usuario_finalizacao?.username || 'usuário'}`;
                                }


                                return (
                                    <tr key={item.id}>
                                        <td>{item.npj}</td>
                                        <td>{item.numero_solicitacao}</td>
                                        {/* USA A NOVA FUNÇÃO DE FORMATAÇÃO */}
                                        <td>{formatValorDisplay(item.valor)}</td>
                                        <td>{formatData(item.data_solicitacao)}</td>
                                        {/* Exibe quem criou */}
                                        <td>{item.usuario_criacao?.username || 'Desconhecido'}</td>
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
                            {/* Informações básicas */}
                            <p><strong>NPJ:</strong> {selectedSolicitacao.npj}</p>
                            <p><strong>Nº Processo:</strong> {selectedSolicitacao.numero_processo || 'N/A'}</p>
                            <p><strong>Nº Solicitação:</strong> {selectedSolicitacao.numero_solicitacao}</p>
                            {/* USA A NOVA FUNÇÃO DE FORMATAÇÃO */}
                            <p><strong>Valor:</strong> R$ {formatValorDisplay(selectedSolicitacao.valor)}</p>
                            <p><strong>Data da Solicitação:</strong> {formatData(selectedSolicitacao.data_solicitacao)}</p>
                            {/* Alteração do texto conforme solicitado */}
                            <p><strong>Confirmação Solicitada (Usuário):</strong> {selectedSolicitacao.aguardando_confirmacao ? 'Sim' : 'Não'}</p>

                            <hr />
                            {/* Informações de Status */}
                            <p><strong>Status Portal BB:</strong> {selectedSolicitacao.status_portal || 'N/A'}</p>
                            <p><strong>Status Robô:</strong> {selectedSolicitacao.status_robo || 'Pendente'}</p>
                            <p><strong>Última Verificação Robô:</strong> {formatData(selectedSolicitacao.ultima_verificacao_robo)}</p>

                            <hr />
                            {/* Informações de Rastreabilidade */}
                            <p><strong>Criado por:</strong> {selectedSolicitacao.usuario_criacao?.username || 'Desconhecido'}</p>
                            <p><strong>Confirmado (Robô) por:</strong> {selectedSolicitacao.usuario_confirmacao?.username || 'N/A'}</p>
                            <p><strong>Finalizado por:</strong> {selectedSolicitacao.usuario_finalizacao?.username || 'N/A'}</p>
                            <p><strong>Data Finalização:</strong> {formatData(selectedSolicitacao.data_finalizacao)}</p>


                            <hr />
                            {/* Comprovantes */}
                            <p><strong>Comprovantes/Documentos:</strong></p>
                            <ul className="comprovantes-list">{formatComprovantes(selectedSolicitacao.comprovantes_path)}</ul>
                        </div>

                        {/* Ações do Modal */}
                        <div className="modal-actions">
                            {modalError && <p className="form-message error">{modalError}</p>}

                            {/* Botão Resetar */}
                            <button
                                onClick={handleResetPendente}
                                className="modal-button-reset"
                                disabled={isModalLoading}
                            >
                                {isModalLoading ? "Processando..." : "Resetar para Pendente"}
                            </button>

                            {/* NOVO: Botão Finalizar */}
                            {mostrarBotaoFinalizar && (
                                <button
                                    onClick={handleFinalizarTratamento}
                                    className="modal-button-finalizar" // Adicionar estilo se necessário
                                    disabled={isModalLoading}
                                >
                                    {isModalLoading ? "Processando..." : "Marcar como Finalizado/Tratado"}
                                </button>
                            )}

                            {/* Botão Fechar */}
                            <button onClick={closeModal} className="modal-close-button" disabled={isModalLoading}>
                                Fechar
                            </button>
                        </div>
                    </div>
                </div>,
                document.getElementById('modal-root') // Garante que o portal exista no index.html
            )}
        </div>
    );
};


// --- COMPONENTE PRINCIPAL DA APLICAÇÃO ---
function App() {
    // ... (código existente do App sem alterações) ...
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [currentUser, setCurrentUser] = useState(null);
    const [solicitacoes, setSolicitacoes] = useState([]);
    const [error, setError] = useState('');

    const fetchData = async () => {
        console.log("Chamando fetchData...");
        setIsLoading(true); // Garante loading ao buscar
        try {
            const userResponse = await getCurrentUser();
            console.log("Dados do usuário recebidos:", userResponse);
            setCurrentUser(userResponse); // Armazena dados do usuário logado

            const solicitacoesResponse = await getSolicitacoes();
            console.log("Solicitações recebidas:", solicitacoesResponse);
            // Ordena por ID decrescente (mais recentes primeiro)
            setSolicitacoes(solicitacoesResponse.sort((a, b) => b.id - a.id));
            setIsLoggedIn(true);
            setError(''); // Limpa erro anterior
        } catch (err) {
             console.error("Erro detalhado em fetchData:", err);
            let detailedError = err.message || 'Verifique a conexão';
            if (err.response) {
                detailedError = `Erro ${err.response.status}: ${err.response.data?.detail || err.message}`;
                 if (err.response.status === 401) {
                     handleLogout(); // Desloga se token for inválido
                     detailedError = "Sessão expirada. Faça login novamente.";
                 }
            } else if (err.request) { detailedError = "Sem resposta do servidor."; }
             setError('Erro ao buscar dados: ' + detailedError);
             // Se não há token, garante estado de deslogado
             if (!localStorage.getItem('token')) {
                 setIsLoggedIn(false);
                 setCurrentUser(null);
             }
        } finally { setIsLoading(false); }
    };

    // Efeito para verificar login inicial
    useEffect(() => {
        console.log("Verificando token no carregamento...");
        const token = localStorage.getItem('token');
        if (token) {
            console.log("Token encontrado. Buscando dados...");
            fetchData(); // Busca dados se houver token
        }
        else {
            console.log("Nenhum token. Indo para login.");
            setIsLoading(false); // Para de carregar se não houver token
            setIsLoggedIn(false); // Garante estado de deslogado
        }
    }, []); // Executa apenas uma vez no mount

    // Handler para sucesso no login
    const handleLoginSuccess = (loginData) => {
        console.log("Login OK, buscando dados pós-login...");
        fetchData(); // Busca dados após login bem-sucedido
    };

    // Handler para logout
    const handleLogout = () => {
        console.log("Executando logout...");
        localStorage.removeItem('token');
        setIsLoggedIn(false);
        setCurrentUser(null);
        setSolicitacoes([]);
        setError('');
        setIsLoading(false); // Para de carregar, se estiver
    };

    // Handler para quando dados precisam ser atualizados (ex: após criar solicitação)
    const handleDataNeedsRefresh = () => {
        console.log("Solicitação de atualização de dados recebida, buscando...");
        fetchData(); // Rebusca todos os dados
    };

    // Tela de carregamento
    if (isLoading) { return <div className="loading-screen">Carregando...</div>; }

    // Tela de login
    if (!isLoggedIn) { return <LoginPage onLoginSuccess={handleLoginSuccess} />; }

    // Tela principal do dashboard
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
                    currentUser={currentUser} // Passa o usuário atual para o modal
                />
            </main>
        </div>
    );
}

export default App;

