import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
// Importa TODAS as funções da API, incluindo as novas e a URL
import {
    API_URL,
    login,
    getCurrentUser,
    getSolicitacoes,
    createSolicitacao,
    updateSolicitacao,
    archiveSolicitation,
    resetarErrosSolicitacoes,
    createUser,
    listUsers,
    updateUserStatus,
    updateUser // <<< NOVO: Importa a função updateUser
} from './api';
import './App.css'; // Voltamos a usar o App.css original como base
import logo from './assets/logo-onesid.png';
import LoginPage from './LoginPage';

// --- Ícones SVG ---
// (Ícones mantidos como na versão anterior)
const DownloadIcon = () => ( <svg xmlns="http://www.w3.org/2000/svg" className="icon icon-download" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}> <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /> </svg> );
const CopyIcon = () => ( <svg xmlns="http://www.w3.org/2000/svg" className="icon icon-copy" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}> <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /> </svg> );
const EllipsisVerticalIcon = () => ( <svg xmlns="http://www.w3.org/2000/svg" className="icon icon-ellipsis" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" /> </svg> );
const CloseIcon = () => ( <svg xmlns="http://www.w3.org/2000/svg" className="icon icon-close" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}> <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /> </svg> );
const DetailsIcon = () => ( <svg xmlns="http://www.w3.org/2000/svg" className="icon icon-details" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"> <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /> </svg> );
const ChevronDownIcon = ({ isOpen }) => ( <svg xmlns="http://www.w3.org/2000/svg" className={`icon icon-chevron ${isOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /> </svg> );
const AdminIcon = () => ( <svg xmlns="http://www.w3.org/2000/svg" className="icon icon-admin" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /> <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /> </svg> );
const EditIcon = () => ( <svg xmlns="http://www.w3.org/2000/svg" className="icon icon-edit" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /> </svg> );


// --- Funções Auxiliares ---
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
                     // Para datas simples, retorna apenas a data formatada
                     return dataOnly.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
                 }
            }
            console.warn("Formato de data não reconhecido:", dataString);
            return dataString; // Retorna original se não conseguir formatar
        }
        // Verifica se a string original parece ter hora
        if (dataString.includes('T') || dataString.includes(' ')) {
             // Para data/hora completas, retorna formato local completo
            return data.toLocaleString('pt-BR', {}); // Formato data e hora local
        } else {
             // Para strings que são apenas data (mas parseadas com sucesso), retorna só data (UTC)
            return data.toLocaleDateString('pt-BR', { timeZone: 'UTC' }); // Formato só data (considera UTC)
        }
    } catch (e) {
         console.error("Erro formatando data:", dataString, e);
        return dataString; // Retorna original em caso de erro
    }
};

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

const normalizeCurrencyString = (rawValue) => {
    if (!rawValue) return '';

    const cleanedValue = String(rawValue).replace(/[^\d,.-]/g, '').trim();
    if (!cleanedValue) return '';

    const hasComma = cleanedValue.includes(',');
    const hasDot = cleanedValue.includes('.');

    if (hasComma && hasDot) {
        return cleanedValue.replace(/\./g, '').replace(',', '.');
    }

    if (hasComma) {
        return cleanedValue.replace(',', '.');
    }

    return cleanedValue;
};

const normalizeDateString = (rawValue) => {
    if (!rawValue) return '';

    const dateValue = String(rawValue).trim();

    const brDateMatch = dateValue.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (brDateMatch) {
        const [, day, month, year] = brDateMatch;
        return `${year}-${month}-${day}`;
    }

    const isoDateMatch = dateValue.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (isoDateMatch) {
        return dateValue;
    }

    return '';
};

const toFortalezaIsoString = (dateTimeLocal) => {
    if (!dateTimeLocal) return null;

    const match = String(dateTimeLocal).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
    if (!match) return null;

    const [, year, month, day, hour, minute] = match;
    return `${year}-${month}-${day}T${hour}:${minute}:00-03:00`;
};

const buildStaticDownloadUrl = (relativePath) => {
    const baseUrl = API_URL.replace(/\/$/, '');
    const normalizedPath = String(relativePath || '').replace(/^\/+/, '');
    const encodedPath = normalizedPath
        .split('/')
        .filter(Boolean)
        .map((segment) => encodeURIComponent(segment))
        .join('/');

    return `${baseUrl}/static/comprovantes/${encodedPath}`;
};

const getRobotStatusClass = (statusRobo, isArchived = false, isTratado = false) => {
    if (isArchived) return 'archived';
    if (isTratado) return 'finalizado';

    const normalizedStatus = String(statusRobo || 'pendente').toLowerCase();
    if (normalizedStatus.includes('erro')) return 'erro';
    if (normalizedStatus.includes('alerta')) return 'alerta';
    if (normalizedStatus.includes('suspens')) return 'pausado';
    if (normalizedStatus.includes('monitorando')) return 'pendente';
    if (normalizedStatus.includes('finalizado')) return 'finalizado';
    return 'pendente';
};

const getPortalStatusClass = (statusPortal) => {
    const normalizedStatus = String(statusPortal || '').toLowerCase();
    if (!normalizedStatus) return 'neutro';
    if (
        normalizedStatus.includes('cancel') ||
        normalizedStatus.includes('reprov') ||
        normalizedStatus.includes('recus') ||
        normalizedStatus.includes('devolv')
    ) {
        return 'erro';
    }
    if (
        normalizedStatus.includes('efetivad') ||
        normalizedStatus.includes('liquid')
    ) {
        return 'finalizado';
    }
    if (
        normalizedStatus.includes('aguardando') ||
        normalizedStatus.includes('processamento')
    ) {
        return 'pendente';
    }
    return 'neutro';
};

const getPrazoFatalState = (prazoFatalEm, statusRobo) => {
    if (!prazoFatalEm) return 'none';

    const prazoDate = new Date(prazoFatalEm);
    if (Number.isNaN(prazoDate.getTime())) return 'none';

    const robotStatus = String(statusRobo || '').toLowerCase();
    if (robotStatus.includes('finalizado')) return 'safe';

    const now = new Date();
    const diffMs = prazoDate.getTime() - now.getTime();
    if (diffMs <= 0) return 'expired';
    if (diffMs <= 6 * 60 * 60 * 1000) return 'critical';
    if (diffMs <= 24 * 60 * 60 * 1000) return 'warning';
    return 'safe';
};

const splitTabbedLine = (text) => String(text || '')
    .split(/\t+/)
    .map((part) => part.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

const parseSolicitacaoPaste = (text) => {
    const rawText = String(text || '');
    const normalizedText = rawText.replace(/\s+/g, ' ').trim();
    if (!normalizedText) {
        throw new Error('Cole uma linha com os dados para preencher automaticamente.');
    }

    const tabParts = splitTabbedLine(rawText);
    if (tabParts.length >= 6) {
        const [npj, numeroSolicitacao, tribunal, especificacao, statusPortal, dataSolicitacao, ...rest] = tabParts;
        const valorTexto = rest.join(' ').trim();

        return {
            npj: npj || '',
            numeroProcesso: '',
            numeroSolicitacao: numeroSolicitacao || '',
            tribunal: tribunal || '',
            especificacao: especificacao || '',
            statusPortal: statusPortal || '',
            valor: normalizeCurrencyString(valorTexto),
            dataSolicitacao: normalizeDateString(dataSolicitacao || '')
        };
    }

    const processMatch = normalizedText.match(/\d{7}-\d{2}\.\d{4}\.\d(?:\.\d{2})?\.\d{4}/);
    const npjMatch = normalizedText.match(/\b[\d/-]{4,}\b/);

    const solicitationRegexes = [
        /solicita(?:c|ç)(?:a|ã)o[:\s#-]*([A-Za-z0-9./-]{4,})/i,
        /(?:n[º°o.]?\s*)?solicita(?:c|ç)(?:a|ã)o[:\s#-]*([A-Za-z0-9./-]{4,})/i
    ];
    const solicitationMatch = solicitationRegexes
        .map((regex) => normalizedText.match(regex))
        .find(Boolean);

    const currencyMatches = [...normalizedText.matchAll(/\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+\.\d{2}\b|\b\d+,\d{2}\b/g)];
    const lastCurrency = currencyMatches.length > 0 ? currencyMatches[currencyMatches.length - 1][0] : '';
    const dateMatch = normalizedText.match(/\b\d{2}\/\d{2}\/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b/);

    const fallbackNumbers = normalizedText.match(/\b\d{4,}\b/g) || [];
    const solicitationFallback = fallbackNumbers.find((item) => item !== npjMatch?.[0] && item !== processMatch?.[0]);

    return {
        npj: npjMatch?.[0] || '',
        numeroProcesso: processMatch?.[0] || '',
        tribunal: '',
        especificacao: '',
        statusPortal: '',
        numeroSolicitacao: solicitationMatch?.[1] || solicitationFallback || '',
        valor: normalizeCurrencyString(lastCurrency),
        dataSolicitacao: normalizeDateString(dateMatch?.[0] || '')
    };
};

// --- COMPONENTE DO FORMULÁRIO (SolicitacaoForm) ---
const SolicitacaoForm = ({ onSolicitacaoCriada }) => {
    const [linhaCopiada, setLinhaCopiada] = useState('');
    const [parsedSolicitacao, setParsedSolicitacao] = useState(null);
    const [prazoFatal, setPrazoFatal] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [success, setSuccess] = useState('');

    useEffect(() => {
        if (!linhaCopiada.trim()) {
            setParsedSolicitacao(null);
            setError('');
            return;
        }

        try {
            const parsed = parseSolicitacaoPaste(linhaCopiada);

            if (!parsed.npj || !parsed.numeroSolicitacao || !parsed.valor || !parsed.dataSolicitacao) {
                throw new Error('Não consegui reconhecer todos os campos obrigatórios da linha: NPJ, número da solicitação, data e valor.');
            }

            setParsedSolicitacao({
                ...parsed,
                aguardandoConfirmacao: true
            });
            setError('');
        } catch (err) {
            setParsedSolicitacao(null);
            setError(err.message || 'Não foi possível interpretar a linha colada.');
        }
    }, [linhaCopiada]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccess('');

        if (!parsedSolicitacao) {
            setError('Cole uma linha válida para confirmar e salvar.');
            setIsLoading(false);
            return;
        }

        let valorFloat;
        try {
             const valorLimpo = parsedSolicitacao.valor.trim().replace(',', '.');
             if (valorLimpo !== '' && !/^\d+([.,]\d{1,2})?$/.test(valorLimpo) ) {
                 throw new Error("Formato de valor inválido. Use 1234.56 ou 1234,56.");
             }
             valorFloat = valorLimpo === '' ? 0.0 : parseFloat(valorLimpo);
             if (isNaN(valorFloat)) {
                 throw new Error("Valor não é um número válido.");
             }
             valorFloat = Math.round(valorFloat * 100) / 100;
        } catch (err) {
            setError(err.message || 'Valor inválido.');
            setIsLoading(false);
            return;
        }

        try {
            const dados = {
                npj: parsedSolicitacao.npj.trim(),
                numero_processo: parsedSolicitacao.numeroProcesso?.trim() || null,
                numero_solicitacao: parsedSolicitacao.numeroSolicitacao.trim(),
                especificacao: parsedSolicitacao.especificacao?.trim() || null,
                status_portal: parsedSolicitacao.statusPortal?.trim() || null,
                prazo_fatal_em: toFortalezaIsoString(prazoFatal),
                monitoramento_ativo: true,
                valor: valorFloat,
                data_solicitacao: parsedSolicitacao.dataSolicitacao,
                aguardando_confirmacao: parsedSolicitacao.aguardandoConfirmacao
            };
            await createSolicitacao(dados);
            setSuccess('Solicitação criada com sucesso!');
            setLinhaCopiada('');
            setParsedSolicitacao(null);
            setPrazoFatal('');
            setTimeout(() => setSuccess(''), 3000);
            if(onSolicitacaoCriada) onSolicitacaoCriada();
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

    // Layout inline original mantido
    return (
        <div className="card">
            <h2>Adicionar Solicitação</h2>
            <form onSubmit={handleSubmit} className="solicitacao-paste-form">
            <div className="paste-helper">
                <label htmlFor="linhaCopiada">Colar linha completa</label>
                <div className="paste-helper-controls">
                    <textarea
                        id="linhaCopiada"
                        value={linhaCopiada}
                        onChange={(e) => setLinhaCopiada(e.target.value)}
                        placeholder="Cole aqui a linha completa para extrair NPJ, processo, solicitação e valor"
                        rows={2}
                    />
                </div>
                <small className="form-hint">
                    Formato com tabs: NPJ [TAB] Nº Solicitação [TAB] Tribunal [TAB] Especificação [TAB] Status [TAB] Data [TAB] Valor
                </small>
            </div>
            {parsedSolicitacao && (
                <div className="recognized-line">
                    <p className="recognized-line-title">Informacoes reconhecidas para envio</p>
                    <p className="recognized-line-text">
                        <strong>NPJ:</strong> {parsedSolicitacao.npj}
                        {' | '}
                        <strong>Solicitacao:</strong> {parsedSolicitacao.numeroSolicitacao}
                        {parsedSolicitacao.tribunal && (
                            <>
                                {' | '}
                                <strong>Tribunal:</strong> {parsedSolicitacao.tribunal}
                            </>
                        )}
                        {parsedSolicitacao.especificacao && (
                            <>
                                {' | '}
                                <strong>Especificacao:</strong> {parsedSolicitacao.especificacao}
                            </>
                        )}
                        {parsedSolicitacao.statusPortal && (
                            <>
                                {' | '}
                                <strong>Status:</strong> {parsedSolicitacao.statusPortal}
                            </>
                        )}
                        {' | '}
                        <strong>Data:</strong> {formatDataHora(parsedSolicitacao.dataSolicitacao)}
                        {' | '}
                        <strong>Valor:</strong> {formatValorDisplay(parsedSolicitacao.valor)}
                        {' | '}
                        <strong>Status Banco:</strong> {parsedSolicitacao.statusPortal || 'Nao informado'}
                        {' | '}
                        <strong>Status Robo inicial:</strong> Pendente
                        {' | '}
                        <strong>Confirmacao Portal:</strong> Sim
                        {prazoFatal && (
                            <>
                                {' | '}
                                <strong>Prazo Fatal:</strong> {formatDataHora(toFortalezaIsoString(prazoFatal))}
                            </>
                        )}
                    </p>
                </div>
            )}
            <div className="deadline-config-grid">
                <div className="form-group">
                    <label htmlFor="prazoFatal">Prazo fatal para comprovante</label>
                    <input
                        id="prazoFatal"
                        type="datetime-local"
                        value={prazoFatal}
                        onChange={(e) => setPrazoFatal(e.target.value)}
                        className="date-input-style"
                    />
                    <small className="form-hint">Comparacao feita no fuso GMT-3 (America/Fortaleza). Ex.: 01/02 as 15:00.</small>
                </div>
            </div>
            <div className="submit-row">
                <button type="submit" disabled={isLoading || !parsedSolicitacao} className="button primary confirm-submit-button">
                    {isLoading ? 'Enviando...' : 'Confirmar e Enviar Solicitação'}
                </button>
            </div>
            {(error || success) && (
                <div className="form-message-container">
                    {error && <p className="form-message error">{error}</p>}
                    {success && <p className="form-message success">{success}</p>}
                </div>
            )}
            </form>
        </div>
    );
};

// --- COMPONENTES ADMIN ---

// Formulário de Criação de Usuário (UserCreateForm)
// ... (Componente UserCreateForm mantido como no arquivo original)
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
        <form onSubmit={handleSubmit} className="admin-user-create-form"> {/* Classe CSS específica */}
            <div className="form-group">
                <label htmlFor="newUsername">Novo Usuário:</label>
                <input id="newUsername" type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Nome de usuário" required />
            </div>
            <div className="form-group">
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
            <button type="submit" disabled={isLoading} className="button primary small">
                {isLoading ? 'Criando...' : 'Criar Usuário'}
            </button>
            {error && <p className="form-message error">{error}</p>}
            {success && <p className="form-message success">{success}</p>}
        </form>
    );
};

// Tabela de Lista de Usuários (UserListTable)
// ... (Componente UserListTable mantido como no arquivo original, incluindo botão Editar)
const UserListTable = ({ users: initialUsers = [], currentUser, onUserListChanged, onEditUser }) => {
    const [users, setUsers] = useState(initialUsers);
    const [loadingStates, setLoadingStates] = useState({}); // { userId: boolean } - Para ativar/desativar
    const [error, setError] = useState('');

    // Atualiza a lista local se a prop mudar
    useEffect(() => {
        setUsers(initialUsers);
    }, [initialUsers]);

    const handleToggleActive = async (userToUpdate) => {
        // Impede admin de desativar a si mesmo ou o usuário 'admin' principal, mas permite reativar
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
             setTimeout(() => setError(''), 5000); // Limpa erro após 5s
        } finally {
            setLoadingStates(prev => ({ ...prev, [userToUpdate.id]: false }));
        }
    };

    return (
        <div className="admin-user-list-container">
            {error && <p className="form-message error">{error}</p>}
            <div className="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Username</th>
                            <th>Role</th>
                            <th>Status</th>
                            <th style={{ textAlign: 'center' }}>Ações</th> {/* Centraliza cabeçalho Ações */}
                        </tr>
                    </thead>
                    <tbody>
                        {users.length > 0 ? (
                            users.map(user => {
                                const isLoadingToggle = loadingStates[user.id];
                                // Condição para desabilitar o botão de ativar/desativar
                                const isToggleDisabled = isLoadingToggle || ((user.id === currentUser.id || user.username === 'admin') && user.is_active);
                                // Condição para desabilitar botão de editar (não pode editar admin principal)
                                const isEditDisabled = user.username === 'admin';

                                return (
                                    <tr key={user.id}>
                                        <td>{user.id}</td>
                                        <td>{user.username}</td>
                                        <td>{user.role}</td>
                                        <td>{user.is_active ? 'Ativo' : 'Inativo'}</td>
                                        <td style={{ textAlign: 'center' }}> {/* Centraliza botões */}
                                            {/* Botão Editar */}
                                            <button
                                                onClick={() => onEditUser(user)}
                                                disabled={isEditDisabled}
                                                className="button small action-button button-edit" // Usa classe genérica e específica
                                                title={isEditDisabled ? "Não pode editar o usuário 'admin'" : 'Editar usuário'}
                                            >
                                                <EditIcon /> {/* Ícone de Edição */}
                                            </button>
                                            {/* Botão Ativar/Desativar */}
                                            <button
                                                onClick={() => handleToggleActive(user)}
                                                disabled={isToggleDisabled}
                                                className={`button small action-button ${user.is_active ? 'button-deactivate' : 'button-activate'}`}
                                                title={isToggleDisabled ? "Não pode alterar status" : (user.is_active ? 'Desativar usuário' : 'Ativar usuário')}
                                                style={{ marginLeft: '0.5rem' }} // Adiciona espaço entre botões
                                            >
                                                {isLoadingToggle ? '...' : (user.is_active ? 'Desativar' : 'Ativar')}
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })
                        ) : (
                            <tr><td colSpan="5" className="table-empty-message">Nenhum outro usuário encontrado.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

// Componente Modal de Edição de Usuário (UserEditModal)
// ... (Componente UserEditModal mantido exatamente como está)
const UserEditModal = ({ userToEdit, onClose, onUserUpdated }) => {
    const [username, setUsername] = useState(userToEdit.username);
    const [password, setPassword] = useState(''); // Começa vazio
    const [role, setRole] = useState(userToEdit.role);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    // Previne edição do username 'admin'
    const isUsernameAdmin = userToEdit.username === 'admin';

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccess('');

        const updateData = {};
        if (!isUsernameAdmin && username.trim() && username.trim() !== userToEdit.username) {
            updateData.username = username.trim();
        }
        if (password.trim()) { // Só envia senha se algo for digitado
            updateData.password = password;
        }
        if (role !== userToEdit.role) {
            updateData.role = role;
        }

        if (Object.keys(updateData).length === 0) {
            setError('Nenhuma alteração detectada.');
            setIsLoading(false);
            return;
        }

        try {
            await updateUser(userToEdit.id, updateData);
            setSuccess('Usuário atualizado com sucesso!');
            // Limpa senha após sucesso
            setPassword('');
            setTimeout(() => {
                 setSuccess('');
                 if(onUserUpdated) onUserUpdated(); // Chama a função para recarregar a lista no AdminPanel
                 onClose(); // Fecha o modal
            }, 2000);
        } catch (err) {
            const detail = err.response?.data?.detail;
             let message = 'Erro ao atualizar usuário.';
             if (typeof detail === 'string') {
                 message += ` ${detail}`;
             } else if (Array.isArray(detail)) {
                 message += ` ${detail.map(d => `${d.loc?.join('/') || 'campo'}: ${d.msg}`).join('; ')}`;
             } else {
                 message += ` ${err.message || 'Verifique os dados.'}`;
             }
            setError(message);
        } finally {
            setIsLoading(false);
        }
    };

    return createPortal(
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal-content admin-modal-content" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                     <h3>Editar Usuário (ID: {userToEdit.id})</h3>
                     <button onClick={onClose} className="modal-action-button modal-close-icon-button" title="Fechar" disabled={isLoading}><CloseIcon /></button>
                </div>
                <form onSubmit={handleSubmit}>
                    <div className="modal-body">
                        {error && <p className="form-message error modal-error">{error}</p>}
                        {success && <p className="form-message success modal-success">{success}</p>}

                        <div className="form-group">
                            <label htmlFor="editUsername">Username:</label>
                            <input
                                id="editUsername"
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="Nome de usuário"
                                required
                                disabled={isUsernameAdmin} // Desabilita se for 'admin'
                                title={isUsernameAdmin ? "Não é possível alterar o nome do usuário 'admin'" : ""}
                            />
                             {isUsernameAdmin && <small className="form-hint">O nome do usuário 'admin' não pode ser alterado.</small>}
                        </div>
                        <div className="form-group">
                            <label htmlFor="editPassword">Nova Senha:</label>
                            <input
                                id="editPassword"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Deixe em branco para manter a atual"
                            />
                            <small className="form-hint">Mínimo 4 caracteres se for alterar.</small>
                        </div>
                        <div className="form-group">
                            <label htmlFor="editRole">Permissão:</label>
                            <select
                                id="editRole"
                                value={role}
                                onChange={(e) => setRole(e.target.value)}
                                required
                                disabled={isUsernameAdmin} // Não pode mudar a role do 'admin'
                                title={isUsernameAdmin ? "Não é possível alterar a permissão do usuário 'admin'" : ""}
                            >
                                <option value="user">Usuário</option>
                                <option value="admin">Admin</option>
                            </select>
                            {isUsernameAdmin && <small className="form-hint">A permissão do usuário 'admin' não pode ser alterada.</small>}
                        </div>
                    </div>
                    <div className="modal-footer">
                        <button type="button" onClick={onClose} className="button secondary small" disabled={isLoading}>Cancelar</button>
                        <button type="submit" disabled={isLoading} className="button primary small">
                            {isLoading ? 'Salvando...' : 'Salvar Alterações'}
                        </button>
                    </div>
                </form>
            </div>
        </div>,
        document.getElementById('modal-root')
    );
};

// Componente do Painel de Administração (AdminPanelModal)
// <<< AJUSTES: Adiciona handlers para abrir/fechar UserEditModal >>>
const AdminPanelModal = ({ currentUser, onDataRefresh, isOpen, onClose }) => {
    const [users, setUsers] = useState([]);
    const [isLoadingUsers, setIsLoadingUsers] = useState(false);
    const [userListError, setUserListError] = useState('');
    const [showArchived, setShowArchived] = useState(false); // Estado para ver arquivados
    const [isResettingErrors, setIsResettingErrors] = useState(false);
    const [resetError, setResetError] = useState('');
    const [resetSuccess, setResetSuccess] = useState('');

    // <<< NOVO: Estados para controlar o modal de edição >>>
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const [editingUser, setEditingUser] = useState(null); // Guarda o usuário sendo editado

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

    // Carrega usuários ao abrir o modal principal
    useEffect(() => {
        if (isOpen) {
            fetchUsers();
            // Também reseta o estado do checkbox 'showArchived' ao abrir,
            // ou busca o estado inicial dos filtros do App se necessário.
            // Por simplicidade, vamos resetar para false:
            setShowArchived(false);
        }
    }, [isOpen, fetchUsers]);

    // Função para recarregar a lista de usuários (chamada pelo UserCreateForm E UserEditModal)
    const refreshUserList = () => {
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
            if(onDataRefresh) onDataRefresh(showArchived, null); // Atualiza lista de solicitações (sem filtro de user aqui)
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
        if(onDataRefresh) onDataRefresh(checked, null); // Pede para App.js recarregar (sem filtro de user aqui)
    };

    // <<< NOVO: Funções para abrir e fechar o modal de edição >>>
    const openEditModal = (user) => {
        console.log("Abrindo modal de edição para:", user);
        setEditingUser(user);
        setIsEditModalOpen(true);
    };

    const closeEditModal = () => {
        console.log("Fechando modal de edição.");
        setIsEditModalOpen(false);
        setEditingUser(null);
    };

    // <<< NOVO: Função chamada pelo UserEditModal após sucesso >>>
    const handleUserUpdated = () => {
        console.log("Usuário atualizado, recarregando lista...");
        refreshUserList(); // Recarrega a lista de usuários no painel admin
        // O modal de edição se fecha sozinho após o timeout de sucesso
    };


    if (!isOpen) return null; // Não renderiza nada se fechado

    return createPortal(
        <> {/* Usa Fragment para permitir múltiplos modais no portal */}
            <div className="modal-backdrop" onClick={onClose}>
                <div className="modal-content admin-modal-content" onClick={e => e.stopPropagation()}>
                    <div className="modal-header">
                         <h3>Painel Administrativo</h3>
                         <button onClick={onClose} className="modal-action-button modal-close-icon-button" title="Fechar"><CloseIcon /></button>
                    </div>
                    <div className="modal-body">
                        <section className="admin-section">
                            <h4>Gerenciar Usuários</h4>
                            {/* Passa refreshUserList para o formulário de criação */}
                            <UserCreateForm onUserCreated={refreshUserList} />
                            {userListError && <p className="form-message error">{userListError}</p>}
                            {isLoadingUsers ? <p>Carregando...</p> : (
                                // Passa refreshUserList e openEditModal para a tabela
                                <UserListTable
                                    users={users}
                                    currentUser={currentUser}
                                    onUserListChanged={refreshUserList}
                                    onEditUser={openEditModal} // <<< NOVO >>>
                                />
                            )}
                        </section>
                         <hr className="modal-divider"/>
                        <section className="admin-section">
                             <h4>Ações Gerais</h4>
                             <div className="admin-actions-container">
                                 <div className="checkbox-container">
                                    <input
                                        type="checkbox"
                                        id="showArchivedAdmin" // ID único para o checkbox no modal
                                        checked={showArchived}
                                        onChange={handleShowArchivedChange}
                                    />
                                    <label htmlFor="showArchivedAdmin"> Exibir arquivadas na tabela principal</label>
                                </div>
                                <button
                                    onClick={handleResetErrors}
                                    disabled={isResettingErrors}
                                    className="button warning small" // Estilo ajustado
                                 >
                                     {isResettingErrors ? 'Resetando...' : 'Resetar Erros'}
                                </button>
                             </div>
                            {resetError && <p className="form-message error">{resetError}</p>}
                            {resetSuccess && <p className="form-message success">{resetSuccess}</p>}
                        </section>
                    </div>
                </div>
            </div>

            {/* <<< NOVO: Renderiza o Modal de Edição condicionalmente >>> */}
            {isEditModalOpen && editingUser && (
                <UserEditModal
                    userToEdit={editingUser}
                    onClose={closeEditModal}
                    onUserUpdated={handleUserUpdated}
                />
            )}
        </>,
        document.getElementById('modal-root')
    );
};
// --- FIM COMPONENTES ADMIN ---

// --- COMPONENTE DA TABELA DE SOLICITAÇÕES ---
const SolicitacoesTable = ({ solicitacoes: allSolicitacoes, currentUser, onDataRefresh, currentFilters }) => {
    // ... (states, refs, lógicas de filtro e paginação mantidas) ...
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedSolicitacao, setSelectedSolicitacao] = useState(null);
    const [isModalLoading, setIsModalLoading] = useState(false);
    const [modalError, setModalError] = useState('');
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [copyStatus, setCopyStatus] = useState('');
    const isAdmin = currentUser?.role === 'admin';
    const [showRobotInfo, setShowRobotInfo] = useState(false); // Estado do Accordion
    const menuRef = useRef(null); // Ref para fechar dropdown

    // --- Estados para Filtros ---
    const [filterNpj, setFilterNpj] = useState('');
    const [filterProcesso, setFilterProcesso] = useState('');
    const [filterStartDate, setFilterStartDate] = useState('');
    const [filterEndDate, setFilterEndDate] = useState('');

    // --- Estados para Paginação ---
    const [currentPage, setCurrentPage] = useState(1);
    const [itemsPerPage, setItemsPerPage] = useState(10);
    const [pageInput, setPageInput] = useState('1');

    // --- Filtragem ---
    const filteredSolicitacoes = useMemo(() => {
        return allSolicitacoes.filter(item => {
            const npjMatch = filterNpj ? item.npj?.toLowerCase().includes(filterNpj.toLowerCase()) : true;
            const processoMatch = filterProcesso ? item.numero_processo?.toLowerCase().includes(filterProcesso.toLowerCase()) : true;

            let dateMatch = true;
            if (filterStartDate || filterEndDate) {
                try {
                    // Garante que a data seja tratada como UTC
                    const itemDate = item.data_solicitacao ? new Date(item.data_solicitacao + 'T00:00:00Z') : null;

                    // Se a data do item for inválida, considera que não bate se algum filtro de data estiver ativo
                    if (!itemDate || isNaN(itemDate.getTime())) {
                        dateMatch = !(filterStartDate || filterEndDate);
                    } else {
                        if (filterStartDate) {
                            const startDate = new Date(filterStartDate + 'T00:00:00Z');
                            if (itemDate < startDate) dateMatch = false;
                        }
                        if (filterEndDate) {
                            const endDate = new Date(filterEndDate + 'T00:00:00Z');
                            // Ajusta endDate para incluir o dia inteiro
                            endDate.setUTCDate(endDate.getUTCDate() + 1);
                            if (itemDate >= endDate) dateMatch = false;
                        }
                    }
                } catch (e) {
                    console.error("Erro ao comparar datas:", e);
                    dateMatch = true; // Ignora filtro de data se houver erro
                }
            }

            return npjMatch && processoMatch && dateMatch;
        });
    }, [allSolicitacoes, filterNpj, filterProcesso, filterStartDate, filterEndDate]);

     // --- Paginação ---
    const indexOfLastItem = currentPage * itemsPerPage;
    const indexOfFirstItem = indexOfLastItem - itemsPerPage;
    const currentSolicitacoes = filteredSolicitacoes.slice(indexOfFirstItem, indexOfLastItem);
    const totalPages = Math.ceil(filteredSolicitacoes.length / itemsPerPage);

    const paginate = (pageNumber) => {
        if (pageNumber >= 1 && pageNumber <= totalPages) {
            setCurrentPage(pageNumber);
            setPageInput(String(pageNumber));
        }
    };

    const handleNextPage = () => paginate(currentPage + 1);
    const handlePrevPage = () => paginate(currentPage - 1);
    const handleItemsPerPageChange = (event) => {
        const nextItemsPerPage = parseInt(event.target.value, 10);
        setItemsPerPage(nextItemsPerPage);
        setCurrentPage(1);
        setPageInput('1');
    };
    const handlePageInputSubmit = (event) => {
        event.preventDefault();
        const requestedPage = parseInt(pageInput, 10);
        if (Number.isNaN(requestedPage)) {
            setPageInput(String(currentPage));
            return;
        }
        paginate(requestedPage);
    };

    // Reset page number when filters change externally (via props) or internally
    useEffect(() => {
        setCurrentPage(1);
        setPageInput('1');
    }, [filterNpj, filterProcesso, filterStartDate, filterEndDate, currentFilters, itemsPerPage]);

    useEffect(() => {
        setPageInput(String(currentPage));
    }, [currentPage]);


    // Fechar Menu Dropdown ao clicar fora
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (menuRef.current && !menuRef.current.contains(event.target)) {
                setIsMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Função interna para chamar onDataRefresh com os filtros atuais
    const triggerRefresh = () => {
         if (onDataRefresh) {
             onDataRefresh(currentFilters.includeArchived, currentFilters.userFilter);
         }
    };

    // Funções do Modal
    const openModal = (solicitacao) => {
        setSelectedSolicitacao(solicitacao);
        setIsModalOpen(true);
        setModalError('');
        setIsMenuOpen(false); // Fecha menu ao abrir modal
        setCopyStatus(''); // Limpa status de cópia
        setShowRobotInfo(false); // Fecha accordion
    };

    const closeModal = () => {
        if (isModalLoading) return; // Não fecha se estiver carregando
        setIsModalOpen(false);
        setSelectedSolicitacao(null);
    };

    const toggleMenu = (e) => {
        e.stopPropagation(); // Impede que o clique feche o modal
        setIsMenuOpen(!isMenuOpen);
    };

    // Função Copiar
    const handleCopyToClipboard = (text) => {
        if (!text) {
             setCopyStatus('Nada copiado');
             setTimeout(() => setCopyStatus(''), 2000);
             return;
        }
        try {
            // Cria um elemento temporário para copiar
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.style.position = 'fixed'; // Impede de piscar
            ta.style.left = '-9999px'; // Fora da tela
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy'); // Usa execCommand por compatibilidade com iframe
            document.body.removeChild(ta);
            setCopyStatus('Copiado!');
            setTimeout(() => setCopyStatus(''), 1500); // Mensagem mais rápida
        } catch (err) {
            console.error('Falha ao copiar:', err);
            setCopyStatus('Falhou!');
            setTimeout(() => setCopyStatus(''), 1500);
        }
    };

    // Função para formatar lista de comprovantes/documentos
    const formatComprovantes = (paths) => {
        if (!paths || paths.length === 0) return <li className="modal-no-files">Nenhum</li>;
        let links = [];
        try {
            if (Array.isArray(paths)) { links = paths.map(String).filter(p => p); } // Garante array de strings e remove vazios/null
            else if (typeof paths === 'string' && paths.startsWith('[')) { links = JSON.parse(paths).map(String).filter(p => p); }
            else if (typeof paths === 'string' && paths.trim() !== '') { links = [paths]; }
        } catch (e) { console.error("Erro ao parsear comprovantes_path:", paths, e); return <li>Erro ao ler caminhos</li>; }

        if (!Array.isArray(links) || links.length === 0) return <li className="modal-no-files">Nenhum</li>;

        return links.map((link, index) => {
            const nomeArquivo = link.split(/[\\/]/).pop() || `Arquivo ${index + 1}`;
            const downloadUrl = buildStaticDownloadUrl(link);


            // Determina o tipo pelo nome (heurística)
            let tipo = 'Documento';
            if (nomeArquivo.toLowerCase().includes('comprovante') || nomeArquivo.toLowerCase().includes('boleto')) {
                tipo = 'Comprovante';
            } else if (nomeArquivo.toLowerCase().endsWith('.png') || nomeArquivo.toLowerCase().endsWith('.jpg')) {
                tipo = 'Screenshot'; // Identifica screenshots
            }
            // Adicione outras heurísticas se necessário (ex: 'guia', 'custas')

            return (
                <li key={index}>
                    <a href={downloadUrl} target="_blank" rel="noopener noreferrer" download={nomeArquivo}
                       className="modal-file-link group" title={`Baixar: ${nomeArquivo}`}>
                        {tipo}
                        <DownloadIcon />
                    </a>
                </li>
            );
        });
    };

    // --- Ações do Modal ---
    const handleResetPendente = async () => {
        if (!selectedSolicitacao || isModalLoading) return;
        setIsModalLoading(true);
        setModalError('');
        setIsMenuOpen(false); // Fecha menu
        console.log(`[SolicitacoesTable] Resetando solicitação ID ${selectedSolicitacao.id} para Pendente...`);
        try {
            // Limpa especificacao também ao resetar
            await updateSolicitacao(selectedSolicitacao.id, {
                status_robo: "Pendente",
                status_portal: null, // Limpa status do portal
                ultima_verificacao_robo: null, // Limpa última verificação
                usuario_confirmacao_id: null, // Limpa confirmação se houve
                especificacao: null, // Limpa especificacao
                proxima_verificacao_em: null,
                alerta_enviado_em: null,
                motivo_encerramento: null,
                monitoramento_ativo: true
            });
            triggerRefresh(); // Atualiza a lista com filtros atuais
            closeModal();
        } catch (err) {
            console.error("Erro ao resetar solicitação:", err);
            setModalError('Falha ao resetar: ' + (err.response?.data?.detail || err.message));
        } finally {
            setIsModalLoading(false);
        }
    };

    const handleFinalizarTratamento = async () => {
        if (!selectedSolicitacao || isModalLoading || selectedSolicitacao.usuario_finalizacao_id) return;
        setIsModalLoading(true);
        setModalError('');
        console.log(`[SolicitacoesTable] Marcando solicitação ID ${selectedSolicitacao.id} como finalizada (tratada)...`);
        try {
            await updateSolicitacao(selectedSolicitacao.id, { finalizar: true });
            triggerRefresh(); // Atualiza a lista com filtros atuais
            closeModal(); // Fecha o modal após sucesso
        } catch (err) {
             console.error("Erro ao marcar como finalizado:", err);
            setModalError('Falha ao finalizar: ' + (err.response?.data?.detail || err.message));
        } finally {
             setIsModalLoading(false);
        }
    };

    const handleToggleArchive = async () => {
        if (!selectedSolicitacao || isModalLoading || !isAdmin) return;
        const newArchiveStatus = !selectedSolicitacao.is_archived;
        setIsModalLoading(true);
        setModalError('');
        setIsMenuOpen(false); // Fecha menu
        console.log(`[SolicitacoesTable] Admin ${currentUser.username} ${newArchiveStatus ? 'arquivando' : 'desarquivando'} solicitação ID ${selectedSolicitacao.id}...`);
        try {
            await archiveSolicitation(selectedSolicitacao.id, newArchiveStatus);
            triggerRefresh(); // Atualiza a lista com filtros atuais
            closeModal(); // Fecha o modal
        } catch (err) {
            console.error("Erro ao arquivar/desarquivar:", err);
            setModalError('Falha ao arquivar/desarquivar: ' + (err.response?.data?.detail || err.message));
        } finally {
            setIsModalLoading(false);
        }
    };


    return (
        <div className="card process-table-container">
            <h2>Solicitações</h2>
            {/* Filtros */}
            <div className="filters-container">
                <div className="form-group">
                    <label htmlFor="filterNpj">Filtrar NPJ</label>
                    <input id="filterNpj" type="text" value={filterNpj} onChange={(e) => setFilterNpj(e.target.value)} placeholder="NPJ..." />
                </div>
                <div className="form-group">
                    <label htmlFor="filterProcesso">Filtrar Nº Processo</label>
                    <input id="filterProcesso" type="text" value={filterProcesso} onChange={(e) => setFilterProcesso(e.target.value)} placeholder="Nº Processo..." />
                </div>
                <div className="form-group">
                    <label htmlFor="filterStartDate">Data Início</label>
                    <input id="filterStartDate" type="date" value={filterStartDate} onChange={(e) => setFilterStartDate(e.target.value)} className="date-input-style"/>
                </div>
                <div className="form-group">
                    <label htmlFor="filterEndDate">Data Fim</label>
                    <input id="filterEndDate" type="date" value={filterEndDate} onChange={(e) => setFilterEndDate(e.target.value)} className="date-input-style"/>
                </div>
            </div>

             <div className="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>NPJ</th>
                            <th className="th-narrow">Nº</th> {/* Cabeçalho ajustado */}
                            <th className="th-valor">Valor</th> {/* Classe para alinhamento */}
                            <th>Data Solicitação</th>
                            <th>Prazo Fatal</th>
                            <th>Criado Por</th>
                            <th style={{minWidth: '220px'}}>Status Banco</th>
                            <th style={{minWidth: '220px'}}>Status Robô</th>
                            <th style={{textAlign: 'center'}}>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {currentSolicitacoes.length > 0 ? (
                            currentSolicitacoes.map(item => {
                                const statusRoboClasse = getRobotStatusClass(item.status_robo, item.is_archived, Boolean(item.usuario_finalizacao_id));
                                const statusPortalClasse = getPortalStatusClass(item.status_portal);
                                const prazoFatalState = getPrazoFatalState(item.prazo_fatal_em, item.status_robo);

                                let statusRoboText = item.status_robo || 'Pendente';
                                if (item.usuario_finalizacao) {
                                    statusRoboText = `Tratado por ${item.usuario_finalizacao.username}`;
                                } else if (item.is_archived) {
                                    statusRoboText = 'Arquivado';
                                }

                                const statusRoboTitle = item.usuario_finalizacao
                                    ? `Tratado por ${item.usuario_finalizacao.username} em ${formatDataHora(item.data_finalizacao)}`
                                    : item.is_archived
                                        ? `Arquivado por ${item.usuario_arquivamento?.username || 'Admin'} em ${formatDataHora(item.data_arquivamento)}`
                                        : item.status_robo || 'Pendente';

                                const statusPortalTitle = item.status_portal || 'Nenhum retorno do banco até o momento';
                                const prazoFatalLabel = item.prazo_fatal_em ? formatDataHora(item.prazo_fatal_em) : 'Nao definido';


                                return (
                                    <tr key={item.id} className={item.is_archived ? 'archived-row' : ''}>
                                        <td>{item.npj}</td>
                                        <td className="td-narrow">{item.numero_solicitacao}</td> {/* Estilo aplicado */}
                                        <td className="td-valor">{formatValorDisplay(item.valor)}</td> {/* Estilo aplicado */}
                                        <td>{formatDataHora(item.data_solicitacao)}</td>
                                        <td>
                                            <span className={`deadline-chip deadline-${prazoFatalState}`} title={prazoFatalLabel}>
                                                {prazoFatalLabel}
                                            </span>
                                        </td>
                                        <td>{item.usuario_criacao?.username || 'N/A'}</td>
                                        <td>
                                          <div className="status-cell status-cell-stacked">
                                            <span
                                              className={`status-indicator status-${statusPortalClasse}`}
                                              title={statusPortalTitle}
                                            ></span>
                                            <span className="status-text" title={statusPortalTitle}>
                                              {item.status_portal || 'Sem retorno do banco'}
                                            </span>
                                          </div>
                                        </td>
                                        <td>
                                          <div className="status-cell status-cell-stacked">
                                            {!item.is_archived && !item.usuario_finalizacao_id && (
                                                <span
                                                  className={`status-indicator status-${statusRoboClasse}`}
                                                  title={statusRoboTitle}
                                                ></span>
                                             )}
                                            <span className="status-text" title={statusRoboTitle}>
                                              {statusRoboText}
                                            </span>
                                          </div>
                                        </td>
                                        <td style={{textAlign: 'center'}}>
                                            <button onClick={() => openModal(item)} className="action-button details-button" title="Ver Detalhes">
                                                <DetailsIcon /> {/* Ícone SVG */}
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })
                        ) : ( <tr><td colSpan="9" className="table-empty-message">Nenhuma solicitação encontrada com os filtros aplicados.</td></tr> )}
                    </tbody>
                </table>
             </div>
             <p className="table-status-legend">
                <strong>Status Banco</strong>: ultimo retorno lido no portal do banco.{' '}
                <strong>Status Robô</strong>: etapa interna controlada pelo OneCost para monitoramento, alertas e tratamento.
             </p>

             {/* Paginação */}
             {totalPages > 1 && (
                <div className="pagination-controls">
                    <div className="pagination-config">
                        <label htmlFor="itemsPerPage" className="pagination-label">Itens por página</label>
                        <select
                            id="itemsPerPage"
                            value={itemsPerPage}
                            onChange={handleItemsPerPageChange}
                            className="pagination-select"
                        >
                            <option value={10}>10</option>
                            <option value={25}>25</option>
                            <option value={50}>50</option>
                            <option value={100}>100</option>
                        </select>
                    </div>
                    <button onClick={handlePrevPage} disabled={currentPage === 1} className="pagination-button">Anterior</button>
                    <span className="pagination-info">Página {currentPage} de {totalPages} ({filteredSolicitacoes.length} itens)</span>
                    <form onSubmit={handlePageInputSubmit} className="pagination-jump-form">
                        <label htmlFor="pageInput" className="pagination-label">Ir para</label>
                        <input
                            id="pageInput"
                            type="number"
                            min={1}
                            max={totalPages}
                            value={pageInput}
                            onChange={(event) => setPageInput(event.target.value)}
                            className="pagination-input"
                        />
                        <button type="submit" className="pagination-button">Ir</button>
                    </form>
                    <button onClick={handleNextPage} disabled={currentPage === totalPages} className="pagination-button">Próxima</button>
                </div>
             )}

            {/* Modal Detalhes com Layout Ajustado e Botão Concluído */}
             {isModalOpen && selectedSolicitacao && createPortal(
                <div className="modal-backdrop" onClick={closeModal}>
                    <div className="modal-content modal-content-wide" onClick={e => e.stopPropagation()}>
                        <div className="modal-header">
                             <h3>Detalhes da Solicitação (ID: {selectedSolicitacao.id})</h3>
                             <div className="modal-header-actions">
                                {/* Menu Dropdown */}
                                <div className="modal-menu-container" ref={menuRef}>
                                    <button onClick={toggleMenu} className="modal-action-button modal-menu-button" title="Mais Ações" disabled={isModalLoading}>
                                        <EllipsisVerticalIcon />
                                    </button>
                                    {isMenuOpen && (
                                        <div className="modal-dropdown-menu">
                                            {/* Opção Resetar Pendente (se não arquivado) */}
                                            {!selectedSolicitacao.is_archived && (
                                                <button onClick={handleResetPendente} disabled={isModalLoading} className="dropdown-item">
                                                    Resetar Pendente
                                                </button>
                                            )}
                                            {/* Opção Arquivar/Desarquivar (somente admin) */}
                                            {isAdmin && (
                                                <button onClick={handleToggleArchive} disabled={isModalLoading} className={`dropdown-item ${selectedSolicitacao.is_archived ? 'action-unarchive' : 'action-archive'}`}>
                                                    {selectedSolicitacao.is_archived ? 'Desarquivar' : 'Arquivar'}
                                                </button>
                                            )}
                                             {/* Mensagem se não houver ações */}
                                             {!isAdmin && selectedSolicitacao.is_archived && (
                                                 <span className="dropdown-item-disabled">Nenhuma ação disponível</span>
                                             )}
                                        </div>
                                    )}
                                </div>
                                {/* Botão Fechar X */}
                                <button onClick={closeModal} className="modal-action-button modal-close-icon-button" title="Fechar" disabled={isModalLoading}>
                                    <CloseIcon />
                                </button>
                            </div>
                        </div>
                        <div className="modal-body">
                             {modalError && <p className="form-message error modal-error">{modalError}</p>}

                             {/* Layout do Modal Atualizado */}
                             <div className="modal-detail-line">
                                <p><strong className="modal-label">NPJ:</strong> {selectedSolicitacao.npj}</p>
                                <div className="modal-field-with-action">
                                     <p><strong className="modal-label">Número CNJ:</strong> {selectedSolicitacao.numero_processo || 'N/A'}</p>
                                     {selectedSolicitacao.numero_processo && (
                                        <button onClick={() => handleCopyToClipboard(selectedSolicitacao.numero_processo)} className="modal-copy-button" title="Copiar Nº Processo">
                                            <CopyIcon />
                                            {copyStatus && <span className="copy-feedback">{copyStatus}</span>}
                                        </button>
                                     )}
                                 </div>
                             </div>

                             <div className="modal-detail-line">
                                <p><strong className="modal-label">Tipo Custa:</strong> {selectedSolicitacao.especificacao || 'N/A'}</p> {/* Exibindo especificacao */}
                                <p><strong className="modal-label">Número:</strong> {selectedSolicitacao.numero_solicitacao}</p>
                                <p><strong className="modal-label">Valor:</strong> {formatValorDisplay(selectedSolicitacao.valor)}</p>
                                <p><strong className="modal-label">Data:</strong> {formatDataHora(selectedSolicitacao.data_solicitacao)}</p>
                             </div>

                             <div className="modal-detail-line">
                                <p><strong className="modal-label">Status do Banco:</strong> <span className={`modal-status-text status-${getPortalStatusClass(selectedSolicitacao.status_portal)}`}>{selectedSolicitacao.status_portal || 'Sem retorno do banco'}</span></p>
                                <p><strong className="modal-label">Status do Robô:</strong> <span className={`modal-status-text status-${getRobotStatusClass(selectedSolicitacao.status_robo, selectedSolicitacao.is_archived, Boolean(selectedSolicitacao.usuario_finalizacao_id))}`}>{selectedSolicitacao.status_robo || 'Pendente'}</span></p>
                             </div>

                             <div className="modal-detail-line">
                                <p><strong className="modal-label">Prazo Fatal:</strong> {formatDataHora(selectedSolicitacao.prazo_fatal_em)}</p>
                                <p><strong className="modal-label">Próxima Verificação:</strong> {formatDataHora(selectedSolicitacao.proxima_verificacao_em)}</p>
                                <p><strong className="modal-label">Alerta Enviado:</strong> {formatDataHora(selectedSolicitacao.alerta_enviado_em)}</p>
                             </div>

                             <div className="modal-detail-line">
                                <p><strong className="modal-label">Monitoramento:</strong> {selectedSolicitacao.monitoramento_ativo ? 'Ativo' : 'Suspenso'}</p>
                                <p><strong className="modal-label">Motivo Encerramento:</strong> {selectedSolicitacao.motivo_encerramento || 'N/A'}</p>
                             </div>

                             <div className="modal-detail-line user-info-line">
                                <p><strong className="modal-label-sm">Criado por:</strong> {selectedSolicitacao.usuario_criacao?.username || 'N/A'}</p>
                                <p><strong className="modal-label-sm">Tratado por:</strong> {selectedSolicitacao.usuario_finalizacao?.username || 'Não'} {selectedSolicitacao.data_finalizacao ? `em ${formatDataHora(selectedSolicitacao.data_finalizacao)}` : ''}</p>
                                <p><strong className="modal-label-sm">Arquivado por:</strong> {selectedSolicitacao.usuario_arquivamento?.username || 'Não'} {selectedSolicitacao.data_arquivamento ? `em ${formatDataHora(selectedSolicitacao.data_arquivamento)}` : ''}</p>
                             </div>

                             <div className="modal-documents-section">
                                <div className="modal-divider-header"><hr/><span className="divider-text">DOCUMENTOS</span><hr/></div>
                                <ul className="modal-files-list">{formatComprovantes(selectedSolicitacao.comprovantes_path)}</ul>
                             </div>

                             {/* Accordion Robô */}
                             <div className="accordion-container">
                                <button onClick={() => setShowRobotInfo(!showRobotInfo)} className="accordion-button" aria-expanded={showRobotInfo}>
                                    <span>Detalhes do Robô</span>
                                    <ChevronDownIcon isOpen={showRobotInfo} />
                                </button>
                                {showRobotInfo && (
                                    <div className="accordion-content">
                                        <p><strong className="modal-label-alt">Confirmação Solicitada:</strong> {selectedSolicitacao.aguardando_confirmacao ? 'Sim' : 'Não'}</p>
                                        <p><strong className="modal-label-alt">Status Robô (nosso sistema):</strong> {selectedSolicitacao.status_robo || 'Pendente'}</p>
                                        <p><strong className="modal-label-alt">Status Portal (banco):</strong> {selectedSolicitacao.status_portal || 'N/A'}</p>
                                        <p><strong className="modal-label-alt">Última Verificação:</strong> {formatDataHora(selectedSolicitacao.ultima_verificacao_robo)}</p>
                                        <p><strong className="modal-label-alt">Próxima Verificação:</strong> {formatDataHora(selectedSolicitacao.proxima_verificacao_em)}</p>
                                        <p><strong className="modal-label-alt">Confirmado (Robô) por:</strong> {selectedSolicitacao.usuario_confirmacao?.username || 'N/A'}</p>
                                    </div>
                                )}
                            </div>
                        </div>
                         <div className="modal-footer">
                            {/* Botão Concluído (Marcar como Tratado) */}
                            {/* Condição: Não arquivado E status robô inclui 'finalizado' E ainda não foi finalizado pelo usuário */}
                            {!selectedSolicitacao.is_archived && selectedSolicitacao.status_robo?.toLowerCase().includes('finalizado') && !selectedSolicitacao.usuario_finalizacao_id && (
                                <button
                                    onClick={handleFinalizarTratamento}
                                    className="button small success" // Estilo verde
                                    disabled={isModalLoading}
                                    title="Marcar que os documentos foram tratados/inseridos no sistema externo"
                                >
                                    {isModalLoading ? '...' : 'Concluído'}
                                </button>
                            )}
                             {/* Botão Fechar (agora sem texto, só o ícone no header) */}
                             {/* <button onClick={closeModal} className="button secondary small" disabled={isModalLoading}>Fechar</button> */}
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
    const [isLoading, setIsLoading] = useState(true); // Controla o carregamento inicial
    const [currentUser, setCurrentUser] = useState(null); // Armazena dados do usuário logado
    const [solicitacoes, setSolicitacoes] = useState([]);
    const [error, setError] = useState(''); // Erro global da aplicação
    const [isAdminModalOpen, setIsAdminModalOpen] = useState(false); // Estado do modal admin

    // <<< NOVO: Estado para os filtros >>>
    const [filters, setFilters] = useState({
        includeArchived: false,
        userFilter: 'me' // 'me', 'sector' ou 'all'
    });

    // Função de Logout - precisa ser definida antes de ser usada no useCallback
     const handleLogout = useCallback(() => {
        console.log("[App] Executando logout...");
        localStorage.removeItem('token');
        setIsLoggedIn(false);
        setCurrentUser(null);
        setSolicitacoes([]);
        setError('');
        setFilters({ includeArchived: false, userFilter: 'me' }); // Reseta filtros no logout
        setIsLoading(false); // Garante que não fique carregando
        setIsAdminModalOpen(false); // Fecha modal admin ao deslogar
    }, []); // useCallback sem dependências


    // Função para buscar dados do usuário e solicitações
    // useCallback para evitar recriações desnecessárias, aceita filtros
    const fetchData = useCallback(async (currentFilters) => {
        console.log(`[App] Chamando fetchData... Filtros:`, currentFilters);
        setError(''); // Limpa erros antigos
        setIsLoading(true); // Inicia loading para busca
        let userToUse = currentUser; // Usa o estado atual como base

        try {
            // Se não temos usuário no estado, busca
            if (!userToUse) {
                console.log("[App] Buscando dados do usuário...");
                userToUse = await getCurrentUser();
                setCurrentUser(userToUse); // Atualiza o estado
                 if (!userToUse) { // Se ainda assim não encontrar usuário, força logout
                     console.error("[App] Não foi possível obter dados do usuário atual após tentativa.");
                     handleLogout();
                     return;
                 }
            } else {
                 console.log("[App] Usando dados do usuário do estado:", userToUse);
            }

            console.log("[App] Buscando solicitações com filtros:", currentFilters);
            const normalizedScope = userToUse.role === 'admin'
                ? (currentFilters.userFilter || 'all')
                : (currentFilters.userFilter === 'sector' ? 'sector' : 'me');
            const userIdParam = normalizedScope === 'me' ? userToUse.id : null;
            const solicitacoesResponse = await getSolicitacoes(currentFilters.includeArchived, userIdParam, normalizedScope);
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
                 if (err.response.status !== 401) { // Só mostra erro se não for 401 (já tratado)
                     setError('Erro ao buscar dados: ' + detailedError);
                 }
             } else if (err.request) {
                 detailedError = "Sem resposta do servidor.";
                 setError('Erro ao buscar dados: ' + detailedError);
             } else {
                  setError('Erro ao buscar dados: ' + detailedError);
             }
             // Se o erro não for 401, mas não temos token, desloga preventivamente
             if (!localStorage.getItem('token') && err.response?.status !== 401) {
                 handleLogout();
             }
        } finally {
             // Garante que o estado de carregamento seja desativado
             setIsLoading(false);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentUser, handleLogout]); // Recria fetchData se currentUser ou handleLogout mudar


    // Efeito para verificar o token e buscar dados iniciais
    useEffect(() => {
        console.log("[App useEffect] Verificando token...");
        const token = localStorage.getItem('token');
        if (token) {
            console.log("[App useEffect] Token encontrado. Buscando dados iniciais...");
            setIsLoading(true);
            getCurrentUser().then(user => {
                setCurrentUser(user);
                const initialFilters = {
                    includeArchived: false,
                    userFilter: user.role === 'admin' ? 'all' : 'me'
                };
                setFilters(initialFilters);
                return fetchData(initialFilters);
            }).catch(err => {
                console.error("[App useEffect] Falha ao recuperar usuário inicial:", err);
                handleLogout();
            });
        } else {
            console.log("[App useEffect] Nenhum token. Indo para login.");
            setIsLoading(false); // Não está carregando se não tem token
            setIsLoggedIn(false);
            setCurrentUser(null);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Executa apenas uma vez ao montar


    // Callback para quando o login for bem-sucedido
    const handleLoginSuccess = useCallback((loginData) => {
        console.log("[App] Login OK. Iniciando busca de dados pós-login...");
        setIsLoading(true); // Mostra carregando enquanto busca dados
        // Primeiro busca o usuário, depois busca os dados com base nele e nos filtros
        getCurrentUser().then(user => {
            const initialFilters = {
                includeArchived: false,
                userFilter: user.role === 'admin' ? 'all' : 'me'
            };
            setCurrentUser(user); // Define o usuário atual
            setFilters(initialFilters); // Reseta filtros no login
            return fetchData(initialFilters); // Busca as solicitações com filtros iniciais
        }).catch(err => {
            console.error("Erro pós-login ao buscar usuário:", err);
            setError("Erro ao carregar dados do usuário.");
            setIsLoading(false);
            handleLogout(); // Desloga se não conseguir buscar o usuário
        });
    }, [fetchData, handleLogout]); // Depende de fetchData e handleLogout


    // Callback para componentes filhos solicitarem atualização de dados ou mudarem filtros
    // <<< AJUSTE: Renomeado para handleFiltersChange >>>
    const handleFiltersChange = useCallback((includeArchived, userFilterValue) => {
        const newFilters = {
            // Se includeArchived não for undefined, usa ele, senão mantém o atual
            includeArchived: includeArchived !== undefined ? includeArchived : filters.includeArchived,
            // Se userFilterValue não for undefined, usa ele, senão mantém o atual
            userFilter: userFilterValue !== undefined ? userFilterValue : filters.userFilter
        };
        console.log(`[App] Solicitação de mudança de filtros/refresh recebida:`, newFilters);
        setFilters(newFilters); // Atualiza o estado dos filtros
        fetchData(newFilters); // Busca dados com os novos filtros
    }, [fetchData, filters]); // Depende de fetchData e do estado atual dos filtros


    // NOVO: Handler para o filtro de usuário (radio buttons)
    const handleUserFilterChange = (event) => {
        const newUserFilter = event.target.value;
        // Chama handleFiltersChange passando undefined para includeArchived para manter o valor atual
        handleFiltersChange(undefined, newUserFilter);
    };


    // Tela de Carregamento Inicial
    // Mostra se isLoading é true E (não está logado OU ainda não tem dados do currentUser)
    if (isLoading && (!isLoggedIn || !currentUser) && localStorage.getItem('token')) {
        return <div className="loading-screen">Carregando...</div>;
    }

    // Tela de Login
    if (!isLoggedIn || !currentUser) { // Verifica currentUser também
        return <LoginPage onLoginSuccess={handleLoginSuccess} />;
    }

    // Tela Principal (Dashboard)
    return (
        <div className="App main-app">
            <header className="app-header">
                <img src={logo} alt="OneSid Logo" className="logo" />
                <div className="user-info">
                    {/* Botão para abrir o modal de Admin */}
                    {currentUser?.role === 'admin' && (
                        <button onClick={() => setIsAdminModalOpen(true)} className="button admin-button" title="Painel Administrativo">
                            <AdminIcon /> Admin
                        </button>
                    )}
                    <span>Olá, {currentUser?.username} ({currentUser?.role}{currentUser?.setor ? ` - ${currentUser.setor}` : ''})</span>
                    <button onClick={handleLogout} className="button logout-button">Sair</button>
                </div>
            </header>
            <main>
                {/* Mensagem de Erro Global */}
                {error && <p className="global-error-message">{error}</p>}

                {/* Formulário de Criação de Solicitação */}
                {/* Passa a função para recarregar usando os filtros atuais */}
                <SolicitacaoForm onSolicitacaoCriada={() => handleFiltersChange(filters.includeArchived, filters.userFilter)} />

                 {/* <<< NOVO: Filtro de Usuário >>> */}
                 <div className="card filter-container">
                     <h4>Exibir:</h4>
                     <div className="filter-options">
                         <label>
                             <input
                                 type="radio"
                                 name="userFilter"
                                 value="me"
                                 checked={filters.userFilter === 'me'}
                                 onChange={handleUserFilterChange}
                                 disabled={isLoading} // Desabilita durante carregamento
                             />
                             Minhas Solicitações
                         </label>
                         {currentUser?.role === 'admin' ? (
                             <label>
                                 <input
                                     type="radio"
                                     name="userFilter"
                                     value="all"
                                     checked={filters.userFilter === 'all'}
                                     onChange={handleUserFilterChange}
                                     disabled={isLoading}
                                 />
                                 Todas
                             </label>
                         ) : (
                             <label>
                                 <input
                                     type="radio"
                                     name="userFilter"
                                     value="sector"
                                     checked={filters.userFilter === 'sector'}
                                     onChange={handleUserFilterChange}
                                     disabled={isLoading}
                                 />
                                 Meu Setor
                             </label>
                         )}
                     </div>
                     {/* Botão de Refresh Manual 
                     <button
                        onClick={() => handleFiltersChange(filters.includeArchived, filters.userFilter)} // Recarrega com os filtros atuais
                        disabled={isLoading}
                        className="button refresh-button"
                        title="Recarregar lista"
                     >
                        {isLoading ? '...' : '🔄'}
                     </button>*/}
                </div>

                {/* Tabela de Solicitações */}
                <SolicitacoesTable
                    solicitacoes={solicitacoes}
                    currentUser={currentUser} // Passa o usuário atual para a tabela
                    onDataRefresh={handleFiltersChange} // Passa a função de refresh/mudança de filtro
                    currentFilters={filters} // Passa os filtros atuais para a tabela usar no refresh
                />
            </main>

            {/* Renderiza o Modal Admin (ele controla a própria visibilidade) */}
            <AdminPanelModal
                currentUser={currentUser}
                // Passa a função que aceita includeArchived e userFilter
                onDataRefresh={handleFiltersChange}
                isOpen={isAdminModalOpen}
                onClose={() => setIsAdminModalOpen(false)}
            />

            <footer className="app-footer">
                OneCost v1.0 - MDR Advocacia
            </footer>
        </div>
    );
}

export default App;
