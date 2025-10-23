import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
// Importa TODAS as funções da API, incluindo as novas e a URL
import {
    API_URL,
    login,
    getCurrentUser,
    getSolicitacoes,
    createSolicitacao,
    updateSolicitacao,
    archiveSolicitation, // <-- Nova
    resetarErrosSolicitacoes, // <-- Nova
    createUser,         // <-- Nova
    listUsers,          // <-- Nova
    updateUserStatus    // <-- Nova
} from './api';
import './App.css';
import logo from './assets/logo-onesid.png';
import LoginPage from './LoginPage';

// --- COMPONENTE AUXILIAR: Formatador de Data/Hora ---
const formatDataHora = (dataString) => {
    if (!dataString) return 'N/A';
    try {
        // Tenta criar Data assumindo UTC se 'Z' ou offset estiver presente, senão local
        const data = new Date(dataString.endsWith('Z') || dataString.includes('+') || dataString.includes('T') ? dataString : dataString + 'Z');
        if (isNaN(data.getTime())) {
            // Fallback para strings de data simples (YYYY-MM-DD) interpretando como UTC
            const parts = dataString.split('-');
            if (parts.length === 3) {
                 const dataOnly = new Date(Date.UTC(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2])));
                 if (!isNaN(dataOnly.getTime())) {
                     return dataOnly.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
                 }
            }
            console.warn("Formato de data não reconhecido:", dataString);
            return dataString; // Retorna original se não conseguir formatar
        }
        // Verifica se a string original parece ter hora
        if (dataString.includes('T') || dataString.includes(' ')) {
            return data.toLocaleString('pt-BR', {}); // Formato data e hora local
        } else {
            return data.toLocaleDateString('pt-BR', { timeZone: 'UTC' }); // Formato só data (considera UTC)
        }
    } catch (e) {
         console.error("Erro formatando data:", dataString, e);
        return dataString; // Retorna original em caso de erro
    }
};

// --- COMPONENTE AUXILIAR: Formatador de Valor ---
const formatValorDisplay = (valor) => {
    if (valor === null || valor === undefined || valor === '') return 'N/A';
    try {
        // Tenta converter string (com ponto ou vírgula) para número
        const num = typeof valor === 'string' ? parseFloat(valor.replace(',', '.')) : parseFloat(valor);
        if (isNaN(num)) {
            console.warn("Valor inválido para formatValorDisplay:", valor);
            return 'Inválido'; // Retorna 'Inválido' se não for número após tentativa
        }
        // Formata como moeda brasileira
        return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    } catch (e) {
        console.error("Erro ao formatar valor:", valor, e);
        return 'Erro'; // Retorna 'Erro' em caso de exceção na formatação
    }
};


