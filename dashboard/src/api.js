import axios from 'axios';

const currentHostname = window.location.hostname;
const isLocalLikeHost =
  currentHostname === 'localhost' ||
  currentHostname === '127.0.0.1' ||
  currentHostname.endsWith('.local') ||
  currentHostname.startsWith('192.168.') ||
  currentHostname.startsWith('10.');

const inferredApiUrl = isLocalLikeHost
  ? `${window.location.protocol}//${currentHostname}:8001`
  : '/api';

export const API_URL = process.env.REACT_APP_API_URL || inferredApiUrl;
console.log(`[api.js] Usando API_URL: ${API_URL}`); // Log para confirmar

const api = axios.create({
  baseURL: API_URL,
});

// Interceptor para adicionar o token de autenticação
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Adiciona Content-Type se não for login
    if (!config.url.endsWith('/login')) {
        if (!config.headers['Content-Type']) {
            config.headers['Content-Type'] = 'application/json';
        }
    }
    return config;
  },
  (error) => {
    console.error("[api.js] Erro no interceptor de requisição:", error);
    return Promise.reject(error);
  }
);

// Interceptor de Resposta: Trata erros 401
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error("[api.js] Erro na resposta da API:", error.response?.status, error.response?.data || error.message);
    const isLoginRequest = String(error.config?.url || '').endsWith('/login');
    if (error.response && error.response.status === 401 && !isLoginRequest) {
      console.warn("[api.js] Recebido erro 401. Removendo token e recarregando.");
      localStorage.removeItem('token');
      // Tenta redirecionar para a raiz (que deve ser o login)
      window.location.href = '/?sessionExpired=true';

    }
    // Adiciona um tratamento mais genérico para Network Error
    if (error.message === 'Network Error' && !error.response) {
        console.error("[api.js] Network Error: Não foi possível conectar à API em", API_URL);
        // Pode retornar um erro mais amigável aqui se desejar
        // return Promise.reject(new Error(`Não foi possível conectar ao servidor em ${API_URL}. Verifique a rede e se o backend está rodando.`));
    }
    return Promise.reject(error);
  }
);


// --- FUNÇÕES DE AUTENTICAÇÃO ---

export const login = async (username, password) => {
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);
  console.log(`[api.js] Enviando para /login com: {username: '${username}'}`); // Log mais detalhado
  const response = await api.post('/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  if (response.data.access_token) {
    localStorage.setItem('token', response.data.access_token);
    console.log("[api.js] Login OK. Token salvo.");
  }
  return response.data;
};

export const getCurrentUser = async () => {
    console.log("[api.js] Buscando /users/me...");
    const response = await api.get('/users/me');
    console.log("[api.js] Dados do usuário:", response.data);
    return response.data;
};

export const getAdSectors = async () => {
    console.log("[api.js] Buscando /sectors/...");
    const response = await api.get('/sectors/');
    console.log("[api.js] Setores do AD:", response.data);
    return response.data?.setores || [];
};


// --- FUNÇÕES DE SOLICITAÇÕES DE CUSTAS ---

// MODIFICADO: Aceita userId opcional
export const getSolicitacoes = async (includeArchived = false, userId = null, scope = null) => {
    console.log(`[api.js] Buscando /solicitacoes... includeArchived=${includeArchived}, userId=${userId}, scope=${scope}`);
    const params = {
        include_archived: includeArchived
    };
    // Adiciona o filtro de usuário se fornecido
    if (userId !== null && userId !== undefined) {
        params.usuario_id = userId; // Nome do parâmetro no backend
    }
    if (scope) {
        params.scope = scope;
    }
    const response = await api.get('/solicitacoes/', { params });
    console.log(`[api.js] Recebidas ${response.data.length} solicitações.`);
    return response.data;
};

export const createSolicitacao = async (solicitacaoData) => {
    console.log("[api.js] Enviando POST /solicitacoes:", solicitacaoData);
    const response = await api.post('/solicitacoes/', solicitacaoData);
    console.log("[api.js] Solicitação criada:", response.data);
    return response.data;
};

export const updateSolicitacao = async (id, solicitacaoData) => {
    console.log(`[api.js] Enviando PUT /solicitacoes/${id}:`, solicitacaoData);
    const response = await api.put(`/solicitacoes/${id}`, solicitacaoData);
    console.log("[api.js] Solicitação atualizada:", response.data);
    return response.data;
};

export const archiveSolicitation = async (id, isArchived) => {
    console.log(`[api.js] Enviando PUT /solicitacoes/${id}/archive: { arquivar: ${isArchived} }`);
    // O corpo da requisição precisa ser um objeto com a chave 'arquivar'
    const response = await api.put(`/solicitacoes/${id}/archive`, { arquivar: isArchived });
    console.log("[api.js] Status arquivamento atualizado:", response.data);
    return response.data;
}

export const resetarErrosSolicitacoes = async () => {
    console.log("[api.js] Enviando POST /solicitacoes/resetar-erros");
    const response = await api.post('/solicitacoes/resetar-erros');
    console.log("[api.js] Resposta reset erros:", response.data);
    return response.data; // { message: "..." }
}


// --- FUNÇÕES DE GERENCIAMENTO DE USUÁRIOS (Admin) ---

export const createUser = async (userData) => { // { username, password, role }
    console.log("[api.js] Enviando POST /users/ :", { username: userData.username, role: userData.role });
    const response = await api.post('/users/', userData);
    console.log("[api.js] Usuário criado:", response.data);
    return response.data;
};

export const listUsers = async () => {
    console.log("[api.js] Buscando GET /users/");
    const response = await api.get('/users/');
    console.log(`[api.js] Recebidos ${response.data.length} usuários.`);
    return response.data;
};

export const backfillUsersFromAd = async (dryRun = true) => {
    console.log(`[api.js] Enviando POST /users/backfill-ad : { dry_run: ${dryRun} }`);
    const response = await api.post('/users/backfill-ad', { dry_run: dryRun });
    console.log("[api.js] Resultado do backfill AD:", response.data);
    return response.data;
};

export const updateUserStatus = async (userId, isActive) => { // Ativar/Desativar
    console.log(`[api.js] Enviando PUT /users/${userId}/status : { is_active: ${isActive} }`);
    const response = await api.put(`/users/${userId}/status`, { is_active: isActive });
    console.log("[api.js] Status do usuário atualizado:", response.data);
    return response.data;
};

// Adicionada função para atualização geral (embora não usada no form atual)
export const updateUser = async (userId, userData) => {
    console.log(`[api.js] Enviando PUT /users/${userId} :`, userData);
    const response = await api.put(`/users/${userId}`, userData);
    console.log("[api.js] Dados do usuário atualizados:", response.data);
    return response.data;
};


export default api;