// --- COMPONENTE DO FORMULÁRIO (SolicitacaoForm) ---
const SolicitacaoForm = ({ onSolicitacaoCriada }) => {
    const [npj, setNpj] = useState('');
    const [numeroProcesso, setNumeroProcesso] = useState('');
    const [numeroSolicitacao, setNumeroSolicitacao] = useState('');
    const [valor, setValor] = useState(''); // Manter como string para o input aceitar vírgula
    const [dataSolicitacao, setDataSolicitacao] = useState(new Date().toISOString().split('T')[0]);
    // NOVO NOME: Indica se o *usuário* marcou que precisa de confirmação no portal
    const [precisaConfirmacaoUsuario, setPrecisaConfirmacaoUsuario] = useState(true);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [success, setSuccess] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccess('');

        // Validação básica do valor (aceita vírgula ou ponto, converte para número)
        let valorFloat;
        try {
             const valorLimpo = valor.trim().replace(',', '.');
             // Permite apenas dígitos, um ponto/vírgula opcional e até 2 casas decimais
             if (!/^\d+([.,]\d{1,2})?$/.test(valor.trim()) || valorLimpo === '') {
                 throw new Error("Formato de valor inválido. Use 1234.56 ou 1234,56.");
             }
             valorFloat = parseFloat(valorLimpo);
             if (isNaN(valorFloat)) {
                 throw new Error("Valor não é um número válido.");
             }
             // Verifica se o valor após conversão tem no máximo 2 casas decimais
             if (Math.round(valorFloat * 100) / 100 !== valorFloat) {
                  //throw new Error("Valor deve ter no máximo 2 casas decimais.");
                  // Alternativamente, arredondar:
                  valorFloat = Math.round(valorFloat * 100) / 100;
                  console.warn("Valor arredondado para 2 casas decimais:", valorFloat);
             }

        } catch (err) {
            setError(err.message || 'Valor inválido.');
            setIsLoading(false);
            return;
        }


        try {
            const dados = {
                npj: npj.trim(),
                numero_processo: numeroProcesso.trim() || null,
                numero_solicitacao: numeroSolicitacao.trim(),
                valor: valorFloat, // Envia o número validado
                data_solicitacao: dataSolicitacao,
                aguardando_confirmacao: precisaConfirmacaoUsuario // Nome do campo na API
            };
            await createSolicitacao(dados);
            setSuccess('Solicitação criada com sucesso!');
            // Limpa o formulário
            setNpj('');
            setNumeroProcesso('');
            setNumeroSolicitacao('');
            setValor(''); // Limpa a string do valor
            setDataSolicitacao(new Date().toISOString().split('T')[0]);
            setPrecisaConfirmacaoUsuario(true);
            setTimeout(() => setSuccess(''), 3000); // Limpa mensagem de sucesso
            if(onSolicitacaoCriada) onSolicitacaoCriada(); // Atualiza a lista principal
        } catch (err) {
             const detail = err.response?.data?.detail;
             let message = 'Erro ao criar solicitação.';
             if (typeof detail === 'string') {
                 message += ` ${detail}`;
             } else if (Array.isArray(detail)) {
                 // Formata erros de validação do Pydantic/FastAPI
                 message += ` ${detail.map(d => `${d.loc?.join('/') || 'campo'}: ${d.msg}`).join('; ')}`;
             } else {
                 message += ` ${err.message || 'Verifique os dados.'}`;
             }
            setError(message);
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
                    {/* Input aceita vírgula ou ponto */}
                    <input
                        id="valor"
                        type="text" // Mantido como text para flexibilidade
                        value={valor}
                        onChange={(e) => setValor(e.target.value)}
                        placeholder="Valor (Ex: 1234,56) *"
                        required
                        inputMode="decimal" // Ajuda teclados mobile
                     />
                </div>
                <div className="form-group">
                    <label htmlFor="dataSolicitacao" style={{ fontSize: '0.8rem', marginBottom: '-0.2rem', color: '#ccc' }}>Data Solicitação:</label>
                    <input id="dataSolicitacao" type="date" value={dataSolicitacao} onChange={(e) => setDataSolicitacao(e.target.value)} required />
                </div>
                {/* Checkbox com novo nome e label */}
                <div className="form-group-checkbox checkbox-container">
                    <input id="precisaConfirmacaoUsuario" type="checkbox" checked={precisaConfirmacaoUsuario} onChange={(e) => setPrecisaConfirmacaoUsuario(e.target.checked)} />
                    <label htmlFor="precisaConfirmacaoUsuario">Precisa de Confirmação no Portal?</label>
                </div>
                <button type="submit" disabled={isLoading}>
                    {isLoading ? 'Salvando...' : 'Salvar Solicitação'}
                </button>
                {/* Mensagens de erro/sucesso */}
                {error && <p className="form-message error">{error}</p>}
                {success && <p className="form-message success">{success}</p>}
            </form>
        </div>
    );
};


// --- COMPONENTE DA TABELA DE SOLICITAÇÕES ---
// Recebe currentUser para verificar permissões
const SolicitacoesTable = ({ solicitacoes, currentUser, onDataRefresh }) => {
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedSolicitacao, setSelectedSolicitacao] = useState(null);
    const [isModalLoading, setIsModalLoading] = useState(false);
    const [modalError, setModalError] = useState('');
    const isAdmin = currentUser?.role === 'admin'; // Verifica se é admin

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

    // Função para formatar lista de comprovantes como links
    const formatComprovantes = (paths) => {
        if (!paths || paths.length === 0) return <li>Nenhum</li>;
        let links = [];
        try {
            // Garante que 'paths' seja um array de strings
            if (Array.isArray(paths)) { links = paths.map(String); }
            else if (typeof paths === 'string' && paths.startsWith('[')) { links = JSON.parse(paths).map(String); }
            else if (typeof paths === 'string' && paths.trim() !== '') { links = [paths]; }
        } catch (e) { console.error("Erro ao parsear comprovantes_path:", paths, e); return <li>Erro ao ler caminhos</li>; }

        if (!Array.isArray(links) || links.length === 0) return <li>Nenhum</li>;

        return links.map((link, index) => {
            const nomeArquivo = link.split(/[\\/]/).pop() || `Arquivo ${index + 1}`;
            // Constrói a URL completa para o backend servir o arquivo
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

    // Define a classe CSS para o indicador de status do robô
     const getRoboStatusClass = (statusRobo) => {
        const s = (statusRobo || 'pendente').toLowerCase();
        if (s.includes('erro')) { return 'erro'; }
        if (s.includes('finalizado')) { return 'finalizado'; }
        return 'pendente'; // Pendente, Aguardando, etc.
    };

    // Função para resetar para Pendente (botão no modal)
    const handleResetPendente = async () => {
        if (!selectedSolicitacao || isModalLoading) return;
        setIsModalLoading(true);
        setModalError('');
        console.log(`[SolicitacoesTable] Resetando solicitação ID ${selectedSolicitacao.id} para Pendente...`);
        try {
            await updateSolicitacao(selectedSolicitacao.id, {
                status_robo: "Pendente",
                status_portal: null, // Limpa status do portal
                ultima_verificacao_robo: null, // Limpa última verificação
                usuario_confirmacao_id: null, // Limpa confirmação se houve
                // Não mexe em finalização ou arquivamento aqui
            });
             if (onDataRefresh) {
                 // Passa o estado atual de showArchived para onDataRefresh
                 const showArchivedCheckbox = document.getElementById('showArchived');
                 onDataRefresh(showArchivedCheckbox ? showArchivedCheckbox.checked : false);
             }
            closeModal();
        } catch (err) {
            console.error("Erro ao resetar solicitação:", err);
            setModalError('Falha ao resetar: ' + (err.response?.data?.detail || err.message));
        } finally {
            setIsModalLoading(false);
        }
    };

    // NOVO: Função para Marcar como Finalizado/Tratado (botão no modal)
    const handleFinalizarTratamento = async () => {
        if (!selectedSolicitacao || isModalLoading || selectedSolicitacao.usuario_finalizacao_id) return;
        setIsModalLoading(true);
        setModalError('');
        console.log(`[SolicitacoesTable] Marcando solicitação ID ${selectedSolicitacao.id} como finalizada...`);
        try {
            // Envia a flag 'finalizar: true' para o backend
            await updateSolicitacao(selectedSolicitacao.id, {
                finalizar: true
            });
             if (onDataRefresh) {
                 const showArchivedCheckbox = document.getElementById('showArchived');
                 onDataRefresh(showArchivedCheckbox ? showArchivedCheckbox.checked : false);
             }
            closeModal(); // Fecha o modal após sucesso
        } catch (err) {
             console.error("Erro ao marcar como finalizado:", err);
            setModalError('Falha ao finalizar: ' + (err.response?.data?.detail || err.message));
        } finally {
             setIsModalLoading(false);
        }
    };

    // NOVO: Função para Arquivar/Desarquivar (Admin - botão no modal)
    const handleToggleArchive = async () => {
        if (!selectedSolicitacao || isModalLoading || !isAdmin) return;
        const newArchiveStatus = !selectedSolicitacao.is_archived;
        setIsModalLoading(true);
        setModalError('');
        console.log(`[SolicitacoesTable] Admin ${currentUser.username} ${newArchiveStatus ? 'arquivando' : 'desarquivando'} solicitação ID ${selectedSolicitacao.id}...`);
        try {
            // A API espera { "is_archived": true/false }
            await archiveSolicitation(selectedSolicitacao.id, newArchiveStatus);
             if (onDataRefresh) {
                 // Ao arquivar/desarquivar, recarrega a lista respeitando o filtro atual
                 const showArchivedCheckbox = document.getElementById('showArchived');
                 onDataRefresh(showArchivedCheckbox ? showArchivedCheckbox.checked : false);
            }
            closeModal(); // Fecha o modal
        } catch (err) {
            console.error("Erro ao arquivar/desarquivar:", err);
            setModalError('Falha ao arquivar/desarquivar: ' + (err.response?.data?.detail || err.message));
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
                            <th>Valor</th>
                            <th>Data Solicitação</th>
                            <th>Criado Por</th>
                            <th>Status Robô/Portal</th> {/* Coluna de Status Atualizada */}
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {solicitacoes.length > 0 ? (
                            solicitacoes.map(item => {
                                const statusRoboClasse = getRoboStatusClass(item.status_robo);
                                // Prioriza Status Portal, senão Robô, senão 'Pendente'
                                let statusText = item.status_portal || item.status_robo || 'Pendente';
                                // NOVO: Adiciona "(Tratado por ...)" se finalizado pelo usuário
                                if(item.usuario_finalizacao) {
                                    statusText += ` (Tratado por ${item.usuario_finalizacao.username})`;
                                }
                                // NOVO: Adiciona "(Arquivado)" se estiver arquivado
                                if(item.is_archived) {
                                    statusText = `(Arquivado)`; // Sobrescreve outros status se arquivado
                                }

                                return (
                                    <tr key={item.id} className={item.is_archived ? 'archived-row' : ''}>
                                        <td>{item.npj}</td>
                                        <td>{item.numero_solicitacao}</td>
                                        {/* Usa a função formatValorDisplay */}
                                        <td>{formatValorDisplay(item.valor)}</td>
                                        <td>{formatDataHora(item.data_solicitacao)}</td>
                                        {/* Agora usa usuario_criacao */}
                                        <td>{item.usuario_criacao?.username || 'Desconhecido'}</td>
                                        <td>
                                          {/* Status combinado (indicador + texto) */}
                                          <div className="status-cell">
                                            {!item.is_archived && ( /* Só mostra bolinha se não arquivado */
                                                <span
                                                  className={`status-indicator status-${statusRoboClasse}`}
                                                  title={`Status Robô: ${item.status_robo || 'Pendente'}\nStatus Portal: ${item.status_portal || 'N/A'}`}
                                                ></span>
                                             )}
                                            <span className="status-text">
                                              {statusText}
                                            </span>
                                          </div>
                                        </td>
                                        <td>
                                            {/* Botão para abrir o modal */}
                                            <button onClick={() => openModal(item)} className="action-button" title="Ver Detalhes e Ações">
                                                👁️
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })
                        ) : ( <tr><td colSpan="7">Nenhuma solicitação encontrada.</td></tr> )}
                    </tbody>
                </table>
             </div>

            {/* Modal de Detalhes (Renderizado via Portal) */}
             {isModalOpen && selectedSolicitacao && createPortal(
                <div className="modal-backdrop" onClick={closeModal}>
                    <div className="modal-content" onClick={e => e.stopPropagation()}>
                        <h3>Detalhes da Solicitação (ID: {selectedSolicitacao.id})</h3>
                        <div className="modal-details">
                            <p><strong>Status Atual:</strong> {selectedSolicitacao.is_archived ? '(Arquivado)' : (selectedSolicitacao.status_portal || selectedSolicitacao.status_robo || 'Pendente')} </p>
                            <hr />
                            <p><strong>NPJ:</strong> {selectedSolicitacao.npj}</p>
                            <p><strong>Nº Processo:</strong> {selectedSolicitacao.numero_processo || 'N/A'}</p>
                            <p><strong>Nº Solicitação Portal:</strong> {selectedSolicitacao.numero_solicitacao}</p>
                            <p><strong>Valor:</strong> {formatValorDisplay(selectedSolicitacao.valor)}</p>
                            <p><strong>Data da Solicitação (Portal):</strong> {formatDataHora(selectedSolicitacao.data_solicitacao)}</p>
                            <p><strong>Confirmação Solicitada (Usuário):</strong> {selectedSolicitacao.aguardando_confirmacao ? 'Sim' : 'Não'}</p>
                            <hr />
                            <p><strong>Criado por:</strong> {selectedSolicitacao.usuario_criacao?.username || 'Desconhecido'}</p>
                            <p><strong>Confirmado (Robô) por:</strong> {selectedSolicitacao.usuario_confirmacao?.username || 'N/A'}</p>
                            <p><strong>Finalizado/Tratado por:</strong> {selectedSolicitacao.usuario_finalizacao?.username || 'Não'} {selectedSolicitacao.data_finalizacao ? `em ${formatDataHora(selectedSolicitacao.data_finalizacao)}` : ''}</p>
                            <p><strong>Arquivado por:</strong> {selectedSolicitacao.usuario_arquivamento?.username || 'Não'} {selectedSolicitacao.data_arquivamento ? `em ${formatDataHora(selectedSolicitacao.data_arquivamento)}` : ''}</p>
                            <hr />
                            <p><strong>Status Robô:</strong> {selectedSolicitacao.status_robo || 'Pendente'}</p>
                            <p><strong>Status Portal (último visto):</strong> {selectedSolicitacao.status_portal || 'N/A'}</p>
                            <p><strong>Última Verificação Robô:</strong> {formatDataHora(selectedSolicitacao.ultima_verificacao_robo)}</p>
                            <hr />
                            <p><strong>Comprovantes/Documentos:</strong></p>
                            <ul className="comprovantes-list">{formatComprovantes(selectedSolicitacao.comprovantes_path)}</ul>
                        </div>
                        {/* Ações no Modal */}
                        <div className="modal-actions">
                             {/* Mensagem de erro específica do modal */}
                            {modalError && <p className="form-message error" style={{ flexGrow: 1, textAlign: 'left' }}>{modalError}</p>}

                            {/* Botão Resetar para Pendente (SÓ SE NÃO ARQUIVADO) */}
                            {!selectedSolicitacao.is_archived && (
                                <button
                                    onClick={handleResetPendente}
                                    className="modal-button-reset"
                                    disabled={isModalLoading}
                                    title={"Força o robô a verificar novamente"}
                                >
                                    {isModalLoading ? "Resetando..." : "Resetar para Pendente"}
                                </button>
                            )}

                            {/* Botão Marcar como Finalizado/Tratado (SÓ SE NÃO ARQUIVADO e se aplicável)*/}
                            {!selectedSolicitacao.is_archived && selectedSolicitacao.status_robo?.toLowerCase().includes('finalizado') && !selectedSolicitacao.usuario_finalizacao_id && (
                                <button
                                    onClick={handleFinalizarTratamento}
                                    className="modal-button-finalize"
                                    disabled={isModalLoading}
                                    title="Marcar que os documentos foram tratados/inseridos no sistema externo"
                                >
                                    {isModalLoading ? 'Finalizando...' : 'Marcar como Tratado'}
                                </button>
                            )}

                             {/* Botão Arquivar/Desarquivar (Admin) */}
                             {isAdmin && (
                                <button
                                    onClick={handleToggleArchive}
                                    className={`modal-button-archive ${selectedSolicitacao.is_archived ? 'secondary' : 'warning'}`}
                                    disabled={isModalLoading}
                                    title={selectedSolicitacao.is_archived ? "Retorna a solicitação para a lista ativa" : "Remove a solicitação da lista principal"}
                                >
                                    {isModalLoading ? (selectedSolicitacao.is_archived ? 'Desarquivando...' : 'Arquivando...') : (selectedSolicitacao.is_archived ? 'Desarquivar' : 'Arquivar')}
                                </button>
                             )}

                            {/* Botão Fechar */}
                            <button onClick={closeModal} className="modal-close-button" disabled={isModalLoading}>
                                Fechar
                            </button>
                        </div>
                    </div>
                </div>,
                document.getElementById('modal-root') // Renderiza no portal do modal
            )}
        </div>
    );
};


// --- NOVO: COMPONENTE DO FORMULÁRIO DE CRIAÇÃO DE USUÁRIO (Admin) ---
const UserCreateForm = ({ onUserCreated }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [role, setRole] = useState('user'); // Default 'user'
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [success, setSuccess] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!username.trim() || !password.trim()) {
            setError('Usuário e senha são obrigatórios.');
            return;
        }
        setIsLoading(true);
        setError('');
        setSuccess('');

        try {
            await createUser({ username: username.trim(), password, role });
            setSuccess(`Usuário '${username.trim()}' criado com sucesso!`);
            setUsername('');
            setPassword('');
            setRole('user');
            setTimeout(() => setSuccess(''), 4000);
            if(onUserCreated) onUserCreated(); // Avisa o painel admin para recarregar a lista
        } catch (err) {
             const message = err.response?.data?.detail || err.message || 'Erro desconhecido.';
            setError(`Erro ao criar usuário: ${message}`);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="user-create-form" style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <div className="form-group" style={{ flexGrow: 1, minWidth: '150px' }}>
                <label htmlFor="newUsername">Novo Usuário:</label>
                <input id="newUsername" type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Nome de usuário" required />
            </div>
            <div className="form-group" style={{ flexGrow: 1, minWidth: '150px' }}>
                <label htmlFor="newPassword">Senha:</label>
                <input id="newPassword" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Senha" required />
            </div>
            <div className="form-group">
                <label htmlFor="newRole">Permissão:</label>
                <select id="newRole" value={role} onChange={(e) => setRole(e.target.value)} required>
                    <option value="user">Usuário</option>
                    <option value="admin">Admin</option>
                </select>
            </div>
            <button type="submit" disabled={isLoading} style={{ padding: '10px 15px', height: '44px' }}>
                {isLoading ? 'Criando...' : 'Criar Usuário'}
            </button>
            {error && <p className="form-message error" style={{ width: '100%', margin: '0.5rem 0 0 0' }}>{error}</p>}
            {success && <p className="form-message success" style={{ width: '100%', margin: '0.5rem 0 0 0' }}>{success}</p>}
        </form>
    );
};

// --- NOVO: COMPONENTE DA TABELA DE GERENCIAMENTO DE USUÁRIOS (Admin) ---
const UserListTable = ({ users: initialUsers = [], currentUser, onUserListChanged }) => {
    const [users, setUsers] = useState(initialUsers);
    const [loadingStates, setLoadingStates] = useState({}); // { userId: boolean }
    const [error, setError] = useState('');

    // Atualiza a lista local se a prop mudar
    useEffect(() => {
        setUsers(initialUsers);
    }, [initialUsers]);

    const handleToggleActive = async (userToUpdate) => {
        // Impede admin de desativar a si mesmo ou o usuário 'admin' principal
        if ((userToUpdate.id === currentUser.id || userToUpdate.username === 'admin') && !userToUpdate.is_active === false) {
             setError("Não é possível desativar a si mesmo ou o usuário 'admin'.");
             setTimeout(() => setError(''), 4000);
             return;
        }


        const newStatus = !userToUpdate.is_active;
        setLoadingStates(prev => ({ ...prev, [userToUpdate.id]: true }));
        setError('');

        try {
            await updateUserStatus(userToUpdate.id, newStatus);
            // Atualiza a lista localmente para refletir a mudança imediatamente
            setUsers(prevUsers => prevUsers.map(u =>
                u.id === userToUpdate.id ? { ...u, is_active: newStatus } : u
            ));
            // Opcional: Chamar onUserListChanged() se precisar recarregar do backend
            // if(onUserListChanged) onUserListChanged();
        } catch (err) {
            setError(`Erro ao ${newStatus ? 'ativar' : 'desativar'} usuário: ${err.response?.data?.detail || err.message}`);
        } finally {
            setLoadingStates(prev => ({ ...prev, [userToUpdate.id]: false }));
        }
    };

    return (
        <div className="user-list-container">
            <h3>Usuários Cadastrados</h3>
            {error && <p className="form-message error">{error}</p>}
            <div className="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Username</th>
                            <th>Role</th>
                            <th>Status</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {users.length > 0 ? (
                            users.map(user => {
                                const isLoading = loadingStates[user.id];
                                // Condição para desabilitar o botão
                                const isDisabled = isLoading || ((user.id === currentUser.id || user.username === 'admin') && user.is_active);

                                return (
                                    <tr key={user.id}>
                                        <td>{user.id}</td>
                                        <td>{user.username}</td>
                                        <td>{user.role}</td>
                                        <td>{user.is_active ? 'Ativo' : 'Inativo'}</td>
                                        <td>
                                            <button
                                                onClick={() => handleToggleActive(user)}
                                                disabled={isDisabled}
                                                className={user.is_active ? 'button-deactivate' : 'button-activate'} // Adicionar estilos CSS
                                                title={isDisabled ? "Não pode alterar status" : (user.is_active ? 'Desativar usuário' : 'Ativar usuário')}
                                            >
                                                {isLoading ? '...' : (user.is_active ? 'Desativar' : 'Ativar')}
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })
                        ) : (
                            <tr><td colSpan="5">Nenhum usuário encontrado (além de você).</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};


// --- NOVO: COMPONENTE DO PAINEL DE ADMINISTRAÇÃO ---
const AdminPanel = ({ currentUser, onDataRefresh }) => {
    const [users, setUsers] = useState([]);
    const [isLoadingUsers, setIsLoadingUsers] = useState(false);
    const [userListError, setUserListError] = useState('');
    const [showArchived, setShowArchived] = useState(false); // Estado para ver arquivados
    const [isResettingErrors, setIsResettingErrors] = useState(false);
    const [resetError, setResetError] = useState('');
    const [resetSuccess, setResetSuccess] = useState('');

    const fetchUsers = useCallback(async () => {
        setIsLoadingUsers(true);
        setUserListError('');
        try {
            const userList = await listUsers();
            setUsers(userList);
        } catch (err) {
            setUserListError('Erro ao carregar lista de usuários: ' + (err.response?.data?.detail || err.message));
        } finally {
            setIsLoadingUsers(false);
        }
    }, []); // useCallback para evitar recriação desnecessária

    // Carrega usuários ao montar o painel
    useEffect(() => {
        fetchUsers();
    }, [fetchUsers]);

    // Função para recarregar a lista de usuários (chamada pelo UserCreateForm)
    const handleUserListChanged = () => {
        fetchUsers();
    };

     // Função para o botão de resetar erros
     const handleResetErrors = async () => {
        setIsResettingErrors(true);
        setResetError('');
        setResetSuccess('');
        try {
            const result = await resetarErrosSolicitacoes();
            setResetSuccess(result.message || 'Status de erro resetados com sucesso.');
            if(onDataRefresh) onDataRefresh(showArchived); // Atualiza lista de solicitações
            setTimeout(() => setResetSuccess(''), 5000);
        } catch (err) {
             setResetError('Erro ao resetar status: ' + (err.response?.data?.detail || err.message));
        } finally {
            setIsResettingErrors(false);
        }
    };

    // Callback para o checkbox de arquivados
    const handleShowArchivedChange = (e) => {
        const checked = e.target.checked;
        setShowArchived(checked);
        if(onDataRefresh) onDataRefresh(checked); // Pede para App.js recarregar com o novo filtro
    };


    return (
        <div className="card admin-panel">
            <h2>Painel Administrativo</h2>

            {/* Gerenciamento de Usuários */}
            <section className="admin-section">
                <UserCreateForm onUserCreated={handleUserListChanged} />
                {userListError && <p className="form-message error">{userListError}</p>}
                {isLoadingUsers ? <p>Carregando usuários...</p> : (
                    <UserListTable users={users} currentUser={currentUser} onUserListChanged={handleUserListChanged} />
                )}
            </section>

             <hr style={{ margin: '2rem 0', borderColor: 'rgba(255,255,255,0.1)' }}/>

             {/* Outras Ações Admin */}
            <section className="admin-section">
                <h3>Ações Gerais</h3>
                 {/* Checkbox para ver arquivados */}
                 <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center' }}>
                    <input
                        type="checkbox"
                        id="showArchived"
                        checked={showArchived}
                        onChange={handleShowArchivedChange}
                        style={{ marginRight: '0.5rem', width: 'auto' }}
                    />
                    <label htmlFor="showArchived"> Exibir solicitações arquivadas</label>
                </div>

                 {/* Botão para Resetar Erros */}
                <button
                    onClick={handleResetErrors}
                    disabled={isResettingErrors}
                    className="button-reset-errors" // Adicionar estilo se necessário
                    style={{ backgroundColor: '#f0ad4e', color: '#111' }}
                 >
                     {isResettingErrors ? 'Resetando...' : 'Resetar Status de Erro'}
                </button>
                {resetError && <p className="form-message error" style={{marginTop: '0.5rem'}}>{resetError}</p>}
                {resetSuccess && <p className="form-message success" style={{marginTop: '0.5rem'}}>{resetSuccess}</p>}
            </section>
        </div>
    );
};


// --- COMPONENTE PRINCIPAL DA APLICAÇÃO ---
function App() {
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isLoading, setIsLoading] = useState(true); // Controla o carregamento inicial
    const [currentUser, setCurrentUser] = useState(null); // Armazena dados do usuário logado
    const [solicitacoes, setSolicitacoes] = useState([]);
    const [error, setError] = useState(''); // Erro global da aplicação

    // Função para buscar dados do usuário e solicitações
    // useCallback para evitar recriações desnecessárias, aceita 'includeArchived'
    const fetchData = useCallback(async (includeArchived = false) => {
        console.log(`[App] Chamando fetchData... includeArchived=${includeArchived}`);
        setError(''); // Limpa erros antigos
        let userToUse = currentUser; // Usa o estado atual como base

        try {
            // Se não temos usuário no estado, busca
            if (!userToUse) {
                console.log("[App] Buscando dados do usuário...");
                userToUse = await getCurrentUser();
                setCurrentUser(userToUse); // Atualiza o estado
            } else {
                 console.log("[App] Usando dados do usuário do estado:", userToUse);
            }

            console.log("[App] Buscando solicitações...");
            const solicitacoesResponse = await getSolicitacoes(includeArchived);
            console.log("[App] Solicitações recebidas:", solicitacoesResponse);
            // Ordena por ID decrescente
            setSolicitacoes(solicitacoesResponse.sort((a, b) => b.id - a.id));
            setIsLoggedIn(true); // Confirma que está logado
        } catch (err) {
             console.error("[App] Erro detalhado em fetchData:", err);
             let detailedError = err.message || 'Verifique a conexão';
             if (err.response) {
                 detailedError = `Erro ${err.response.status}: ${err.response.data?.detail || err.message}`;
                 // O interceptor já trata o 401 para deslogar
             } else if (err.request) {
                 detailedError = "Sem resposta do servidor.";
             }
             setError('Erro ao buscar dados: ' + detailedError);
             // Se o erro não for 401, mas não temos token, desloga preventivamente
             if (!localStorage.getItem('token') && err.response?.status !== 401) {
                 handleLogout(); // Chama a função de logout definida abaixo
             }
        } finally {
             // Garante que o estado de carregamento seja desativado
             setIsLoading(false);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentUser]); // Recria fetchData SÓ se currentUser mudar

     // Função de Logout - precisa ser definida antes de ser usada no useCallback
     const handleLogout = useCallback(() => {
        console.log("[App] Executando logout...");
        localStorage.removeItem('token');
        setIsLoggedIn(false);
        setCurrentUser(null);
        setSolicitacoes([]);
        setError('');
        setIsLoading(false); // Garante que não fique carregando
    }, []); // useCallback sem dependências


    // Efeito para verificar o token e buscar dados iniciais
    useEffect(() => {
        console.log("[App useEffect] Verificando token...");
        const token = localStorage.getItem('token');
        if (token) {
            console.log("[App useEffect] Token encontrado. Buscando dados iniciais...");
            setIsLoading(true); // Ativa o loading ANTES de chamar fetchData
            fetchData(false); // Busca inicial sem arquivados
        } else {
            console.log("[App useEffect] Nenhum token. Indo para login.");
            setIsLoading(false); // Não está carregando se não tem token
            setIsLoggedIn(false);
            setCurrentUser(null);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fetchData]); // Adiciona fetchData como dependência

    // Callback para quando o login for bem-sucedido
    const handleLoginSuccess = useCallback((loginData) => {
        console.log("[App] Login OK. Iniciando busca de dados pós-login...");
        setIsLoading(true); // Mostra carregando enquanto busca dados
        setCurrentUser(null); // Limpa usuário anterior para forçar busca em fetchData
        // fetchData será chamado pelo useEffect porque currentUser mudou para null
        // OU podemos chamar diretamente:
        // fetchData(false); // Mas precisa garantir que o estado currentUser seja atualizado *antes*
        // A abordagem mais segura é deixar o useEffect reagir à limpeza do currentUser
        // Ajuste: Vamos chamar fetchData diretamente após limpar currentUser para garantir.
        fetchData(false); // Busca dados após login, sem arquivados

    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fetchData]); // Depende de fetchData


    // Callback para componentes filhos solicitarem atualização de dados
    const handleDataNeedsRefresh = useCallback((includeArchived = false) => {
        console.log(`[App] Solicitação de atualização de dados recebida. includeArchived=${includeArchived}`);
        // Ativa o loading SÓ se não estiver já carregando de outra forma
        // if (!isLoading) setIsLoading(true); // Opcional: Mostrar loading em refresh? Pode piscar.
        fetchData(includeArchived);
    }, [fetchData]); // Depende de fetchData


    // Tela de Carregamento Inicial
    if (isLoading && !currentUser) { // Mostra loading só se estiver realmente carregando dados iniciais
        return <div className="loading-screen">Carregando...</div>;
    }

    // Tela de Login
    if (!isLoggedIn) {
        return <LoginPage onLoginSuccess={handleLoginSuccess} />;
    }

    // Tela Principal (Dashboard)
    return (
        <div className="App main-app">
            <header className="app-header">
                <img src={logo} alt="MDR Advocacia Logo" className="logo" />
                <div className="user-info">
                    <span>Olá, {currentUser?.username || 'Usuário'} ({currentUser?.role || 'N/D'})</span>
                    <button onClick={handleLogout} className="logout-button">Sair</button>
                </div>
            </header>
            <main>
                {/* Mensagem de Erro Global */}
                {error && <p className="global-error-message">{error}</p>}

                 {/* Painel Admin - Renderizado Condicionalmente */}
                 {currentUser?.role === 'admin' && (
                     <AdminPanel currentUser={currentUser} onDataRefresh={handleDataNeedsRefresh} />
                 )}

                {/* Formulário de Criação de Solicitação (Todos usuários ativos podem ver) */}
                <SolicitacaoForm onSolicitacaoCriada={() => handleDataNeedsRefresh(false)} /> {/* Sempre recarrega sem arquivados ao criar */}

                {/* Tabela de Solicitações */}
                <SolicitacoesTable
                    solicitacoes={solicitacoes}
                    currentUser={currentUser} // Passa o usuário atual para a tabela
                    onDataRefresh={handleDataNeedsRefresh} // Passa a função de refresh
                />
            </main>
        </div>
    );
}

export default App;

